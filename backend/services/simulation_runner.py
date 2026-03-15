"""
シミュレーション実行サービス
バックグラウンドでシミュレーション全体を走らせ、DBに結果を書き込む。
SSEイベントはキューに積む。
"""

import asyncio
import json
import os
import random
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from db.database import db_conn, get_simulation, update_simulation, save_persistent_agents, get_persistent_agents, increment_agent_use_count
from core.llm_client import OracleLLMClient
from core.entity_extractor import extract_entities
from core.profile_generator import generate_agents
from core.memory_manager import MemoryManager
from core.board_simulator import BoardSimulator
from core.reporter import generate_report
from core.parameter_planner import plan_parameters, convert_planner_boards
from services.board_generator import generate_boards

# グローバルSSEキュー: sim_id -> list of event queues
_sse_queues: Dict[str, List[asyncio.Queue]] = {}


def register_sse_queue(sim_id: str, q: asyncio.Queue):
    if sim_id not in _sse_queues:
        _sse_queues[sim_id] = []
    _sse_queues[sim_id].append(q)


def unregister_sse_queue(sim_id: str, q: asyncio.Queue):
    if sim_id in _sse_queues:
        try:
            _sse_queues[sim_id].remove(q)
        except ValueError:
            pass


async def _emit(sim_id: str, event_type: str, data: Dict[str, Any]):
    """SSEキューにイベントを積む"""
    event = {"type": event_type, "data": data}
    for q in _sse_queues.get(sim_id, []):
        await q.put(event)


def _emit_sync(sim_id: str, event_type: str, data: Dict[str, Any]):
    """同期コンテキストからSSEイベントを積む"""
    event = {"type": event_type, "data": data}
    for q in _sse_queues.get(sim_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# DB用パス
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")


async def run_simulation(
    sim_id: str,
    seed_text: str,
    prompt: str,
    scale: str,
    custom_agents: Optional[int],
    custom_rounds: Optional[int],
):
    """
    非同期でシミュレーション全体を実行する。
    1. エンティティ抽出
    2. エージェント生成
    3. 板自動生成
    4. シミュレーション実行（スレッド単位）
    5. レポート生成
    """
    llm = OracleLLMClient()

    # auto スケール用のパラメータプランナー結果
    _plan: Optional[Dict[str, Any]] = None

    try:
        loop = asyncio.get_event_loop()

        # --- Step 0 (auto専用): パラメータプランナー ---
        if scale == "auto":
            update_simulation(sim_id, status="planning", progress=0.02)
            await _emit(sim_id, "status_update", {"status": "planning", "progress": 0.02})
            print("[SimRunner] Step 0: パラメータプランナー実行中...", flush=True)
            _plan = await loop.run_in_executor(
                None,
                lambda: plan_parameters(prompt=prompt, seed_text=seed_text or "", llm=llm),
            )
            print(f"[SimRunner] Step 0: プランナー完了 → {_plan}", flush=True)

        # --- Step 1: エンティティ抽出 ---
        # 一時停止チェック
        _check = get_simulation(sim_id)
        if _check and _check.get("status") == "paused":
            print(f"[SimRunner] シミュレーション {sim_id} は一時停止中です (Step 1前)")
            return
        update_simulation(sim_id, status="extracting", progress=0.05)
        await _emit(sim_id, "status_update", {"status": "extracting", "progress": 0.05, "prompt": prompt})

        full_seed = f"{prompt}\n\n{seed_text}" if seed_text else prompt
        llm_extract = llm  # 全処理で同じモデル（qwen3.5:9b）
        entity_data = await loop.run_in_executor(
            None, lambda: extract_entities(full_seed, llm_extract)
        )
        theme = entity_data.get("theme", "議論テーマ")
        entities = entity_data.get("entities", [])
        key_issues = entity_data.get("key_issues", [])

        update_simulation(sim_id, theme=theme, status="generating_agents", progress=0.15)
        await _emit(sim_id, "status_update", {"status": "generating_agents", "progress": 0.15, "theme": theme})

        # --- Step 2: エージェント生成 ---
        # 一時停止チェック
        _check = get_simulation(sim_id)
        if _check and _check.get("status") == "paused":
            print(f"[SimRunner] シミュレーション {sim_id} は一時停止中です (Step 2前)")
            return
        if scale == "auto":
            agent_count = _plan["agent_count"] if _plan else (custom_agents or 8)
        else:
            agent_count = custom_agents or (5 if scale == "mini" else 12)

        print(f"[SimRunner] Step 2: エージェント生成開始 (scale={scale}, count={agent_count})", flush=True)
        oracle_agents = await loop.run_in_executor(
            None,
            lambda: generate_agents(
                entity_data=entity_data,
                llm=llm,
                scale=scale,
                custom_agents=custom_agents,
                agent_roles=_plan.get("agent_roles") if _plan else None,
            ),
        )
        print(f"[SimRunner] Step 2: エージェント生成完了 ({len(oracle_agents)}人)", flush=True)

        # エージェントを永続テーブルにも保存（次回以降のシミュレーションで使い回し可能）
        persistent_data = []
        for a in oracle_agents:
            persistent_data.append({
                "name": a.name, "username": a.username, "bio": a.bio,
                "persona": a.persona, "age": a.age, "gender": a.gender,
                "mbti": a.mbti, "tone_style": a.tone_style,
                "profession": a.profession,
                "interested_topics": a.interested_topics,
                "posting_style": getattr(a, "posting_style", "emotional"),
            })
        save_persistent_agents(persistent_data)
        increment_agent_use_count([a.name for a in oracle_agents])
        print(f"[SimRunner] エージェント永続保存完了 ({len(persistent_data)}人)")

        # エージェントをDBに保存
        with db_conn() as conn:
            for a in oracle_agents:
                conn.execute(
                    """INSERT OR REPLACE INTO agents
                       (id, simulation_id, name, username, bio, persona, age, gender,
                        mbti, tone_style, profession, interested_topics, stance, hidden_agenda,
                        posting_style)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()),
                        sim_id,
                        a.name,
                        a.username,
                        a.bio,
                        a.persona,
                        a.age,
                        a.gender,
                        a.mbti,
                        a.tone_style,
                        a.profession,
                        json.dumps(a.interested_topics, ensure_ascii=False),
                        json.dumps(a.stance, ensure_ascii=False),
                        a.hidden_agenda,
                        getattr(a, "posting_style", "emotional"),
                    ),
                )

        # エージェント生成をSSEに通知
        for a in oracle_agents:
            await _emit(sim_id, "new_agent", {
                "name": a.name,
                "role": a.tone_style,
                "personality_snippet": a.persona[:60] if a.persona else "",
            })

        update_simulation(
            sim_id,
            agent_count=len(oracle_agents),
            status="generating_boards",
            progress=0.25,
        )

        # --- Step 3: 板自動生成（auto の場合はプランナー結果を使用） ---
        # 一時停止チェック
        _check = get_simulation(sim_id)
        if _check and _check.get("status") == "paused":
            print(f"[SimRunner] シミュレーション {sim_id} は一時停止中です (Step 3前)")
            return
        if scale == "auto" and _plan and _plan.get("boards"):
            print("[SimRunner] Step 3: パラメータプランナーの板構成を使用（LLM呼び出しスキップ）", flush=True)
            boards_config = convert_planner_boards(_plan["boards"])
        else:
            print("[SimRunner] Step 3: 板自動生成開始", flush=True)
            boards_config = await loop.run_in_executor(
                None,
                lambda: generate_boards(entities, theme, key_issues, llm),
            )

        # 板とスレッドをDBに保存
        board_db_map = {}  # board_name -> board_id
        thread_db_map = {}  # thread_title -> thread_id
        now = datetime.now().isoformat()

        with db_conn() as conn:
            for b in boards_config:
                board_id = str(uuid.uuid4())
                board_db_map[b["name"]] = board_id
                conn.execute(
                    "INSERT INTO boards (id, simulation_id, name, emoji, description, created_at) VALUES (?,?,?,?,?,?)",
                    (board_id, sim_id, b["name"], b["emoji"], b["description"], now),
                )
                await _emit(
                    sim_id,
                    "board_created",
                    {
                        "board_id": board_id,
                        "name": b["name"],
                        "emoji": b["emoji"],
                        "description": b["description"],
                    },
                )
                for title in b.get("initial_threads", []):
                    thread_id = str(uuid.uuid4())
                    thread_db_map[title] = thread_id
                    conn.execute(
                        "INSERT INTO threads (id, board_id, simulation_id, title, is_active, created_at) VALUES (?,?,?,?,?,?)",
                        (thread_id, board_id, sim_id, title, 1, now),
                    )
                    await _emit(
                        sim_id,
                        "thread_created",
                        {
                            "thread_id": thread_id,
                            "board_id": board_id,
                            "title": title,
                        },
                    )

        update_simulation(
            sim_id,
            board_count=len(boards_config),
            status="simulating",
            progress=0.30,
        )

        # --- Step 4: シミュレーション実行（スレッド単位） ---
        print(f"[SimRunner] Step 3: 板自動生成完了 ({len(boards_config)}板)", flush=True)
        print(f"[SimRunner] Step 4: シミュレーション実行開始（スレッド単位）", flush=True)

        # MemoryManager初期化
        db_dir_abs = os.path.abspath(DB_DIR)
        memory = MemoryManager(db_dir=db_dir_abs, project_id=sim_id, llm=llm)

        # スレッド総数を計算（進捗管理用）
        total_threads_all = sum(
            len(b.get("initial_threads", []))
            for b in boards_config
        )

        # ラウンド総数（進捗表示用）
        # auto: プランナー決定値 → custom_rounds → scale固定値の優先順
        if scale == "auto" and _plan and _plan.get("rounds_per_thread"):
            rounds_per_thread = _plan["rounds_per_thread"]
        else:
            rounds_per_thread = custom_rounds or (2 if scale == "mini" else 5)
        round_total = rounds_per_thread * max(1, total_threads_all)
        update_simulation(sim_id, round_total=round_total)

        total_posts_global = 0
        completed_threads = 0

        # 板ごとにスレッドをループ
        for board_idx, b_config in enumerate(boards_config):
            board_name = b_config["name"]
            board_id = board_db_map.get(board_name)
            if not board_id:
                continue

            threads_in_board = b_config.get("initial_threads", [])
            if not threads_in_board:
                continue

            print(f"[SimRunner] 板: {board_name} ({len(threads_in_board)}スレッド)", flush=True)

            # スレッドごとにBoardSimulatorを実行
            for thread_title in threads_in_board:
                # 一時停止チェック（各スレッド/ラウンドの前）
                _check = get_simulation(sim_id)
                if _check and _check.get("status") == "paused":
                    print(f"[SimRunner] シミュレーション {sim_id} は一時停止中です (Step 4: {thread_title}前)")
                    return

                thread_id = thread_db_map.get(thread_title)
                if not thread_id:
                    completed_threads += 1
                    continue

                print(f"[SimRunner]   スレッド: {thread_title}", flush=True)
                _emit_sync(
                    sim_id,
                    "round_start",
                    {
                        "round_num": 1,
                        "board": board_name,
                        "thread": thread_title,
                    },
                )

                # スレッド専用のBoardSimulatorを作成
                # board_name と thread_title を渡すことで、
                # スレタイに沿った5ch文化のシミュレーションを実行
                simulator = BoardSimulator(
                    agents=oracle_agents,
                    entity_data=entity_data,
                    question=prompt,
                    memory_manager=memory,
                    llm=llm,
                    scale=scale,
                    custom_rounds=custom_rounds,
                    board_name=board_name,
                    thread_title=thread_title,
                    rounds_per_thread=rounds_per_thread if scale == "auto" else None,
                )

                try:
                    await loop.run_in_executor(None, simulator.run)
                except Exception as e:
                    print(f"[SimRunner] スレッド '{thread_title}' シミュレーション失敗: {e}")
                    completed_threads += 1
                    continue

                # 投稿をDBに保存（全投稿がこのスレッドへ）
                with db_conn() as conn:
                    for post_idx, p in enumerate(simulator.posts):
                        post_num = post_idx + 1  # スレッド内の1-indexed連番
                        post_id = str(uuid.uuid4())
                        ts = p.get("timestamp", datetime.now().strftime("%Y/%m/%d %H:%M"))

                        conn.execute(
                            """INSERT INTO posts
                               (id, thread_id, board_id, simulation_id, post_num, agent_name,
                                username, content, reply_to, emotion, round_num, timestamp, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                post_id,
                                thread_id,
                                board_id,
                                sim_id,
                                post_num,
                                p.get("agent_name", ""),
                                p.get("username", "名無し"),
                                p.get("content", ""),
                                p.get("anchor_to"),
                                p.get("emotion", "neutral"),
                                p.get("round_num", 0),
                                ts,
                                datetime.now().isoformat(),
                            ),
                        )

                        conn.execute(
                            "UPDATE agents SET post_count = post_count + 1 WHERE simulation_id=? AND name=?",
                            (sim_id, p.get("agent_name", "")),
                        )

                        conn.execute(
                            "UPDATE threads SET last_post_at=? WHERE id=?", (ts, thread_id)
                        )

                        await _emit(
                            sim_id,
                            "new_post",
                            {
                                "board_id": board_id,
                                "thread_id": thread_id,
                                "board_name": board_name,
                                "thread_title": thread_title,
                                "post": {
                                    "post_id": post_id,
                                    "post_num": post_num,
                                    "agent_name": p.get("agent_name", ""),
                                    "username": p.get("username", "名無し"),
                                    "content": p.get("content", ""),
                                    "reply_to": p.get("anchor_to"),
                                    "timestamp": ts,
                                    "emotion": p.get("emotion", "neutral"),
                                },
                            },
                        )
                        total_posts_global += 1

                completed_threads += 1
                progress = 0.30 + 0.55 * (completed_threads / max(1, total_threads_all))
                update_simulation(
                    sim_id,
                    total_posts=total_posts_global,
                    progress=progress,
                )

                await _emit(
                    sim_id,
                    "round_complete",
                    {
                        "round_num": simulator.num_rounds,
                        "post_count": len(simulator.posts),
                        "board": board_name,
                        "thread": thread_title,
                    },
                )

                print(
                    f"[SimRunner]   完了: {len(simulator.posts)}投稿 (累計: {total_posts_global})",
                    flush=True,
                )

        update_simulation(sim_id, status="reporting", progress=0.88)

        # --- Step 5: レポート生成 ---
        # 一時停止チェック
        _check = get_simulation(sim_id)
        if _check and _check.get("status") == "paused":
            print(f"[SimRunner] シミュレーション {sim_id} は一時停止中です (Step 5前)")
            return
        # 全投稿からスレッドログを生成
        all_posts_text_parts = []
        for board_name, board_id in board_db_map.items():
            all_posts_text_parts.append(f"\n━━━━ 【{board_name}】 ━━━━")
            with db_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM posts WHERE board_id=? ORDER BY post_num", (board_id,)
                ).fetchall()
                for row in rows:
                    anchor = f"\n  >>{row['reply_to']}" if row["reply_to"] else ""
                    all_posts_text_parts.append(
                        f"{row['post_num']}: {row['agent_name']} {row['timestamp']}{anchor}\n  {row['content']}"
                    )
        thread_log = "\n".join(all_posts_text_parts[:200])  # 最大200投稿

        try:
            report_data = await loop.run_in_executor(
                None,
                lambda: generate_report(
                    project_id=sim_id,
                    thread_log=thread_log,
                    agents=oracle_agents,
                    question=prompt,
                    theme=theme,
                    llm=llm,
                ),
            )
        except Exception as e:
            print(f"[SimRunner] レポート生成失敗: {e}")
            report_data = {
                "summary": "レポート生成に失敗しました",
                "details": str(e),
                "confidence": 0.0,
                "key_findings": [],
                "agent_positions": {},
                "turning_points": [],
                "consensus": "不明",
                "minority_views": [],
                "prediction": "",
            }

        with db_conn() as conn:
            def _json_field(val, default="[]"):
                if isinstance(val, str):
                    return val
                return json.dumps(val, ensure_ascii=False) if val else default

            conn.execute(
                """INSERT OR REPLACE INTO reports
                   (id, simulation_id, summary, details, confidence, key_findings,
                    agent_positions, turning_points, consensus, minority_views, prediction,
                    stance_distribution, activity_by_round, consensus_score, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    sim_id,
                    str(report_data.get("summary", "")),
                    str(report_data.get("details", "")) if isinstance(report_data.get("details"), str) else json.dumps(report_data.get("details", ""), ensure_ascii=False),
                    float(report_data.get("confidence", 0.5)) if not isinstance(report_data.get("confidence"), dict) else 0.5,
                    _json_field(report_data.get("key_findings", []), "[]"),
                    _json_field(report_data.get("agent_positions", {}), "{}"),
                    _json_field(report_data.get("turning_points", []), "[]"),
                    str(report_data.get("consensus", "")),
                    _json_field(report_data.get("minority_views", []), "[]"),
                    str(report_data.get("prediction", "")),
                    _json_field(report_data.get("stance_distribution", {}), "{}"),
                    _json_field(report_data.get("activity_by_round", []), "[]"),
                    float(report_data.get("consensus_score", report_data.get("confidence", 0.5))),
                    datetime.now().isoformat(),
                ),
            )

        update_simulation(sim_id, status="completed", progress=1.0)

        # 所要時間を計算
        _final_sim = get_simulation(sim_id)
        _elapsed = None
        if _final_sim:
            try:
                _t0 = datetime.fromisoformat(_final_sim["created_at"])
                _t1 = datetime.fromisoformat(_final_sim["updated_at"])
                _elapsed = (_t1 - _t0).total_seconds()
            except Exception:
                pass

        await _emit(sim_id, "sim_complete", {
            "report_ready": True,
            "total_posts": total_posts_global,
            "duration": _elapsed,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        update_simulation(sim_id, status="failed", progress=0.0)
        await _emit(sim_id, "error", {"message": str(e)})
