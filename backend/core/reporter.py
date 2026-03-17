"""
Oracle レポーター
スレッドログ + エージェント記憶 → 分析レポート生成。
2段階生成: Step1=構造化データ(JSON), Step2=詳細分析(テキスト)
"""

import json
import re
from typing import List, Dict, Any
from .llm_client import OracleLLMClient
from .profile_generator import OracleAgent

# --- Step 1: 構造化データ ---
STEP1_SYSTEM = """掲示板シミュレーション分析の専門家。JSON形式のみで回答する。"""

STEP1_USER = """以下の掲示板ログを分析してください。

【議題】{question}
【テーマ】{theme}
【エージェント】{agent_list}

【ログ抜粋】
{thread_log_excerpt}

以下のJSONで返してください:
{{
  "summary": "結論・要旨（200-300字）",
  "confidence": 0.0-1.0,
  "key_findings": ["発見1", "発見2", "発見3"],
  "agent_positions": {{"名前": "賛成/反対/中立/懐疑 — 理由"}},
  "turning_points": ["転換点1", "転換点2"],
  "consensus": "高/中/低 — 説明",
  "minority_views": ["少数意見1"],
  "prediction": "予測（100字以内）",
  "consensus_score": 0.0-1.0
}}"""

# --- Step 2: 詳細分析 ---
STEP2_SYSTEM = """あなたはバーチャル並行世界シミュレーターの記録官です。
シミュレーション空間内で「実際に起きた出来事」として、未来予測レポートを執筆してください。
書き方の原則:
- 「〜が議論された」ではなく「〜が形成された」「〜が可視化された」「〜が生まれた」等、出来事として描写
- 住民の発言を [>>投稿番号@板名] 形式で引用し、証拠として埋め込む
- 現在形・分析口調を避け、過去形・記録口調で書く
- 全体を通じて「この世界線では〜が起きた」という臨場感を維持する"""

STEP2_USER = """以下の掲示板ログをもとに、バーチャル並行世界の予測レポートを日本語で執筆してください。

【シミュレーション議題】{question}
【世界テーマ】{theme}
【観測期間の要旨】{summary}
【時間軸】{time_horizon}後の並行世界

【掲示板ログ】
{thread_log_excerpt}

以下の構成で2000字程度のレポートを書いてください（JSON不要、テキストのみ）:

01
{section1_title}
（この世界線で「功利主義的適応」「抜け道」「同調圧力」「予期せぬ連帯」など、テーマに合った現象がどう展開したか。発言引用 [>>N@板名] を3〜5個埋め込む）

02
{section2_title}
（対立・軋轢・不満が可視化されたプロセスと、それが生んだ構造変化。引用2〜3個）

03
{section3_title}
（この世界線が示す未来への示唆・構造的な問題点。引用1〜2個）

セクションタイトルは議題・テーマに合わせて自由に設定してください。"""


def _calc_stance_distribution(agents: List[OracleAgent], agent_positions: Dict[str, str]) -> Dict[str, int]:
    """エージェントの立場分布をカウント"""
    dist = {"賛成": 0, "反対": 0, "中立": 0, "懐疑": 0}
    for a in agents:
        pos_text = agent_positions.get(a.name, "")
        stance_val = a.stance.get("position", "")
        combined = f"{pos_text} {stance_val}".lower()
        if "賛成" in combined or "推進" in combined:
            dist["賛成"] += 1
        elif "反対" in combined or "批判" in combined:
            dist["反対"] += 1
        elif "懐疑" in combined or "疑問" in combined:
            dist["懐疑"] += 1
        else:
            dist["中立"] += 1
    return dist


def _calc_activity_by_round(project_id: str) -> List[int]:
    """ラウンドごとの投稿数をDBから取得"""
    try:
        from db.database import db_conn
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT round_num, COUNT(*) as cnt FROM posts WHERE simulation_id=? GROUP BY round_num ORDER BY round_num",
                (project_id,)
            ).fetchall()
        return [r["cnt"] for r in rows] if rows else []
    except Exception:
        return []


def generate_report(
    project_id: str,
    thread_log: str,
    agents: List[OracleAgent],
    question: str,
    theme: str,
    llm: OracleLLMClient,
    cooldown_sec: float = 10.0,
    time_horizon: str = "3ヶ月",
) -> Dict[str, Any]:
    """2段階でレポート生成"""
    # 並列スレッド処理直後にOllamaが高負荷な場合があるため冷却待機
    if cooldown_sec > 0:
        import time as _t
        print(f"[Reporter] Ollama冷却待機 {cooldown_sec:.0f}秒...", flush=True)
        _t.sleep(cooldown_sec)
    # ログ要約
    max_log_chars = 6000
    if len(thread_log) > max_log_chars:
        half = max_log_chars // 2
        thread_log_excerpt = thread_log[:half] + "\n\n... [中略] ...\n\n" + thread_log[-half:]
    else:
        thread_log_excerpt = thread_log

    agent_list = ", ".join([f"{a.name}({a.tone_style})" for a in agents])

    # --- Step 1: 構造化データ ---
    step1_messages = [
        {"role": "system", "content": STEP1_SYSTEM},
        {"role": "user", "content": STEP1_USER.format(
            question=question, theme=theme,
            agent_list=agent_list,
            thread_log_excerpt=thread_log_excerpt,
        )},
    ]

    result = {}
    try:
        result = llm.chat_json(step1_messages, temperature=0.3, num_predict=4096)
        print(f"[Reporter] Step1 成功: confidence={result.get('confidence')}", flush=True)
    except Exception as e:
        print(f"[Reporter] Step1 失敗: {e}", flush=True)
        result = _fallback_step1(agents, question, theme)

    # --- Step 2: 詳細分析 ---
    summary = result.get("summary", "")
    step2_messages = [
        {"role": "system", "content": STEP2_SYSTEM},
        {"role": "user", "content": STEP2_USER.format(
            question=question, theme=theme,
            summary=summary,
            thread_log_excerpt=thread_log_excerpt,
            time_horizon=time_horizon,
            section1_title="（タイトルを自由に決めてください）",
            section2_title="（タイトルを自由に決めてください）",
            section3_title="（タイトルを自由に決めてください）",
        )},
    ]

    try:
        details = llm.chat(step2_messages, temperature=0.4, num_predict=4096)
        # thinkingタグ除去
        details = re.sub(r"<think>[\s\S]*?</think>", "", details).strip()
        if "<think>" in details:
            details = re.sub(r"<think>[\s\S]*", "", details).strip()
        print(f"[Reporter] Step2 成功: {len(details)}字", flush=True)
        result["details"] = details
    except Exception as e:
        print(f"[Reporter] Step2 失敗: {e}", flush=True)
        result.setdefault("details", f"テーマ「{theme}」について{len(agents)}エージェントによる掲示板シミュレーションを実施しました。")

    # --- DB計算フィールド ---
    agent_positions = result.get("agent_positions", {})
    if not isinstance(agent_positions, dict):
        agent_positions = {}

    result["stance_distribution"] = _calc_stance_distribution(agents, agent_positions)
    result["activity_by_round"] = _calc_activity_by_round(project_id)

    # デフォルト補完
    result.setdefault("summary", f"「{question}」に関するシミュレーション結果。{len(agents)}エージェントが議論に参加。")
    result.setdefault("confidence", 0.5)
    result.setdefault("key_findings", [])
    result.setdefault("agent_positions", {})
    result.setdefault("turning_points", [])
    result.setdefault("consensus", "不明")
    result.setdefault("minority_views", [])
    result.setdefault("prediction", "")
    result.setdefault("consensus_score", float(result.get("confidence", 0.5)))

    return result


def _fallback_step1(agents, question, theme):
    """LLM失敗時のフォールバック"""
    positions = {}
    for a in agents:
        pos = a.stance.get("position", "中立")
        positions[a.name] = pos
    return {
        "summary": f"「{question}」に関するシミュレーション結果。{len(agents)}エージェントが議論に参加しました。",
        "details": f"テーマ「{theme}」について{len(agents)}エージェントによる掲示板シミュレーションを実施しました。",
        "confidence": 0.4,
        "key_findings": [f"エージェント数: {len(agents)}"],
        "agent_positions": positions,
        "turning_points": [],
        "consensus": "不明",
        "minority_views": [],
        "prediction": "レポート生成に失敗しました。スレッドログを直接参照してください。",
    }


def format_report_markdown(
    report: Dict[str, Any],
    theme: str,
    question: str,
) -> str:
    """レポートをMarkdown形式に整形（vault保存用）"""
    agent_positions = "\n".join(
        f"- **{name}**: {pos}"
        for name, pos in report.get("agent_positions", {}).items()
    )
    key_findings = "\n".join(
        f"- {f}" for f in report.get("key_findings", [])
    )
    turning_points = "\n".join(
        f"- {t}" for t in report.get("turning_points", [])
    )
    minority_views = "\n".join(
        f"- {v}" for v in report.get("minority_views", [])
    )

    return f"""# Oracle シミュレーションレポート

## テーマ
{theme}

## 議題
{question}

**確信度**: {report['confidence']:.0%}

## 結論・要旨
{report['summary']}

## 詳細分析
{report['details']}

## 主要な発見
{key_findings}

## エージェントの立場
{agent_positions}

## 議論の転換点
{turning_points}

## 合意形成
{report.get('consensus', '不明')}

## 少数意見
{minority_views}

## 予測
{report.get('prediction', '')}
"""
