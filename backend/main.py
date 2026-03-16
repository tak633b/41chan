"""
Oracle Channel - FastAPI メインアプリ
"""

import asyncio
import concurrent.futures
import os
import sys

# .env ファイルを自動ロード
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ[_k.strip()] = _v.strip()  # .env を正とする（LaunchAgent等の環境変数を上書き）



# パスの解決（core/ がここから参照できるように）
sys.path.insert(0, os.path.dirname(__file__))

# スレッドプールを拡大（ZAI APIの長時間ブロッキング呼び出し対策）
asyncio.get_event_loop().set_default_executor(
    concurrent.futures.ThreadPoolExecutor(max_workers=16)
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db, list_interrupted_simulations, update_simulation
from api.simulation import router as sim_router
from api.board import router as board_router
from api.stream import router as stream_router
from api.report import router as report_router
from api.ask import router as ask_router

app = FastAPI(
    title="41ch API",
    description="5ch風シミュレーション閲覧Webアプリのバックエンド",
    version="1.0.0",
)

# CORS設定（フロントエンド: localhost:3000 を許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(sim_router, prefix="/api")
app.include_router(board_router, prefix="/api")
app.include_router(stream_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(ask_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """起動時にDBを初期化 + 中断シミュレーションを自動再開"""
    init_db()
    print("[41ch] バックエンド起動完了 🎌")

    # 中断シミュレーションの自動再開
    interrupted = list_interrupted_simulations()
    if interrupted:
        print(f"[41ch] 中断シミュレーション {len(interrupted)}件 を検出 → 自動再開します")
        from services.simulation_runner import run_simulation
        for sim in interrupted:
            sim_id = sim["id"]
            print(f"[41ch] 再開: {sim_id[:8]} ({sim.get('theme', 'テーマ未設定')[:30]})")
            # progressをリセットして再開（どのステップまで進んでいたかに関わらず最初から）
            update_simulation(sim_id, status="simulating", progress=0.01)
            asyncio.create_task(
                run_simulation(
                    sim_id=sim_id,
                    seed_text=sim.get("theme", ""),
                    prompt=sim.get("prompt", ""),
                    scale=sim.get("scale", "mini"),
                    custom_agents=sim.get("custom_agents"),
                    custom_rounds=sim.get("custom_rounds"),
                )
            )
    else:
        print("[41ch] 中断シミュレーションなし")


@app.get("/")
async def root():
    return {"message": "Oracle Channel API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
