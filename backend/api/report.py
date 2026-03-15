"""
レポート API
GET /api/simulation/{id}/report
GET /api/simulation/{id}/report/download
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from db.database import get_report, get_simulation, db_conn

router = APIRouter()


def _get_report_extra(sim_id: str, report: dict):
    """レポートに付加するメタ情報をDBから収集する"""
    # ボード一覧
    boards = []
    posts_index = {}
    stance_distribution = {}
    activity_by_round = []

    try:
        with db_conn() as conn:
            # ボード情報
            board_rows = conn.execute(
                "SELECT id, name FROM boards WHERE simulation_id=?", (sim_id,)
            ).fetchall()
            boards = [{"id": r["id"], "name": r["name"]} for r in board_rows]

            # posts_index: board_name:post_num → {board_id, thread_id, board_name}
            post_rows = conn.execute(
                """SELECT p.post_num, p.board_id, p.thread_id, b.name as board_name
                   FROM posts p
                   JOIN boards b ON b.id = p.board_id
                   WHERE p.simulation_id=?
                   ORDER BY p.created_at""",
                (sim_id,),
            ).fetchall()
            for row in post_rows:
                key = f"{row['board_name']}:{row['post_num']}"
                if key not in posts_index:
                    posts_index[key] = {
                        "board_id": row["board_id"],
                        "thread_id": row["thread_id"],
                        "board_name": row["board_name"],
                        "post_num": row["post_num"],
                    }

            # エージェント立場分布 (DBから直接集計)
            agent_rows = conn.execute(
                "SELECT stance FROM agents WHERE simulation_id=?", (sim_id,)
            ).fetchall()
            for row in agent_rows:
                try:
                    stance = json.loads(row["stance"] or "{}")
                    pos = stance.get("position", "中立")
                    matched = False
                    for category in ["賛成", "反対", "中立", "懐疑"]:
                        if category in pos:
                            stance_distribution[category] = stance_distribution.get(category, 0) + 1
                            matched = True
                            break
                    if not matched:
                        stance_distribution["中立"] = stance_distribution.get("中立", 0) + 1
                except Exception:
                    pass

            # ラウンドごとの投稿数
            round_rows = conn.execute(
                """SELECT round_num, COUNT(*) as count
                   FROM posts WHERE simulation_id=?
                   GROUP BY round_num ORDER BY round_num""",
                (sim_id,),
            ).fetchall()
            activity_by_round = [r["count"] for r in round_rows]
    except Exception as e:
        print(f"[report.py] 追加データ取得失敗: {e}")

    # LLMが生成した stance_distribution を優先。なければDB集計値を使用
    llm_stance = {}
    try:
        llm_stance = json.loads(report.get("stance_distribution", "{}") or "{}")
    except Exception:
        pass
    final_stance = llm_stance if llm_stance else stance_distribution

    # LLMが生成した activity_by_round を優先
    llm_activity = []
    try:
        llm_activity = json.loads(report.get("activity_by_round", "[]") or "[]")
    except Exception:
        pass
    final_activity = llm_activity if llm_activity else activity_by_round

    # consensus_score
    consensus_score = 0.5
    try:
        cs = report.get("consensus_score")
        if cs is not None:
            consensus_score = float(cs)
        else:
            consensus_score = float(report.get("confidence", 0.5))
    except Exception:
        pass

    return boards, posts_index, final_stance, final_activity, consensus_score


@router.get("/simulation/{sim_id}/report")
async def get_report_api(sim_id: str):
    """レポート取得"""
    report = get_report(sim_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # シミュレーションのテーマを取得
    sim = get_simulation(sim_id)
    sim_theme = sim.get("theme", "") if sim else ""

    # 追加メタ情報
    boards, posts_index, stance_distribution, activity_by_round, consensus_score = (
        _get_report_extra(sim_id, report)
    )

    return {
        "simulation_id": sim_id,
        "theme": sim_theme,
        "summary": report.get("summary", ""),
        "details": report.get("details", ""),
        "confidence": report.get("confidence", 0.5),
        "key_findings": json.loads(report.get("key_findings", "[]")),
        "agent_positions": json.loads(report.get("agent_positions", "{}")),
        "turning_points": json.loads(report.get("turning_points", "[]")),
        "consensus": report.get("consensus", ""),
        "minority_views": json.loads(report.get("minority_views", "[]")),
        "prediction": report.get("prediction", ""),
        "created_at": report.get("created_at", ""),
        # 追加フィールド
        "boards": boards,
        "posts_index": posts_index,
        "stance_distribution": stance_distribution,
        "activity_by_round": activity_by_round,
        "consensus_score": consensus_score,
    }


@router.get("/simulation/{sim_id}/report/download")
async def download_report(sim_id: str, format: str = "md"):
    """レポートをMarkdown形式でダウンロード"""
    report = get_report(sim_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    sim = get_simulation(sim_id)
    theme = sim.get("theme", "不明") if sim else "不明"

    key_findings = json.loads(report.get("key_findings", "[]"))
    agent_positions = json.loads(report.get("agent_positions", "{}"))
    turning_points = json.loads(report.get("turning_points", "[]"))
    minority_views = json.loads(report.get("minority_views", "[]"))

    md_lines = [
        f"# オラクルちゃんねる レポート",
        f"",
        f"**テーマ**: {theme}",
        f"**確信度**: {report.get('confidence', 0.5):.0%}",
        f"",
        f"## 要旨",
        report.get("summary", ""),
        f"",
        f"## 詳細分析",
        report.get("details", ""),
        f"",
        f"## 主要な発見",
    ]
    for kf in key_findings:
        md_lines.append(f"- {kf}")
    md_lines += [
        f"",
        f"## エージェントの立場",
    ]
    for name, pos in agent_positions.items():
        md_lines.append(f"- **{name}**: {pos}")
    md_lines += [
        f"",
        f"## 議論の転換点",
    ]
    for tp in turning_points:
        md_lines.append(f"- {tp}")
    md_lines += [
        f"",
        f"## 合意形成",
        report.get("consensus", ""),
        f"",
        f"## 少数意見",
    ]
    for mv in minority_views:
        md_lines.append(f"- {mv}")
    if report.get("prediction"):
        md_lines += [
            f"",
            f"## 予測",
            report.get("prediction", ""),
        ]

    content = "\n".join(md_lines)
    return PlainTextResponse(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{sim_id[:8]}.md"'},
    )
