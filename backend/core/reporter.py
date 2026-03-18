"""
41chan Reporter
Thread log + agent memories -> analysis report generation.
2-stage generation: Step1=structured data (JSON), Step2=detailed analysis (text)
"""

import json
import re
from typing import List, Dict, Any
from .llm_client import OracleLLMClient
from .profile_generator import OracleAgent

# --- Step 1: Structured data ---
STEP1_SYSTEM = """You are an expert analyst of imageboard simulation discussions. Reply in JSON format only. All text must be in English."""

STEP1_USER = """Analyze the following imageboard thread log.

[Topic] {question}
[Theme] {theme}
[Agents] {agent_list}

[Thread Log Excerpt]
{thread_log_excerpt}

Return the following JSON:
{{
  "summary": "conclusion/summary (200-300 chars)",
  "confidence": 0.0-1.0,
  "key_findings": ["finding 1", "finding 2", "finding 3"],
  "agent_positions": {{"name": "pro/con/neutral/skeptical — reason"}},
  "turning_points": ["turning point 1", "turning point 2"],
  "consensus": "high/medium/low — explanation",
  "minority_views": ["minority view 1"],
  "prediction": "prediction (under 100 chars)",
  "consensus_score": 0.0-1.0
}}"""

# --- Step 2: Detailed analysis ---
STEP2_SYSTEM = """You are the chronicler of a virtual parallel-world simulator.
Write a future prediction report as if you are documenting "events that actually happened" inside the simulation space.
Writing principles:
- Use "was formed", "became visible", "emerged" etc. instead of "was discussed"
- Cite anon posts as [>>post_number@board_name] embedded as evidence
- Write in past tense / chronicle style, avoid present tense / analytical tone
- Maintain the immersion that "in this timeline, X happened" throughout"""

STEP2_USER = """Based on the following imageboard thread log, write a virtual parallel-world prediction report in English.

[Simulation Topic] {question}
[World Theme] {theme}
[Observation Period Summary] {summary}
[Timeline] Parallel world {time_horizon} from now

[Thread Log]
{thread_log_excerpt}

Write a ~2000 word report with the following structure (no JSON, text only):

01
{section1_title}
(How phenomena fitting the theme — utilitarian adaptation, workarounds, social pressure, unexpected solidarity — unfolded in this timeline. Embed 3-5 post citations [>>N@board_name])

02
{section2_title}
(The process by which conflicts, friction, and discontent became visible, and the structural changes they produced. 2-3 citations)

03
{section3_title}
(Implications for the future and structural problems revealed by this timeline. 1-2 citations)

Section titles should be set freely to match the topic and theme."""


def _calc_stance_distribution(agents: List[OracleAgent], agent_positions: Dict[str, str]) -> Dict[str, int]:
    """Count stance distribution across agents"""
    dist = {"pro": 0, "con": 0, "neutral": 0, "skeptical": 0}
    for a in agents:
        pos_text = agent_positions.get(a.name, "")
        stance_val = a.stance.get("position", "")
        combined = f"{pos_text} {stance_val}".lower()
        if "pro" in combined or "support" in combined or "for" in combined:
            dist["pro"] += 1
        elif "con" in combined or "against" in combined or "oppose" in combined:
            dist["con"] += 1
        elif "skeptic" in combined or "doubt" in combined or "question" in combined:
            dist["skeptical"] += 1
        else:
            dist["neutral"] += 1
    return dist


def _calc_activity_by_round(project_id: str) -> List[int]:
    """Get post count per round from DB"""
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


def _select_representative_posts(thread_log: str, max_posts: int = 50) -> str:
    """Select representative posts (prioritize emotion!=neutral, then anchor replies, fill with normal)"""
    lines = thread_log.strip().split("\n")

    # Parse post blocks (simple: lines starting with digit are new posts)
    posts = []
    current_post = []
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 2 and stripped[0].isdigit() and ": " in stripped[:10]:
            if current_post:
                posts.append("\n".join(current_post))
            current_post = [line]
        elif stripped.startswith("━━━━"):
            if current_post:
                posts.append("\n".join(current_post))
                current_post = []
            posts.append(line)  # Keep header lines as-is
        else:
            current_post.append(line)
    if current_post:
        posts.append("\n".join(current_post))

    if len(posts) <= max_posts:
        return thread_log

    # Classify: header lines, emotional posts, anchored posts, normal posts
    headers = []
    emotional = []
    anchored = []
    normal = []
    for post in posts:
        if post.strip().startswith("━━━━") or not any(c.isdigit() for c in post[:5]):
            headers.append(post)
        elif any(em in post for em in ["excited", "angry", "thoughtful", "dismissive", "amused"]):
            emotional.append(post)
        elif ">>" in post:
            anchored.append(post)
        else:
            normal.append(post)

    # Select: headers + emotional first + anchored + normal up to 50 posts
    selected = headers[:]
    remaining = max_posts - len(selected)
    for pool in [emotional, anchored, normal]:
        if remaining <= 0:
            break
        take = min(len(pool), remaining)
        selected.extend(pool[:take])
        remaining -= take

    return "\n".join(selected)


def generate_report(
    project_id: str,
    thread_log: str,
    agents: List[OracleAgent],
    question: str,
    theme: str,
    llm: OracleLLMClient,
    cooldown_sec: float = 10.0,
    time_horizon: str = "3 months",
) -> Dict[str, Any]:
    """Generate report in 2 stages"""
    # ZAI backend: no cooldown needed (only Ollama needs it)
    effective_cooldown = 0.0 if llm.backend == "zai" else cooldown_sec
    if effective_cooldown > 0:
        import time as _t
        print(f"[Reporter] Ollama cooldown wait {effective_cooldown:.0f}s...", flush=True)
        _t.sleep(effective_cooldown)

    # Select representative posts (max 50) to reduce context size
    thread_log_selected = _select_representative_posts(thread_log, max_posts=50)

    # Log excerpt
    max_log_chars = 6000
    if len(thread_log_selected) > max_log_chars:
        half = max_log_chars // 2
        thread_log_excerpt = thread_log_selected[:half] + "\n\n... [truncated] ...\n\n" + thread_log_selected[-half:]
    else:
        thread_log_excerpt = thread_log_selected

    agent_list = ", ".join([f"{a.name}({a.tone_style})" for a in agents])

    # --- Step 1: Structured data ---
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
        print(f"[Reporter] Step1 success: confidence={result.get('confidence')}", flush=True)
    except Exception as e:
        print(f"[Reporter] Step1 failed: {e}", flush=True)
        result = _fallback_step1(agents, question, theme)

    # --- Step 2: Detailed analysis ---
    summary = result.get("summary", "")
    step2_messages = [
        {"role": "system", "content": STEP2_SYSTEM},
        {"role": "user", "content": STEP2_USER.format(
            question=question, theme=theme,
            summary=summary,
            thread_log_excerpt=thread_log_excerpt,
            time_horizon=time_horizon,
            section1_title="(Choose a title freely)",
            section2_title="(Choose a title freely)",
            section3_title="(Choose a title freely)",
        )},
    ]

    try:
        details = llm.chat(step2_messages, temperature=0.4, num_predict=4096)
        # Remove thinking tags
        details = re.sub(r"<think>[\s\S]*?</think>", "", details).strip()
        if "<think>" in details:
            details = re.sub(r"<think>[\s\S]*", "", details).strip()
        print(f"[Reporter] Step2 success: {len(details)} chars", flush=True)
        result["details"] = details
    except Exception as e:
        print(f"[Reporter] Step2 failed: {e}", flush=True)
        result.setdefault("details", f"A simulation on the theme '{theme}' was conducted with {len(agents)} agents.")

    # --- DB computed fields ---
    agent_positions = result.get("agent_positions", {})
    if not isinstance(agent_positions, dict):
        agent_positions = {}

    result["stance_distribution"] = _calc_stance_distribution(agents, agent_positions)
    result["activity_by_round"] = _calc_activity_by_round(project_id)

    # Set defaults
    result.setdefault("summary", f"Simulation results for '{question}'. {len(agents)} agents participated.")
    result.setdefault("confidence", 0.5)
    result.setdefault("key_findings", [])
    result.setdefault("agent_positions", {})
    result.setdefault("turning_points", [])
    result.setdefault("consensus", "unknown")
    result.setdefault("minority_views", [])
    result.setdefault("prediction", "")
    result.setdefault("consensus_score", float(result.get("confidence", 0.5)))

    return result


def _fallback_step1(agents, question, theme):
    """Fallback when LLM fails"""
    positions = {}
    for a in agents:
        pos = a.stance.get("position", "neutral")
        positions[a.name] = pos
    return {
        "summary": f"Simulation results for '{question}'. {len(agents)} agents participated.",
        "details": f"A simulation on the theme '{theme}' was conducted with {len(agents)} agents.",
        "confidence": 0.4,
        "key_findings": [f"Agent count: {len(agents)}"],
        "agent_positions": positions,
        "turning_points": [],
        "consensus": "unknown",
        "minority_views": [],
        "prediction": "Report generation failed. Please refer to the thread log directly.",
    }


def format_report_markdown(
    report: Dict[str, Any],
    theme: str,
    question: str,
) -> str:
    """Format report as Markdown (for vault storage)"""
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

    return f"""# 41chan Simulation Report

## Theme
{theme}

## Topic
{question}

**Confidence**: {report['confidence']:.0%}

## Summary
{report['summary']}

## Detailed Analysis
{report['details']}

## Key Findings
{key_findings}

## Agent Positions
{agent_positions}

## Discussion Turning Points
{turning_points}

## Consensus Formation
{report.get('consensus', 'unknown')}

## Minority Views
{minority_views}

## Prediction
{report.get('prediction', '')}
"""
