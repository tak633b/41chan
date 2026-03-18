"""
エージェント対話 API（Post-sim Agent Chat）
POST /api/simulation/{sim_id}/agent/{agent_id}/chat — エージェントに質問
GET  /api/simulation/{sim_id}/agent/{agent_id}/chat/history — チャット履歴取得
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
    """エージェントに質問する"""
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

    # 投稿履歴テキスト
    posts_text = "\n".join([
        f"  >>{p['post_num']} (Round {p['round_num']}): {p['content'][:200]}"
        for p in posts
    ]) if posts else "（投稿なし）"

    # チャット履歴取得
    history = get_agent_chat_history(sim_id, agent_id)

    # ユーザーメッセージを保存
    add_agent_chat_message(sim_id, agent_id, "user", req.message)

    # LLMプロンプト構築
    system_prompt = f"""あなたは「{agent_name}」です。以下の設定に従って、自分の言葉で答えてください。

【設定】
名前: {agent_name}
プロフィール: {bio}
ペルソナ: {persona}
口調: {tone_style}
立場: {stance}

【あなたがした投稿】
{posts_text}

【ルール】
- あなたは上記の投稿をした本人として答える
- 「なぜそう書いたのか」「どう思っているのか」を自分の言葉で説明する
- キャラクターの口調・性格を維持する
- 5chの住人としてのカジュアルな口調で答える（敬語禁止）
- 日本語のみ
- 200字以内で簡潔に"""

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
    """チャット履歴取得"""
    history = get_agent_chat_history(sim_id, agent_id)
    return {"history": history}


@router.get("/simulation/{sim_id}/agent/{agent_id}/profile")
async def get_agent_profile(sim_id: str, agent_id: str):
    """エージェントプロフィール取得"""
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
