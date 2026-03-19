"""
Agent Chat API (Post-sim Agent Chat)
POST /api/simulation/{sim_id}/agent/{agent_id}/chat — Chat with an agent
GET  /api/simulation/{sim_id}/agent/{agent_id}/chat/history — Get chat history
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm_client import OracleLLMClient
from db.database import (
    db_conn, get_simulation, get_agent_chat_history,
    add_agent_chat_message,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/simulation/{sim_id}/agent/{agent_id}/chat")
async def chat_with_agent(sim_id: str, agent_id: str, req: ChatRequest):
    """Chat with an agent in character"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # エージェント情報取得
    with db_conn() as conn:
        agent_row = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=? AND id=?", (sim_id, agent_id)
        ).fetchone()
        if not agent_row:
            raise HTTPException(status_code=404, detail="Agent not found")

        # エージェントの全投稿を取得
        posts = conn.execute(
            "SELECT content, post_num, round_num, emotion FROM posts WHERE simulation_id=? AND agent_name=? ORDER BY post_num",
            (sim_id, agent_row["name"]),
        ).fetchall()

    agent = dict(agent_row)
    agent_name = agent["name"]
    persona = agent.get("persona", "")
    bio = agent.get("bio", "")
    tone_style = agent.get("tone_style", "")
    stance = agent.get("stance", "{}")

    # Post history text
    posts_text = "\n".join([
        f"  >>{p['post_num']} (Round {p['round_num']}): {p['content'][:200]}"
        for p in posts
    ]) if posts else "(No posts)"

    # チャット履歴取得
    history = get_agent_chat_history(sim_id, agent_id)

    # ユーザーメッセージを保存
    add_agent_chat_message(sim_id, agent_id, "user", req.message)

    # Build LLM prompt
    system_prompt = f"""You are "{agent_name}". Answer in character based on the following profile.

[Profile]
Name: {agent_name}
Bio: {bio}
Persona: {persona}
Tone/Style: {tone_style}
Stance: {stance}

[Your posts in the thread]
{posts_text}

[Rules]
- You ARE the person who wrote the posts above. Answer as yourself.
- Explain why you wrote what you wrote, and what you really think.
- Stay in character — maintain your tone, personality, and mannerisms.
- Write like an anonymous imageboard user — casual, blunt, no formalities.
- English only. No Japanese. No Chinese.
- Keep it under 100 words."""

    messages = [{"role": "system", "content": system_prompt}]

    # 過去のチャット履歴をコンテキストに追加
    for h in history[-10:]:  # 直近10件
        role = "user" if h["role"] == "user" else "assistant"
        messages.append({"role": role, "content": h["content"]})

    # 今回の質問
    messages.append({"role": "user", "content": req.message})

    # LLM呼び出し
    llm = OracleLLMClient()
    loop = asyncio.get_event_loop()
    try:
        reply = await loop.run_in_executor(None, lambda: llm.chat(messages, temperature=0.7))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM呼び出し失敗: {str(e)}")

    # エージェント返答を保存
    add_agent_chat_message(sim_id, agent_id, "agent", reply)

    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "reply": reply,
        "post_count": len(posts),
    }


@router.get("/simulation/{sim_id}/agent/{agent_id}/chat/history")
async def get_chat_history(sim_id: str, agent_id: str):
    """Get chat history"""
    history = get_agent_chat_history(sim_id, agent_id)
    return {"history": history}


@router.get("/simulation/{sim_id}/agent/{agent_id}/profile")
async def get_agent_profile(sim_id: str, agent_id: str):
    """Get agent profile"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    with db_conn() as conn:
        agent_row = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=? AND id=?", (sim_id, agent_id)
        ).fetchone()
        if not agent_row:
            raise HTTPException(status_code=404, detail="Agent not found")

    agent = dict(agent_row)
    return {
        "agent_id": agent["id"],
        "name": agent["name"],
        "mbti": agent.get("mbti", ""),
        "role": agent.get("profession", ""),
        "tone_style": agent.get("tone_style", ""),
        "personality_snippet": agent.get("persona", ""),
        "post_count": agent.get("post_count", 0),
    }
