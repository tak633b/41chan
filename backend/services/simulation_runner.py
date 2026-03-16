"""
シミュレーション実行サービス
バックグラウンドでシミュレーション全体を走らせ、DBに結果を書き込む。
SSEイベントはキューに積む。
"""

import asyncio
import json
import os
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
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
                "emotional_wound": getattr(a, "emotional_wound", ""),
                "information_bias": getattr(a, "information_bias", ""),
                "speech_patterns": getattr(a, "speech_patterns", []),
                "debate_tactics": getattr(a, "debate_tactics", ""),
                "social_position": getattr(a, "social_position", ""),
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
                        posting_style, emotional_wound, information_bias, speech_patterns,
                        debate_tactics, social_position)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                        getattr(a, "emotional_wound", ""),
                        getattr(a, "information_bias", ""),
                        json.dumps(getattr(a, "speech_patterns", []), ensure_ascii=False),
                        getattr(a, "debate_tactics", ""),
                        getattr(a, "social_position", ""),
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
                lambda: generate_boards(entities, theme, key_issues, llm, scale=scale),
            )

        # 板とスレッドをDBに保存
        board_db_map = {}  # board_name -> board_id
        thread_db_map = {}  # thread_title -> thread_id
        now = datetime.now().isoformat()

        # boards/threads を先にDBへ全コミットしてから emit する
        # （with db_conn() 内で await すると commit 前に posts INSERT が走り FOREIGN KEY エラーになる）
        board_emit_queue = []   # (board_id, name, emoji, description)
        thread_emit_queue = []  # (thread_id, board_id, title)

        with db_conn() as conn:
            for b in boards_config:
                board_id = str(uuid.uuid4())
                board_db_map[b["name"]] = board_id
                conn.execute(
                    "INSERT INTO boards (id, simulation_id, name, emoji, description, created_at) VALUES (?,?,?,?,?,?)",
                    (board_id, sim_id, b["name"], b["emoji"], b["description"], now),
                )
                board_emit_queue.append((board_id, b["name"], b["emoji"], b["description"]))
                for title in b.get("initial_threads", []):
                    # initial_threads がdictのリストの場合に対応
                    if isinstance(title, dict):
                        title = title.get("title", title.get("name", str(title)))
                    thread_id = str(uuid.uuid4())
                    thread_db_map[title] = thread_id
                    conn.execute(
                        "INSERT INTO threads (id, board_id, simulation_id, title, is_active, created_at) VALUES (?,?,?,?,?,?)",
                        (thread_id, board_id, sim_id, title, 1, now),
                    )
                    thread_emit_queue.append((thread_id, board_id, title))
        # commit 完了後に emit
        for board_id, name, emoji, description in board_emit_queue:
            await _emit(sim_id, "board_created", {
                "board_id": board_id, "name": name, "emoji": emoji, "description": description,
            })
        for thread_id, board_id, title in thread_emit_queue:
            await _emit(sim_id, "thread_created", {
                "thread_id": thread_id, "board_id": board_id, "title": title,
            })

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
        _counter_lock = threading.Lock()  # 共有カウンタ保護用

        # スレッド並列実行: mini=1, full/auto=2
        MAX_PARALLEL = 1 if scale == "mini" else 4
        semaphore = asyncio.Semaphore(MAX_PARALLEL)
        print(f"[SimRunner] 並列度: {MAX_PARALLEL} (scale={scale})", flush=True)

        # 全スレッドタスクを収集
        all_thread_tasks = []
        for b_config in boards_config:
            board_name = b_config["name"]
            board_id = board_db_map.get(board_name)
            if not board_id:
                continue
            for thread_title in b_config.get("initial_threads", []):
                if isinstance(thread_title, dict):
                    thread_title = thread_title.get("title", thread_title.get("name", str(thread_title)))
                thread_id = thread_db_map.get(thread_title)
                if thread_id:
                    all_thread_tasks.append((board_name, board_id, thread_title, thread_id))

        async def _run_one_thread(board_name: str, board_id: str, thread_title: str, thread_id: str):
            """1スレッド分のシミュレーション（独立LLMクライアント）"""
            nonlocal total_posts_global, completed_threads

            async with semaphore:
                # 一時停止チェック
                _check = get_simulation(sim_id)
                if _check and _check.get("status") == "paused":
                    print(f"[SimRunner] 一時停止中のためスキップ: {thread_title}")
                    return

                print(f"[SimRunner]   スレッド開始: [{board_name}] {thread_title}", flush=True)
                _emit_sync(sim_id, "round_start", {
                    "round_num": 1, "board": board_name, "thread": thread_title,
                })

                # スレッドごとに独立したLLMクライアント（_last_call_time競合なし）
                thread_llm = OracleLLMClient()
                thread_memory = MemoryManager(db_dir=db_dir_abs, project_id=sim_id, llm=thread_llm)

                # リアルタイム投稿コールバック（DB保存 + SSE emit）
                post_counter_ref = [0]  # ミュータブルなカウンター

                def _on_post(p: dict):
                    post_counter_ref[0] += 1
                    post_num = post_counter_ref[0]
                    post_id = str(uuid.uuid4())
                    ts = p.get("timestamp", datetime.now().strftime("%Y/%m/%d %H:%M"))

                    with db_conn() as conn:
                        conn.execute(
                            """INSERT INTO posts
                               (id, thread_id, board_id, simulation_id, post_num, agent_name,
                                username, content, reply_to, emotion, round_num, timestamp, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                post_id, thread_id, board_id, sim_id, post_num,
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

                    # 書き込み中プレースホルダー
                    _emit_sync(sim_id, "post_thinking", {
                        "board_id": board_id,
                        "thread_id": thread_id,
                        "agent_name": p.get("agent_name", ""),
                        "username": p.get("username", "名無し"),
                        "post_num": post_num,
                    })
                    import time as _time
                    _time.sleep(0.3 + (hash(post_id) % 6) * 0.1)

                    _emit_sync(sim_id, "new_post", {
                        "board_id": board_id, "thread_id": thread_id,
                        "board_name": board_name, "thread_title": thread_title,
                        "post": {
                            "post_id": post_id, "post_num": post_num,
                            "agent_name": p.get("agent_name", ""),
                            "username": p.get("username", "名無し"),
                            "content": p.get("content", ""),
                            "reply_to": p.get("anchor_to"),
                            "timestamp": ts,
                            "emotion": p.get("emotion", "neutral"),
                        },
                    })

                simulator = BoardSimulator(
                    agents=oracle_agents,
                    entity_data=entity_data,
                    question=prompt,
                    memory_manager=thread_memory,
                    llm=thread_llm,
                    scale=scale,
                    custom_rounds=custom_rounds,
                    board_name=board_name,
                    thread_title=thread_title,
                    rounds_per_thread=rounds_per_thread if scale == "auto" else None,
                    on_post_generated=_on_post,
                )
                simulator.sim_id = sim_id  # 過去シミュ除外用

                try:
                    await loop.run_in_executor(None, simulator.run)
                except Exception as e:
                    print(f"[SimRunner] スレッド '{thread_title}' 失敗: {e}")
                    with _counter_lock:
                        completed_threads += 1
                    return

                with _counter_lock:
                    total_posts_global += len(simulator.posts)
                    completed_threads += 1
                    _done = completed_threads
                    _total_g = total_posts_global

                progress = 0.30 + 0.55 * (_done / max(1, total_threads_all))
                update_simulation(sim_id, total_posts=_total_g, progress=progress)

                await _emit(sim_id, "round_complete", {
                    "round_num": simulator.num_rounds,
                    "post_count": len(simulator.posts),
                    "board": board_name, "thread": thread_title,
                })
                print(
                    f"[SimRunner]   完了: [{board_name}] {thread_title} "
                    f"({len(simulator.posts)}投稿, 累計{_total_g}, {_done}/{total_threads_all}スレッド)",
                    flush=True,
                )

        # 全スレッドを並列実行（Semaphoreで同時実行数を制御）
        print(f"[SimRunner] Step 4: {total_threads_all}スレッドを並列実行開始 (並列度={MAX_PARALLEL})", flush=True)
        await asyncio.gather(*[
            _run_one_thread(bn, bid, tt, tid)
            for bn, bid, tt, tid in all_thread_tasks
        ])

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
