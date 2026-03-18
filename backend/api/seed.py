"""
シード素材投入 API
POST /api/seed/extract — URLまたはテキストからSeedData抽出
POST /api/seed/apply — SeedDataをシミュレーションに適用
"""

import json
import re
import asyncio
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.seed_extractor import extract_from_text, SeedData
from core.llm_client import OracleLLMClient
from db.database import get_simulation, update_simulation, db_conn

router = APIRouter()


class SeedExtractRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None


class SeedDataResponse(BaseModel):
    theme: str
    question: str
    entities: List[str]
    tone: str
    background_context: str


class SeedApplyRequest(BaseModel):
    sim_id: str
    seed_data: SeedDataResponse


async def _async_fetch_url(url: str) -> str:
    """httpxで非同期URLフェッチ"""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text
        import re as _re
        text = _re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=_re.IGNORECASE)
        text = _re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=_re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()
        title_match = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        return f"タイトル: {title}\n\n{text[:5000]}"


@router.post("/seed/extract", response_model=SeedDataResponse)
async def extract_seed(req: SeedExtractRequest):
    """URLまたはテキストからシード情報を抽出"""
    if not req.url and not req.text:
        raise HTTPException(status_code=400, detail="urlまたはtextのいずれかを指定してください")

    try:
        if req.url:
            article_text = await _async_fetch_url(req.url)
        else:
            article_text = req.text

        # Extract用はOllamaを使用（ZAIのレート制限を回避）
        ollama_llm = OracleLLMClient(backend="ollama")
        loop = asyncio.get_event_loop()
        seed = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: extract_from_text(article_text, llm=ollama_llm)),
            timeout=60.0
        )

        return SeedDataResponse(
            theme=seed.theme,
            question=seed.question,
            entities=seed.entities,
            tone=seed.tone,
            background_context=seed.background_context,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="タイムアウト: 処理に時間がかかりすぎました。別のURLを試すか、テキストを直接入力してください。")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"URL取得失敗: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽出失敗: {str(e)}")


@router.post("/seed/apply")
async def apply_seed(req: SeedApplyRequest):
    """SeedDataをシミュレーションに適用"""
    sim = get_simulation(req.sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    seed_json = json.dumps(req.seed_data.model_dump(), ensure_ascii=False)
    with db_conn() as conn:
        try:
            conn.execute(
                "UPDATE simulations SET seed_data=?, theme=?, prompt=? WHERE id=?",
                (seed_json, req.seed_data.theme, req.seed_data.question, req.sim_id),
            )
        except Exception:
            conn.execute(
                "UPDATE simulations SET theme=?, prompt=? WHERE id=?",
                (req.seed_data.theme, req.seed_data.question, req.sim_id),
            )

    return {"ok": True, "sim_id": req.sim_id}
