"""
質問スレ回答ハンドラー
ユーザーの質問に対して関連エージェント3-5人がSSEで1レスずつ回答する。
"""

import asyncio
import json
import random
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List

from core.llm_client import OracleLLMClient
from core.memory_manager import MemoryManager

ANSWER_SYSTEM = """You are an anonymous imageboard character.
Stay faithful to your persona and tone. Answer the question in 1-3 sentences.
English only. No Japanese. No Chinese."""

ANSWER_PROMPT = """You are "{agent_name}", an anonymous imageboard poster.

[Character Profile]
{persona}

[Tone/Style] {tone_style}
- authority: Authoritative, assertive, formal. "I believe...", "It's clear that..."
- worker: Practical, matter-of-fact, mixes formal/informal.
- youth: Shitposter energy. "lmao", "based", "cope", "literally who"
- outsider: Polite, business-like, formulaic.
- lurker: Terse, one-liners, cuts to the heart of it.

[Stance] {stance}

[Your memories (reference)]
{memories}

[User's question]
{question}

Answer the above question as your character in 1-3 sentences.
Stay true to your tone, stance, and memories. English only."""


async def generate_answers(
    question: str,
    agents_data: List[Dict[str, Any]],
    memory_manager: MemoryManager,
    llm: OracleLLMClient,
    sim_id: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    質問に対するエージェント回答を非同期ジェネレーターで返す。
    
    Yields:
        {"type": "thinking", "data": {"agent_name": str}}
        {"type": "answer", "data": {"agent_name": str, "username": str, "content": str, "reply_to": None}}
        {"type": "complete", "data": {"answer_count": int}}
    """
    if not agents_data:
        yield {"type": "complete", "data": {"answer_count": 0}}
        return

    # 関連エージェント3-5人を選択（関連記憶スコアで選ぶ簡易版）
    # 記憶から関連度を計算
    scored_agents = []
    for agent in agents_data:
        agent_name = agent.get("name", "")
        try:
            memories = memory_manager.recall(
                agent_id=agent_name,
                context=question,
                top_k=2,
                current_round=999,
            )
            score = len(memories)
        except Exception:
            score = 1
        scored_agents.append((score, agent))

    # スコア降順ソート + ランダム要素
    scored_agents.sort(key=lambda x: x[0] + random.random() * 0.5, reverse=True)
    selected = [a for _, a in scored_agents[:5]]
    if len(selected) < 3 and len(agents_data) >= 3:
        selected = random.sample(agents_data, 3)

    answer_count = 0
    post_num_start = 1000  # 質問スレの番号は1000番台から

    for i, agent in enumerate(selected):
        agent_name = agent.get("name", "Unknown")
        username = agent.get("username", "Anonymous")
        persona = agent.get("persona", "")[:500]
        tone_style = agent.get("tone_style", "worker")
        stance_dict = agent.get("stance", {})
        if isinstance(stance_dict, str):
            try:
                stance_dict = json.loads(stance_dict)
            except Exception:
                stance_dict = {}
        stance = stance_dict.get("position", "Neutral") + " — " + stance_dict.get("reason", "")

        # 記憶を取得
        try:
            memories = memory_manager.recall(
                agent_id=agent_name,
                context=question,
                top_k=3,
                current_round=999,
            )
            mem_text = "\n".join(f"- {m['content'][:80]}" for m in memories[:3])
        except Exception:
            mem_text = "(No memories)"

        # 考え中イベント
        yield {"type": "thinking", "data": {"agent_name": agent_name}}
        await asyncio.sleep(0.5)

        # LLM呼び出し（同期なのでスレッドで実行）
        prompt = ANSWER_PROMPT.format(
            agent_name=agent_name,
            persona=persona,
            tone_style=tone_style,
            stance=stance,
            memories=mem_text,
            question=question,
        )
        messages = [
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None, lambda m=messages: llm.chat(m, temperature=0.85)
            )
        except Exception as e:
            content = f"(Error generating response: {e})"

        post_num = post_num_start + i
        timestamp = datetime.now().strftime("%Y/%m/%d %H:%M")

        yield {
            "type": "answer",
            "data": {
                "agent_name": agent_name,
                "username": username,
                "content": content,
                "reply_to": None,
                "post_num": post_num,
                "timestamp": timestamp,
            },
        }
        answer_count += 1
        await asyncio.sleep(0.3)

    yield {"type": "complete", "data": {"answer_count": answer_count}}
