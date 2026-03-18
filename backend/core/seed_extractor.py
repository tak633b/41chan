"""
シード素材からシミュレーションのテーマ・登場人物・議題を自動抽出する。
ニュース記事URL or テキストから SeedData を生成。
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import requests
from .llm_client import OracleLLMClient


@dataclass
class SeedData:
    theme: str = ""
    question: str = ""
    entities: List[str] = field(default_factory=list)
    tone: str = "neutral"
    background_context: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SeedData":
        return cls(
            theme=d.get("theme", ""),
            question=d.get("question", ""),
            entities=d.get("entities", []),
            tone=d.get("tone", "neutral"),
            background_context=d.get("background_context", ""),
        )


def fetch_article_text(url: str) -> str:
    """URLからテキストを抽出（簡易版: HTML→テキスト変換）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # 簡易HTMLタグ除去
        text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
        text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # タイトル抽出
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        return f"タイトル: {title}\n\n{text[:5000]}"
    except Exception as e:
        raise ValueError(f"URL取得失敗: {e}")


def extract_seed_from_text(text: str, llm: Optional[OracleLLMClient] = None) -> SeedData:
    """テキストからSeedDataを抽出"""
    if llm is None:
        llm = OracleLLMClient()

    prompt = f"""以下のテキストから、5ch掲示板シミュレーションのシード情報を抽出してください。

【テキスト】
{text[:4000]}

以下のJSON形式で返してください:
{{
  "theme": "シミュレーションのテーマ（30字以内）",
  "question": "議論の中心となる問い（疑問文で）",
  "entities": ["関連するエンティティ1", "エンティティ2", "エンティティ3"],
  "tone": "議論のトーン（neutral/heated/humorous/serious のいずれか）",
  "background_context": "議論の背景情報（100〜200字で要約）"
}}

日本語で返してください。"""

    messages = [
        {"role": "system", "content": "テキストからシミュレーション用のシード情報を抽出するアシスタント。JSON形式で返す。"},
        {"role": "user", "content": prompt},
    ]

    result = llm.chat_json(messages, temperature=0.3)
    return SeedData(
        theme=result.get("theme", ""),
        question=result.get("question", ""),
        entities=result.get("entities", []),
        tone=result.get("tone", "neutral"),
        background_context=result.get("background_context", ""),
    )


def extract_from_url(url: str, llm: Optional[OracleLLMClient] = None) -> SeedData:
    """URLからSeedDataを抽出"""
    text = fetch_article_text(url)
    return extract_seed_from_text(text, llm)


def extract_from_text(text: str, llm: Optional[OracleLLMClient] = None) -> SeedData:
    """テキストからSeedDataを抽出"""
    return extract_seed_from_text(text, llm)
