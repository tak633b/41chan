"""
SQLite データベース初期化・操作ヘルパー
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "oracle.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS simulations (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    scale TEXT NOT NULL DEFAULT 'mini',
    custom_agents INTEGER,
    custom_rounds INTEGER,
    status TEXT NOT NULL DEFAULT 'initializing',
    progress REAL DEFAULT 0.0,
    round_current INTEGER DEFAULT 0,
    round_total INTEGER DEFAULT 0,
    agent_count INTEGER DEFAULT 0,
    board_count INTEGER DEFAULT 0,
    total_posts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boards (
    id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '💬',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    board_id TEXT NOT NULL,
    simulation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    last_post_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (board_id) REFERENCES boards(id),
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    board_id TEXT NOT NULL,
    simulation_id TEXT NOT NULL,
    post_num INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    reply_to INTEGER,
    emotion TEXT DEFAULT 'neutral',
    round_num INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(id),
    FOREIGN KEY (board_id) REFERENCES boards(id),
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    name TEXT NOT NULL,
    username TEXT NOT NULL,
    bio TEXT DEFAULT '',
    persona TEXT DEFAULT '',
    age INTEGER DEFAULT 0,
    gender TEXT DEFAULT 'other',
    mbti TEXT DEFAULT '',
    tone_style TEXT DEFAULT 'worker',
    profession TEXT DEFAULT '',
    interested_topics TEXT DEFAULT '[]',
    stance TEXT DEFAULT '{}',
    hidden_agenda TEXT DEFAULT '',
    posting_style TEXT DEFAULT 'emotional',
    post_count INTEGER DEFAULT 0,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL UNIQUE,
    summary TEXT DEFAULT '',
    details TEXT DEFAULT '',
    confidence REAL DEFAULT 0.5,
    key_findings TEXT DEFAULT '[]',
    agent_positions TEXT DEFAULT '{}',
    turning_points TEXT DEFAULT '[]',
    consensus TEXT DEFAULT '',
    minority_views TEXT DEFAULT '[]',
    prediction TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    stance_distribution TEXT DEFAULT '{}',
    activity_by_round TEXT DEFAULT '[]',
    consensus_score REAL DEFAULT 0.5,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS persistent_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT NOT NULL,
    bio TEXT DEFAULT '',
    persona TEXT DEFAULT '',
    age INTEGER DEFAULT 0,
    gender TEXT DEFAULT 'other',
    mbti TEXT DEFAULT '',
    tone_style TEXT DEFAULT 'worker',
    profession TEXT DEFAULT '',
    interested_topics TEXT DEFAULT '[]',
    posting_style TEXT DEFAULT 'emotional',
    use_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    rating TEXT DEFAULT 'unrated',
    post_frequency TEXT DEFAULT 'medium',
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS ask_history (
    id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answers TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE INDEX IF NOT EXISTS idx_boards_sim ON boards(simulation_id);
CREATE INDEX IF NOT EXISTS idx_threads_board ON threads(board_id);
CREATE INDEX IF NOT EXISTS idx_threads_sim ON threads(simulation_id);
CREATE INDEX IF NOT EXISTS idx_posts_thread ON posts(thread_id);
CREATE INDEX IF NOT EXISTS idx_posts_sim ON posts(simulation_id);
CREATE INDEX IF NOT EXISTS idx_agents_sim ON agents(simulation_id);
"""


def get_db():
    """コンテキストマネージャー: DB接続を返す"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def db_conn():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """DBスキーマを初期化"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db_conn() as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"[DB] 初期化完了: {DB_PATH}")


# --- CRUD ヘルパー ---

def get_simulation(sim_id: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM simulations WHERE id=?", (sim_id,)).fetchone()
        return dict(row) if row else None


def update_simulation(sim_id: str, **kwargs):
    from datetime import datetime, timezone
    kwargs["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [sim_id]
    with db_conn() as conn:
        conn.execute(f"UPDATE simulations SET {sets} WHERE id=?", vals)


def get_boards(sim_id: str) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """SELECT b.*, 
               (SELECT COUNT(*) FROM threads WHERE board_id=b.id) as thread_count,
               (SELECT COUNT(*) FROM posts WHERE board_id=b.id) as post_count
               FROM boards b
               WHERE b.simulation_id=?""",
            (sim_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_threads(board_id: str) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """SELECT t.*, COUNT(p.id) as post_count
               FROM threads t
               LEFT JOIN posts p ON p.thread_id=t.id
               WHERE t.board_id=?
               GROUP BY t.id
               ORDER BY t.created_at""",
            (board_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_posts(thread_id: str) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE thread_id=? ORDER BY post_num",
            (thread_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_agents(sim_id: str) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE simulation_id=?", (sim_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_report(sim_id: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE simulation_id=?", (sim_id,)
        ).fetchone()
        return dict(row) if row else None


def save_persistent_agents(agents_data: List[Dict]):
    """エージェントを永続テーブルに保存（既存ならスキップ）"""
    with db_conn() as conn:
        for a in agents_data:
            conn.execute(
                """INSERT OR IGNORE INTO persistent_agents
                   (id, name, username, bio, persona, age, gender, mbti,
                    tone_style, profession, interested_topics, posting_style, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    a.get("id", str(uuid.uuid4())),
                    a["name"],
                    a.get("username", ""),
                    a.get("bio", ""),
                    a.get("persona", ""),
                    a.get("age", 30),
                    a.get("gender", "other"),
                    a.get("mbti", ""),
                    a.get("tone_style", "worker"),
                    a.get("profession", ""),
                    json.dumps(a.get("interested_topics", []), ensure_ascii=False) if isinstance(a.get("interested_topics"), list) else a.get("interested_topics", "[]"),
                    a.get("posting_style", "emotional"),
                    datetime.now().isoformat(),
                ),
            )


def get_persistent_agents(limit: int = 20, include_bad: bool = True) -> List[Dict]:
    """永続エージェントを取得（使用回数が少ない順 + ランダム）"""
    with db_conn() as conn:
        if include_bad:
            rows = conn.execute(
                "SELECT * FROM persistent_agents ORDER BY use_count ASC, RANDOM() LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM persistent_agents WHERE rating != 'bad' ORDER BY use_count ASC, RANDOM() LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def increment_agent_use_count(agent_names: List[str]):
    """使用回数をインクリメント"""
    with db_conn() as conn:
        for name in agent_names:
            conn.execute(
                "UPDATE persistent_agents SET use_count = use_count + 1 WHERE name=?",
                (name,),
            )
