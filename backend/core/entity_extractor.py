"""
Oracle エンティティ抽出器
シードテキストからエンティティ（人物・組織・概念）と関係を抽出する。
"""

import json
from typing import Dict, Any
from .llm_client import OracleLLMClient


EXTRACT_SYSTEM = "テキスト分析の専門家。JSONのみ返す。説明文は書くな。思考タグなし。<think>を使うな。"

EXTRACT_USER_TEMPLATE = """以下のテーマを分析し、エンティティと関係を抽出してJSON返せ。

テーマ: {seed_text}

形式:
{{"entities":[{{"name":"名前","type":"person","description":"説明20字以内"}}],"relationships":[{{"source":"A","target":"B","type":"opposes","description":"関係10字"}}],"theme":"テーマ20字以内","key_issues":["争点1","争点2"]}}

ルール:
- エンティティ5〜8個（person/organization/concept）
- relationships 3〜5個
- key_issues 3個
- 短く簡潔に"""


def extract_entities(seed_text: str, llm: OracleLLMClient) -> Dict[str, Any]:
    """シードテキストからエンティティと関係を抽出する。"""
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": EXTRACT_USER_TEMPLATE.format(seed_text=seed_text)},
    ]

    result = llm.chat_json(messages, temperature=0.3)

    if "entities" not in result:
        result["entities"] = []
    if "relationships" not in result:
        result["relationships"] = []
    if "theme" not in result:
        result["theme"] = "未知のテーマ"
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
