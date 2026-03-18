"""
GraphRAG API
GET /api/simulation/{sim_id}/graph — エージェント関係グラフ
GET /api/simulation/{sim_id}/relationship/{relationship_id}/evidence — 関係の根拠投稿
"""

from fastapi import APIRouter, HTTPException
from db.database import get_simulation, db_conn
from core.relationship_tracker import get_agent_graph

router = APIRouter()


@router.get("/simulation/{sim_id}/graph")
async def get_graph(sim_id: str):
    """エージェント関係グラフを返す（vis.js形式 + relationship_id付き）"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    graph = get_agent_graph(sim_id)

    # エッジに relationship_id を付与する
    with db_conn() as conn:
        rels = conn.execute(
            "SELECT id, from_agent_id, to_agent_id, relation_type FROM agent_relationships WHERE sim_id=?",
            (sim_id,),
        ).fetchall()

    rel_map = {}
    for r in rels:
        key = (r["from_agent_id"], r["to_agent_id"], r["relation_type"])
        rel_map[key] = r["id"]

    for edge in graph.get("edges", []):
        key = (edge["from"], edge["to"], edge["label"])
        edge["relationship_id"] = rel_map.get(key, "")

    return graph


@router.get("/simulation/{sim_id}/relationship/{relationship_id}/evidence")
async def get_relationship_evidence(sim_id: str, relationship_id: str):
    """関係の根拠となった投稿を返す"""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    with db_conn() as conn:
        rel = conn.execute(
            "SELECT * FROM agent_relationships WHERE id=? AND sim_id=?",
            (relationship_id, sim_id),
        ).fetchone()
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found")

        from_agent = rel["from_agent_id"]
        to_agent = rel["to_agent_id"]
        relation_type = rel["relation_type"]
        evidence_text = rel["evidence"] or ""

        # evidence フィールドには "投稿: ..." or "LLM分析: ..." 形式のテキストが入っている
        # 両エージェントの関連投稿を取得して根拠として返す
        evidence_posts = []

        # from_agent と to_agent の投稿を取得（関連するもの）
        posts = conn.execute(
            """SELECT p.agent_name, p.content, p.created_at, p.post_num
               FROM posts p
               WHERE p.simulation_id=? AND p.agent_name IN (?, ?)
               ORDER BY p.post_num ASC""",
            (sim_id, from_agent, to_agent),
        ).fetchall()

        # evidence テキストに含まれる内容と部分一致する投稿を優先
        evidence_snippet = evidence_text.replace("投稿: ", "").replace("LLM分析: ", "")[:80]

        matched = []
        others = []
        for p in posts:
            if evidence_snippet and evidence_snippet[:30] in p["content"]:
                matched.append(p)
            else:
                others.append(p)

        # マッチした投稿を先に、残りを後に（最大10件）
        selected = matched + others
        for p in selected[:10]:
            evidence_posts.append({
                "agent_name": p["agent_name"],
                "content": p["content"],
                "created_at": p["created_at"],
            })

    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "relation_type": relation_type,
        "evidence_text": evidence_text,
        "evidence_posts": evidence_posts,
    }
