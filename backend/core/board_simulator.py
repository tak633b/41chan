"""
41chan Board Simulator (4chan culture edition)
Thread-based simulation. Authentic 4chan board culture with shitposting, greentext, and imageboard lingo.
"""

import json
import re
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .profile_generator import OracleAgent, TONE_STYLES, POSTING_STYLES
from .memory_manager import MemoryManager
from .llm_client import OracleLLMClient
from db.database import get_agent_past_posts


def _extract_persona_sections(persona: str, sections: list) -> str:
    """Extract specified sections from [tag]-format persona, return / separated"""
    result = []
    for section in sections:
        tag = f"[{section}]"
        if tag in persona:
            start = persona.index(tag) + len(tag)
            next_pipe = persona.find("|", start)
            end = next_pipe if next_pipe != -1 else len(persona)
            content = persona[start:end].strip()
            if content:
                result.append(f"{section}:{content}")
    return " / ".join(result) if result else persona[:150]

# Board format constants
BOARD_HEADER_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[{board_name}] {thread_title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Theme: {theme}
Topic: {question}
"""

BATCH_ACTION_PROMPT_4CHAN = """[CRITICAL] You MUST write ONLY in English. Any response containing Japanese, Chinese, or other non-English text is a failure. ALL posts must be in English only.

You are NOT a polite assistant. You are an anon on 4chan.

[Board] {board_name}
[Thread Title] {thread_title}
[Theme] {theme}
[Topic/Question] {question}
[Round] {round_num}

[Recent Posts (last {history_count})]
{recent_posts}

[Participating Anons]
{agents_info}

━━━━ ABSOLUTE RULES ━━━━
■ Tone: No politeness. Casual, blunt, shitposting tone only.
■ Post length enforcement:
  - 1-2 line ultra-short posts ("kek", "based", "lmao", "cope", "seethe", "who asked"): 60%+
  - 2-3 line normal replies: ~30%
  - Long posts (3+ lines): max 10%. Must start with "long post incoming" or ">tfw"
■ Use >>N anchor replies to specifically quote/react to prior posts
■ Mix: agreement, shitposting, counterarguments, sarcasm, and ignoring
■ 4chan lingo: kek, based, cringe, cope, seethe, anon, anons, lmao, lol, ngl, tbh, kekked, ngmi, wagmi, fren, OP, checked, trips, dubs
■ Use greentext (>text) for reactions and storytelling
■ English only. No Japanese. No Chinese.
■ Don't post just "kek based lmao" with no substance — say something about the topic.
■ Every anon posts different content. No repeated phrases.
■ Vary opening lines: never start two consecutive posts the same way.

{first_round_hint}
Generate {post_count_target} posts now.
Select appropriate anons from the list (same anon can post multiple times).

Output ONLY the following JSON array (no code blocks, no explanations):

[
  {{
    "agent_name": "anon name (from the list above)",
    "username": "Anonymous@{board_name}",
    "content": "post content (casual, no politeness)",
    "anchor_to": null,
    "emotion": "neutral",
    "round_num": {round_num}
  }}
]

anchor_to is the post number being replied to (integer, e.g. 3) or null.
emotion is one of: neutral/excited/angry/thoughtful/dismissive/amused

[Greentext usage]
Use >text for:
- Storytelling: >be me >do thing >mfw
- Reactions: >he actually thinks X
- Irony: >implying X
- Disagreement with prior post content
Only use when it fits the post naturally."""


# Style-specific instructions per posting style (must reference topic)
STYLE_INSTRUCTIONS = {
    "info_provider": "Give specific numbers, examples, or news about the topic. 3-6 lines.",
    "debater":       "Point out a specific weakness, oversight, or counterexample to >>N's argument. Start from a completely different angle each time. 1-3 lines.",
    "joker":         "Make fun of the topic or use an analogy. Don't give a straight answer.",
    "questioner":    "Ask a simple genuine question about the topic.",
    "veteran":       "Share your experienced opinion on the topic condescendingly. Based on experience.",
    "passerby":      "One-line gut reaction to the topic. Then disappear.",
    "emotional":     "Emotional reaction to the topic. Must reference the actual content. Short but specific.",
    "storyteller":   "Share a personal story related to the topic. Specific episode. Medium length.",
    "agreeer":       "Agree with a specific part of the prior post. Quote what you agree with.",
    "contrarian":    "Take the opposite side from the majority. With specific reasoning.",
}

# Emotion-based reactions (4chan style)
AA_BY_EMOTION = {
    "excited": [
        "HOLY SHIT",
        "LET'S FUCKING GO",
        "BASED",
        "THIS IS THE GREATEST THING EVER",
        ">mfw this actually happened",
    ],
    "angry": [
        "FUCK YOU",
        "ABSOLUTE GARBAGE",
        ">seething rn",
        "I HATE THIS SO MUCH",
        "kys fr",
    ],
    "amused": [
        "kek",
        "lmaooo",
        "KEK",
        ">he actually thought",
        "I'm dead",
    ],
    "dismissive": [
        "cope",
        "seethe",
        "who asked",
        "don't care didn't ask",
        ">implying anyone cares",
    ],
    "thoughtful": [
        "hmm",
        "ngl this makes me think",
        ">tfw actually considering this",
        "wait...",
    ],
    "neutral": [
        "ok",
        "sure",
        "whatever",
        ">be me\n>reading this thread",
    ],
}

# General/situation-dependent reactions
AA_GENERAL = [
    "kek", "lmao", "based", "cringe", "cope", "seethe",
    ">he actually believes this",
    ">mfw reading OP's post",
    ">tfw no argument",
    "not gonna make it",
    "we're so back",
]

def _ngram_jaccard(a: str, b: str, n: int = 3) -> float:
    """Compute Jaccard similarity of character n-grams (0.0-1.0)"""
    if not a or not b:
        return 0.0
    set_a = {a[i:i+n] for i in range(len(a) - n + 1)}
    set_b = {b[i:i+n] for i in range(len(b) - n + 1)}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _is_too_similar(content: str, candidates: List[str], threshold: float = 0.35) -> bool:
    """Return True if content is >= threshold similar to any candidate post"""
    for past in candidates:
        if _ngram_jaccard(content, past) >= threshold:
            return True
    return False


def _similarity_score(content: str, candidates: List[str]) -> float:
    """Return max similarity score against past posts"""
    if not candidates:
        return 0.0
    return max(_ngram_jaccard(content, past) for past in candidates)


def _maybe_aa(emotion: str, posting_style: str) -> str:
    """Insert reaction text only for joker/emotional/agreeer styles (30% chance)"""
    if posting_style not in ("joker", "emotional", "agreeer"):
        return ""
    if random.random() > 0.30:
        return ""
    candidates = AA_BY_EMOTION.get(emotion, []) + (AA_GENERAL if random.random() > 0.5 else [])
    return random.choice(candidates) if candidates else ""


# Anchor rate hint based on style
def _anchor_hint(anchor_rate: float) -> str:
    if anchor_rate >= 0.5:
        return "Reply to prior posts with >>N as much as possible."
    elif anchor_rate >= 0.3:
        return "Use >>N replies when appropriate."
    else:
        return ">>N replies are optional."


# Single-post prompt (style-specific)
SINGLE_POST_PROMPT = """[Anonymous posting]
Stance: {stance_position} | Type: {style_label}
{style_instruction}

Board: {board_name} | Topic: {question}

[Thread so far]
{recent_posts}

{own_posts_hint}{extra_hint}■ ABSOLUTE RULES: English only. No Japanese. No politeness. Must reference the specific topic content. Write from a different angle than your past posts. Don't include real names in posts (anonymous board). Vary your opening line from last time (never repeat same opener). {anchor_hint}
■ Greentext (>text) only for joker/emotional/agreeer types, only when emotionally fitting, end of post (30% max). Skip if it doesn't fit.
JSON: {{"content":"post content (can end with fitting reaction)","anchor_to":number or null,"emotion":"neutral/excited/angry/amused/dismissive"}}"""


class BoardSimulator:
    """4chan culture imageboard simulator (thread-based)"""

    def __init__(
        self,
        agents: List[OracleAgent],
        entity_data: Dict[str, Any],
        question: str,
        memory_manager: MemoryManager,
        llm: OracleLLMClient,
        scale: str = "mini",
        custom_rounds: Optional[int] = None,
        board_name: str = "",
        thread_title: str = "",
        rounds_per_thread: Optional[int] = None,
        on_post_generated: Optional[Any] = None,
    ):
        self.agents = agents
        self.theme = entity_data.get("theme", "Discussion Topic")
        self.key_issues = entity_data.get("key_issues", [])
        self.question = question
        self.memory = memory_manager
        self.llm = llm
        self.scale = scale
        self.board_name = board_name or "random"
        self.thread_title = thread_title or self.theme

        # Round count priority:
        #   1. custom_rounds (user-specified) <- highest priority
        #   2. rounds_per_thread (parameter planner value)
        #   3. scale fixed value (mini=2, full=5, else=2)
        if custom_rounds is not None and custom_rounds >= 1:
            self.num_rounds = custom_rounds
        elif rounds_per_thread is not None:
            self.num_rounds = rounds_per_thread
        elif scale == "mini":
            self.num_rounds = 2
        elif scale == "full":
            self.num_rounds = 5
        else:
            self.num_rounds = 2

        self.on_post_generated = on_post_generated
        self.posts: List[Dict[str, Any]] = []
        self.post_counter = 0
        self._passerby_posted: set = set()  # track passerby agents who already posted

        # Pseudo-timestamps for posts
        self.base_time = datetime(2026, 3, 12, 9, 0, 0)
        self.time_offset = 0  # in minutes

        # Past simulation post cache (for similarity checking)
        # sim_id is injected externally by SimulationRunner. None = fetch from all sims
        self.sim_id: Optional[str] = None
        self._past_posts_cache: Dict[str, List[str]] = {}  # agent_name -> contents

    # ------------------------------------------------------------------
    # Past post cache & similarity checking
    # ------------------------------------------------------------------

    def _get_past_posts(self, agent_name: str) -> List[str]:
        """Get agent's past simulation posts with caching"""
        if agent_name not in self._past_posts_cache:
            try:
                self._past_posts_cache[agent_name] = get_agent_past_posts(
                    agent_name,
                    exclude_sim_id=self.sim_id or "",
                    limit=100,
                )
            except Exception:
                self._past_posts_cache[agent_name] = []
        return self._past_posts_cache[agent_name]

    def _get_current_sim_own_posts(self, agent_name: str) -> List[str]:
        """Return list of content strings posted by agent in current simulation"""
        return [p["content"] for p in self.posts if p.get("agent_name") == agent_name]

    def _check_and_maybe_regenerate(
        self,
        agent: OracleAgent,
        content: str,
        round_num: int,
        post_index: int,
        max_retry: int = 1,
        extra_candidates: Optional[List[str]] = None,
    ) -> str:
        """Regenerate post if too similar to past posts (max 1 retry)"""
        past_db = self._get_past_posts(agent.name)
        past_cur = self._get_current_sim_own_posts(agent.name)
        # Also check last 5 posts in thread (including other agents)
        recent_all = [p["content"] for p in self.posts[-5:]]
        # Include same-batch posts
        batch_posts = extra_candidates if extra_candidates else []
        all_past = past_db + past_cur + recent_all + batch_posts

        if not all_past:
            return content

        for attempt in range(max_retry):
            score = _similarity_score(content, all_past)
            if score < 0.45:
                break
            # Pass top 2 similar posts as feedback for regeneration
            similar_examples = sorted(
                all_past,
                key=lambda p: _ngram_jaccard(content, p),
                reverse=True,
            )[:2]
            forbidden_hint = "\n".join(f"- {s[:60]}" for s in similar_examples)
            print(f"  [SimilarityCheck] {agent.name} similarity detected score={score:.2f} (attempt {attempt+1}) — regenerating")
            regen = self._generate_single_post(
                agent, round_num, post_index,
                forbidden_snippets=forbidden_hint,
            )
            if regen:
                content = regen.get("content", content).strip()
            else:
                break

        return content

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _generate_thread_opener(self):
        """Generate >>1 OP post via template (no LLM call needed)"""
        content = (
            f"[{self.thread_title}]\n"
            f"Theme: {self.theme}\n\n"
            f"Discuss, anons."
        )

        post_time = self.base_time
        username = f"Anonymous@{self.board_name}"
        post = {
            "num": 1,
            "agent_name": "OP",
            "username": username,
            "content": content,
            "round_num": 0,
            "timestamp": post_time.strftime("%Y/%m/%d %H:%M"),
            "action_type": "post",
            "anchor_to": None,
            "emotion": "neutral",
        }
        self.posts.append(post)
        self.post_counter = 1
        print(f"[BoardSim] >>1 OP post generated")

        # Real-time emit callback
        if self.on_post_generated:
            self.on_post_generated(post)

    def run(self) -> str:
        """Run simulation and return board log string"""
        print(f"\n[BoardSim] Starting: {self.num_rounds} rounds, {len(self.agents)} anons")
        print(f"[BoardSim] Board: {self.board_name} | Thread: {self.thread_title}\n")

        # Pre-fetch past posts for all agents
        for agent in self.agents:
            self._get_past_posts(agent.name)

        # >>1: Generate OP post (template)
        self._generate_thread_opener()

        for round_num in range(self.num_rounds):
            print(f"[BoardSim] Round {round_num + 1}/{self.num_rounds}")
            self._process_batch(round_num)

        print(f"[BoardSim] Done: {self.post_counter} posts generated\n")

        # After sim: distill all agent experiences into long-term memory
        print(f"[BoardSim] Starting long-term memory distillation...", flush=True)
        for agent in self.agents:
            agent_posts = [p["content"] for p in self.posts if p.get("agent_name") == agent.name]
            if len(agent_posts) >= 2:
                try:
                    self.memory.distill_experience(
                        agent_id=agent.name,
                        sim_id=self.memory.project_id,
                        theme=self.theme,
                        all_posts=agent_posts,
                    )
                    print(f"[BoardSim] Long-term memory saved: {agent.name}", flush=True)
                except Exception as e:
                    print(f"[BoardSim] Long-term memory distillation failed {agent.name}: {e}", flush=True)

        return self._format_thread()

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def _build_posting_sequence(self, round_num: int, target_count: int) -> List[OracleAgent]:
        """Generate posting order using power-law distribution (style-frequency weighted)"""
        # frequency -> max posts per round
        MAX_PER_ROUND = {"once": 1, "low": 1, "medium": 2, "high": 4}
        # frequency -> weight (higher frequency = more likely to be selected)
        FREQ_WEIGHT = {"once": 1, "low": 1, "medium": 3, "high": 6}

        agent_counts: Dict[str, int] = {}
        sequence: List[OracleAgent] = []
        attempts = 0

        while len(sequence) < target_count and attempts < target_count * 4:
            attempts += 1
            candidates: List[OracleAgent] = []
            for agent in self.agents:
                p_style = getattr(agent, "posting_style", "emotional")
                freq = POSTING_STYLES.get(p_style, {}).get("frequency", "medium")
                # Passerby agents only post once per simulation
                if freq == "once" and agent.name in self._passerby_posted:
                    continue
                count = agent_counts.get(agent.name, 0)
                if count >= MAX_PER_ROUND.get(freq, 2):
                    continue
                w = FREQ_WEIGHT.get(freq, 3)
                candidates.extend([agent] * w)

            if not candidates:
                break

            # Prevent consecutive same-agent posts: prefer non-repeat candidates
            last_agent = sequence[-1] if sequence else None
            if last_agent is not None:
                non_repeat_candidates = [c for c in candidates if c.name != last_agent.name]
                # Use alternates if available; if everyone is same agent, allow repeat
                if non_repeat_candidates:
                    candidates = non_repeat_candidates

            agent = random.choice(candidates)
            sequence.append(agent)
            agent_counts[agent.name] = agent_counts.get(agent.name, 0) + 1

            p_style = getattr(agent, "posting_style", "emotional")
            freq = POSTING_STYLES.get(p_style, {}).get("frequency", "medium")
            if freq == "once":
                self._passerby_posted.add(agent.name)

            # Burst: debater anons double-post (40% chance)
            # Max 2 consecutive posts (no triple-posting)
            if freq == "high" and random.random() < 0.4:
                cur = agent_counts.get(agent.name, 0)
                # Don't burst if previous post was same agent
                prev = sequence[-2] if len(sequence) >= 2 else None
                already_consecutive = (prev is not None and prev.name == agent.name)
                if cur < MAX_PER_ROUND.get("high", 4) and len(sequence) < target_count and not already_consecutive:
                    sequence.append(agent)
                    agent_counts[agent.name] = cur + 1

        return sequence[:target_count]

    # Batch size constant (posts per LLM call)
    BATCH_SIZE = 4

    def _process_batch(self, round_num: int):
        """Determine posting order by style frequency and generate in batches (BATCH_SIZE at a time)"""
        if self.scale == "mini":
            post_count_target = random.randint(6, 8)
        else:
            post_count_target = random.randint(12, 15)

        posting_agents = self._build_posting_sequence(round_num, post_count_target)

        i = 0
        while i < len(posting_agents):
            # Generate BATCH_SIZE posts at a time
            batch_end = min(i + self.BATCH_SIZE, len(posting_agents))
            batch_agents = posting_agents[i:batch_end]

            batch_results = self._generate_batch_posts(batch_agents, round_num, i)

            for j, post_data in enumerate(batch_results):
                if post_data is None:
                    continue

                agent_name = post_data.get("agent_name", "")
                # Find agent from batch results
                agent = None
                for a in batch_agents:
                    if a.name == agent_name:
                        agent = a
                        break
                if agent is None and j < len(batch_agents):
                    agent = batch_agents[j]

                content = post_data.get("content", "").strip()
                # LLM sometimes outputs >>N at the start (duplicate of anchor_to) — strip it
                content = re.sub(r'^>>\d+\s*', '', content).strip()
                if not content:
                    continue

                self.post_counter += 1
                self.time_offset += random.randint(2, 15)
                post_time = self.base_time + timedelta(minutes=self.time_offset)

                username = f"Anonymous@{self.board_name}"

                anchor_to = post_data.get("anchor_to")
                if anchor_to is not None:
                    try:
                        anchor_to = int(anchor_to)
                        if anchor_to < 1 or anchor_to > self.post_counter - 1:
                            anchor_to = None
                    except (ValueError, TypeError):
                        anchor_to = None

                emotion = post_data.get("emotion", "neutral")

                post = {
                    "num": self.post_counter,
                    "agent_name": agent.name if agent else agent_name,
                    "username": username,
                    "round_num": round_num,
                    "timestamp": post_time.strftime("%Y/%m/%d %H:%M"),
                    "action_type": "post",
                    "anchor_to": anchor_to,
                    "content": content,
                    "emotion": emotion,
                }
                self.posts.append(post)

                # Real-time callback (call if defined)
                if self.on_post_generated:
                    self.on_post_generated(post)

                self.memory.store(
                    agent_id=agent.name if agent else agent_name,
                    round_num=round_num,
                    event_type="post",
                    content=f"Round {round_num+1}: [{self.thread_title}] {content[:120]}",
                    importance=0.7,
                    related_agents=[a.name for a in self.agents if (a.name != (agent.name if agent else agent_name))],
                )

                p_style = getattr(agent, "posting_style", "emotional") if agent else "emotional"
                style_label = POSTING_STYLES.get(p_style, {}).get("label", p_style)
                print(f"  [{agent.name if agent else agent_name}/{style_label}] {content[:60]}...")

            i = batch_end

    def _generate_batch_posts(self, agents_batch: List[OracleAgent], round_num: int, start_index: int) -> List[Dict[str, Any]]:
        """Generate posts for BATCH_SIZE anons in a single LLM call (each post different content)"""
        recent_posts = self._get_recent_posts(8)

        agent_specs = []
        for j, agent in enumerate(agents_batch):
            p_style = getattr(agent, "posting_style", "emotional")
            style_info = POSTING_STYLES.get(p_style, {})
            style_label = style_info.get("label", "anon")
            style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
            anchor_rate = style_info.get("anchor_rate", 0.3)
            stance_pos = agent.stance.get("position", "neutral") if isinstance(agent.stance, dict) else "neutral"
            speech_str = ", ".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
            tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
            # Use anonymous ID (not real name in spec_line)
            anon_id = f"Anon{j+1:02d}"
            spec_line = f"{j+1}. {anon_id} (internal ref only) | Stance:{stance_pos} | Type:{style_label} | {style_instruction}"
            if speech_str:
                spec_line += f" | Catchphrases:{speech_str}"
            if tactics_str:
                spec_line += f" | Debate tactic:{tactics_str}"
            agent_specs.append((agent.name, anon_id, spec_line))

        # agents_text uses anon IDs, not real names
        agents_text = "\n".join(spec_line for _, _, spec_line in agent_specs)
        # Real name -> anon_id mapping (for name restoration)
        name_to_anon = {name: anon_id for name, anon_id, _ in agent_specs}
        anon_to_name = {anon_id: name for name, anon_id, _ in agent_specs}

        # First reply after OP should start with >>1 reply
        extra_hint = ""
        if round_num == 0 and start_index == 0 and len(self.posts) == 1:
            extra_hint = "This is the first reply in the thread. Start with >>1 and acknowledge OP.\n"

        if len(agents_batch) == 1:
            agent = agents_batch[0]
            _, anon_id_single, spec_line_single = agent_specs[0]
            p_style = getattr(agent, "posting_style", "emotional")
            style_info = POSTING_STYLES.get(p_style, {})
            style_label = style_info.get("label", "anon")
            style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
            stance_pos = agent.stance.get("position", "neutral") if isinstance(agent.stance, dict) else "neutral"
            post_ctx = _extract_persona_sections(agent.persona, ["identity", "speech", "stance_detail", "tactics"])
            speech_str = ", ".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
            tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
            spec_line_full = f"1. {anon_id_single} | Stance:{stance_pos} | Type:{style_label} | {style_instruction}"
            if speech_str:
                spec_line_full += f" | Catchphrases:{speech_str}"
            if tactics_str:
                spec_line_full += f" | Debate tactic:{tactics_str}"
            spec_line_full += f"\nPersona: {post_ctx}"
            # Past posts for this agent (repetition prevention)
            own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
            if own_posts:
                own_snippets = [f"- {p['content'][:100]}" for p in own_posts[-5:]]
                own_posts_hint = f"\n[{anon_id_single}'s past posts (NEVER repeat same content/phrases. Write from a completely different angle)]\n" + "\n".join(own_snippets) + "\n"
            else:
                own_posts_hint = ""
            # MemoryManager recall (short-term memory within simulation)
            memory_hint = ""
            try:
                context_query = f"{self.question} {recent_posts[-200:]}"
                memories = self.memory.recall(agent.name, context_query, top_k=3, current_round=round_num)
                if memories:
                    mem_lines = "\n".join(f"- {m['content'][:120]}" for m in memories)
                    memory_hint = f"\n[{anon_id_single}'s long-term memory (past thoughts/feelings/realizations)]\n{mem_lines}\n"
            except Exception:
                pass
            # Long-term memory (cross-simulation)
            try:
                lt_memories = self.memory.recall_longterm(agent.name, context_query, top_k=2)
                if lt_memories:
                    lt_lines = "\n".join(f"- {m['content'][:150]}" for m in lt_memories)
                    memory_hint += f"\n[{anon_id_single}'s memories from past simulations]\n{lt_lines}\n"
            except Exception:
                pass
            intro_line = f"The following anon posts one reply.\n\n{spec_line_full}{own_posts_hint}{memory_hint}"
        else:
            # Multiple agents: include past post hints + long-term memory for each
            own_posts_hints = []
            for agent, (_, anon_id_m, _) in zip(agents_batch, agent_specs):
                own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
                hints = []
                if own_posts:
                    own_snippets = [f"  - {p['content'][:80]}" for p in own_posts[-5:]]
                    hints.append(f"[{anon_id_m}'s past posts (no repeats, write from different angle)]\n" + "\n".join(own_snippets))
                # MemoryManager recall (short-term)
                try:
                    context_query = f"{self.question} {recent_posts[-200:]}"
                    memories = self.memory.recall(agent.name, context_query, top_k=2, current_round=round_num)
                    if memories:
                        mem_lines = "\n".join(f"  - {m['content'][:100]}" for m in memories)
                        hints.append(f"[{anon_id_m}'s long-term memory]\n{mem_lines}")
                except Exception:
                    pass
                # Long-term memory (cross-simulation)
                try:
                    lt_memories = self.memory.recall_longterm(agent.name, context_query, top_k=1)
                    if lt_memories:
                        lt_lines = "\n".join(f"  - {m['content'][:100]}" for m in lt_memories)
                        hints.append(f"[{anon_id_m}'s past simulation memories]\n{lt_lines}")
                except Exception:
                    pass
                if hints:
                    own_posts_hints.append("\n".join(hints))
            own_hints_str = ("\n\n" + "\n".join(own_posts_hints)) if own_posts_hints else ""
            intro_line = f"The following {len(agents_batch)} anons each post one reply.\n\n{agents_text}{own_hints_str}"

        batch_prompt = f"""{intro_line}

Board: {self.board_name} | Topic: {self.question}
[Thread so far]
{recent_posts if recent_posts else "(no posts yet)"}

■ ABSOLUTE RULES:
- English only. No Japanese.
- No politeness. Casual anon tone only.
- Must reference something specific about "{self.question}".
- Don't just post "kek based lmao" — say something about the topic.
- No repeated phrases from your own past posts. Write from a completely different angle.
- Every anon posts different content. No shared phrases.
- Don't include real names or identifying info in post content. Anonymous board.
- Vary your opening line from last time. Never start two consecutive posts with the same word/phrase.
- IMPORTANT: Each post must have unique content/perspective/angle.

{extra_hint}Return as JSON array (name = anon ID only, don't include names in content):
[{{"name":"AnonID (from list above)","content":"post content (no names in content)","anchor_to":number or null,"emotion":"neutral/excited/angry/amused/dismissive"}}]"""

        messages = [
            {"role": "system", "content": "[CRITICAL] ALL output MUST be in English only. No Japanese. No Chinese. Post as an anonymous imageboard user. Return only JSON array. Never include real names in post content."},
            {"role": "user", "content": batch_prompt},
        ]

        try:
            raw = self.llm.chat(messages, temperature=0.9)
            match = re.search(r'\[[\s\S]*?\]', raw)
            if match:
                posts = json.loads(match.group())
                # Restore anon_id -> real name for agent_name field
                result = []
                for i, post_data in enumerate(posts[:len(agents_batch)]):
                    anon_name = post_data.get("name", "")
                    real_name = anon_to_name.get(anon_name)
                    if not real_name and i < len(agents_batch):
                        real_name = agents_batch[i].name
                    post_data["agent_name"] = real_name
                    result.append(post_data)
                return result
            else:
                raise ValueError("JSON array not found")
        except Exception as e:
            print(f"  [BatchPost] Batch generation failed: {e} — falling back to individual generation")
            # Fallback: generate one at a time
            results = []
            for j, agent in enumerate(agents_batch):
                post = self._generate_single_post(agent, round_num, start_index + j)
                if post:
                    results.append(post)
            return results

    def _generate_single_post(self, agent: OracleAgent, round_num: int, post_index: int, forbidden_snippets: str = "") -> Optional[Dict[str, Any]]:
        """Generate a single post for one agent (posting_style aware) — fallback"""
        recent_posts = self._get_recent_posts(8)

        p_style = getattr(agent, "posting_style", "emotional")
        style_info = POSTING_STYLES.get(p_style, {})
        style_label = style_info.get("label", "anon")
        style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
        anchor_rate = style_info.get("anchor_rate", 0.3)
        anchor_hint = _anchor_hint(anchor_rate)

        extra_hint = ""
        if round_num == 0 and post_index == 0 and len(self.posts) == 1:
            extra_hint = "This is the first reply in the thread. Start with >>1 and acknowledge OP.\n"

        # Get own past posts (for repetition prevention)
        own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
        own_posts_hint = ""
        if own_posts:
            own_snippets = [f"- {p['content'][:80]}" for p in own_posts[-5:]]
            own_posts_hint = f"[Your past posts (write something DIFFERENT from these)]\n" + "\n".join(own_snippets) + "\n\n"
        if forbidden_snippets:
            own_posts_hint += f"[Especially avoid content similar to these (regeneration)]\n{forbidden_snippets}\n\n"

        # MemoryManager recall (short-term memory within simulation)
        try:
            context_query = f"{self.question} {recent_posts[-200:]}"
            memories = self.memory.recall(agent.name, context_query, top_k=3, current_round=round_num)
            if memories:
                mem_lines = "\n".join(f"- {m['content'][:120]}" for m in memories)
                own_posts_hint += f"[Long-term memory (past thoughts/feelings/realizations)]\n{mem_lines}\n\n"
        except Exception:
            pass
        # Long-term memory (cross-simulation)
        try:
            lt_memories = self.memory.recall_longterm(agent.name, context_query, top_k=2)
            if lt_memories:
                lt_lines = "\n".join(f"- {m['content'][:150]}" for m in lt_memories)
                own_posts_hint += f"[Memories from past simulations]\n{lt_lines}\n\n"
        except Exception:
            pass

        reply_ctx = _extract_persona_sections(agent.persona, ["trigger", "tactics", "hidden", "wound"])
        speech_str = ", ".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
        tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
        extra_persona = ""
        if speech_str:
            extra_persona += f"Catchphrases:{speech_str} "
        if tactics_str:
            extra_persona += f"Debate tactic:{tactics_str} "
        if reply_ctx:
            extra_persona += f"Persona:{reply_ctx}"

        messages = [
            {
                "role": "system",
                "content": "[CRITICAL] ALL output MUST be in English only. No Japanese. No Chinese. Post as an anonymous imageboard user. Return only JSON.",
            },
            {
                "role": "user",
                "content": SINGLE_POST_PROMPT.format(
                    board_name=self.board_name,
                    question=self.question,
                    stance_position=agent.stance.get("position", "neutral") if isinstance(agent.stance, dict) else "neutral",
                    style_label=style_label,
                    style_instruction=style_instruction,
                    anchor_hint=anchor_hint,
                    recent_posts=recent_posts if recent_posts else "(no posts yet)",
                    extra_hint=extra_hint + (f"{extra_persona}\n" if extra_persona else ""),
                    own_posts_hint=own_posts_hint,
                ),
            },
        ]

        try:
            raw = self.llm.chat(messages, temperature=0.9)
            # Extract JSON
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", raw, flags=re.IGNORECASE)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                data = json.loads(match.group(0))
                data["agent_name"] = agent.name
                return data
            else:
                print(f"  [{agent.name}] JSON extraction failed: {raw[:100]}")
                return None
        except Exception as e:
            print(f"  [{agent.name}] Generation failed: {e}")
            return None

    # ------------------------------------------------------------------
    # JSON array parser
    # ------------------------------------------------------------------

    def _parse_posts_from_llm(self, content: str) -> List[Dict[str, Any]]:
        """Extract JSON array [{...}] from LLM response"""
        # Strip code blocks
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", content, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()

        # Extract [{...}] JSON array (from first [ to last ])
        match = re.search(r'\[[\s\S]*\]', cleaned)
        if not match:
            print(f"[BoardSim] JSON array not found. Response first 200 chars: {content[:200]}")
            return []

        json_str = match.group(0)
        try:
            posts = json.loads(json_str)
            if isinstance(posts, list):
                return posts
        except json.JSONDecodeError:
            # Remove control chars and retry
            json_str_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
            json_str_clean = re.sub(r"\s+", " ", json_str_clean)
            try:
                posts = json.loads(json_str_clean)
                if isinstance(posts, list):
                    return posts
            except json.JSONDecodeError as e:
                print(f"[BoardSim] JSON parse failed: {e}. First chars: {json_str[:200]}")

        return []

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _anon_id(agent_name: str) -> str:
        """Agent name -> 4chan-style anonymous ID (8 char alphanumeric)"""
        import hashlib
        h = int(hashlib.md5((agent_name + "41chan_salt").encode()).hexdigest(), 16)
        return format(h % (36 ** 8), "08x")  # e.g. 01hmgtde

    def _get_recent_posts(self, n: int) -> str:
        """Format last n posts as string (4chan format) — use anon IDs, not real names"""
        recent = self.posts[-n:] if len(self.posts) >= n else self.posts
        lines = []
        for p in recent:
            anchor = f" >>{p['anchor_to']}" if p.get("anchor_to") else ""
            anon = self._anon_id(p.get("agent_name", ""))
            lines.append(
                f">>{p['num']} {p['username']} (ID:{anon}){anchor}\n"
                f"  {p['content'][:120]}"
            )
        return "\n".join(lines)

    def _format_thread(self) -> str:
        """Format board log in 4chan style — use anon IDs, not real names"""
        lines = [
            BOARD_HEADER_TEMPLATE.format(
                board_name=self.board_name,
                thread_title=self.thread_title,
                theme=self.theme,
                question=self.question,
            )
        ]
        for p in self.posts:
            anchor_str = f"\n  >>{p['anchor_to']}" if p.get("anchor_to") else ""
            anon = self._anon_id(p.get("agent_name", ""))
            lines.append(
                f"\n{p['num']}: {p['username']} {p['timestamp']} ID:{anon}"
                f"{anchor_str}\n  {p['content']}"
            )
        lines.append(f"\n\n--- Total replies: {self.post_counter} ---")
        return "\n".join(lines)
