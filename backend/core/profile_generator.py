"""
Oracle プロフィール生成器
MiroFish準拠の2000字ペルソナを生成。口調5タイプ、個人vs組織の区別あり。
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

# ─── 日本人名リスト ───────────────────────────────────────────────
LAST_NAMES = [
    "田中", "佐藤", "鈴木", "高橋", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
    "吉田", "山口", "松本", "井上", "林", "石川", "前田", "藤田", "岡田", "後藤",
    "森", "長谷川", "近藤", "坂本", "遠藤", "青木", "池田", "橋本", "山田", "石田",
    "西村", "三浦", "岡本", "藤原", "上田", "中島", "原田", "安藤", "河野", "小川",
    "内田", "菊池", "野口", "久保", "新井", "木下", "杉山", "横山", "荒木", "宮崎",
    "大塚", "星野", "今井", "武田", "千葉", "堀", "関", "水野", "丸山", "矢野",
]
FIRST_NAMES_M = [
    "太郎", "一郎", "健太", "拓海", "翔太", "和彦", "正之", "誠", "大輔", "浩二",
    "隆", "修", "博", "剛", "亮", "勇気", "直人", "哲也", "雄一", "慎一",
    "俊介", "達也", "光司", "康平", "祐介", "賢二", "徹", "悠介", "武史", "敬介",
    "蓮", "湊", "樹", "颯真", "律", "陸", "朝陽", "結翔", "悠真", "凛太郎",
    "龍之介", "壮馬", "航", "匠", "奏", "暖", "新", "蒼", "碧", "陽翔",
]
FIRST_NAMES_F = [
    "花子", "美咲", "陽子", "恵子", "裕子", "真由美", "あゆみ", "さくら", "千尋", "由美",
    "智子", "麻衣", "友香", "理恵", "綾", "奈々", "彩", "美穂", "沙織", "菜々子",
    "里奈", "佳奈", "有紀", "明日香", "優子", "純子", "真希", "亜矢", "瑞穂", "詩織",
    "凛", "紬", "陽葵", "芽依", "澪", "結菜", "杏", "莉子", "琴音", "日和",
    "楓", "柚希", "心春", "乃愛", "咲良", "桜", "凪", "葵", "栞", "茜",
]

# ─── 年齢レンジ（口調タイプ別）─────────────────────────────────────
AGE_RANGES = {
    "authority": (45, 65),
    "worker":    (30, 50),
    "youth":     (18, 28),
    "outsider":  (35, 55),
    "lurker":    (20, 70),
}

# ─── MBTI 役割×立場 推奨マッピング ────────────────────────────────
MBTI_ROLE_MAP = {
    "authority": {
        "推進派": ["ENTJ", "ESTJ", "ENFJ"],
        "反対派": ["ISTJ", "INTJ", "INFJ"],
        "中立":   ["ESTJ", "ISFJ", "ENFJ"],
        "懐疑":   ["INTJ", "INTP", "ISTJ"],
    },
    "worker": {
        "推進派": ["ESTP", "ESFJ", "ENFP"],
        "反対派": ["ISFJ", "ISTJ", "ISTP"],
        "中立":   ["ISFP", "ESFP", "ISFJ"],
        "懐疑":   ["ISTP", "INTP", "INFP"],
    },
    "youth": {
        "推進派": ["ENFP", "ENTP", "ESFP"],
        "反対派": ["INFP", "ISFP", "INTP"],
        "中立":   ["ISFP", "INFP", "ESFP"],
        "懐疑":   ["INTP", "ENTP", "INTJ"],
    },
    "outsider": {
        "推進派": ["ENTJ", "ESTJ", "ENTP"],
        "反対派": ["ISTJ", "INTJ", "ISFJ"],
        "中立":   ["ESTJ", "ESFJ", "ISTJ"],
        "懐疑":   ["INTJ", "INTP", "ISTP"],
    },
    "lurker": {
        "推進派": ["INFJ", "INTJ", "INTP"],
        "反対派": ["INFP", "INTP", "INTJ"],
        "中立":   ["INFJ", "INFP", "INTP"],
        "懐疑":   ["INTP", "INTJ", "ISTP"],
    },
}

# ─── MBTI ガイダンス文（プロンプト共通） ────────────────────────────
MBTI_GUIDANCE = """
MBTIの選び方:
- ENTJ/ESTJ: リーダー気質、目標志向、組織をまとめる
- INTJ/INTP: 分析的、批判的思考、独立思考者
- ENFP/ENTP: 創造的、新しいアイデア好き、議論好き
- ISFJ/ISTJ: 堅実、伝統重視、規律正しい
- INFP/INFJ: 理想主義、価値観重視、共感力高い
- ESTP/ESFP: 行動派、実践重視、今この瞬間を生きる
- ISFP: 芸術的、穏やか、自分のペースを大事にする
- ESFJ: 社交的、人の役に立ちたい、調和重視
各エージェントの役割・性格・年齢に合ったMBTIを選んでください。
同じMBTIタイプが3人以上いないようにしてください。
"""

# ─── 年齢ガイダンス文（プロンプト共通） ────────────────────────────
AGE_GUIDANCE = """
年齢の目安（役割に合わせて設定）:
- authority: 45-65歳（教授・管理職は年配）
- worker: 30-50歳（現場の中堅）
- youth: 18-28歳（学生・若手）
- outsider: 35-55歳（企業・行政の実務者）
- lurker: 20-70歳（幅広い）
全員同じ年齢にしないこと。最低でも10歳以上の年齢差をつけること。
"""


def _select_mbti(tone: str, stance: str) -> str:
    """役割（口調タイプ）と立場に適したMBTIをランダムに選択"""
    candidates = MBTI_ROLE_MAP.get(tone, {}).get(stance, MBTI_TYPES)
    return random.choice(candidates)


def _deduplicate_mbti(llm_mbti: str, tone: str, existing_agents: list) -> str:
    """MBTIが2人以上被らないようにする"""
    used_mbtis = {}
    for a in existing_agents:
        used_mbtis[a.mbti] = used_mbtis.get(a.mbti, 0) + 1

    # LLMが返したMBTIが被ってなければそのまま
    if llm_mbti in MBTI_TYPES and used_mbtis.get(llm_mbti, 0) < 2:
        return llm_mbti

    # 使われていないMBTIから選ぶ
    available = [m for m in MBTI_TYPES if used_mbtis.get(m, 0) == 0]
    if not available:
        available = [m for m in MBTI_TYPES if used_mbtis.get(m, 0) < 2]
    if available:
        return random.choice(available)
    return random.choice(MBTI_TYPES)


def _normalize_name(name: str) -> str:
    """名前のスペース・全角半角を統一（スペースなし）"""
    return name.replace(" ", "").replace("　", "").strip()


def _generate_japanese_name(gender: str, used_names: Optional[set] = None) -> str:
    """日本人名をランダム生成（重複回避付き、苗字被りも防止）"""
    if used_names is None:
        used_names = set()
    first_pool = FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F

    # 既に使われてる苗字を収集
    used_lasts = set()
    for n in used_names:
        for last in LAST_NAMES:
            if n.startswith(last):
                used_lasts.add(last)
                break

    # 苗字が被らないように試行
    available_lasts = [l for l in LAST_NAMES if l not in used_lasts]
    if not available_lasts:
        available_lasts = LAST_NAMES  # 全部使い切ったらリセット

    for _ in range(50):
        last = random.choice(available_lasts)
        first = random.choice(first_pool)
        name = f"{last}{first}"
        if name not in used_names:
            used_names.add(name)
            return name

    name = f"{random.choice(available_lasts)}{random.choice(first_pool)}"
    used_names.add(name)
    return name


# ─── 掲示板投稿スタイル（5ch住民タイプ）────────────────────────────────
POSTING_STYLES = {
    "info_provider": {
        "label": "情報提供者",
        "description": "知識豊富、ソース付き、長文傾向。です/ます or だ/である調",
        "avg_length": "long",
        "anchor_rate": 0.3,
        "frequency": "medium",
        "weight": 0.10,
    },
    "debater": {
        "label": "レスバ戦士",
        "description": "攻撃的、反論好き、「お前」「はい論破」、短文連投",
        "avg_length": "short",
        "anchor_rate": 0.7,
        "frequency": "high",
        "weight": 0.08,
    },
    "joker": {
        "label": "ネタ師",
        "description": "面白い一言、皮肉、比喩表現、ネットスラング多用",
        "avg_length": "short",
        "anchor_rate": 0.2,
        "frequency": "medium",
        "weight": 0.10,
    },
    "questioner": {
        "label": "質問者",
        "description": "「〜ってどうなの？」「マジで？」素朴な疑問",
        "avg_length": "short",
        "anchor_rate": 0.4,
        "frequency": "low",
        "weight": 0.10,
    },
    "veteran": {
        "label": "古参",
        "description": "「にわかは黙ってろ」経験ベース、上から目線",
        "avg_length": "medium",
        "anchor_rate": 0.3,
        "frequency": "medium",
        "weight": 0.05,
    },
    "passerby": {
        "label": "通りすがり",
        "description": "1-2回だけ投稿、感想述べて去る",
        "avg_length": "short",
        "anchor_rate": 0.1,
        "frequency": "once",
        "weight": 0.15,
    },
    "emotional": {
        "label": "感情的反応者",
        "description": "「ワロタ」「マジかよ」「は？」感情ベースの短文",
        "avg_length": "very_short",
        "anchor_rate": 0.5,
        "frequency": "medium",
        "weight": 0.15,
    },
    "storyteller": {
        "label": "自分語り",
        "description": "「俺の場合は〜」「うちでは〜」体験談ベース中〜長文",
        "avg_length": "medium",
        "anchor_rate": 0.2,
        "frequency": "low",
        "weight": 0.10,
    },
    "agreeer": {
        "label": "同意マン",
        "description": "「それな」「これ」「ほんこれ」「>>X わかる」",
        "avg_length": "very_short",
        "anchor_rate": 0.6,
        "frequency": "medium",
        "weight": 0.12,
    },
    "contrarian": {
        "label": "逆張り",
        "description": "多数派と逆の意見、「みんな〜って言うけど実は〜」",
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
    """重み付きランダムで投稿スタイルを選択"""
    styles = list(POSTING_STYLES.keys())
    weights = [POSTING_STYLES[s]["weight"] for s in styles]
    return random.choices(styles, weights=weights, k=1)[0]


# 口調タイプ定義
TONE_STYLES = {
    "authority": {
        "label": "権威層",
        "description": "教授・部長・管理職。丁寧だが断定的。敬語ベース、長文。",
        "post_interval_min": 3,
        "post_interval_max": 5,
    },
    "worker": {
        "label": "実務層",
        "description": "技術員・事務職・中間管理職。現場感のある標準語。です/ます混在。",
        "post_interval_min": 2,
        "post_interval_max": 3,
    },
    "youth": {
        "label": "若手層",
        "description": "学生・若手職員。なんJ寄りカジュアル。関西弁混じり。",
        "post_interval_min": 1,
        "post_interval_max": 2,
    },
    "outsider": {
        "label": "外部者",
        "description": "業者・派遣会社・行政。ビジネス丁寧語。定型表現、本音を隠す。",
        "post_interval_min": 5,
        "post_interval_max": 10,
    },
    "lurker": {
        "label": "ROM専",
        "description": "観察者。たまに鋭い一言。低頻度だが核心を突く。",
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
    posting_style: str = "emotional"      # POSTING_STYLES のキー
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


PERSON_PERSONA_PROMPT = """5ch住民のキャラ設計。JSONのみ返せ。

名前:{name} 説明:{description} 立場:{stance} 役割:{role}
テーマ:{theme} 争点:{key_issues}

JSON:
{{"bio":"プロフ50字","persona":"性格と口調と立場を200字で","age":整数,"gender":"male/female","mbti":"XXXX","profession":"職業","interested_topics":["話題1","話題2"],"tone_style":"authority/worker/youth/outsider/lurker","stance":{{"position":"賛成/反対/中立","reason":"理由30字"}},"hidden_agenda":"本音30字","trigger_topics":["トピック1"]}}""".format(
    name="{name}",
    description="{description}",
    stance="{stance}",
    role="{role}",
    theme="{theme}",
    key_issues="{key_issues}",
)

ORG_PERSONA_PROMPT = """組織の掲示板代表アカウント設計。JSONのみ返せ。

名前:{name} 説明:{description} 立場:{stance} 役割:{role}
テーマ:{theme} 争点:{key_issues}

JSON:
{{"bio":"公式プロフ50字","persona":"組織の立場と発言スタイル200字","age":45,"gender":"other","mbti":"XXXX","profession":"職能","interested_topics":["分野1","分野2"],"tone_style":"authority/outsider","stance":{{"position":"公式立場","reason":"根拠30字"}},"hidden_agenda":"本音30字","trigger_topics":["トピック1"]}}""".format(
    name="{name}",
    description="{description}",
    stance="{stance}",
    role="{role}",
    theme="{theme}",
    key_issues="{key_issues}",
)


def _is_valid_japanese_person_name(name: str) -> bool:
    """
    名前が有効な日本人のフルネームかどうかを判定する。
    - 最低2文字以上8文字以下
    - 既知の姓リストに一致する接頭辞を持つ
    - 概念語・役割語でないこと
    """
    if not name or len(name) < 2 or len(name) > 8:
        return False
    # 概念語・役割語ブラックリスト
    CONCEPT_WORDS = [
        "大学", "学校", "学部", "研究", "自由", "環境", "経済", "政治", "科学",
        "技術", "学生", "教員", "教授", "職員", "組合", "委員", "組織", "団体",
        "企業", "会社", "行政", "市民", "住民", "支持", "反対", "推進", "慎重",
        "保守", "革新", "保護", "利用", "推進派", "反対派", "懐疑派", "中立派",
        "ベテラン", "若手", "管理職", "現場", "外部", "内部", "関係者",
    ]
    for word in CONCEPT_WORDS:
        if word in name:
            return False
    # 既知の姓リストに一致する接頭辞を持つかチェック
    for last in LAST_NAMES:
        if name.startswith(last) and len(name) > len(last):
            return True
    return False


def _make_username(name: str, agent_id: int) -> str:
    """掲示板ID（コテハン）を生成"""
    import unicodedata
    # ASCII以外は除去してローマ字風に
    clean = "".join(c for c in name if c.isascii() and (c.isalnum() or c in "_-"))
    if not clean:
        clean = f"agent{agent_id:03d}"
    suffix = random.randint(100, 999)
    return f"{clean[:12]}_{suffix}"


def _parse_structured_persona(persona: str) -> dict:
    """[tag]value|[tag]value形式のペルソナから個別セクションを抽出する。
    自由文ペルソナにも対応（キーワードベースで部分抽出）"""
    result = {
        "emotional_wound": "",
        "information_bias": "",
        "speech_patterns": [],
        "debate_tactics": "",
        "social_position": "",
    }
    
    if not persona:
        return result
    
    # 自由文ペルソナからの簡易抽出（タグなし形式）
    if "[" not in persona:
        # 口癖らしきものを抽出（「〜」パターン）
        import re as _re
        speech_matches = _re.findall(r'「([^」]{2,20})」', persona)
        if speech_matches:
            result["speech_patterns"] = speech_matches[:4]
        # トラウマ・コンプレックスキーワード
        wound_kw = ["トラウマ", "コンプレックス", "恐れ", "不安", "経験から", "目撃した", "押し付け"]
        for kw in wound_kw:
            idx = persona.find(kw)
            if idx != -1:
                result["emotional_wound"] = persona[max(0,idx-20):idx+60].strip()
                break
        # 情報バイアス
        bias_kw = ["日経", "朝日", "読売", "NHK", "Twitter", "5ch", "ネット", "専門誌", "現場の情報"]
        for kw in bias_kw:
            if kw in persona:
                result["information_bias"] = kw
                break
        return result
    
    # [tag]value|[tag]value... 形式をパース
    sections = persona.split("|")
    for section in sections:
        section = section.strip()
        if not section.startswith("["):
            continue
        
        # [tag]を抽出
        if "]" not in section:
            continue
        tag_end = section.index("]")
        tag = section[1:tag_end]  # [と]を除去
        value = section[tag_end+1:].strip()
        
        if tag == "wound" and not result["emotional_wound"]:
            result["emotional_wound"] = value[:100]
        elif tag == "bias" and not result["information_bias"]:
            result["information_bias"] = value[:100]
        elif tag == "speech" and not result["speech_patterns"]:
            # 「」や・で分割
            patterns = []
            for sep in ["・", "、", "「", "」"]:
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
    """職業が空・概念名の場合、toneに応じたデフォルトを返す"""
    if prof and len(prof) >= 2 and prof not in ("不明", "なし", ""):
        return prof
    defaults = {
        "authority": random.choice(["大学教授", "学部長", "研究科長", "副学長", "部門長"]),
        "worker": random.choice(["事務職員", "技術職員", "研究員", "図書館司書", "システム管理者"]),
        "youth": random.choice(["大学生", "大学院生", "研究室学生", "学部3年生", "修士1年"]),
        "outsider": random.choice(["IT企業社員", "フリーランス", "行政職員", "NPO職員", "記者"]),
        "lurker": random.choice(["無職", "自営業", "主婦", "定年退職者", "パート"]),
    }
    return defaults.get(tone, "会社員")


# 立場の分散パターン（賛成・反対・中立をバランスよく）
STANCE_CYCLE = [
    {"position": "賛成", "reason": "AI活用で教育の質が向上する"},
    {"position": "反対", "reason": "学生の思考力が低下する恐れ"},
    {"position": "中立", "reason": "条件付きで認めるべき"},
    {"position": "反対", "reason": "不正行為の温床になる"},
    {"position": "賛成", "reason": "時代の流れに逆らえない"},
    {"position": "懐疑", "reason": "効果が不明で判断できない"},
    {"position": "賛成", "reason": "業務効率化に不可欠"},
    {"position": "反対", "reason": "プライバシーやセキュリティが心配"},
]


def _assign_stance(llm_stance: Any, idx: int, total: int) -> Dict[str, str]:
    """立場を分散。LLMが返したらそれを使うが、全員同じにならないようcycleで補完"""
    if isinstance(llm_stance, dict) and llm_stance.get("position"):
        return llm_stance
    return STANCE_CYCLE[idx % len(STANCE_CYCLE)]


def _assign_tone(entity: Dict[str, Any]) -> str:
    """エンティティ情報からデフォルトの口調タイプを推定"""
    desc = (entity.get("description", "") + entity.get("attributes", {}).get("role", "")).lower()
    if any(kw in desc for kw in ["教授", "部長", "管理", "執行", "理事", "学長", "長"]):
        return "authority"
    if any(kw in desc for kw in ["学生", "若手", "２０代", "20代"]):
        return "youth"
    if any(kw in desc for kw in ["業者", "派遣", "行政", "委員", "外部"]):
        return "outsider"
    if entity.get("type") in ("organization", "concept"):
        return "authority"
    return "worker"


def _replace_bad_agents(llm: "OracleLLMClient", theme: str, key_issues: list):
    """bad評価のエージェントを削除して新しいエージェントに入れ替え"""
    try:
        from db.database import db_conn
        with db_conn() as conn:
            bad_rows = conn.execute("SELECT id, name FROM persistent_agents WHERE rating='bad'").fetchall()
            if not bad_rows:
                return
            bad_names = [r["name"] for r in bad_rows]
            print(f"[ProfileGenerator] 👎 {len(bad_names)}人を入れ替え: {', '.join(bad_names)}")
            for r in bad_rows:
                conn.execute("DELETE FROM persistent_agents WHERE id=?", (r["id"],))
    except Exception as e:
        print(f"[ProfileGenerator] bad入れ替え失敗: {e}")


def _row_to_agent(row: dict, idx: int, total: int, key_issues: list) -> OracleAgent:
    """DB行 → OracleAgent変換ヘルパー"""
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
        country="日本",
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
    """stock_agents.json を一度だけ読み込んでキャッシュ"""
    global _stock_agents_cache
    if _stock_agents_cache is None:
        path = _os.path.abspath(_STOCK_AGENTS_PATH)
        if _os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _stock_agents_cache = json.load(f)
            print(f"[ProfileGenerator] ✅ ストックエージェント {len(_stock_agents_cache)}名を読み込み")
        else:
            _stock_agents_cache = []
            print(f"[ProfileGenerator] ⚠️ stock_agents.json が見つかりません: {path}")
    return _stock_agents_cache


def _stock_agent_to_oracle(s: dict, idx: int, total: int, key_issues: list, stance_override: Optional[dict] = None) -> OracleAgent:
    """stock_agents.json の1エントリ → OracleAgent 変換"""
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
        country="日本",
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
    """ストックエージェントからランダム選択して OracleAgent リストを返す。
    DBにエージェントが存在する場合はDBのis_activeを優先する。"""
    # まずDBからアクティブなエージェントを取得（is_active=1 のみ）
    try:
        from db.database import get_persistent_agents
        db_agents = [a for a in get_persistent_agents(limit=200, include_bad=False) if a.get("is_active", 1) == 1]
        if db_agents:
            selected = random.sample(db_agents, min(agent_count, len(db_agents)))
            agents = []
            for idx, row in enumerate(selected):
                agents.append(_row_to_agent(row, idx, len(selected), key_issues))
            print(f"[ProfileGenerator] 📦 ストックエージェント(DB) {len(agents)}名を選択 (アクティブ:{len(db_agents)}名中)")
            return agents
    except Exception as e:
        print(f"[ProfileGenerator] DB取得失敗、JSONフォールバック: {e}")

    # DBが空またはエラーの場合はstock_agents.jsonから読み込み
    stock = _load_stock_agents()
    if not stock:
        return []
    selected = random.sample(stock, min(agent_count, len(stock)))
    agents = []
    for idx, s in enumerate(selected):
        agents.append(_stock_agent_to_oracle(s, idx, len(selected), key_issues))
    print(f"[ProfileGenerator] 📦 ストックエージェント(JSON) {len(agents)}名を選択")
    return agents


def _try_reuse_persistent_agents(scale: str, custom_agents: Optional[int], key_issues: list, theme: str) -> tuple:
    """永続保存済みエージェントから再利用を試みる。
    Returns: (reused_agents: list, shortage: int) — shortageが0なら全員揃った"""
    try:
        from db.database import get_persistent_agents
        agent_count = custom_agents or {"mini": 5, "full": 12, "auto": 8}.get(scale, 8)

        # bad評価のエージェントを先に削除
        _replace_bad_agents(None, theme, key_issues)

        cached = [a for a in get_persistent_agents(limit=agent_count + 20, include_bad=False) if a.get("is_active", 1) == 1]

        if not cached:
            return ([], agent_count)  # 全員新規生成

        # ランダムに選択（足りない分はshortageとして返す）
        selected = random.sample(cached, min(agent_count, len(cached)))
        agents = []
        for idx, row in enumerate(selected):
            agents.append(_row_to_agent(row, idx, agent_count, key_issues))

        shortage = max(0, agent_count - len(agents))
        return (agents, shortage)
    except Exception as e:
        print(f"[ProfileGenerator] 永続エージェント再利用失敗: {e}")
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
    エンティティデータからエージェントを生成する。
    reuse_agents=True の場合、永続保存済みエージェントを優先的に使い回す。
    """
    entities = entity_data.get("entities", [])
    theme = entity_data.get("theme", "")
    key_issues = entity_data.get("key_issues", [])

    # ストックエージェントを最優先で使用
    if reuse_agents:
        agent_count = custom_agents or {"mini": 5, "full": 12, "auto": 8}.get(scale, 8)
        stock_agents = _try_reuse_stock_agents(agent_count, key_issues)
        if stock_agents:
            # スタンスをテーマに合わせて上書き
            for idx, agent in enumerate(stock_agents):
                agent.stance = _assign_stance({}, idx, len(stock_agents))
            print(f"[ProfileGenerator] 📦 ストックエージェント {len(stock_agents)}人で確定 ⚡")
            return stock_agents

    # 永続エージェントの再利用を試みる（ストックが空の場合のフォールバック）
    reused_agents = []
    if reuse_agents:
        reused_agents, shortage = _try_reuse_persistent_agents(scale, custom_agents, key_issues, theme)
        if reused_agents and shortage == 0:
            print(f"[ProfileGenerator] 永続エージェント {len(reused_agents)}人を再利用 ⚡")
            return reused_agents
        elif reused_agents and shortage > 0:
            print(f"[ProfileGenerator] 永続エージェント {len(reused_agents)}人を再利用 + {shortage}人を新規生成")
            # 不足分は以下のフローで生成。custom_agentsをshortageに上書き
            custom_agents = shortage
            scale = "custom"
        # reused_agents が空 → 全員新規生成（通常フロー続行）

    # agent_roles が指定されている場合はロールベース生成
    if agent_roles:
        print(
            f"[ProfileGenerator] ロール指定モード: {sum(r.get('count', 1) for r in agent_roles)}エージェント",
            flush=True,
        )
        return _generate_agents_from_roles(agent_roles, theme, key_issues, llm)

    # スケールに応じてエージェント数を決定
    if scale == "mini":
        target_count = min(len(entities), 8)
    elif scale == "full":
        target_count = min(max(len(entities), 20), 50)
    else:  # custom
        target_count = custom_agents or len(entities)

    # エンティティが少なすぎる場合は全部使う
    selected = entities[:target_count] if len(entities) >= target_count else entities

    # full/custom スケールではエンティティを拡張（同一エンティティから複数エージェント）
    if scale in ("full", "custom") and len(entities) < target_count:
        extra_needed = target_count - len(entities)
        # 既存エンティティを重複させて拡張（後で微妙に差分をつける）
        for i in range(extra_needed):
            base = entities[i % len(entities)].copy()
            base["name"] = f"{base['name']}_{i+2}"
            selected.append(base)

    # --- バッチ生成: グループ化（4-5人ずつ）でAPI呼び出し削減 ---
    profiles_list = []
    batch_size = 3  # Nemotron 30B: 3 agents per batch
    used_names: set = set()

    for batch_idx in range(0, len(selected), batch_size):
        batch_entities = selected[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (len(selected) + batch_size - 1) // batch_size

        print(f"[ProfileGenerator] バッチ {batch_num}/{total_batches}: {len(batch_entities)}エージェント生成中...")

        # バッチ内エンティティ情報をまとめる（拡張版）
        entity_list_text_enhanced = "\n".join(
            f"{i+1}. 【{e['name']}】type={e.get('type','person')} / "
            f"説明:{e.get('description','')[:80]} / "
            f"立場:{e.get('attributes',{}).get('stance','不明')} / "
            f"口調:{e.get('_tone','worker')}"
            for i, e in enumerate(batch_entities)
        )

        batch_prompt = f"""テーマ「{theme}」（争点:{', '.join(key_issues[:2])}）の5ch住民ペルソナ。

口調タイプ:
- authority: 教授・管理職。「〜と考えます」「結論から申し上げると」
- worker: 技術員・事務職。「現場としては」「正直なところ」
- youth: 学生・若手。なんJ語「草」「それな」「ワイは〜」
- outsider: 外部者。「弊社としましては」「ご検討いただければ」
- lurker: ROM専。短文「結局」「本質は」

投稿スタイル: info_provider/debater/joker/questioner/veteran/passerby/emotional/storyteller/agreeer/contrarian

{entity_list_text_enhanced}

nameは日本人フルネーム必須（田中太郎形式）。概念名禁止。
personaは[identity]〜|[backstory]〜|[personality]〜|[wound]〜|[speech]〜|[board]〜|[stance_detail]〜|[hidden]〜|[trigger]〜|[bias]〜|[social]〜|[tactics]〜|[memory]〜|[quirk]〜 の形式で800字以上書け。改行禁止。

JSON配列で返せ（説明不要）:
[{{"name":"田中太郎","bio":"プロフ80字以内","persona":"[identity]...の構造化ペルソナ800字以上","age":30,"gender":"male","mbti":"INTJ","profession":"職業","interested_topics":["話題1","話題2"],"tone_style":"worker","posting_style":"debater","stance":{{"position":"賛成","reason":"理由50字","confidence":0.7}},"hidden_agenda":"本音40字","trigger_topics":["トピック1","トピック2"],"emotional_wound":"トラウマ40字","information_bias":"信じる情報源40字","speech_patterns":["口癖1","口癖2","口癖3"],"debate_tactics":"議論戦略30字","social_position":"年収帯・世代40字"}}]"""

        try:
            messages = [
                {"role": "system", "content": "JSON配列のみ返せ。説明不要。"},
                {"role": "user", "content": batch_prompt},
            ]
            raw = llm.chat(messages, temperature=0.8)
            match = re.search(r'\[[\s\S]*\]', raw)
            if match:
                batch_profiles = json.loads(match.group())
                profiles_list.extend(batch_profiles)
                print(f"[ProfileGenerator] バッチ {batch_num} 成功: {len(batch_profiles)}エージェント")
            else:
                raise ValueError("JSON array not found")
        except Exception as e:
            print(f"[ProfileGenerator] バッチ {batch_num} 失敗: {e} — フォールバック使用")
            for e_data in batch_entities:
                profiles_list.append(
                    _fallback_profile(e_data, e_data.get("type") == "person", used_names)
                )

    agents = []
    for idx, entity in enumerate(selected):
        # 一括生成結果からマッチするプロファイルを探す
        profile_data = None
        for p in profiles_list:
            if p.get("name") == entity["name"] or p.get("index") == idx + 1:
                profile_data = p
                break
        if profile_data is None and idx < len(profiles_list):
            profile_data = profiles_list[idx]
        if profile_data is None:
            profile_data = _fallback_profile(entity, entity.get("type") == "person", used_names)

        # personaから構造化セクションを抽出（LLMが個別フィールドで返さない場合のフォールバック）
        persona_text = profile_data.get("persona", "")
        if persona_text:
            parsed_sections = _parse_structured_persona(persona_text)
            # profile_dataにマージ（個別フィールドが空の場合のみ）
            for key, value in parsed_sections.items():
                existing = profile_data.get(key)
                is_empty = not existing or (isinstance(existing, list) and len(existing) == 0) or (isinstance(existing, str) and len(existing.strip()) == 0)
                if is_empty and value:
                    profile_data[key] = value
        
        # フィールド補完（全エージェントを個性的に）
        attrs = entity.get("attributes", {})
        # tone_style: LLM指定があればそれ、なければエンティティから推定、さらに無ければランダム
        tone_style = profile_data.get("tone_style", "")
        if tone_style not in TONE_STYLES:
            tone_style = _assign_tone(entity)
        # 全員同じtoneにならないよう、2人以上同じtoneなら強制変更
        tone_counts = {}
        for a in agents:
            tone_counts[a.tone_style] = tone_counts.get(a.tone_style, 0) + 1
        if tone_counts.get(tone_style, 0) >= 2:
            available = [t for t in TONE_STYLES if tone_counts.get(t, 0) < 1]
            if not available:
                available = [t for t in TONE_STYLES if tone_counts.get(t, 0) < 2]
            if available:
                tone_style = random.choice(available)
        # gender: LLM指定があればそれ、なければランダム（50:50）
        gender = profile_data.get("gender", "")
        if gender not in ("male", "female"):
            gender = _pick_gender(tone_style)
        # age: LLM指定があればそれ、なければtoneに応じたランダム
        age = profile_data.get("age", random.randint(*AGE_RANGES.get(tone_style, (22, 55))))

        # ── 名前の決定（全エージェントに日本人名を強制）──────────────
        llm_name = _normalize_name(profile_data.get("name", ""))
        if llm_name and _is_valid_japanese_person_name(llm_name) and llm_name not in used_names:
            name = llm_name
            used_names.add(name)
        elif _is_valid_japanese_person_name(_normalize_name(entity.get("name", ""))) and _normalize_name(entity["name"]) not in used_names:
            name = _normalize_name(entity["name"])
            used_names.add(name)
        else:
            # 概念名・組織名・重複 → 日本人名を生成
            gender_for_name = gender if gender in ("male", "female") else random.choice(["male", "female"])
            name = _generate_japanese_name(gender_for_name, used_names)

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
            country=profile_data.get("country", "日本"),
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

    # 永続エージェントの再利用分と結合
    if reused_agents:
        # IDを再割り当て（重複防止）
        for i, a in enumerate(agents):
            a.agent_id = len(reused_agents) + i
        all_agents = reused_agents + agents
        print(f"[ProfileGenerator] 計{len(all_agents)}エージェント（再利用{len(reused_agents)} + 新規{len(agents)}）")
        return all_agents

    print(f"[ProfileGenerator] {len(agents)}エージェント生成完了")
    return agents


def _generate_agents_from_roles(
    agent_roles: List[Dict[str, Any]],
    theme: str,
    key_issues: List[str],
    llm: OracleLLMClient,
) -> List["OracleAgent"]:
    """
    パラメータプランナーのロール指定からエージェントを生成する。

    agent_roles 例:
      [{"role": "大学教員", "tone": "authority", "stance": "推進派", "count": 2}, ...]
    """
    # ロールを個別エージェントスペックに展開
    specs: List[Dict[str, Any]] = []
    for role_spec in agent_roles:
        for _ in range(max(1, int(role_spec.get("count", 1)))):
            specs.append({
                "role": role_spec.get("role", "参加者"),
                "tone": role_spec.get("tone", "worker"),
                "stance": role_spec.get("stance", "中立"),
            })

    # バッチ生成（5人ずつ）
    profiles_list: List[Dict[str, Any]] = []
    batch_size = 3  # Nemotron 30B: 3 agents per batch
    used_names: set = set()

    for batch_idx in range(0, len(specs), batch_size):
        batch_specs = specs[batch_idx: batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        total_batches = (len(specs) + batch_size - 1) // batch_size

        print(
            f"[ProfileGenerator] ロールバッチ {batch_num}/{total_batches}: "
            f"{len(batch_specs)}エージェント生成中...",
            flush=True,
        )

        spec_list_text = "\n".join(
            f"{i + 1}. 役割: {s['role']} / 口調: {s['tone']} / 立場: {s['stance']}"
            for i, s in enumerate(batch_specs)
        )

        batch_prompt = f"""テーマ「{theme}」（争点:{', '.join(key_issues[:2])}）の5ch住民ペルソナ。

{spec_list_text}

nameは日本人フルネーム必須（例:佐藤花子）。概念名禁止。

JSON配列で返せ:
[{{"name":"佐藤花子","bio":"プロフ50字","persona":"性格口調立場200字","age":30,"gender":"female","mbti":"ENFP","profession":"職業","interested_topics":["話題"],"tone_style":"worker","stance":{{"position":"賛成","reason":"理由"}},"hidden_agenda":"本音","trigger_topics":["トピック"]}}]"""

        try:
            messages = [
                {
                    "role": "system",
                    "content": "JSON配列のみ返せ。説明不要。",
                },
                {"role": "user", "content": batch_prompt},
            ]
            raw = llm.chat(messages, temperature=0.8)
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                batch_profiles = json.loads(match.group())
                profiles_list.extend(batch_profiles)
                print(
                    f"[ProfileGenerator] ロールバッチ {batch_num} 成功: {len(batch_profiles)}エージェント",
                    flush=True,
                )
            else:
                raise ValueError("JSON array not found")
        except Exception as e:
            print(
                f"[ProfileGenerator] ロールバッチ {batch_num} 失敗: {e} — フォールバック使用",
                flush=True,
            )
            for s in batch_specs:
                profiles_list.append(
                    _fallback_profile_from_spec(s, theme, key_issues, used_names)
                )

    # profiles_list → OracleAgent に変換
    agents: List[OracleAgent] = []
    for idx, spec in enumerate(specs):
        profile_data = profiles_list[idx] if idx < len(profiles_list) else \
            _fallback_profile_from_spec(spec, theme, key_issues, used_names)

        tone_style = profile_data.get("tone_style", spec["tone"])
        if tone_style not in TONE_STYLES:
            tone_style = spec["tone"]

        # 名前: 日本人名を強制、重複排除
        name = profile_data.get("name", "")
        if not name or name == spec["role"] or name in TONE_STYLES or not _is_valid_japanese_person_name(name) or name in used_names:
            gender_hint = profile_data.get("gender", "")
            if gender_hint not in ("male", "female"):
                gender_hint = _pick_gender(tone_style)
            name = _generate_japanese_name(gender_hint, used_names)

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
            country="日本",
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

    print(f"[ProfileGenerator] ロールベース生成完了: {len(agents)}エージェント", flush=True)
    return agents


def _fallback_profile_from_spec(
    spec: Dict[str, Any],
    theme: str,
    key_issues: List[str],
    used_names: Optional[set] = None,
) -> Dict[str, Any]:
    """ロールスペックからフォールバックプロファイルを生成"""
    if used_names is None:
        used_names = set()
    tone = spec.get("tone", "worker")
    stance = spec.get("stance", "中立")
    role = spec.get("role", "参加者")

    # gender: tone別の確率分布
    gender = _pick_gender(tone)
    name = _generate_japanese_name(gender, used_names)
    age = random.randint(*AGE_RANGES.get(tone, (25, 50)))
    mbti = _select_mbti(tone, stance)

    persona_snippets = {
        "authority": f"大学・組織の管理職として{theme}に関わる。丁寧な言葉遣いだが主張は明確。",
        "worker":    f"現場の実務担当として{theme}の影響を直接受ける立場にある。",
        "youth":     f"学生・若手として{theme}に興味を持ち、自分なりの意見を発信する。",
        "outsider":  f"外部の立場から{theme}を観察し、ビジネス視点で関与する。",
        "lurker":    f"普段は静観しているが、{theme}の核心を鋭く突く発言をすることがある。",
    }

    return {
        "name": name,
        "bio": f"{role}（{stance}）",
        "persona": persona_snippets.get(tone, f"{role}として{theme}に関わる人物。立場: {stance}。"),
        "age": age,
        "gender": gender,
        "mbti": mbti,
        "profession": role,
        "interested_topics": (key_issues[:3] if key_issues else ["議論"]),
        "tone_style": tone,
        "stance": {"position": stance, "reason": ""},
        "hidden_agenda": "",
        "trigger_topics": [],
    }


def _fallback_profile(entity: Dict[str, Any], is_individual: bool, used_names=None) -> Dict[str, Any]:
    """LLM失敗時のフォールバック（構造化ペルソナ付き）"""
    attrs = entity.get("attributes", {})
    tone = _assign_tone(entity)
    name = entity.get("name", "不明")
    description = entity.get("description", "")
    stance = attrs.get("stance", "中立")

    speech_templates = {
        "authority": ["結論から申し上げると", "エビデンスとしては", "私の立場からは"],
        "worker": ["現場としては", "正直なところ", "実際やってみると"],
        "youth": ["草", "それな", "ワイは"],
        "outsider": ["弊社としましては", "ご検討いただければ", "一般論として"],
        "lurker": ["結局", "本質は", "まあ"],
    }
    speech = speech_templates.get(tone, [""])

    persona = (
        f"[identity]{name}は{attrs.get('role', '関係者')}|"
        f"[backstory]{description[:60] if description else 'テーマに関心がある'}|"
        f"[personality]標準的な性格・論理的思考|"
        f"[wound]特になし|"
        f"[speech]{'・'.join(speech)}|"
        f"[board]通常の頻度で書き込む|"
        f"[stance_detail]立場:{stance}|"
        f"[hidden]特になし|"
        f"[trigger]批判されると反応|"
        f"[bias]一般的なメディア|"
        f"[social]一般的な立場|"
        f"[tactics]論理的に反論|"
        f"[memory]特筆すべきエピソードなし|"
        f"[quirk]特になし"
    )

    candidates = TONE_POSTING_AFFINITY.get(tone, list(POSTING_STYLES.keys()))
    posting = random.choice(candidates)

    return {
        "bio": description[:200] if description else f"{name}の公式アカウント",
        "persona": persona,
        "age": random.randint(25, 50) if is_individual else 30,
        "gender": "male" if is_individual else "other",
        "mbti": random.choice(MBTI_TYPES),
        "profession": attrs.get("role", "関係者"),
        "interested_topics": ["政策", "教育", "技術"],
        "tone_style": tone,
        "posting_style": posting,
        "stance": {"position": stance, "reason": "", "confidence": 0.5},
        "hidden_agenda": "",
        "trigger_topics": [],
        "emotional_wound": "",
        "information_bias": "",
        "speech_patterns": speech,
        "debate_tactics": "状況に応じて対応",
        "social_position": "",
    }


def _pick_gender(tone: str) -> str:
    """口調タイプに応じた性別をランダム選択（確率分布付き）"""
    # tone別の male 出現確率（残りは female）
    male_prob = {
        "authority": 0.70,
        "worker":    0.60,
        "youth":     0.60,
        "outsider":  0.55,
        "lurker":    0.50,
    }
    p = male_prob.get(tone, 0.55)
    return "male" if random.random() < p else "female"
