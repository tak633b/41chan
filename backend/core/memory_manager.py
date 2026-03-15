"""
Oracle メモリマネージャー
Zep CE の本質的機能を自前実装。
- 時系列管理（SQLite）
- 重複解消（ChromaDB セマンティック類似度 0.92 閾値）
- 要約（10件超えたら LLM 要約）
- ハイブリッド検索（セマンティック + 時系列 + 重要度）
"""

import json
import sqlite3
import uuid
import os
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Any, Optional
from .llm_client import OracleLLMClient

# ChromaDB はオプション（インストール済みの場合のみ使用）
try:
    import chromadb

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[MemoryManager] ChromaDB が未インストール。ベクトル検索は無効化されます。")


SUMMARIZE_THRESHOLD = 10  # 短期記憶がこの件数を超えたら要約

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    round_num INT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    importance FLOAT DEFAULT 0.5,
    related_agents TEXT,
    summary_group_id TEXT,
    is_active BOOL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_episodes_agent ON episodes(agent_id, round_num);
CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id);
"""


class MemoryManager:
    """エージェント記憶管理システム"""

    def __init__(self, db_dir: str, project_id: str, llm: Optional[OracleLLMClient] = None):
        """
        Args:
            db_dir: SQLite + ChromaDB のディレクトリ
            project_id: プロジェクトID
            llm: 要約・重複解消に使うLLMクライアント（Noneなら要約スキップ）
        """
        os.makedirs(db_dir, exist_ok=True)
        self.project_id = project_id
        self.llm = llm

        # SQLite — メインのoracle.dbとは別ファイルにしてロック競合を回避
        self.db_path = os.path.join(db_dir, f"memory_{project_id[:8]}.db")
        self._init_sqlite()

        # ChromaDB（利用可能な場合）
        self.chroma_client = None
        self.collection = None
        if CHROMA_AVAILABLE:
            chroma_path = os.path.join(db_dir, "chroma")
            os.makedirs(chroma_path, exist_ok=True)
            try:
                self.chroma_client = chromadb.PersistentClient(path=chroma_path)
                coll_name = f"oracle_{project_id[:20].replace('-', '_')}"
                self.collection = self.chroma_client.get_or_create_collection(
                    name=coll_name
                )
                print(f"[MemoryManager] ChromaDB初期化完了: {coll_name}")
            except Exception as e:
                print(f"[MemoryManager] ChromaDB初期化失敗: {e} — SQLiteのみ使用")
                self.collection = None

    @contextmanager
    def _db_conn(self):
        """SQLite接続コンテキストマネージャー（必ずclose()する）"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_sqlite(self):
        """SQLite テーブルを初期化"""
        with self._db_conn() as conn:
            for stmt in CREATE_TABLE_SQL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.commit()

    # ------------------------------------------------------------------
    # 記憶保存
    # ------------------------------------------------------------------

    def store(
        self,
        agent_id: str,
        round_num: int,
        event_type: str,
        content: str,
        importance: float = 0.5,
        related_agents: Optional[List[str]] = None,
    ) -> str:
        """エピソードを保存する。重複チェック付き。"""
        # 重複チェック（ChromaDB）
        if self.collection is not None and len(content) > 10:
            try:
                results = self.collection.query(
                    query_texts=[content],
                    n_results=1,
                    where={"agent_id": agent_id},
                )
                if results["distances"] and results["distances"][0]:
                    sim = 1.0 - results["distances"][0][0]  # cosine → similarity
                    if sim >= 0.92:
                        # 重複エピソード → スキップ
                        existing_id = results["ids"][0][0] if results["ids"][0] else None
                        return existing_id or ""
            except Exception:
                pass  # 重複チェック失敗は無視して保存続行

        episode_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # SQLite に保存
        with self._db_conn() as conn:
            conn.execute(
                """INSERT INTO episodes
                   (id, agent_id, project_id, round_num, timestamp,
                    event_type, content, importance, related_agents, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    episode_id,
                    agent_id,
                    self.project_id,
                    round_num,
                    now,
                    event_type,
                    content,
                    importance,
                    json.dumps(related_agents or [], ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()

        # ChromaDB にも保存
        if self.collection is not None:
            try:
                self.collection.add(
                    ids=[episode_id],
                    documents=[content],
                    metadatas=[
                        {
                            "agent_id": agent_id,
                            "project_id": self.project_id,
                            "round_num": round_num,
                            "event_type": event_type,
                            "importance": importance,
                        }
                    ],
                )
            except Exception as e:
                pass  # ChromaDB保存失敗は無視

        # 要約チェック
        self._check_and_summarize(agent_id)

        return episode_id

    # ------------------------------------------------------------------
    # 要約
    # ------------------------------------------------------------------

    def _check_and_summarize(self, agent_id: str):
        """短期記憶が閾値を超えたら要約を実行"""
        with self._db_conn() as conn:
            count = conn.execute(
                """SELECT COUNT(*) FROM episodes
                   WHERE agent_id=? AND project_id=? AND is_active=1
                     AND summary_group_id IS NULL""",
                (agent_id, self.project_id),
            ).fetchone()[0]

        if count > SUMMARIZE_THRESHOLD and self.llm is not None:
            self._summarize(agent_id)

    def _summarize(self, agent_id: str):
        """LLM で古いエピソードを要約してまとめる"""
        with self._db_conn() as conn:
            rows = conn.execute(
                """SELECT id, round_num, content FROM episodes
                   WHERE agent_id=? AND project_id=? AND is_active=1
                     AND summary_group_id IS NULL
                   ORDER BY round_num ASC LIMIT ?""",
                (agent_id, self.project_id, SUMMARIZE_THRESHOLD),
            ).fetchall()

        if not rows:
            return

        episodes_text = "\n".join(
            f"Round {r[1]}: {r[2]}" for r in rows
        )
        group_id = str(uuid.uuid4())

        try:
            messages = [
                {
                    "role": "system",
                    "content": "あなたはエージェントの記憶要約専門家です。",
                },
                {
                    "role": "user",
                    "content": f"""以下のエピソードを要約してください。
エージェント視点で書き、感情変化・印象変化・重要な発見を含めてください（300字以内）。

{episodes_text}

要約（エージェント視点の一人称で）:""",
                },
            ]
            summary = self.llm.chat(messages, temperature=0.3)
        except Exception as e:
            summary = f"[要約失敗: {e}] " + "; ".join(r[2][:30] for r in rows[:3])

        # 要約を新規エピソードとして保存
        summary_episode_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        episode_ids = [r[0] for r in rows]
        rounds = [r[1] for r in rows]

        with self._db_conn() as conn:
            conn.execute(
                """INSERT INTO episodes
                   (id, agent_id, project_id, round_num, timestamp,
                    event_type, content, importance, summary_group_id, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 'summary', ?, 0.8, ?, 1, ?)""",
                (
                    summary_episode_id,
                    agent_id,
                    self.project_id,
                    max(rounds),
                    now,
                    f"[Round {min(rounds)}-{max(rounds)} 要約] {summary}",
                    group_id,
                    now,
                ),
            )
            # 元エピソードを非活性化
            for eid in episode_ids:
                conn.execute(
                    "UPDATE episodes SET is_active=0, summary_group_id=? WHERE id=?",
                    (group_id, eid),
                )
            conn.commit()

        print(f"[MemoryManager] {agent_id}: {len(rows)}件を要約 (group={group_id[:8]})")

    # ------------------------------------------------------------------
    # 検索（ハイブリッド）
    # ------------------------------------------------------------------

    def recall(
        self,
        agent_id: str,
        context: str,
        top_k: int = 5,
        current_round: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        エージェントが発言前に「思い出す」ハイブリッド検索。

        スコア = semantic×0.5 + recency×0.3 + importance×0.2
        """
        semantic_results: Dict[str, float] = {}

        # 1. セマンティック検索（ChromaDB）
        if self.collection is not None and len(context) > 5:
            try:
                results = self.collection.query(
                    query_texts=[context],
                    n_results=min(top_k * 2, 20),
                    where={"agent_id": agent_id},
                )
                if results["ids"] and results["ids"][0]:
                    for eid, dist in zip(
                        results["ids"][0], results["distances"][0]
                    ):
                        semantic_results[eid] = 1.0 - dist
            except Exception:
                pass

        # 2. 時系列検索（SQLite — 直近エピソード）
        with self._db_conn() as conn:
            rows = conn.execute(
                """SELECT id, round_num, content, importance, event_type
                   FROM episodes
                   WHERE agent_id=? AND project_id=? AND is_active=1
                   ORDER BY round_num DESC LIMIT ?""",
                (agent_id, self.project_id, top_k * 3),
            ).fetchall()

        if not rows:
            return []

        # 3. スコア統合
        max_round = max(r[1] for r in rows) if rows else 1
        scored = []
        for row in rows:
            eid, round_num, content, importance, event_type = row
            sem_score = semantic_results.get(eid, 0.0)
            recency = round_num / max(max_round, 1)
            score = sem_score * 0.5 + recency * 0.3 + importance * 0.2
            scored.append(
                {
                    "id": eid,
                    "round_num": round_num,
                    "content": content,
                    "importance": importance,
                    "event_type": event_type,
                    "score": score,
                }
            )

        # 4. スコア上位 top_k を返す
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def get_all_episodes(self, agent_id: str) -> List[Dict[str, Any]]:
        """エージェントの全エピソードを取得（レポート用）"""
        with self._db_conn() as conn:
            rows = conn.execute(
                """SELECT round_num, content, importance, event_type
                   FROM episodes
                   WHERE agent_id=? AND project_id=?
                   ORDER BY round_num ASC""",
                (agent_id, self.project_id),
            ).fetchall()
        return [
            {
                "round_num": r[0],
                "content": r[1],
                "importance": r[2],
                "event_type": r[3],
            }
            for r in rows
        ]
