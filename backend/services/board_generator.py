"""
板自動生成サービス
LLMにエンティティ・テーマ・論点を渡して、適切な板構成を生成する。
"""

import json
from typing import Any, Dict, List

from core.llm_client import OracleLLMClient

BOARD_GEN_SYSTEM = "JSONのみ返せ。"

BOARD_GEN_PROMPT = """テーマ:{theme}
JSON:
{{"boards":[{{"name":"板","emoji":"📚","description":"説明","initial_threads":["【】スレ"]}}]}}"""


def generate_boards(
    entities: List[Dict[str, Any]],
    theme: str,
    key_issues: List[str],
    llm: OracleLLMClient,
) -> List[Dict[str, Any]]:
    """
    テーマから板構成を自動生成する。

    Returns:
        [{"name": str, "emoji": str, "description": str, "initial_threads": [str, ...]}, ...]
    """
    # エンティティを要約（最小限）
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

    # バリデーション
    validated = []
    has_zatsudan = False
    for b in boards:
        name = b.get("name", "")
        if not name:
            continue
        if "雑談" in name or "なんでも" in name:
            has_zatsudan = True
        validated.append(
            {
                "name": name,
                "emoji": b.get("emoji", "💬"),
                "description": b.get("description", ""),
                "initial_threads": b.get("initial_threads", [f"【{name}】総合スレ"]),
            }
        )

    # 雑談板がなければ追加
    if not has_zatsudan:
        validated.append(
            {
                "name": "雑談・なんでも板",
                "emoji": "💬",
                "description": "テーマ周辺の雑談",
                "initial_threads": ["【雑談】何でも語るスレ"],
            }
        )

    # 3〜6板に収める
    return validated[:6] if len(validated) > 6 else validated
