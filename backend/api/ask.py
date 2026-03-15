"""
質問スレ API
POST /api/simulation/{id}/ask  → SSEストリーム
GET  /api/simulation/{id}/ask/history
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db.database import db_conn, get_simulation
from models.schemas import AskRequest
from services.question_handler import generate_answers
from core.llm_client import OracleLLMClient
from core.memory_manager import MemoryManager
import os

router = APIRouter()

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")


@router.post("/simulation/{sim_id}/ask")
async def ask_question(sim_id: str, body: AskRequest):
    """質問投稿 → SSEで回答ストリーム"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim.get("status") not in ("completed", "reporting"):
        raise HTTPException(status_code=400, detail="Simulation is not completed yet")

    # エージェント取得
    with db_conn() as conn:
        agents = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=?", (sim_id,)
        ).fetchall()
    agents_data = [dict(a) for a in agents]

    llm = OracleLLMClient()
    db_dir_abs = os.path.abspath(DB_DIR)
    memory = MemoryManager(db_dir=db_dir_abs, project_id=sim_id, llm=llm)

    ask_id = str(uuid.uuid4())
    question = body.question
    answers_list = []

    async def event_generator():
        nonlocal answers_list
        try:
            async for event in generate_answers(
                question=question,
                agents_data=agents_data,
                memory_manager=memory,
                llm=llm,
                sim_id=sim_id,
            ):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"

                if event["type"] == "answer":
                    answers_list.append(event["data"])

        finally:
            # 履歴保存
            with db_conn() as conn:
                conn.execute(
                    """INSERT INTO ask_history (id, simulation_id, question, answers, created_at)
                       VALUES (?,?,?,?,?)""",
                    (
                        ask_id,
                        sim_id,
                        question,
                        json.dumps(answers_list, ensure_ascii=False),
                        datetime.now().isoformat(),
                    ),
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/simulation/{sim_id}/ask/history")
async def get_ask_history(sim_id: str):
    """質問履歴取得"""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ask_history WHERE simulation_id=? ORDER BY created_at DESC",
            (sim_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "question": r["question"],
            "answers": json.loads(r["answers"] or "[]"),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
