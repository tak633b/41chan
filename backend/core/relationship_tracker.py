"""
GraphRAG: エージェント間の関係（賛同・対立・引用・影響）を追跡。
投稿内容からLLMで関係を抽出し、SQLiteに保存。
"""

import json
import threading
from typing import List, Dict, Any, Optional
from .llm_client import OracleLLMClient
from db.database import upsert_agent_relationship, get_agent_relationships, db_conn


def extract_relationships_async(sim_id: str, post: dict, all_posts: list, agents: list):
    """非同期（バックグラウンドスレッド）で関係抽出を実行"""
    t = threading.Thread(
        target=_extract_relationships_sync,
        args=(sim_id, post, all_posts, agents),
        daemon=True,
    )
    t.start()


def _extract_relationships_sync(sim_id: str, post: dict, all_posts: list, agents: list):
    """投稿から関係を抽出してDBに保存"""
    try:
        agent_name = post.get("agent_name", "")
        content = post.get("content", "")
        anchor_to = post.get("anchor_to")

        if not agent_name or not content or len(content) < 10:
            return

        # アンカー先の投稿を取得
        anchor_post = None
        if anchor_to:
            for p in all_posts:
                if p.get("num") == anchor_to or p.get("post_num") == anchor_to:
                    anchor_post = p
                    break

        # エージェント名リスト
        agent_names = [a.name if hasattr(a, 'name') else a.get("name", "") for a in agents]

        # アンカー先があれば簡易ルールで関係推定（LLMコスト節約）
        if anchor_post and anchor_post.get("agent_name"):
            target_name = anchor_post["agent_name"]
            target_content = anchor_post.get("content", "")

            # 簡易テキスト分析
            relation = _infer_relation_simple(content, target_content)
            if relation:
                upsert_agent_relationship(
                    sim_id=sim_id,
                    from_id=agent_name,
                    to_id=target_name,
                    relation_type=relation,
                    strength=1.0,
                    evidence=f"投稿: {content[:100]}",
                )
        else:
            # アンカーなしの場合、5投稿に1回だけLLMで関係分析
            post_num = post.get("num", post.get("post_num", 0))
            if post_num % 5 != 0:
                return

            _extract_with_llm(sim_id, post, all_posts[-10:], agent_names)

    except Exception as e:
        print(f"[RelTracker] 関係抽出エラー: {e}")


def _infer_relation_simple(content: str, target_content: str) -> Optional[str]:
    """簡易テキスト分析で関係を推定（LLMなし）"""
    agree_words = ["それな", "同意", "わかる", "確かに", "その通り", "正論", "せやな", "いいこと言った"]
    disagree_words = ["は？", "ねーよ", "嘘乙", "アホか", "違う", "反論", "論破", "それは違う", "おかしい", "ないわ"]
    quote_words = [">>"]

    content_lower = content.lower()

    for w in agree_words:
        if w in content_lower:
            return "agree"

    for w in disagree_words:
        if w in content_lower:
            return "disagree"

    if ">>" in content:
        return "quote"

    return None


def _extract_with_llm(sim_id: str, post: dict, recent_posts: list, agent_names: list):
    """LLMで関係を抽出（コスト制御のため頻度を制限）"""
    try:
        llm = OracleLLMClient()

        posts_text = "\n".join([
            f">>{p.get('num', p.get('post_num', '?'))} {p.get('agent_name', '？')}: {p.get('content', '')[:80]}"
            for p in recent_posts
        ])

        prompt = f"""以下の掲示板投稿から、エージェント間の関係を抽出してください。

【対象投稿】
{post.get('agent_name', '？')}: {post.get('content', '')[:200]}

【直近の投稿】
{posts_text}

【エージェント一覧】
{', '.join(agent_names[:15])}

JSON配列で返してください。関係がなければ空配列 [] を返す:
[
  {{"from": "発言者名", "to": "対象者名", "type": "agree/disagree/quote/influence", "strength": 1.0}}
]"""

        messages = [
            {"role": "system", "content": "掲示板投稿からエージェント間の関係を分析する。JSON配列のみ返す。"},
            {"role": "user", "content": prompt},
        ]

        result = llm.chat(messages, temperature=0.2)

        # JSON抽出
        import re
        match = re.search(r'\[[\s\S]*?\]', result)
        if match:
            relations = json.loads(match.group())
            for rel in relations:
                if rel.get("from") and rel.get("to") and rel.get("type"):
                    upsert_agent_relationship(
                        sim_id=sim_id,
                        from_id=rel["from"],
                        to_id=rel["to"],
                        relation_type=rel["type"],
                        strength=float(rel.get("strength", 1.0)),
                        evidence=f"LLM分析: {post.get('content', '')[:80]}",
                    )
    except Exception as e:
        print(f"[RelTracker] LLM関係抽出失敗: {e}")


def get_agent_graph(sim_id: str) -> dict:
    """vis.js形式のグラフデータを返す"""
    relationships = get_agent_relationships(sim_id)

    # エージェント情報取得 + スレ主（post_num=1の投稿者）を特定
    with db_conn() as conn:
        agents = conn.execute(
            "SELECT id, name, post_count, tone_style FROM agents WHERE simulation_id=?",
            (sim_id,),
        ).fetchall()
        first_post = conn.execute(
            "SELECT agent_name FROM posts WHERE simulation_id=? ORDER BY post_num ASC LIMIT 1",
            (sim_id,),
        ).fetchone()

    thread_starter_name = first_post["agent_name"] if first_post else None

    # ノード生成
    agent_map = {}
    nodes = []
    for a in agents:
        agent_map[a["name"]] = a["id"]
        nodes.append({
            "id": a["name"],
            "label": a["name"],
            "title": f"{a['name']} ({a['tone_style']})\n投稿数: {a['post_count']}",
            "value": a["post_count"] or 1,
            "group": a["tone_style"],
        })

    # エッジ生成
    edges = []
    color_map = {
        "agree": "#2ecc71",      # 緑
        "disagree": "#e74c3c",   # 赤
        "quote": "#3498db",      # 青
        "influence": "#f39c12",  # オレンジ
    }
    for rel in relationships:
        edges.append({
            "from": rel["from_agent_id"],
            "to": rel["to_agent_id"],
            "label": rel["relation_type"],
            "value": rel["strength"],
            "color": {"color": color_map.get(rel["relation_type"], "#999")},
            "arrows": "to",
            "title": rel.get("evidence", ""),
        })

    # グラフ統計（スレ主を除外）
    stats = _compute_graph_stats(nodes, edges, thread_starter_id=thread_starter_name)

    return {"nodes": nodes, "edges": edges, "stats": stats}


def _compute_graph_stats(nodes: list, edges: list, thread_starter_id=None) -> dict:
    """グラフ統計を計算"""
    if not edges:
        return {"most_influential": None, "strongest_rivalry": None, "opinion_changers": []}

    # 影響力: to として最も多く参照されるエージェント（スレ主は除外）
    influence_count = {}
    for e in edges:
        to_id = e["to"]
        if to_id == thread_starter_id:
            continue
        influence_count[to_id] = influence_count.get(to_id, 0) + 1

    most_influential = max(influence_count.items(), key=lambda x: x[1])[0] if influence_count else None

    # 最も激しい対立
    disagree_pairs = {}
    for e in edges:
        if e.get("label") == "disagree":
            pair = tuple(sorted([e["from"], e["to"]]))
            disagree_pairs[pair] = disagree_pairs.get(pair, 0) + e.get("value", 1)

    strongest_rivalry = None
    if disagree_pairs:
        pair = max(disagree_pairs.items(), key=lambda x: x[1])
        strongest_rivalry = {"agents": list(pair[0]), "intensity": pair[1]}

    return {
        "most_influential": most_influential,
        "strongest_rivalry": strongest_rivalry,
    }
