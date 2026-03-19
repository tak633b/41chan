"""
Entity Extractor
Extract entities (people, organizations, concepts) and relationships from seed text.
"""

import json
from typing import Dict, Any
from .llm_client import OracleLLMClient


EXTRACT_SYSTEM = "You are a text analysis expert. Return ONLY JSON. No explanations. No thinking tags. Do not use <think>."

EXTRACT_USER_TEMPLATE = """Analyze the following topic and extract entities and relationships as JSON.

Topic: {seed_text}

Format:
{{"entities":[{{"name":"name","type":"person","description":"brief description"}}],"relationships":[{{"source":"A","target":"B","type":"opposes","description":"relationship"}}],"theme":"theme in 50 chars","key_issues":["issue1","issue2"]}}

Rules:
- 5-8 entities (person/organization/concept)
- 3-5 relationships
- 3 key_issues
- Keep it concise"""


def _fallback_entities(seed_text: str) -> Dict[str, Any]:
    """Simple fallback when LLM fails — infer minimal entities from text."""
    theme = seed_text[:50].strip().rstrip(".!?")
    return {
        "entities": [
            {"name": "Proponents", "type": "concept", "description": "Those in favor", "attributes": {"stance": "for", "role": "", "motivation": ""}},
            {"name": "Opponents", "type": "concept", "description": "Those against", "attributes": {"stance": "against", "role": "", "motivation": ""}},
            {"name": "Neutrals", "type": "concept", "description": "Neutral parties", "attributes": {"stance": "neutral", "role": "", "motivation": ""}},
        ],
        "relationships": [
            {"source": "Proponents", "target": "Opponents", "type": "opposes", "description": "Opposing views"},
        ],
        "theme": theme,
        "key_issues": ["Arguments for and against", "Scope of impact", "Future outlook"],
    }


def extract_entities(seed_text: str, llm: OracleLLMClient) -> Dict[str, Any]:
    """Extract entities and relationships from seed text."""
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": EXTRACT_USER_TEMPLATE.format(seed_text=seed_text)},
    ]

    try:
        result = llm.chat_json(messages, temperature=0.3)
    except (ValueError, Exception) as e:
        print(f"[EntityExtractor] chat_json failed, using fallback: {e}", flush=True)
        result = _fallback_entities(seed_text)

    if "entities" not in result:
        result["entities"] = []
    if "relationships" not in result:
        result["relationships"] = []
    if "theme" not in result:
        result["theme"] = "Unknown topic"
    if "key_issues" not in result:
        result["key_issues"] = []

    # attributes がなくても下流で困らないようデフォルト補完
    for ent in result["entities"]:
        if "attributes" not in ent:
            ent["attributes"] = {"stance": "", "role": "", "motivation": ""}

    print(
        f"[EntityExtractor] テーマ: {result['theme']} | "
        f"エンティティ: {len(result['entities'])}個 | "
        f"関係: {len(result['relationships'])}個"
    )
    return result
