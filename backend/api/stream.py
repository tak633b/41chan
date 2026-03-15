"""
SSE ストリーム API
GET /api/simulation/{id}/stream
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.simulation_runner import register_sse_queue, unregister_sse_queue

router = APIRouter()


@router.get("/simulation/{sim_id}/stream")
async def simulation_stream(sim_id: str):
    """SSEストリームエンドポイント"""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    register_sse_queue(sim_id, q)

    async def event_generator():
        try:
            # 接続確認イベント
            yield f"event: connected\ndata: {json.dumps({'sim_id': sim_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    event_type = event.get("type", "message")
                    payload = json.dumps(event.get("data", event), ensure_ascii=False)
                    yield f"event: {event_type}\ndata: {payload}\n\n"

                    # sim_complete または error でストリーム終了
                    if event_type in ("sim_complete", "error"):
                        yield f"event: close\ndata: {{}}\n\n"
                        break
                except asyncio.TimeoutError:
                    # keep-alive
                    yield ": keepalive\n\n"
        finally:
            unregister_sse_queue(sim_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
