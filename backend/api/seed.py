"""
シード素材投入 API
POST /api/seed/extract — URLまたはテキストからSeedData抽出
POST /api/seed/apply — SeedDataをシミュレーションに適用
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.seed_extractor import extract_from_url, extract_from_text, SeedData
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


@router.post("/seed/extract", response_model=SeedDataResponse)
async def extract_seed(req: SeedExtractRequest):
    """URLまたはテキストからシード情報を抽出"""
    if not req.url and not req.text:
        raise HTTPException(status_code=400, detail="urlまたはtextのいずれかを指定してください")

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if req.url:
            seed = await loop.run_in_executor(None, lambda: extract_from_url(req.url))
        else:
            seed = await loop.run_in_executor(None, lambda: extract_from_text(req.text))

        return SeedDataResponse(
            theme=seed.theme,
            question=seed.question,
            entities=seed.entities,
            tone=seed.tone,
            background_context=seed.background_context,
        )
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
