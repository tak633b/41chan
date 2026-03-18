"""
Board auto-generation service
Passes entities, theme, and key issues to LLM to generate appropriate board structure.
"""

import json
from typing import Any, Dict, List

from core.llm_client import OracleLLMClient

BOARD_GEN_SYSTEM = "Return JSON only. All text must be in English."

BOARD_GEN_PROMPT = """Theme:{theme}
JSON:
{{"boards":[{{"name":"board name","emoji":"📚","description":"description","initial_threads":["[Tag] Thread title"]}}]}}
All board names, descriptions, and thread titles must be in English.
Use 4chan-style thread title tags like [Discussion], [Question], [Hot Take], [Serious], [Greentext], [News], [Opinion]."""


def generate_boards(
    entities: List[Dict[str, Any]],
    theme: str,
    key_issues: List[str],
    llm: OracleLLMClient,
    scale: str = "full",
) -> List[Dict[str, Any]]:
    """
    Auto-generate board structure from theme.

    Returns:
        [{"name": str, "emoji": str, "description": str, "initial_threads": [str, ...]}, ...]
    """
    # Summarize entities (minimal)
    entity_names = ", ".join(e.get('name', '?') for e in entities[:3])
    issues_text = ", ".join(key_issues[:2])

    messages = [
        {"role": "system", "content": BOARD_GEN_SYSTEM},
        {
            "role": "user",
            "content": BOARD_GEN_PROMPT.format(
                theme=theme,
            ),
        },
    ]

    result = llm.chat_json(messages, temperature=0.6)
    boards = result.get("boards", [])

    # Validation
    validated = []
    has_random = False
    for b in boards:
        name = b.get("name", "")
        if not name:
            continue
        if "random" in name.lower() or "general" in name.lower() or "chat" in name.lower():
            has_random = True
        validated.append(
            {
                "name": name,
                "emoji": b.get("emoji", "💬"),
                "description": b.get("description", ""),
                "initial_threads": b.get("initial_threads", [f"[{name}] General thread"]),
            }
        )

    # Add random/chat board if missing
    if not has_random:
        validated.append(
            {
                "name": "Random",
                "emoji": "💬",
                "description": "Off-topic discussion related to the theme",
                "initial_threads": ["[Random] Anything goes"],
            }
        )

    # mini scale: force 1 board, 1 thread
    if scale == "mini":
        if validated:
            first_board = validated[0]
            first_board["initial_threads"] = first_board["initial_threads"][:1] if first_board.get("initial_threads") else [f"[{first_board['name']}] General thread"]
            return [first_board]
        return validated

    # full scale: limit to 2 boards, 2 threads/board
    result_boards = validated[:2]
    for b in result_boards:
        b["initial_threads"] = b["initial_threads"][:2] if b.get("initial_threads") else [f"[{b['name']}] General thread"]

    return result_boards
