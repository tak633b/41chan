"""
シミュレーション管理 API
POST /api/simulation/create
GET  /api/simulation/{id}/status
GET  /api/simulations
DELETE /api/simulation/{id}
GET  /api/simulation/{id}/agents
GET  /api/simulation/{id}/agent/{agentId}
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from db.database import db_conn, get_boards, get_report, get_simulation, update_simulation, get_persistent_agents
from models.schemas import AgentDetail, AgentInfo, SimulationStatus, SimulationSummary
from services.simulation_runner import _emit, run_simulation

router = APIRouter()


@router.post("/simulation/create")
async def create_simulation(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    scale: str = Form("auto"),
    custom_agents: int = Form(None),
    custom_rounds: int = Form(None),
    seed_file: UploadFile = File(None),
):
    """シミュレーション作成"""
    # ファイル読み込み
    seed_text = ""
    if seed_file and seed_file.filename:
        content = await seed_file.read()
        seed_text = content.decode("utf-8", errors="ignore")

    sim_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    with db_conn() as conn:
        conn.execute(
            """INSERT INTO simulations
               (id, theme, prompt, scale, custom_agents, custom_rounds, status, progress,
                round_current, round_total, agent_count, board_count, total_posts, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sim_id,
                "",
                prompt,
                scale,
                custom_agents,
                custom_rounds,
                "initializing",
                0.0,
                0,
                0,
                0,
                0,
                0,
                now,
                now,
            ),
        )

    # バックグラウンドでシミュレーション実行（threading.Thread で確実に起動）
    import threading, asyncio as _aio
    def _run_sim():
        try:
            _aio.run(run_simulation(
                sim_id=sim_id,
                seed_text=seed_text,
                prompt=prompt,
                scale=scale,
                custom_agents=custom_agents,
                custom_rounds=custom_rounds,
            ))
        except Exception as e:
            print(f"[SimRunner] スレッド内エラー: {e}", file=__import__('sys').stderr, flush=True)
    t = threading.Thread(target=_run_sim, daemon=False)
    t.start()

    return {"simulation_id": sim_id, "status": "initializing"}


@router.get("/simulation/{sim_id}/status", response_model=SimulationStatus)
async def get_status(sim_id: str):
    """シミュレーション状態取得"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    boards = get_boards(sim_id)
    # 所要時間計算
    elapsed = None
    try:
        from datetime import datetime as _dt
        ca = sim.get("created_at", "")
        ua = sim.get("updated_at", "")
        if ca and ua:
            t0 = _dt.fromisoformat(ca)
            t1 = _dt.fromisoformat(ua)
            elapsed = (t1 - t0).total_seconds()
    except Exception:
        pass

    return SimulationStatus(
        id=sim["id"],
        theme=sim.get("theme", ""),
        prompt=sim.get("prompt", ""),
        status=sim.get("status", ""),
        progress=sim.get("progress", 0.0),
        round_current=sim.get("round_current", 0),
        round_total=sim.get("round_total", 0),
        agent_count=sim.get("agent_count", 0),
        created_at=sim.get("created_at", ""),
        board_count=len(boards),
        total_posts=sim.get("total_posts", 0),
        elapsed_seconds=elapsed,
    )


@router.get("/simulations", response_model=List[SimulationSummary])
async def list_simulations():
    """シミュレーション一覧"""
    with db_conn() as conn:
        rows = conn.execute(
            """SELECT s.*, 
               COUNT(DISTINCT b.id) as board_count,
               s.total_posts
               FROM simulations s
               LEFT JOIN boards b ON b.simulation_id=s.id
               GROUP BY s.id
               ORDER BY s.created_at DESC"""
        ).fetchall()
    result = []
    from datetime import datetime as _dt
    for r in rows:
        rd = dict(r)
        elapsed = None
        try:
            ca, ua = rd.get("created_at", ""), rd.get("updated_at", "")
            if ca and ua:
                elapsed = (_dt.fromisoformat(ua) - _dt.fromisoformat(ca)).total_seconds()
        except Exception:
            pass
        result.append(SimulationSummary(
            id=rd["id"],
            theme=rd["theme"] or (rd.get("prompt") or "")[:30],
            created_at=rd["created_at"],
            status=rd["status"],
            board_count=rd["board_count"],
            total_posts=rd["total_posts"] or 0,
            elapsed_seconds=elapsed,
        ))
    return result


@router.delete("/simulation/{sim_id}")
async def delete_simulation(sim_id: str):
    """シミュレーション削除"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    with db_conn() as conn:
        conn.execute("DELETE FROM posts WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM threads WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM boards WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM agents WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM reports WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM ask_history WHERE simulation_id=?", (sim_id,))
        conn.execute("DELETE FROM simulations WHERE id=?", (sim_id,))
    return {"ok": True}


@router.post("/simulation/{sim_id}/pause")
async def pause_simulation(sim_id: str):
    """シミュレーション一時停止"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    status = sim.get("status", "")
    if status in ("completed", "failed", "paused"):
        raise HTTPException(status_code=400, detail=f"Cannot pause: status={status}")
    update_simulation(sim_id, status="paused")
    await _emit(sim_id, "status_update", {"status": "paused"})
    return {"ok": True, "previous_status": status}


@router.post("/simulation/{sim_id}/resume")
async def resume_simulation(sim_id: str, background_tasks: BackgroundTasks):
    """シミュレーション再開（最初からやり直し）"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim.get("status") != "paused":
        raise HTTPException(status_code=400, detail="Not paused")
    # ステータスをリセットしてバックグラウンドで再実行
    update_simulation(sim_id, status="initializing", progress=0.0)
    await _emit(sim_id, "status_update", {"status": "initializing", "progress": 0.0})
    background_tasks.add_task(
        run_simulation,
        sim_id=sim_id,
        seed_text="",
        prompt=sim.get("prompt", ""),
        scale=sim.get("scale", "auto"),
        custom_agents=sim.get("custom_agents"),
        custom_rounds=sim.get("custom_rounds"),
    )
    return {"ok": True}


@router.get("/simulation/{sim_id}/agents")
async def get_agents(sim_id: str):
    """エージェント一覧"""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=?", (sim_id,)
        ).fetchall()
    result = []
    for r in rows:
        result.append(
            {
                "agent_id": r["id"],
                "name": r["name"],
                "username": r["username"],
                "bio": r["bio"],
                "persona": r["persona"],
                "age": r["age"],
                "gender": r["gender"],
                "mbti": r["mbti"],
                "tone_style": r["tone_style"],
                "posting_style": r["posting_style"] if "posting_style" in r.keys() else "",
                "profession": r["profession"],
                "interested_topics": json.loads(r["interested_topics"] or "[]"),
                "post_count": r["post_count"],
                "emotional_wound": r["emotional_wound"] if "emotional_wound" in r.keys() else "",
                "information_bias": r["information_bias"] if "information_bias" in r.keys() else "",
                "speech_patterns": json.loads(r["speech_patterns"] or "[]") if "speech_patterns" in r.keys() else [],
                "debate_tactics": r["debate_tactics"] if "debate_tactics" in r.keys() else "",
                "social_position": r["social_position"] if "social_position" in r.keys() else "",
            }
        )
    return result


@router.get("/simulation/{sim_id}/agent/{agent_id}")
async def get_agent_detail(sim_id: str, agent_id: str):
    """エージェント詳細"""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=? AND id=?", (sim_id, agent_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        recent_posts = conn.execute(
            "SELECT * FROM posts WHERE simulation_id=? AND agent_name=? ORDER BY created_at DESC LIMIT 10",
            (sim_id, row["name"]),
        ).fetchall()

    return {
        "agent_id": row["id"],
        "name": row["name"],
        "username": row["username"],
        "bio": row["bio"],
        "persona": row["persona"],
        "age": row["age"],
        "gender": row["gender"],
        "mbti": row["mbti"],
        "tone_style": row["tone_style"],
        "profession": row["profession"],
        "interested_topics": json.loads(row["interested_topics"] or "[]"),
        "stance": json.loads(row["stance"] or "{}"),
        "hidden_agenda": row["hidden_agenda"],
        "post_count": row["post_count"],
        "recent_posts": [
            {
                "post_id": p["id"],
                "post_num": p["post_num"],
                "agent_name": p["agent_name"],
                "username": p["username"],
                "content": p["content"],
                "reply_to": p["reply_to"],
                "timestamp": p["timestamp"],
                "emotion": p["emotion"],
            }
            for p in recent_posts
        ],
    }


# ===== 永続エージェント管理 API =====

@router.get("/agents/persistent")
async def list_persistent_agents():
    """ストック済みエージェント一覧"""
    agents = get_persistent_agents(limit=200)
    result = []
    for a in agents:
        topics = a.get("interested_topics", "[]")
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except:
                topics = []
        result.append({
            "id": a["id"],
            "name": a["name"],
            "username": a.get("username", ""),
            "bio": a.get("bio", ""),
            "persona": a.get("persona", ""),
            "age": a.get("age", 0),
            "gender": a.get("gender", "other"),
            "mbti": a.get("mbti", ""),
            "tone_style": a.get("tone_style", ""),
            "profession": a.get("profession", ""),
            "interested_topics": topics,
            "posting_style": a.get("posting_style", "emotional"),
            "use_count": a.get("use_count", 0),
            "created_at": a.get("created_at", ""),
            "rating": a.get("rating", "unrated"),
        })
    return result


@router.post("/agents/persistent/{agent_id}/rate")
async def rate_persistent_agent(agent_id: str, rating: str = "good"):
    """エージェントを評価（good/bad）"""
    if rating not in ("good", "bad", "unrated"):
        return {"error": "rating must be good, bad, or unrated"}
    with db_conn() as conn:
        conn.execute(
            "UPDATE persistent_agents SET rating=? WHERE id=?",
            (rating, agent_id),
        )
    return {"ok": True, "agent_id": agent_id, "rating": rating}


@router.delete("/agents/persistent/{agent_id}")
async def delete_persistent_agent(agent_id: str):
    """エージェントを削除"""
    with db_conn() as conn:
        conn.execute("DELETE FROM persistent_agents WHERE id=?", (agent_id,))
    return {"ok": True}


@router.post("/agents/persistent/generate")
async def generate_persistent_agents(count: int = 3):
    """新規エージェントを指定人数生成してストックに追加"""
    import threading

    if count < 1 or count > 20:
        raise HTTPException(status_code=400, detail="生成数は1〜20人で指定してください")

    t = threading.Thread(target=_generate_agents_sync, args=(count,), daemon=False)
    t.start()

    return {"ok": True, "count": count, "message": f"{count}人のエージェント生成を開始しました"}


def _generate_agents_sync(count: int):
    """同期的にエージェントを生成してストックに追加"""
    import random
    import sys
    from core.llm_client import OracleLLMClient
    from db.database import db_conn

    llm = OracleLLMClient()
    msg = f"[AgentGenerator] {count}人の新規エージェント生成開始"
    print(msg, file=sys.stderr, flush=True)
    sys.stderr.flush()

    POSTING_STYLES = [
        "info_provider", "debater", "joker", "questioner", "veteran",
        "passerby", "emotional", "storyteller", "agreeer", "contrarian",
    ]
    FREQUENCIES = ["once", "low", "medium", "high"]
    GENDERS = ["male", "female"]
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISTP", "ESTJ", "ESTP", "ISFJ", "ISFP", "ESFJ", "ESFP",
    ]

    # 既存エージェントの名前を取得（重複防止）
    with db_conn() as conn:
        existing = {row["name"] for row in conn.execute("SELECT name FROM persistent_agents").fetchall()}

    generated = 0
    for i in range(count):
        style = random.choice(POSTING_STYLES)
        gender = random.choice(GENDERS)
        mbti = random.choice(MBTI_TYPES)
        age = random.randint(18, 65)
        freq = random.choice(FREQUENCIES)

        prompt = f"""5ch掲示板のリアルな住民キャラクターを1人作ってください。

【条件】
- 性別: {"男性" if gender == "male" else "女性"}
- 年齢: {age}歳
- MBTI: {mbti}
- 投稿スタイル: {style}
- 既存のキャラ名と被らないこと: {', '.join(list(existing)[:10])}

以下のJSON形式で返してください:
{{
  "name": "日本人のフルネーム（漢字）",
  "profession": "職業",
  "tone_style": "口調の特徴（例: タメ口で皮肉屋）",
  "bio": "一行の紹介文",
  "persona": "200〜300字の詳細なペルソナ。性格、5chでの書き込み傾向、日常の趣味、議論での立ち位置を含む",
  "interested_topics": ["関心トピック1", "関心トピック2", "関心トピック3"]
}}

日本語のみ。英語禁止。"""

        try:
            result = llm.chat_json(
                [
                    {"role": "system", "content": "キャラクター設定を作るライター。JSON形式で返す。日本語のみ。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
            )

            name = result.get("name", "")
            if not name or name in existing:
                print(f"  [{i+1}/{count}] 名前が空か重複、スキップ", file=sys.stderr, flush=True)
                continue

            import uuid
            agent_id = str(uuid.uuid4())
            topics_json = json.dumps(result.get("interested_topics", []), ensure_ascii=False)

            with db_conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO persistent_agents
                       (id, name, username, age, gender, mbti, profession, tone_style, posting_style,
                        post_frequency, persona, bio, interested_topics, use_count, rating, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,'unrated',datetime('now'))""",
                    (
                        agent_id, name, name, age, gender, mbti,
                        result.get("profession", ""),
                        result.get("tone_style", ""),
                        style, freq,
                        result.get("persona", ""),
                        result.get("bio", ""),
                        topics_json,
                    ),
                )
            existing.add(name)
            generated += 1
            print(f"  [{i+1}/{count}] {name} ({style}) 生成OK", file=sys.stderr, flush=True)

        except Exception as e:
            import traceback
            print(f"  [{i+1}/{count}] 生成失敗: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

        import time
        time.sleep(2)

    print(f"[AgentGenerator] 完了: {generated}/{count}人生成", file=sys.stderr, flush=True)
    sys.stderr.flush()


@router.post("/agents/persistent/enhance")
async def enhance_persistent_agents():
    """bad以外の全エージェントのペルソナをLLMで強化"""
    import asyncio
    from core.llm_client import OracleLLMClient

    agents = get_persistent_agents(limit=200, include_bad=False)
    if not agents:
        return {"ok": False, "error": "強化対象のエージェントがいません"}

    # バックグラウンドで実行
    import threading
    t = threading.Thread(target=_enhance_agents_sync, args=(agents,), daemon=False)
    t.start()

    return {"ok": True, "target_count": len(agents), "message": "ペルソナ強化を開始しました"}


def _enhance_agents_sync(agents: list):
    """同期的にエージェントのペルソナを強化"""
    import time
    from core.llm_client import OracleLLMClient

    llm = OracleLLMClient()
    print(f"[PersonaEnhance] {len(agents)}人のペルソナ強化開始")

    for i, agent in enumerate(agents):
        name = agent["name"]
        current_persona = agent.get("persona", "")
        profession = agent.get("profession", "")
        age = agent.get("age", 30)
        gender = agent.get("gender", "other")
        mbti = agent.get("mbti", "")
        tone_style = agent.get("tone_style", "")
        posting_style = agent.get("posting_style", "")
        bio = agent.get("bio", "")

        prompt = f"""以下の5ch住民キャラクターのペルソナを充実させてください。

【現在の情報】
名前: {name}
年齢: {age}歳 / 性別: {gender}
職業: {profession}
MBTI: {mbti}
口調: {tone_style}
投稿スタイル: {posting_style}
現在のBIO: {bio}
現在のペルソナ: {current_persona}

【依頼】
この人物の以下を具体的に書いてください（200〜300字、日本語のみ）:
- 性格の特徴（具体的なエピソードを交えて）
- 5chでの書き込み傾向（どんな話題に反応するか、どんな口調か）
- 日常生活の一面（趣味、習慣、こだわり）
- 議論での立ち位置（どんな時に熱くなるか、何を重視するか）

ペルソナテキストのみ返してください。JSON不要。"""

        try:
            messages = [
                {"role": "system", "content": "キャラクター設定を書くライター。テキストのみ返す。"},
                {"role": "user", "content": prompt},
            ]
            enhanced = llm.chat(messages, temperature=0.85)
            enhanced = enhanced.strip()

            if len(enhanced) > 50:  # 十分な長さがあれば更新
                with db_conn() as conn:
                    conn.execute(
                        "UPDATE persistent_agents SET persona=? WHERE id=?",
                        (enhanced, agent["id"]),
                    )
                print(f"  [{i+1}/{len(agents)}] {name}: ペルソナ強化OK ({len(enhanced)}字)")
            else:
                print(f"  [{i+1}/{len(agents)}] {name}: 生成結果が短すぎてスキップ")
        except Exception as e:
            print(f"  [{i+1}/{len(agents)}] {name}: 失敗 - {e}")

        time.sleep(2)  # レート制限対策

    print(f"[PersonaEnhance] 完了")
