"""
Oracle パラメータプランナー
プロンプト/シード内容をLLMで分析し、シミュレーションの最適なパラメータを1回のLLM呼び出しで決定する。
"""

from typing import Any, Dict, List, Optional
from .llm_client import OracleLLMClient

PLANNER_SYSTEM = "5ch掲示板シミュレーションのプランナー。JSONのみ返せ。説明不要。"

PLANNER_USER_TEMPLATE = """テーマ: {prompt}
追加情報: {seed_text}

JSONで返せ:
{{"agent_count":8,"agent_roles":[{{"role":"教授","tone":"authority","stance":"推進派","count":2}}],"boards":[{{"name":"議論板","threads":["【議論】スレタイ","【質問】スレタイ"]}}],"rounds_per_thread":3,"total_estimated_posts":150,"reasoning":"理由"}}

条件:
- agent_count: 6-15
- tone: authority/worker/youth/outsider/lurker
- boards: 2-5板、スレ2-4本/板、5ch風スレタイ（【悲報】【朗報】等）
- rounds_per_thread: 2-8"""

VALID_TONES = {"authority", "worker", "youth", "outsider", "lurker"}


def plan_parameters(
    prompt: str,
    seed_text: str,
    llm: OracleLLMClient,
) -> Dict[str, Any]:
    """
    プロンプト/シードを分析してシミュレーションパラメータを決定する。

    LLM呼び出しは1回のみ（追加コスト最小限）。

    Returns:
        {
            "agent_count": int (6-15),
            "agent_roles": [{"role": str, "tone": str, "stance": str, "count": int}, ...],
            "boards": [{"name": str, "threads": [str, ...]}, ...],
            "rounds_per_thread": int (2-8),
            "total_estimated_posts": int (100-300),
            "reasoning": str,
        }
    """
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {
            "role": "user",
            "content": PLANNER_USER_TEMPLATE.format(
                prompt=prompt,
                seed_text=seed_text or "（なし）",
            ),
        },
    ]

    print("[ParameterPlanner] パラメータ決定中...", flush=True)
    result = llm.chat_json(messages, temperature=0.4)

    # バリデーション・クランプ
    result = _validate_and_clamp(result)

    print(
        f"[ParameterPlanner] 決定: エージェント{result['agent_count']}人, "
        f"{len(result['boards'])}板, "
        f"{result['rounds_per_thread']}ラウンド/スレッド",
        flush=True,
    )
    print(f"[ParameterPlanner] 理由: {result.get('reasoning', '')}", flush=True)

    return result


def _validate_and_clamp(result: Dict[str, Any]) -> Dict[str, Any]:
    """LLM応答のバリデーションとクランプ。範囲外は安全な値に収める。"""
    # --- agent_count: 6-15 ---
    agent_count = result.get("agent_count", 8)
    try:
        agent_count = int(agent_count)
    except (ValueError, TypeError):
        agent_count = 8
    agent_count = max(6, min(15, agent_count))
    result["agent_count"] = agent_count

    # --- agent_roles の検証 ---
    agent_roles: List[Dict[str, Any]] = result.get("agent_roles", [])
    if not isinstance(agent_roles, list) or len(agent_roles) == 0:
        agent_roles = [
            {"role": "参加者", "tone": "worker", "stance": "中立", "count": agent_count}
        ]

    # toneのバリデーションと count の整数化
    for r in agent_roles:
        if r.get("tone") not in VALID_TONES:
            r["tone"] = "worker"
        try:
            r["count"] = max(1, int(r.get("count", 1)))
        except (ValueError, TypeError):
            r["count"] = 1

    # agent_roles の合計を agent_count に一致させる
    total = sum(r["count"] for r in agent_roles)
    if total != agent_count:
        diff = agent_count - total
        if diff > 0:
            # 不足分を最後のロールに加算
            agent_roles[-1]["count"] += diff
        else:
            # 超過分を count が大きいロールから削る
            remaining = abs(diff)
            for r in sorted(agent_roles, key=lambda x: -x["count"]):
                cut = min(r["count"] - 1, remaining)
                r["count"] -= cut
                remaining -= cut
                if remaining <= 0:
                    break

    # count=0 のロールを除去
    agent_roles = [r for r in agent_roles if r.get("count", 0) > 0]
    result["agent_roles"] = agent_roles

    # --- boards: 2-5板 ---
    boards: List[Dict[str, Any]] = result.get("boards", [])
    if not isinstance(boards, list) or len(boards) == 0:
        boards = [
            {"name": "総合議論板", "threads": ["【議論】総合スレ", "【質問】なんでも聞くスレ"]},
            {"name": "雑談板", "threads": ["【雑談】何でも語るスレ"]},
        ]

    # 板数クランプ (2-5)
    boards = boards[:5]
    if len(boards) < 2:
        boards.append({"name": "雑談板", "threads": ["【雑談】何でも語るスレ"]})

    # スレッド数クランプ (2-4本/板)
    for b in boards:
        threads = b.get("threads", [])
        if not isinstance(threads, list) or len(threads) == 0:
            threads = [f"【{b.get('name', '板')}】総合スレ"]
        threads = threads[:4]
        if len(threads) < 2:
            threads.append(f"【{b.get('name', '板')}】雑談スレ")
        b["threads"] = threads

    result["boards"] = boards

    # --- rounds_per_thread: 2-8 ---
    rounds = result.get("rounds_per_thread", 3)
    try:
        rounds = int(rounds)
    except (ValueError, TypeError):
        rounds = 3
    result["rounds_per_thread"] = max(2, min(8, rounds))

    # --- total_estimated_posts: 100-300 ---
    total_posts = result.get("total_estimated_posts", 150)
    try:
        total_posts = int(total_posts)
    except (ValueError, TypeError):
        total_posts = 150
    result["total_estimated_posts"] = max(100, min(300, total_posts))

    # --- reasoning ---
    if "reasoning" not in result:
        result["reasoning"] = ""

    return result


def convert_planner_boards(planner_boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    パラメータプランナーの board 形式を simulation_runner / board_generator が
    期待する形式に変換する。

    Input:  [{"name": str, "threads": [str, ...]}, ...]
    Output: [{"name": str, "emoji": str, "description": str, "initial_threads": [str, ...]}, ...]
    """
    _EMOJI_MAP = {
        "雑談": "💬", "政策": "📋", "議論": "🗣️", "学生": "🎓", "教員": "📚",
        "経営": "💼", "技術": "🔧", "行政": "🏛️", "市民": "👥", "研究": "🔬",
        "情報": "📡", "経済": "💰", "法律": "⚖️", "医療": "🏥", "環境": "🌿",
    }

    result = []
    for b in planner_boards:
        name = b.get("name", "板")
        # 名前から絵文字を推定
        emoji = "💬"
        for kw, em in _EMOJI_MAP.items():
            if kw in name:
                emoji = em
                break
        result.append({
            "name": name,
            "emoji": emoji,
            "description": f"{name}での議論・情報交換",
            "initial_threads": b.get("threads", [f"【{name}】総合スレ"]),
        })
    return result
