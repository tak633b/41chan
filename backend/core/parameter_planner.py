"""
41chan Parameter Planner
Analyzes prompt/seed content with LLM and determines optimal simulation parameters in a single LLM call.
"""

from typing import Any, Dict, List, Optional
from .llm_client import OracleLLMClient

PLANNER_SYSTEM = "You are a planner for an English imageboard simulation. Return JSON only. No explanations."

PLANNER_USER_TEMPLATE = """Theme: {prompt}
Additional info: {seed_text}

Return JSON:
{{"agent_count":8,"agent_roles":[{{"role":"tech expert","tone":"authority","stance":"pro","count":2}}],"boards":[{{"name":"Technology","threads":["[Discussion] Thread title","[Question] Thread title"]}}],"rounds_per_thread":3,"total_estimated_posts":150,"reasoning":"reason"}}

Constraints:
- agent_count: 6-15
- tone: authority/worker/youth/outsider/lurker
- boards: 2-5 boards, 2-4 threads/board, 4chan-style thread titles ([Serious], [Greentext], [Hot Take], [Question], etc.)
- rounds_per_thread: 2-8
- All board names and thread titles must be in English
- Generate boards and threads relevant to the theme"""

VALID_TONES = {"authority", "worker", "youth", "outsider", "lurker"}


def plan_parameters(
    prompt: str,
    seed_text: str,
    llm: OracleLLMClient,
) -> Dict[str, Any]:
    """
    Analyze prompt/seed and determine simulation parameters.

    Single LLM call only (minimal additional cost).

    Returns:
        {
            "agent_count": int (6-15),
            "agent_roles": [{"role": str, "tone": str, "stance": str, "count": int}, ...],
            "boards": [{"name": str, "threads": [str, ...]}, ...],
            "rounds_per_thread": int (2-8),
            "total_estimated_posts": int (100-300),
            "reasoning": str,
        }
    """
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {
            "role": "user",
            "content": PLANNER_USER_TEMPLATE.format(
                prompt=prompt,
                seed_text=seed_text or "(none)",
            ),
        },
    ]

    print("[ParameterPlanner] Determining parameters...", flush=True)
    result = llm.chat_json(messages, temperature=0.4)

    # Validation and clamping
    result = _validate_and_clamp(result)

    print(
        f"[ParameterPlanner] Decided: {result['agent_count']} agents, "
        f"{len(result['boards'])} boards, "
        f"{result['rounds_per_thread']} rounds/thread",
        flush=True,
    )
    print(f"[ParameterPlanner] Reasoning: {result.get('reasoning', '')}", flush=True)

    return result


def _validate_and_clamp(result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clamp LLM response. Out-of-range values are set to safe defaults."""
    # --- agent_count: 6-15 ---
    agent_count = result.get("agent_count", 8)
    try:
        agent_count = int(agent_count)
    except (ValueError, TypeError):
        agent_count = 8
    agent_count = max(6, min(15, agent_count))
    result["agent_count"] = agent_count

    # --- agent_roles validation ---
    agent_roles: List[Dict[str, Any]] = result.get("agent_roles", [])
    if not isinstance(agent_roles, list) or len(agent_roles) == 0:
        agent_roles = [
            {"role": "anon", "tone": "worker", "stance": "neutral", "count": agent_count}
        ]

    # Validate tone and convert count to int
    for r in agent_roles:
        if r.get("tone") not in VALID_TONES:
            r["tone"] = "worker"
        try:
            r["count"] = max(1, int(r.get("count", 1)))
        except (ValueError, TypeError):
            r["count"] = 1

    # Align agent_roles total with agent_count
    total = sum(r["count"] for r in agent_roles)
    if total != agent_count:
        diff = agent_count - total
        if diff > 0:
            # Add deficit to last role
            agent_roles[-1]["count"] += diff
        else:
            # Remove excess from largest roles
            remaining = abs(diff)
            for r in sorted(agent_roles, key=lambda x: -x["count"]):
                cut = min(r["count"] - 1, remaining)
                r["count"] -= cut
                remaining -= cut
                if remaining <= 0:
                    break

    # Remove roles with count=0
    agent_roles = [r for r in agent_roles if r.get("count", 0) > 0]
    result["agent_roles"] = agent_roles

    # --- boards: 2-5 boards ---
    boards: List[Dict[str, Any]] = result.get("boards", [])
    if not isinstance(boards, list) or len(boards) == 0:
        boards = [
            {"name": "General Discussion", "threads": ["[Discussion] General thread", "[Question] Ask anything"]},
            {"name": "Random", "threads": ["[Random] Anything goes"]},
        ]

    # Clamp board count (2-5)
    boards = boards[:5]
    if len(boards) < 2:
        boards.append({"name": "Random", "threads": ["[Random] Anything goes"]})

    # Clamp thread count per board (2-4)
    for b in boards:
        threads = b.get("threads", [])
        if not isinstance(threads, list) or len(threads) == 0:
            threads = [f"[{b.get('name', 'board')}] General thread"]
        threads = threads[:4]
        if len(threads) < 2:
            threads.append(f"[{b.get('name', 'board')}] Random thread")
        b["threads"] = threads

    result["boards"] = boards

    # --- rounds_per_thread: 2-8 ---
    rounds = result.get("rounds_per_thread", 3)
    try:
        rounds = int(rounds)
    except (ValueError, TypeError):
        rounds = 3
    result["rounds_per_thread"] = max(2, min(8, rounds))

    # --- total_estimated_posts: 100-300 ---
    total_posts = result.get("total_estimated_posts", 150)
    try:
        total_posts = int(total_posts)
    except (ValueError, TypeError):
        total_posts = 150
    result["total_estimated_posts"] = max(100, min(300, total_posts))

    # --- reasoning ---
    if "reasoning" not in result:
        result["reasoning"] = ""

    return result


def convert_planner_boards(planner_boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert parameter planner board format to the format expected by
    simulation_runner / board_generator.

    Input:  [{"name": str, "threads": [str, ...]}, ...]
    Output: [{"name": str, "emoji": str, "description": str, "initial_threads": [str, ...]}, ...]
    """
    _EMOJI_MAP = {
        "random": "💬", "politics": "📋", "discussion": "🗣️", "tech": "🔧",
        "technology": "🔧", "science": "🔬", "business": "💼", "news": "📰",
        "sports": "⚽", "anime": "🎌", "gaming": "🎮", "music": "🎵",
        "food": "🍔", "health": "🏥", "finance": "💰", "law": "⚖️",
        "environment": "🌿", "history": "📚", "general": "💬",
    }

    result = []
    for b in planner_boards:
        name = b.get("name", "board")
        # Infer emoji from name
        emoji = "💬"
        for kw, em in _EMOJI_MAP.items():
            if kw.lower() in name.lower():
                emoji = em
                break
        result.append({
            "name": name,
            "emoji": emoji,
            "description": f"Discussion and debate on {name}",
            "initial_threads": b.get("threads", [f"[{name}] General thread"]),
        })
    return result
