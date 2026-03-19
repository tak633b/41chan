"""
Seed Extractor
Extract simulation themes, entities, and discussion topics from seed material.
Generates SeedData from news article URLs or raw text.
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
    og_image: str = ""
    source_url: str = ""

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
            og_image=d.get("og_image", ""),
            source_url=d.get("source_url", ""),
        )


def extract_og_image(html: str) -> str:
    """Extract og:image URL from HTML meta tags."""
    patterns = [
        r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+content=["\'](.*?)["\']\s+property=["\']og:image["\']',
        r'<meta\s+name=["\']twitter:image["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+content=["\'](.*?)["\']\s+name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1).strip()
            if url and url.startswith(("http://", "https://")):
                return url
    return ""


def fetch_article_text(url: str) -> tuple:
    """Extract text and og:image from URL. Returns (text, og_image_url)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        import certifi
        resp = requests.get(url, headers=headers, timeout=(5, 10), verify=certifi.where())
        resp.raise_for_status()
        html = resp.text

        # Extract OG image before stripping tags
        og_image = extract_og_image(html)

        # Simple HTML tag removal
        text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
        text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # Title extraction
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        return f"Title: {title}\n\n{text[:5000]}", og_image
    except Exception as e:
        return f"URL: {url}\n\n(Failed to fetch article directly. Infer the topic from the URL domain/path: {e})", ""


def extract_seed_from_text(text: str, llm: Optional[OracleLLMClient] = None) -> SeedData:
    """Extract SeedData from text."""
    if llm is None:
        llm = OracleLLMClient()

    prompt = f"""Extract seed information for an imageboard simulation from the following text.

[Text]
{text[:4000]}

Return in this JSON format:
{{
  "theme": "Simulation theme (concise, under 50 chars)",
  "question": "Central discussion question (as a question)",
  "entities": ["Entity 1", "Entity 2", "Entity 3"],
  "tone": "Discussion tone (neutral/heated/humorous/serious)",
  "background_context": "Background context summary (100-200 words)"
}}

Respond in English."""

    messages = [
        {"role": "system", "content": "You extract seed information for simulations from text. Return only JSON."},
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
    """Extract SeedData from URL."""
    text, og_image = fetch_article_text(url)
    seed = extract_seed_from_text(text, llm)
    seed.og_image = og_image
    seed.source_url = url
    return seed


def extract_from_text(text: str, llm: Optional[OracleLLMClient] = None) -> SeedData:
    """Extract SeedData from text."""
    return extract_seed_from_text(text, llm)
