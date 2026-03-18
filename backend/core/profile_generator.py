"""
41chan Profile Generator
Generates 2000-char personas in the MiroFish style.
5 tone types, distinguishes individual vs organization agents.
"""

import json
import random
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .llm_client import OracleLLMClient

MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

# ─── English name lists ───────────────────────────────────────────────
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Taylor",
    "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Green", "Adams", "Nelson", "Baker", "Hill", "Rivera", "Campbell",
    "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Collins",
    "Edwards", "Stewart", "Flores", "Morris", "Nguyen", "Murphy", "Rivera", "Cook", "Rogers", "Morgan",
    "Peterson", "Cooper", "Reed", "Bailey", "Bell", "Gonzalez", "Ward", "Cox", "Richardson", "Howard",
]
FIRST_NAMES_M = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Christopher", "Daniel", "Matthew", "Anthony", "Donald", "Mark", "Paul", "Steven", "Andrew", "Kenneth",
    "Joshua", "Kevin", "Brian", "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan",
    "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon",
    "Benjamin", "Samuel", "Raymond", "Gregory", "Patrick", "Frank", "Alexander", "Jack", "Dennis", "Jerry",
]
FIRST_NAMES_F = [
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan", "Jessica", "Sarah", "Karen",
    "Lisa", "Nancy", "Betty", "Margaret", "Sandra", "Ashley", "Dorothy", "Kimberly", "Emily", "Donna",
    "Michelle", "Carol", "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia",
    "Kathleen", "Amy", "Angela", "Shirley", "Anna", "Brenda", "Pamela", "Emma", "Nicole", "Helen",
    "Samantha", "Katherine", "Christine", "Debra", "Rachel", "Carolyn", "Janet", "Catherine", "Maria", "Heather",
]

# ─── Age ranges by tone type ─────────────────────────────────────────
AGE_RANGES = {
    "authority": (45, 65),
    "worker":    (30, 50),
    "youth":     (18, 28),
    "outsider":  (35, 55),
    "lurker":    (20, 70),
}

# ─── MBTI role × stance recommended mapping ────────────────────────────
MBTI_ROLE_MAP = {
    "authority": {
        "pro":       ["ENTJ", "ESTJ", "ENFJ"],
        "con":       ["ISTJ", "INTJ", "INFJ"],
        "neutral":   ["ESTJ", "ISFJ", "ENFJ"],
        "skeptical": ["INTJ", "INTP", "ISTJ"],
    },
    "worker": {
        "pro":       ["ESTP", "ESFJ", "ENFP"],
        "con":       ["ISFJ", "ISTJ", "ISTP"],
        "neutral":   ["ISFP", "ESFP", "ISFJ"],
        "skeptical": ["ISTP", "INTP", "INFP"],
    },
    "youth": {
        "pro":       ["ENFP", "ENTP", "ESFP"],
        "con":       ["INFP", "ISFP", "INTP"],
        "neutral":   ["ISFP", "INFP", "ESFP"],
        "skeptical": ["INTP", "ENTP", "INTJ"],
    },
    "outsider": {
        "pro":       ["ENTJ", "ESTJ", "ENTP"],
        "con":       ["ISTJ", "INTJ", "ISFJ"],
        "neutral":   ["ESTJ", "ESFJ", "ISTJ"],
        "skeptical": ["INTJ", "INTP", "ISTP"],
    },
    "lurker": {
        "pro":       ["INFJ", "INTJ", "INTP"],
        "con":       ["INFP", "INTP", "INTJ"],
        "neutral":   ["INFJ", "INFP", "INTP"],
        "skeptical": ["INTP", "INTJ", "ISTP"],
    },
}

# ─── MBTI guidance text (shared in prompts) ────────────────────────────
MBTI_GUIDANCE = """
How to pick MBTI:
- ENTJ/ESTJ: Leader type, goal-oriented, organizes others
- INTJ/INTP: Analytical, critical thinker, independent
- ENFP/ENTP: Creative, loves new ideas, enjoys debate
- ISFJ/ISTJ: Reliable, tradition-oriented, disciplined
- INFP/INFJ: Idealistic, value-driven, high empathy
- ESTP/ESFP: Action-oriented, practical, lives in the moment
- ISFP: Artistic, calm, goes at their own pace
- ESFJ: Sociable, helpful, harmony-focused
Choose MBTI that fits each agent's role, personality, and age.
No more than 2 agents with the same MBTI type.
"""

# ─── Age guidance text (shared in prompts) ────────────────────────────
AGE_GUIDANCE = """
Age guidelines (set according to role):
- authority: 45-65 (professors, managers tend to be older)
- worker: 30-50 (mid-career professionals)
- youth: 18-28 (students, young workers)
- outsider: 35-55 (corporate/government practitioners)
- lurker: 20-70 (wide range)
Don't make everyone the same age. At least 10+ years difference between agents.
"""


def _select_mbti(tone: str, stance: str) -> str:
    """Select a random MBTI suitable for the given tone type and stance"""
    candidates = MBTI_ROLE_MAP.get(tone, {}).get(stance, MBTI_TYPES)
    return random.choice(candidates)


def _deduplicate_mbti(llm_mbti: str, tone: str, existing_agents: list) -> str:
    """Ensure no more than 2 agents share the same MBTI"""
    used_mbtis = {}
    for a in existing_agents:
        used_mbtis[a.mbti] = used_mbtis.get(a.mbti, 0) + 1

    # Use the LLM-returned MBTI if it's not overused
    if llm_mbti in MBTI_TYPES and used_mbtis.get(llm_mbti, 0) < 2:
        return llm_mbti

    # Pick from unused MBTIs
    available = [m for m in MBTI_TYPES if used_mbtis.get(m, 0) == 0]
    if not available:
        available = [m for m in MBTI_TYPES if used_mbtis.get(m, 0) < 2]
    if available:
        return random.choice(available)
    return random.choice(MBTI_TYPES)


def _normalize_name(name: str) -> str:
    """Normalize name spacing"""
    return name.replace("  ", " ").strip()


def _generate_english_name(gender: str, used_names: Optional[set] = None) -> str:
    """Generate a random English name (with deduplication, no repeated last names)"""
    if used_names is None:
        used_names = set()
    first_pool = FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F

    # Collect already-used last names
    used_lasts = set()
    for n in used_names:
        parts = n.split(" ")
        if len(parts) >= 2:
            used_lasts.add(parts[-1])

    # Try to avoid duplicate last names
    available_lasts = [l for l in LAST_NAMES if l not in used_lasts]
    if not available_lasts:
        available_lasts = LAST_NAMES  # Reset if all used

    for _ in range(50):
        last = random.choice(available_lasts)
        first = random.choice(first_pool)
        name = f"{first} {last}"
        if name not in used_names:
            used_names.add(name)
            return name

    name = f"{random.choice(first_pool)} {random.choice(available_lasts)}"
    used_names.add(name)
    return name


# ─── Board posting styles (4chan anon types) ────────────────────────────────
POSTING_STYLES = {
    "info_provider": {
        "label": "Info Provider",
        "description": "Knowledgeable, cites sources, tends toward long posts. Informative tone.",
        "avg_length": "long",
        "anchor_rate": 0.3,
        "frequency": "medium",
        "weight": 0.10,
    },
    "debater": {
        "label": "Debater",
        "description": "Aggressive, loves to argue, 'ur wrong', 'cope', short rapid-fire posts",
        "avg_length": "short",
        "anchor_rate": 0.7,
        "frequency": "high",
        "weight": 0.08,
    },
    "joker": {
        "label": "Shitposter",
        "description": "Funny one-liners, irony, memes, heavy use of net slang (kek, lmao, based)",
        "avg_length": "short",
        "anchor_rate": 0.2,
        "frequency": "medium",
        "weight": 0.10,
    },
    "questioner": {
        "label": "Questioner",
        "description": "'Wait what?', 'Is this real?', naive genuine curiosity",
        "avg_length": "short",
        "anchor_rate": 0.4,
        "frequency": "low",
        "weight": 0.10,
    },
    "veteran": {
        "label": "Oldfag",
        "description": "'Lurk moar newfag', experience-based, condescending to newcomers",
        "avg_length": "medium",
        "anchor_rate": 0.3,
        "frequency": "medium",
        "weight": 0.05,
    },
    "passerby": {
        "label": "Passerby",
        "description": "Posts 1-2 times, gives opinion, leaves",
        "avg_length": "short",
        "anchor_rate": 0.1,
        "frequency": "once",
        "weight": 0.15,
    },
    "emotional": {
        "label": "Reactor",
        "description": "'kek', 'lmao', 'wtf', 'holy shit' — emotion-driven short posts",
        "avg_length": "very_short",
        "anchor_rate": 0.5,
        "frequency": "medium",
        "weight": 0.15,
    },
    "storyteller": {
        "label": "Storyteller",
        "description": "'greentext story time', 'this happened to me', medium-long anecdotes",
        "avg_length": "medium",
        "anchor_rate": 0.2,
        "frequency": "low",
        "weight": 0.10,
    },
    "agreeer": {
        "label": "Agreefag",
        "description": "'based', 'this', 'kek >>X', short agreement posts",
        "avg_length": "very_short",
        "anchor_rate": 0.6,
        "frequency": "medium",
        "weight": 0.12,
    },
    "contrarian": {
        "label": "Contrarian",
        "description": "Disagrees with majority, 'everyone says X but actually Y'",
        "avg_length": "medium",
        "anchor_rate": 0.4,
        "frequency": "medium",
        "weight": 0.05,
    },
}


TONE_POSTING_AFFINITY = {
    "authority": ["info_provider", "debater", "veteran"],
    "worker": ["info_provider", "debater", "emotional", "veteran", "storyteller"],
    "youth": ["joker", "questioner", "emotional", "agreeer", "contrarian", "passerby"],
    "outsider": ["info_provider", "passerby", "agreeer"],
    "lurker": ["questioner", "contrarian", "passerby"],
}


def _assign_posting_style() -> str:
    """Select posting style via weighted random"""
    styles = list(POSTING_STYLES.keys())
    weights = [POSTING_STYLES[s]["weight"] for s in styles]
    return random.choices(styles, weights=weights, k=1)[0]


# Tone type definitions
TONE_STYLES = {
    "authority": {
        "label": "Authority",
        "description": "Professor, manager, executive. Polite but assertive. Formal, long posts.",
        "post_interval_min": 3,
        "post_interval_max": 5,
    },
    "worker": {
        "label": "Worker",
        "description": "Technician, office worker, middle management. Practical, down-to-earth.",
        "post_interval_min": 2,
        "post_interval_max": 3,
    },
    "youth": {
        "label": "Youth",
        "description": "Student, young adult. Casual, meme-heavy, greentext storyteller.",
        "post_interval_min": 1,
        "post_interval_max": 2,
    },
    "outsider": {
        "label": "Outsider",
        "description": "Contractor, corporate rep, bureaucrat. Business-speak, hides true opinions.",
        "post_interval_min": 5,
        "post_interval_max": 10,
    },
    "lurker": {
        "label": "Lurker",
        "description": "Observer. Rarely posts but cuts to the core when they do.",
        "post_interval_min": 10,
        "post_interval_max": 20,
    },
}


@dataclass
class OracleAgent:
    agent_id: int
    name: str
    username: str
    bio: str
    persona: str
    age: int
    gender: str           # "male" | "female" | "other"
    mbti: str
    country: str
    profession: str
    interested_topics: List[str]
    tone_style: str       # "authority" | "worker" | "youth" | "outsider" | "lurker"
    stance: Dict[str, Any]
    relationships: Dict[str, str]
    hidden_agenda: str
    trigger_topics: List[str]
    entity_type: str = "person"           # "person" | "organization" | "concept"
    posting_style: str = "emotional"      # key of POSTING_STYLES
    post_frequency: str = "medium"        # "once" | "low" | "medium" | "high"
    emotional_wound: str = ""
    information_bias: str = ""
    speech_patterns: List[str] = field(default_factory=list)
    debate_tactics: str = ""
    social_position: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "username": self.username,
            "bio": self.bio,
            "persona": self.persona,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "tone_style": self.tone_style,
            "stance": self.stance,
            "relationships": self.relationships,
            "hidden_agenda": self.hidden_agenda,
            "trigger_topics": self.trigger_topics,
            "entity_type": self.entity_type,
            "posting_style": self.posting_style,
            "post_frequency": self.post_frequency,
            "emotional_wound": self.emotional_wound,
            "information_bias": self.information_bias,
            "speech_patterns": self.speech_patterns,
            "debate_tactics": self.debate_tactics,
            "social_position": self.social_position,
        }


PERSON_PERSONA_PROMPT = """Design a 4chan anon persona. Return JSON only.

Name:{name} Description:{description} Stance:{stance} Role:{role}
Theme:{theme} Key Issues:{key_issues}

JSON:
{{"bio":"profile 50 chars","persona":"personality, posting style, and stance in 200 chars","age":integer,"gender":"male/female","mbti":"XXXX","profession":"job","interested_topics":["topic1","topic2"],"tone_style":"authority/worker/youth/outsider/lurker","stance":{{"position":"pro/con/neutral","reason":"reason 30 chars"}},"hidden_agenda":"true motive 30 chars","trigger_topics":["topic1"]}}""".format(
    name="{name}",
    description="{description}",
    stance="{stance}",
    role="{role}",
    theme="{theme}",
    key_issues="{key_issues}",
)

ORG_PERSONA_PROMPT = """Design an organization's board representative account. Return JSON only.

Name:{name} Description:{description} Stance:{stance} Role:{role}
Theme:{theme} Key Issues:{key_issues}

JSON:
{{"bio":"official profile 50 chars","persona":"org stance and posting style 200 chars","age":45,"gender":"other","mbti":"XXXX","profession":"function","interested_topics":["field1","field2"],"tone_style":"authority/outsider","stance":{{"position":"official stance","reason":"rationale 30 chars"}},"hidden_agenda":"true motive 30 chars","trigger_topics":["topic1"]}}""".format(
    name="{name}",
    description="{description}",
    stance="{stance}",
    role="{role}",
    theme="{theme}",
    key_issues="{key_issues}",
)


def _is_valid_english_name(name: str) -> bool:
    """
    Determine if the name is a valid English full name.
    - At least 2 words, total length 3-40 chars
    - Matches known last name pool with a first name prefix
    - Not a concept/role word
    """
    if not name or len(name) < 3 or len(name) > 40:
        return False
    # Concept/role word blacklist
    CONCEPT_WORDS = [
        "university", "school", "department", "research", "freedom", "environment",
        "economy", "politics", "science", "technology", "student", "faculty",
        "professor", "staff", "union", "committee", "organization", "group",
        "enterprise", "company", "government", "citizen", "resident", "support",
        "opposition", "promotion", "skeptic", "neutral", "veteran", "manager",
        "outsider", "insider", "stakeholder",
    ]
    name_lower = name.lower()
    for word in CONCEPT_WORDS:
        if word in name_lower:
            return False
    # Check that it contains a known last name and at least one first name part
    parts = name.split()
    if len(parts) < 2:
        return False
    for last in LAST_NAMES:
        if parts[-1] == last:
            return True
    return False


def _make_username(name: str, agent_id: int) -> str:
    """Generate a board handle (tripcode-style)"""
    clean = "".join(c for c in name if c.isascii() and (c.isalnum() or c in "_-"))
    if not clean:
        clean = f"agent{agent_id:03d}"
    suffix = random.randint(100, 999)
    return f"{clean[:12]}_{suffix}"


def _parse_structured_persona(persona: str) -> dict:
    """Extract individual sections from [tag]value|[tag]value format.
    Also handles free-text personas (keyword-based partial extraction)."""
    result = {
        "emotional_wound": "",
        "information_bias": "",
        "speech_patterns": [],
        "debate_tactics": "",
        "social_position": "",
    }

    if not persona:
        return result

    # Simple extraction from free-text persona (no tags)
    if "[" not in persona:
        import re as _re
        # Extract speech patterns from quoted phrases
        speech_matches = _re.findall(r'"([^"]{2,30})"', persona)
        if not speech_matches:
            speech_matches = _re.findall(r"'([^']{2,30})'", persona)
        if speech_matches:
            result["speech_patterns"] = speech_matches[:4]
        # Trauma/complex keywords
        wound_kw = ["trauma", "complex", "fear", "anxiety", "experienced", "witnessed", "forced"]
        for kw in wound_kw:
            idx = persona.lower().find(kw)
            if idx != -1:
                result["emotional_wound"] = persona[max(0, idx-20):idx+60].strip()
                break
        # Information bias
        bias_kw = ["reddit", "twitter", "4chan", "fox news", "cnn", "nyt", "wsj", "forums", "field data"]
        for kw in bias_kw:
            if kw in persona.lower():
                result["information_bias"] = kw
                break
        return result

    # Parse [tag]value|[tag]value... format
    sections = persona.split("|")
    for section in sections:
        section = section.strip()
        if not section.startswith("["):
            continue

        if "]" not in section:
            continue
        tag_end = section.index("]")
        tag = section[1:tag_end]
        value = section[tag_end+1:].strip()

        if tag == "wound" and not result["emotional_wound"]:
            result["emotional_wound"] = value[:100]
        elif tag == "bias" and not result["information_bias"]:
            result["information_bias"] = value[:100]
        elif tag == "speech" and not result["speech_patterns"]:
            patterns = []
            for sep in ["·", ",", '"', "'"]:
                if sep in value:
                    patterns = [p.strip() for p in value.split(sep) if p.strip()]
                    break
            result["speech_patterns"] = patterns[:5] if patterns else []
        elif tag == "tactics" and not result["debate_tactics"]:
            result["debate_tactics"] = value[:100]
        elif tag == "social" and not result["social_position"]:
            result["social_position"] = value[:100]

    return result


def _ensure_profession(prof: str, tone: str) -> str:
    """Return a default profession by tone if the given one is empty or generic"""
    if prof and len(prof) >= 2 and prof not in ("unknown", "none", ""):
        return prof
    defaults = {
        "authority": random.choice(["University Professor", "Department Head", "Research Director", "VP of Research", "Dean"]),
        "worker": random.choice(["Office Worker", "Technician", "Research Staff", "Librarian", "Systems Admin"]),
        "youth": random.choice(["College Student", "Grad Student", "Research Assistant", "Junior Year", "Masters Student"]),
        "outsider": random.choice(["IT Consultant", "Freelancer", "Government Official", "NGO Worker", "Journalist"]),
        "lurker": random.choice(["Unemployed", "Self-employed", "Homemaker", "Retiree", "Part-timer"]),
    }
    return defaults.get(tone, "Office Worker")


# Stance distribution pattern (balanced pro/con/neutral)
STANCE_CYCLE = [
    {"position": "pro", "reason": "AI adoption improves quality of life"},
    {"position": "con", "reason": "Risks outweigh the benefits"},
    {"position": "neutral", "reason": "Conditional acceptance is reasonable"},
    {"position": "con", "reason": "Creates opportunities for abuse"},
    {"position": "pro", "reason": "Can't fight the tide of progress"},
    {"position": "skeptical", "reason": "Insufficient evidence to judge"},
    {"position": "pro", "reason": "Essential for operational efficiency"},
    {"position": "con", "reason": "Privacy and security concerns are real"},
]


def _assign_stance(llm_stance: Any, idx: int, total: int) -> Dict[str, str]:
    """Distribute stances. Use LLM stance if provided, else cycle to prevent everyone agreeing"""
    if isinstance(llm_stance, dict) and llm_stance.get("position"):
        return llm_stance
    return STANCE_CYCLE[idx % len(STANCE_CYCLE)]


def _assign_tone(entity: Dict[str, Any]) -> str:
    """Infer default tone type from entity info"""
    desc = (entity.get("description", "") + entity.get("attributes", {}).get("role", "")).lower()
    if any(kw in desc for kw in ["professor", "director", "manager", "executive", "head", "dean", "vp"]):
        return "authority"
    if any(kw in desc for kw in ["student", "youth", "young", "undergrad", "junior"]):
        return "youth"
    if any(kw in desc for kw in ["contractor", "vendor", "agency", "government", "committee", "external"]):
        return "outsider"
    if entity.get("type") in ("organization", "concept"):
        return "authority"
    return "worker"


def _replace_bad_agents(llm: "OracleLLMClient", theme: str, key_issues: list):
    """Delete bad-rated agents and replace with new ones"""
    try:
        from db.database import db_conn
        with db_conn() as conn:
            bad_rows = conn.execute("SELECT id, name FROM persistent_agents WHERE rating='bad'").fetchall()
            if not bad_rows:
                return
            bad_names = [r["name"] for r in bad_rows]
            print(f"[ProfileGenerator] 👎 Replacing {len(bad_names)} agents: {', '.join(bad_names)}")
            for r in bad_rows:
                conn.execute("DELETE FROM persistent_agents WHERE id=?", (r["id"],))
    except Exception as e:
        print(f"[ProfileGenerator] Failed to replace bad agents: {e}")


def _row_to_agent(row: dict, idx: int, total: int, key_issues: list) -> OracleAgent:
    """Convert DB row → OracleAgent"""
    topics = row.get("interested_topics", "[]")
    if isinstance(topics, str):
        try:
            topics = json.loads(topics)
        except:
            topics = key_issues[:3]

    p_style = row.get("posting_style", _assign_posting_style())
    stance = _assign_stance({}, idx, total)

    return OracleAgent(
        agent_id=idx,
        name=row["name"],
        username=row.get("username", _make_username(row["name"], idx)),
        bio=row.get("bio", ""),
        persona=row.get("persona", ""),
        age=row.get("age", 30),
        gender=row.get("gender", "other"),
        mbti=row.get("mbti", random.choice(MBTI_TYPES)),
        country="USA",
        profession=row.get("profession", ""),
        interested_topics=topics if isinstance(topics, list) else key_issues[:3],
        tone_style=row.get("tone_style", "worker"),
        stance=stance,
        relationships={},
        hidden_agenda="",
        trigger_topics=[],
        entity_type="person",
        posting_style=p_style,
        post_frequency=POSTING_STYLES.get(p_style, {}).get("frequency", "medium"),
    )


import os as _os

_STOCK_AGENTS_PATH = _os.path.join(_os.path.dirname(__file__), "..", "agents", "stock_agents.json")
_stock_agents_cache: Optional[List[dict]] = None


def _load_stock_agents() -> List[dict]:
    """Load stock_agents.json only (public agents only).
    Real agents (stock_agents_real.json / agents/private/) are not included.
    """
    global _stock_agents_cache
    if _stock_agents_cache is None:
        agents_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "agents"))
        _stock_agents_cache = []
        fpath = _os.path.join(agents_dir, "stock_agents.json")
        if _os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            _stock_agents_cache.extend(loaded)
            print(f"[ProfileGenerator] ✅ Loaded {len(loaded)} agents from stock_agents.json")
        else:
            print(f"[ProfileGenerator] ℹ️ stock_agents.json not found")
        print(f"[ProfileGenerator] ✅ Total stock agents: {len(_stock_agents_cache)} (public only)")
    return _stock_agents_cache


_private_agents_cache: Optional[List[dict]] = None

def _load_private_agents() -> List[dict]:
    """Load all .json files under agents/private/ (real agents).
    Not shown in listings but can be used when explicitly specified in simulations.
    """
    global _private_agents_cache
    if _private_agents_cache is None:
        private_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "agents", "private"))
        _private_agents_cache = []
        if _os.path.isdir(private_dir):
            for fname in _os.listdir(private_dir):
                if fname.endswith(".json"):
                    fpath = _os.path.join(private_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                        _private_agents_cache.extend(loaded)
                        print(f"[ProfileGenerator] 🔒 Loaded {len(loaded)} agents from private/{fname}")
                    except Exception as e:
                        print(f"[ProfileGenerator] ⚠️ Failed to load private/{fname}: {e}")
        # Deduplicate by name
        seen = set()
        deduped = []
        for a in _private_agents_cache:
            if a.get("name") not in seen:
                seen.add(a.get("name"))
                deduped.append(a)
        _private_agents_cache = deduped
        print(f"[ProfileGenerator] 🔒 Total private agents: {len(_private_agents_cache)}")
    return _private_agents_cache


def _stock_agent_to_oracle(s: dict, idx: int, total: int, key_issues: list, stance_override: Optional[dict] = None) -> OracleAgent:
    """Convert stock_agents.json entry → OracleAgent"""
    topics = s.get("interested_topics", [])
    if not isinstance(topics, list):
        topics = key_issues[:3]
    p_style = s.get("posting_style", _assign_posting_style())
    stance = stance_override or _assign_stance({}, idx, total)
    speech = s.get("speech_patterns", [])
    return OracleAgent(
        agent_id=idx,
        name=s["name"],
        username=s.get("username", _make_username(s["name"], idx)),
        bio=s.get("bio", ""),
        persona=s.get("persona", ""),
        age=s.get("age", 30),
        gender=s.get("gender", "male"),
        mbti=s.get("mbti", random.choice(MBTI_TYPES)),
        country="USA",
        profession=s.get("profession", ""),
        interested_topics=topics,
        tone_style=s.get("tone_style", "worker"),
        stance=stance,
        relationships={},
        hidden_agenda=s.get("hidden_agenda", ""),
        trigger_topics=[],
        entity_type="person",
        posting_style=p_style,
        post_frequency=s.get("post_frequency", POSTING_STYLES.get(p_style, {}).get("frequency", "medium")),
        emotional_wound=s.get("emotional_wound", ""),
        information_bias=s.get("information_bias", ""),
        speech_patterns=speech if isinstance(speech, list) else [],
        debate_tactics=s.get("debate_tactics", ""),
        social_position=s.get("social_position", ""),
    )


def _try_reuse_stock_agents(agent_count: int, key_issues: list) -> List[OracleAgent]:
    """Randomly select from stock agents and return as OracleAgent list.
    If DB agents exist, prefer DB is_active flag."""
    # First try to get active agents from DB (is_active=1 only)
    try:
        from db.database import get_persistent_agents
        db_agents = [a for a in get_persistent_agents(limit=200, include_bad=False) if a.get("is_active", 1) == 1]
        if db_agents:
            selected = random.sample(db_agents, min(agent_count, len(db_agents)))
            agents = []
            for idx, row in enumerate(selected):
                agents.append(_row_to_agent(row, idx, len(selected), key_issues))
            print(f"[ProfileGenerator] 📦 Selected {len(agents)} stock agents (DB) from {len(db_agents)} active")
            return agents
    except Exception as e:
        print(f"[ProfileGenerator] DB fetch failed, falling back to JSON: {e}")

    # Fall back to stock_agents.json if DB is empty or errors
    stock = _load_stock_agents()
    if not stock:
        return []
    selected = random.sample(stock, min(agent_count, len(stock)))
    agents = []
    for idx, s in enumerate(selected):
        agents.append(_stock_agent_to_oracle(s, idx, len(selected), key_issues))
    print(f"[ProfileGenerator] 📦 Selected {len(agents)} stock agents (JSON)")
    return agents


def _try_reuse_persistent_agents(scale: str, custom_agents: Optional[int], key_issues: list, theme: str) -> tuple:
    """Try to reuse previously saved persistent agents.
    Returns: (reused_agents: list, shortage: int) — shortage=0 means everyone is available"""
    try:
        from db.database import get_persistent_agents
        agent_count = custom_agents or {"mini": 5, "full": 12, "auto": 8}.get(scale, 8)

        # Remove bad-rated agents first
        _replace_bad_agents(None, theme, key_issues)

        cached = [a for a in get_persistent_agents(limit=agent_count + 20, include_bad=False) if a.get("is_active", 1) == 1]

        if not cached:
            return ([], agent_count)  # Generate all new

        # Randomly select (return shortage for missing ones)
        selected = random.sample(cached, min(agent_count, len(cached)))
        agents = []
        for idx, row in enumerate(selected):
            agents.append(_row_to_agent(row, idx, agent_count, key_issues))

        shortage = max(0, agent_count - len(agents))
        return (agents, shortage)
    except Exception as e:
        print(f"[ProfileGenerator] Failed to reuse persistent agents: {e}")
        agent_count = custom_agents or {"mini": 5, "full": 12, "auto": 8}.get(scale, 8)
        return ([], agent_count)


def generate_agents(
    entity_data: Dict[str, Any],
    llm: OracleLLMClient,
    scale: str = "mini",
    custom_agents: Optional[int] = None,
    agent_roles: Optional[List[Dict[str, Any]]] = None,
    reuse_agents: bool = True,
) -> List[OracleAgent]:
    """
    Generate agents from entity data.
    If reuse_agents=True, prioritize reusing previously saved persistent agents.
    """
    entities = entity_data.get("entities", [])
    theme = entity_data.get("theme", "")
    key_issues = entity_data.get("key_issues", [])

    # Stock agents take highest priority
    if reuse_agents:
        agent_count = custom_agents or {"mini": 5, "full": 12, "auto": 8}.get(scale, 8)
        stock_agents = _try_reuse_stock_agents(agent_count, key_issues)
        if stock_agents:
            # Override stance to match theme
            for idx, agent in enumerate(stock_agents):
                agent.stance = _assign_stance({}, idx, len(stock_agents))
            print(f"[ProfileGenerator] 📦 Using {len(stock_agents)} stock agents ⚡")
            return stock_agents

    # Try to reuse persistent agents (fallback if stock is empty)
    reused_agents = []
    if reuse_agents:
        reused_agents, shortage = _try_reuse_persistent_agents(scale, custom_agents, key_issues, theme)
        if reused_agents and shortage == 0:
            print(f"[ProfileGenerator] Reusing {len(reused_agents)} persistent agents ⚡")
            return reused_agents
        elif reused_agents and shortage > 0:
            print(f"[ProfileGenerator] Reusing {len(reused_agents)} persistent agents + generating {shortage} new")
            # Override custom_agents with shortage count
            custom_agents = shortage
            scale = "custom"
        # Empty reused_agents → generate all new (normal flow continues)

    # Role-based generation if agent_roles specified
    if agent_roles:
        print(
            f"[ProfileGenerator] Role-based mode: {sum(r.get('count', 1) for r in agent_roles)} agents",
            flush=True,
        )
        return _generate_agents_from_roles(agent_roles, theme, key_issues, llm)

    # Determine agent count by scale
    if scale == "mini":
        target_count = min(len(entities), 8)
    elif scale == "full":
        target_count = min(max(len(entities), 20), 50)
    else:  # custom
        target_count = custom_agents or len(entities)

    # Use all entities if fewer than needed
    selected = entities[:target_count] if len(entities) >= target_count else entities

    # Expand entities for full/custom scale (multiple agents from same entity)
    if scale in ("full", "custom") and len(entities) < target_count:
        extra_needed = target_count - len(entities)
        for i in range(extra_needed):
            base = entities[i % len(entities)].copy()
            base["name"] = f"{base['name']}_{i+2}"
            selected.append(base)

    # --- Batch generation: group 3 at a time to reduce API calls ---
    profiles_list = []
    batch_size = 3
    used_names: set = set()

    for batch_idx in range(0, len(selected), batch_size):
        batch_entities = selected[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (len(selected) + batch_size - 1) // batch_size

        print(f"[ProfileGenerator] Batch {batch_num}/{total_batches}: generating {len(batch_entities)} agents...")

        entity_list_text_enhanced = "\n".join(
            f"{i+1}. [{e['name']}] type={e.get('type','person')} / "
            f"desc:{e.get('description','')[:80]} / "
            f"stance:{e.get('attributes',{}).get('stance','unknown')} / "
            f"tone:{e.get('_tone','worker')}"
            for i, e in enumerate(batch_entities)
        )

        batch_prompt = f"""Create 4chan anon personas for the theme "{theme}" (issues: {', '.join(key_issues[:2])}).

Tone types:
- authority: Professor/manager. "In my professional opinion", "The evidence clearly shows"
- worker: Technician/office. "From my experience", "Honestly though"
- youth: Student/young. greentext, "kek", "based", "this desu"
- outsider: Contractor/corp. "Our company's position is", "We'd like to suggest"
- lurker: Observer. Short cuts: "This.", "The real issue is"

Posting styles: info_provider/debater/joker/questioner/veteran/passerby/emotional/storyteller/agreeer/contrarian

{entity_list_text_enhanced}

name MUST be a real English full name (e.g. John Smith). No concept names.
persona must use format [identity]...|[backstory]...|[personality]...|[wound]...|[speech]...|[board]...|[stance_detail]...|[hidden]...|[trigger]...|[bias]...|[social]...|[tactics]...|[memory]...|[quirk]... (800+ chars, no line breaks).

Return JSON array only (no explanation):
[{{"name":"John Smith","bio":"profile under 80 chars","persona":"[identity]...structured persona 800+ chars","age":30,"gender":"male","mbti":"INTJ","profession":"job","interested_topics":["topic1","topic2"],"tone_style":"worker","posting_style":"debater","stance":{{"position":"pro","reason":"reason 50 chars","confidence":0.7}},"hidden_agenda":"true motive 40 chars","trigger_topics":["topic1","topic2"],"emotional_wound":"trauma 40 chars","information_bias":"trusted source 40 chars","speech_patterns":["catchphrase1","catchphrase2","catchphrase3"],"debate_tactics":"strategy 30 chars","social_position":"income bracket, generation 40 chars"}}]"""

        try:
            messages = [
                {"role": "system", "content": "Return JSON array only. No explanation."},
                {"role": "user", "content": batch_prompt},
            ]
            raw = llm.chat(messages, temperature=0.8)
            match = re.search(r'\[[\s\S]*\]', raw)
            if match:
                batch_profiles = json.loads(match.group())
                profiles_list.extend(batch_profiles)
                print(f"[ProfileGenerator] Batch {batch_num} success: {len(batch_profiles)} agents")
            else:
                raise ValueError("JSON array not found")
        except Exception as e:
            print(f"[ProfileGenerator] Batch {batch_num} failed: {e} — using fallback")
            for e_data in batch_entities:
                profiles_list.append(
                    _fallback_profile(e_data, e_data.get("type") == "person", used_names)
                )

    agents = []
    for idx, entity in enumerate(selected):
        # Find matching profile from batch results
        profile_data = None
        for p in profiles_list:
            if p.get("name") == entity["name"] or p.get("index") == idx + 1:
                profile_data = p
                break
        if profile_data is None and idx < len(profiles_list):
            profile_data = profiles_list[idx]
        if profile_data is None:
            profile_data = _fallback_profile(entity, entity.get("type") == "person", used_names)

        # Extract structured sections from persona (fallback if LLM didn't return individual fields)
        persona_text = profile_data.get("persona", "")
        if persona_text:
            parsed_sections = _parse_structured_persona(persona_text)
            for key, value in parsed_sections.items():
                existing = profile_data.get(key)
                is_empty = not existing or (isinstance(existing, list) and len(existing) == 0) or (isinstance(existing, str) and len(existing.strip()) == 0)
                if is_empty and value:
                    profile_data[key] = value

        # Fill in fields (make each agent unique)
        attrs = entity.get("attributes", {})
        # tone_style: use LLM value if valid, else infer from entity, else random
        tone_style = profile_data.get("tone_style", "")
        if tone_style not in TONE_STYLES:
            tone_style = _assign_tone(entity)
        # Prevent all agents having the same tone — force change if 2+ already
        tone_counts = {}
        for a in agents:
            tone_counts[a.tone_style] = tone_counts.get(a.tone_style, 0) + 1
        if tone_counts.get(tone_style, 0) >= 2:
            available = [t for t in TONE_STYLES if tone_counts.get(t, 0) < 1]
            if not available:
                available = [t for t in TONE_STYLES if tone_counts.get(t, 0) < 2]
            if available:
                tone_style = random.choice(available)
        # gender: use LLM value if valid, else random by tone
        gender = profile_data.get("gender", "")
        if gender not in ("male", "female"):
            gender = _pick_gender(tone_style)
        # age: use LLM value if available, else random by tone
        age = profile_data.get("age", random.randint(*AGE_RANGES.get(tone_style, (22, 55))))

        # ── Name determination (force English names for all agents) ──────────────
        llm_name = _normalize_name(profile_data.get("name", ""))
        if llm_name and _is_valid_english_name(llm_name) and llm_name not in used_names:
            name = llm_name
            used_names.add(name)
        elif _is_valid_english_name(_normalize_name(entity.get("name", ""))) and _normalize_name(entity["name"]) not in used_names:
            name = _normalize_name(entity["name"])
            used_names.add(name)
        else:
            # Concept/org name or duplicate → generate English name
            gender_for_name = gender if gender in ("male", "female") else random.choice(["male", "female"])
            name = _generate_english_name(gender_for_name, used_names)

        username = _make_username(name, idx)

        p_style = profile_data.get("posting_style", "")
        if p_style not in POSTING_STYLES:
            candidates = TONE_POSTING_AFFINITY.get(tone_style, list(POSTING_STYLES.keys()))
            p_style = random.choice(candidates)

        stance_data = _assign_stance(profile_data.get("stance", {}), idx, len(selected))
        if "confidence" not in stance_data:
            stance_data["confidence"] = round(random.uniform(0.3, 0.9), 2)

        agent = OracleAgent(
            agent_id=idx,
            name=name,
            username=username,
            bio=profile_data.get("bio", entity.get("description", "")[:200]),
            persona=profile_data.get("persona", entity.get("description", "")),
            age=int(age) if isinstance(age, (int, float)) else 30,
            gender=gender if gender in ("male", "female", "other") else "other",
            mbti=_deduplicate_mbti(profile_data.get("mbti", ""), tone_style, agents),
            country=profile_data.get("country", "USA"),
            profession=_ensure_profession(profile_data.get("profession", attrs.get("role", "")), tone_style),
            interested_topics=profile_data.get("interested_topics", key_issues[:3]),
            tone_style=tone_style,
            stance=stance_data,
            relationships={},
            hidden_agenda=profile_data.get("hidden_agenda", ""),
            trigger_topics=profile_data.get("trigger_topics", []),
            entity_type=entity.get("type", "person"),
            posting_style=p_style,
            post_frequency=POSTING_STYLES[p_style]["frequency"],
            emotional_wound=profile_data.get("emotional_wound", ""),
            information_bias=profile_data.get("information_bias", ""),
            speech_patterns=profile_data.get("speech_patterns", []),
            debate_tactics=profile_data.get("debate_tactics", ""),
            social_position=profile_data.get("social_position", ""),
        )
        agents.append(agent)

    # Combine with reused persistent agents
    if reused_agents:
        for i, a in enumerate(agents):
            a.agent_id = len(reused_agents) + i
        all_agents = reused_agents + agents
        print(f"[ProfileGenerator] Total {len(all_agents)} agents (reused:{len(reused_agents)} + new:{len(agents)})")
        return all_agents

    print(f"[ProfileGenerator] {len(agents)} agents generated")
    return agents


def _generate_agents_from_roles(
    agent_roles: List[Dict[str, Any]],
    theme: str,
    key_issues: List[str],
    llm: OracleLLMClient,
) -> List["OracleAgent"]:
    """
    Generate agents from parameter planner role specs.

    agent_roles example:
      [{"role": "university professor", "tone": "authority", "stance": "pro", "count": 2}, ...]
    """
    # Expand roles into individual agent specs
    specs: List[Dict[str, Any]] = []
    for role_spec in agent_roles:
        for _ in range(max(1, int(role_spec.get("count", 1)))):
            specs.append({
                "role": role_spec.get("role", "participant"),
                "tone": role_spec.get("tone", "worker"),
                "stance": role_spec.get("stance", "neutral"),
            })

    # Batch generation (3 per batch)
    profiles_list: List[Dict[str, Any]] = []
    batch_size = 3
    used_names: set = set()

    for batch_idx in range(0, len(specs), batch_size):
        batch_specs = specs[batch_idx: batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (len(specs) + batch_size - 1) // batch_size

        print(
            f"[ProfileGenerator] Role batch {batch_num}/{total_batches}: "
            f"generating {len(batch_specs)} agents...",
            flush=True,
        )

        spec_list_text = "\n".join(
            f"{i + 1}. Role: {s['role']} / Tone: {s['tone']} / Stance: {s['stance']}"
            for i, s in enumerate(batch_specs)
        )

        batch_prompt = f"""Create 4chan anon personas for the theme "{theme}" (issues: {', '.join(key_issues[:2])}).

{spec_list_text}

name MUST be a real English full name (e.g. Jane Doe). No concept names.

Return JSON array:
[{{"name":"Jane Doe","bio":"profile 50 chars","persona":"personality, tone, stance 200 chars","age":30,"gender":"female","mbti":"ENFP","profession":"job","interested_topics":["topic"],"tone_style":"worker","stance":{{"position":"pro","reason":"reason"}},"hidden_agenda":"true motive","trigger_topics":["topic"]}}]"""

        try:
            messages = [
                {
                    "role": "system",
                    "content": "Return JSON array only. No explanation.",
                },
                {"role": "user", "content": batch_prompt},
            ]
            raw = llm.chat(messages, temperature=0.8)
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                batch_profiles = json.loads(match.group())
                profiles_list.extend(batch_profiles)
                print(
                    f"[ProfileGenerator] Role batch {batch_num} success: {len(batch_profiles)} agents",
                    flush=True,
                )
            else:
                raise ValueError("JSON array not found")
        except Exception as e:
            print(
                f"[ProfileGenerator] Role batch {batch_num} failed: {e} — using fallback",
                flush=True,
            )
            for s in batch_specs:
                profiles_list.append(
                    _fallback_profile_from_spec(s, theme, key_issues, used_names)
                )

    # Convert profiles_list → OracleAgent
    agents: List[OracleAgent] = []
    for idx, spec in enumerate(specs):
        profile_data = profiles_list[idx] if idx < len(profiles_list) else \
            _fallback_profile_from_spec(spec, theme, key_issues, used_names)

        tone_style = profile_data.get("tone_style", spec["tone"])
        if tone_style not in TONE_STYLES:
            tone_style = spec["tone"]

        # Name: force English name, deduplicate
        name = profile_data.get("name", "")
        if not name or name == spec["role"] or name in TONE_STYLES or not _is_valid_english_name(name) or name in used_names:
            gender_hint = profile_data.get("gender", "")
            if gender_hint not in ("male", "female"):
                gender_hint = _pick_gender(tone_style)
            name = _generate_english_name(gender_hint, used_names)

        username = _make_username(name, idx)
        age = profile_data.get("age", random.randint(*AGE_RANGES.get(tone_style, (22, 55))))
        gender = profile_data.get("gender", "")
        if gender not in ("male", "female"):
            gender = _pick_gender(tone_style)

        p_style = _assign_posting_style()
        agent = OracleAgent(
            agent_id=idx,
            name=name,
            username=username,
            bio=profile_data.get("bio", ""),
            persona=profile_data.get("persona", ""),
            age=int(age) if isinstance(age, (int, float)) else 30,
            gender=gender if gender in ("male", "female", "other") else "other",
            mbti=_deduplicate_mbti(profile_data.get("mbti", ""), tone_style, agents),
            country="USA",
            profession=_ensure_profession(profile_data.get("profession", ""), tone_style),
            interested_topics=profile_data.get(
                "interested_topics", key_issues[:3] if key_issues else []
            ),
            tone_style=tone_style,
            stance=_assign_stance(profile_data.get("stance", {}), idx, len(specs)),
            relationships={},
            hidden_agenda=profile_data.get("hidden_agenda", ""),
            trigger_topics=profile_data.get("trigger_topics", []),
            entity_type="person",
            posting_style=p_style,
            post_frequency=POSTING_STYLES[p_style]["frequency"],
        )
        agents.append(agent)

    print(f"[ProfileGenerator] Role-based generation complete: {len(agents)} agents", flush=True)
    return agents


def _fallback_profile_from_spec(
    spec: Dict[str, Any],
    theme: str,
    key_issues: List[str],
    used_names: Optional[set] = None,
) -> Dict[str, Any]:
    """Generate fallback profile from role spec"""
    if used_names is None:
        used_names = set()
    tone = spec.get("tone", "worker")
    stance = spec.get("stance", "neutral")
    role = spec.get("role", "participant")

    gender = _pick_gender(tone)
    name = _generate_english_name(gender, used_names)
    age = random.randint(*AGE_RANGES.get(tone, (25, 50)))
    mbti = _select_mbti(tone, stance)

    persona_snippets = {
        "authority": f"A manager/academic involved with {theme}. Formal but assertive.",
        "worker":    f"A field practitioner directly affected by {theme}.",
        "youth":     f"A student/young adult interested in {theme}, sharing their own take.",
        "outsider":  f"An external observer of {theme} engaging from a business perspective.",
        "lurker":    f"Mostly silent, but cuts to the core of {theme} when they do post.",
    }

    return {
        "name": name,
        "bio": f"{role} ({stance})",
        "persona": persona_snippets.get(tone, f"A {role} involved with {theme}. Stance: {stance}."),
        "age": age,
        "gender": gender,
        "mbti": mbti,
        "profession": role,
        "interested_topics": (key_issues[:3] if key_issues else ["discussion"]),
        "tone_style": tone,
        "stance": {"position": stance, "reason": ""},
        "hidden_agenda": "",
        "trigger_topics": [],
    }


def _fallback_profile(entity: Dict[str, Any], is_individual: bool, used_names=None) -> Dict[str, Any]:
    """Fallback when LLM fails (with structured persona)"""
    attrs = entity.get("attributes", {})
    tone = _assign_tone(entity)
    name = entity.get("name", "Unknown")
    description = entity.get("description", "")
    stance = attrs.get("stance", "neutral")

    speech_templates = {
        "authority": ["In my professional opinion", "The evidence clearly shows", "From my perspective"],
        "worker": ["From my experience", "Honestly though", "In practice"],
        "youth": ["kek", "based", "ngl"],
        "outsider": ["Our position is", "We'd suggest", "Generally speaking"],
        "lurker": ["This.", "The real issue is", "Well"],
    }
    speech = speech_templates.get(tone, [""])

    persona = (
        f"[identity]{name} is a {attrs.get('role', 'stakeholder')}|"
        f"[backstory]{description[:60] if description else 'Has interest in the topic'}|"
        f"[personality]Logical thinker, standard personality|"
        f"[wound]Nothing notable|"
        f"[speech]{' · '.join(speech)}|"
        f"[board]Posts at normal frequency|"
        f"[stance_detail]Stance:{stance}|"
        f"[hidden]Nothing notable|"
        f"[trigger]Reacts when criticized|"
        f"[bias]Mainstream media|"
        f"[social]Average position|"
        f"[tactics]Argues logically|"
        f"[memory]No notable episodes|"
        f"[quirk]Nothing notable"
    )

    candidates = TONE_POSTING_AFFINITY.get(tone, list(POSTING_STYLES.keys()))
    posting = random.choice(candidates)

    return {
        "bio": description[:200] if description else f"{name}'s account",
        "persona": persona,
        "age": random.randint(25, 50) if is_individual else 30,
        "gender": "male" if is_individual else "other",
        "mbti": random.choice(MBTI_TYPES),
        "profession": attrs.get("role", "stakeholder"),
        "interested_topics": ["policy", "education", "technology"],
        "tone_style": tone,
        "posting_style": posting,
        "stance": {"position": stance, "reason": "", "confidence": 0.5},
        "hidden_agenda": "",
        "trigger_topics": [],
        "emotional_wound": "",
        "information_bias": "",
        "speech_patterns": speech,
        "debate_tactics": "Responds to the situation",
        "social_position": "",
    }


def _pick_gender(tone: str) -> str:
    """Randomly select gender by tone type (with probability distribution)"""
    # Male probability per tone (remainder is female)
    male_prob = {
        "authority": 0.70,
        "worker":    0.60,
        "youth":     0.60,
        "outsider":  0.55,
        "lurker":    0.50,
    }
    p = male_prob.get(tone, 0.55)
    return "male" if random.random() < p else "female"
