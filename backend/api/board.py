"""
板・スレッド API
GET /api/simulation/{id}/boards
GET /api/simulation/{id}/board/{boardId}/threads
GET /api/simulation/{id}/thread/{threadId}
"""

import json

from fastapi import APIRouter, HTTPException

from db.database import db_conn, get_boards, get_posts, get_threads

router = APIRouter()


@router.get("/simulation/{sim_id}/boards")
async def get_boards_api(sim_id: str):
    """板一覧"""
    boards = get_boards(sim_id)
    return boards


@router.get("/simulation/{sim_id}/board/{board_id}/threads")
async def get_threads_api(sim_id: str, board_id: str):
    """スレッド一覧"""
    threads = get_threads(board_id)
    return threads


@router.get("/simulation/{sim_id}/thread/{thread_id}")
async def get_thread_detail(sim_id: str, thread_id: str):
    """スレッド詳細（全投稿）"""
    with db_conn() as conn:
        row = conn.execute(
            """SELECT t.*, b.name as board_name
               FROM threads t
               LEFT JOIN boards b ON b.id=t.board_id
               WHERE t.id=?""",
            (thread_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Thread not found")
        thread = dict(row)

        posts = [
            dict(r) for r in conn.execute(
                "SELECT * FROM posts WHERE thread_id=? ORDER BY post_num",
                (thread_id,),
            ).fetchall()
        ]

    return {
        "thread_id": thread["id"],
        "title": thread["title"],
        "board_name": thread.get("board_name", ""),
        "board_id": thread["board_id"],
        "simulation_id": thread["simulation_id"],
        "posts": [
            {
                "post_id": p["id"],
                "post_num": p["post_num"],
                "agent_name": p["agent_name"],
                "username": p["username"],
                "content": p["content"],
                "reply_to": p["reply_to"],
                "timestamp": p["timestamp"],
                "emotion": p.get("emotion", "neutral"),
            }
            for p in posts
        ],
    }
