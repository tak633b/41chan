"""
Oracle 掲示板シミュレーター（5ch文化対応版）
スレッド単位でシミュレーション。スレタイに沿った議論・リアルな5ch文化を再現。
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
    """[tag]形式のペルソナから指定セクションを抽出して / 区切りで返す"""
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

# 掲示板フォーマット定数
BOARD_HEADER_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【{board_name}】{thread_title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
テーマ: {theme}
議題: {question}
"""

BATCH_ACTION_PROMPT_5CH = """あなたは丁寧なアシスタントではありません。5chの住民です。

【板名】{board_name}
【スレタイ】{thread_title}
【テーマ】{theme}
【議題/質問】{question}
【ラウンド】{round_num}

【これまでの流れ（直近{history_count}件）】
{recent_posts}

【参加エージェント一覧】
{agents_info}

━━━━ 絶対ルール ━━━━
■ 口調: 敬語・丁寧語は禁止。タメ口・ぞんざいな口調のみ。
■ レス長の厳守:
  - 1〜2行の超短いレス（「草」「それな」「ワロタ」「は？」「知らんがな」「嘘乙」「はい論破」など）: 60%以上
  - 2〜3行の普通のレス: 30%程度
  - 長文（3行超）: 10%以下。必ず先頭に「長文すまん」を付ける
■ >>N でアンカー返信を積極的に使う（前の投稿を具体的に引用・反応する）
■ 同意だけでなく、煽り・反論・茶化し・スルーを混ぜる
■ AA OK: 「草」「ｗｗｗ」「キタ━━(ﾟ∀ﾟ)━━!!」など
■ 5ch的表現を使う: 「草」「それな」「ワロタ」「マジで？」「嘘乙」「は？」「知らんがな」「ガチ勢か」「センス無い」
■ 日本語のみ。英語は一切使うな。データや統計も日本語で書け。
■ 「マジかよ 草 ワロタ」「それな」だけの投稿禁止。議題について具体的な内容を書け。
■ 全員違う内容を書け。同じフレーズの繰り返し禁止。
■ 冒頭フレーズの多様化: 同じ書き出しを連続させるな。冒頭は毎回違う表現にすること。前回と同じ1語目で始めるな。

{first_round_hint}
今回は{post_count_target}件の投稿を生成してください。
エージェント一覧から適切な人物を選んで発言させてください（同一エージェントが複数回発言してもよい）。

出力は以下のJSON配列のみ（コードブロックや説明文は一切不要）:

[
  {{
    "agent_name": "エージェント名（上記一覧から選ぶ）",
    "username": "名無しさん＠{board_name}",
    "content": "投稿内容（敬語禁止、短く）",
    "anchor_to": null,
    "emotion": "neutral",
    "round_num": {round_num}
  }}
]

anchor_to は直前のレス番号（整数、例: 3）または null。
emotionは neutral/excited/angry/thoughtful/dismissive/amused のいずれか。

【AAの使い方】
contentの末尾にAAを付けてよい。ただし「投稿の感情・内容と一致する場合のみ」「joker/emotional/agreeer タイプのみ」「30%以下の確率で」。
意味が合わないなら付けない。AAの種類は感情に合わせること:
- 興奮・キタ系: キタ━━━(ﾟ∀ﾟ)━━━!! ヽ(ﾟ∀ﾟ)ﾉ
- 怒り・ゴルァ系: ヽ(`Д´)ﾉ ( ﾟДﾟ)ｺﾞﾙｧ!! m9(^Д^)
- 笑い系: ( ´,_ゝ｀)プッ (´∀｀)ｗ
- 落ち込み: orz OTL
- 呆れ: (´・ω・｀) ( ﾟдﾟ)ﾊｧ?
- 思案: （´-`）.｡oO
必ずJSON配列のみで回答してください。"""


# 投稿スタイル別の具体的指示（必ず議題の内容に触れること）
STYLE_INSTRUCTIONS = {
    "info_provider": "議題について具体的な数字・事例・ニュースを挙げて説明する。3〜6行。",
    "debater":       ">>Nの意見の具体的な弱点・見落とし・反例を挙げて反論する。冒頭フレーズは毎回全く異なる視点から始めること。1〜3行。",
    "joker":         "議題を茶化す・例え話にする。真面目に答えない。",
    "questioner":    "議題について素朴な疑問を投げる。",
    "veteran":       "上から目線で議題への持論を語る。経験ベース。",
    "passerby":      "議題への率直な一言感想。1行で消える。",
    "emotional":     "議題への感情的リアクション。内容に必ず触れること。短文だが具体的に言及すること。",
    "storyteller":   "議題に関連する体験談を語る。具体的なエピソード。中文。",
    "agreeer":       "直前の投稿の具体的な部分に同意する。相手の内容を引用して同意。",
    "contrarian":    "多数派と逆の立場を取る。具体的な根拠付き。",
}

# 感情別AAセット（5ch伝統 + 2ch AA辞典）
AA_BY_EMOTION = {
    "excited": [
        "キタ━━━(ﾟ∀ﾟ)━━━!!",
        "ｷﾀ━(ﾟ∀ﾟ)━!",
        "ヽ(ﾟ∀ﾟ)ﾉ",
        "(´∀｀*)ウェ━ハハハ!!",
        "+　　　+\n　 ∧＿∧ 　+\n　（0ﾟ・∀・）　　　ﾜｸﾜｸﾃｶﾃｶ\n　（0ﾟ∪ ∪ +\n　と＿_）__）　+",
        " n ∧＿∧\n(ﾖ（´∀｀　） ｸﾞｯｼﾞｮﾌﾞ!\n　Y 　　　つ",
    ],
    "angry": [
        "ヽ(`Д´)ﾉ",
        "( ﾟДﾟ)ｺﾞﾙｧ!!",
        "m9(^Д^)",
        "( `皿´)",
        "　　 ∧∧　　／￣￣￣￣￣\n　(,,ﾟДﾟ)＜　ゴルァ！\n ⊂　　⊃　＼＿＿＿＿＿\n～|　　|\n　 し`J",
        "　　＿＿＿_∧∧　　／￣￣￣￣￣￣￣￣\n～'　＿＿__(,,ﾟДﾟ)＜　逝ってよし！\n　 ＵU 　 　Ｕ U　　　＼＿＿＿＿＿＿＿＿",
        "　 ∧＿∧　ﾊﾟｰﾝ\n（　・∀・）\n　　⊂彡☆))Д´)",
    ],
    "amused": [
        "( ´,_ゝ｀)プッ",
        "(´∀｀)ｗ",
        "ﾌﾞﾌﾞｯ",
        "（笑）",
        " ∧＿∧　ﾊﾟｰﾝ\n（　・∀・）\n　　⊂彡☆))Д´)",
        " ∧＿∧　　／￣￣￣￣￣\n（　´∀｀）＜　オマエモナー\n（　　　　） 　＼＿＿＿＿＿\n｜ ｜　|\n（_＿）＿）",
    ],
    "dismissive": [
        "(´・ω・｀)",
        "やれやれ (´-ω-｀)",
        "( ﾟдﾟ)ﾊｧ?",
        "しらんがな (´_ゝ｀)",
        "　 ∧＿∧　　　／￣￣￣￣\n　（ ´･ω･)　＜　ショボーン\n　（ つ旦と）　　＼＿＿＿＿\n　と＿）＿）",
        "　　( ﾟдﾟ )　ｶﾞﾀｯ\n　　.r　　 ヾ\n＿_|_|　/￣￣￣/＿\n　　＼/　　　　 /\n　　　　￣￣￣",
    ],
    "thoughtful": [
        "（´-`）.｡oO（…）",
        "ﾑ(｀・ω・´)ﾑ",
        "ﾒﾓﾒﾓ(ΦωΦ)ﾒﾓﾒﾓ",
        " 　　　*　　　　　　*\n　＊　　　　　＋　　うそです\n 　　 n ∧＿∧　n\n＋　(ﾖ（* ´∀｀）E)\n 　 　 Y 　　　 Y　　　　＊",
        "　 ∧＿∧ +　+\n（　・∀・）　　 +　　　\n（　　　　つ旦　　\n｜ ｜　|\n（_＿）＿）",
    ],
    "neutral": [
        "　 ∧＿∧\n　（　´∀｀）＜ ぬるぽ",
        "　 　　　＿＿＿_\n　 　　　／　　 　 　＼\n　　　／　 _ノ 　ヽ､_　 ＼\n　 ／ oﾟ(（●）) (（●）)ﾟo ＼ \n　 |　　　　 （__人__）'　　　　|\n　 ＼　　 　　｀⌒´ 　 　 ／",
    ],
}
# 汎用・状況依存AA（落ち込み・驚き・定番レス）
AA_GENERAL = [
    "orz", "OTL", "Σ(ﾟДﾟ)", "(ry", "なんだこれ…w", "以上チラ裏",
    "　　　 ∧ ∧＿__\n 　／(*ﾟーﾟ)　／＼\n／|￣∪∪￣|＼／\n 　|　 しぃ 　 |／\n 　 ￣￣￣￣",
    "　　　　 　　／⌒ヽ\n⊂二二二（　＾ω＾）二⊃\n　　　　　　|　　　 / 　　　　　　ﾌﾞｰﾝ\n　　 　　　 （　ヽノ\n　　　　　　 ﾉ>ノ\n　　 三　　レﾚ",
    "　 ∧＿∧\n　（　´∀｀）＜ ぬるぽ",
    "　　Λ＿Λ　　＼＼\n　 （　・∀・）　　　|　|　ｶﾞｯ\n　と　　　　）　 　 |　|\n　　 Ｙ　/ノ　　　 人\n　　　 /　）　 　 < 　>_Λ∩\n　 ＿/し'　／／. Ｖ｀Д´）/\n　（＿フ彡　　　　　 　　/",
    "　 ∩＿＿＿∩\n　　 | ノ　　　　　 ヽ\n　　/　　●　　　● |　クマ──！！\n　 |　　　　( _●_)　 ミ\n　彡､　　　|∪|　　､｀＼\n/　＿＿　 ヽノ　/´>　 )\n(＿＿＿）　　　/　(_／",
]

def _ngram_jaccard(a: str, b: str, n: int = 3) -> float:
    """文字n-gramのJaccard係数で類似度を計算（0.0〜1.0）"""
    if not a or not b:
        return 0.0
    set_a = {a[i:i+n] for i in range(len(a) - n + 1)}
    set_b = {b[i:i+n] for i in range(len(b) - n + 1)}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _is_too_similar(content: str, candidates: List[str], threshold: float = 0.35) -> bool:
    """過去投稿リストのいずれかとthreshold以上類似していればTrue"""
    for past in candidates:
        if _ngram_jaccard(content, past) >= threshold:
            return True
    return False


def _similarity_score(content: str, candidates: List[str]) -> float:
    """過去投稿との最大類似度スコアを返す"""
    if not candidates:
        return 0.0
    return max(_ngram_jaccard(content, past) for past in candidates)


def _maybe_aa(emotion: str, posting_style: str) -> str:
    """posting_styleがjoker/emotionalの時だけランダムでAA挿入（30%確率）"""
    if posting_style not in ("joker", "emotional", "agreeer"):
        return ""
    if random.random() > 0.30:
        return ""
    candidates = AA_BY_EMOTION.get(emotion, []) + (AA_GENERAL if random.random() > 0.5 else [])
    return random.choice(candidates) if candidates else ""


# アンカー率に応じたヒント
def _anchor_hint(anchor_rate: float) -> str:
    if anchor_rate >= 0.5:
        return "できるだけ>>Nでアンカーをつけて返信する。"
    elif anchor_rate >= 0.3:
        return "必要なら>>Nでアンカーをつける。"
    else:
        return "アンカーは使わなくてもOK。"


# 1人1ターン方式プロンプト（スタイル別）
SINGLE_POST_PROMPT = """【匿名住人として投稿】
立場: {stance_position} | タイプ: {style_label}
{style_instruction}

板: {board_name} | 議題: {question}

【スレの流れ】
{recent_posts}

{own_posts_hint}{extra_hint}■絶対ルール: 日本語のみ。英語禁止。敬語禁止。議題の具体的な内容に触れること。自分の過去の投稿と違う切り口で書け。投稿内容に人名を書くな（匿名掲示板）。冒頭フレーズを前回と変えること（同じ書き出しの繰り返し厳禁）。{anchor_hint}
■AAは「joker/emotional/agreeer」タイプのみ、内容と感情が一致する場合だけ末尾に付けてよい（30%以下）。合わないなら付けない。
JSON: {{"content":"投稿内容（末尾に意味が合うAAを付けてよい）","anchor_to":番号またはnull,"emotion":"neutral/excited/angry/amused/dismissive"}}"""


class BoardSimulator:
    """5ch文化対応 掲示板シミュレーター（スレッド単位）"""

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
        self.theme = entity_data.get("theme", "議論テーマ")
        self.key_issues = entity_data.get("key_issues", [])
        self.question = question
        self.memory = memory_manager
        self.llm = llm
        self.scale = scale
        self.board_name = board_name or "名無し板"
        self.thread_title = thread_title or self.theme

        # ラウンド数の優先順位:
        #   1. rounds_per_thread (パラメータプランナー決定値)
        #   2. custom_rounds (ユーザー指定)
        #   3. scale 固定値 (mini=2, full=5, それ以外=2)
        if rounds_per_thread is not None:
            self.num_rounds = rounds_per_thread
        elif custom_rounds:
            self.num_rounds = custom_rounds
        elif scale == "mini":
            self.num_rounds = 2
        elif scale == "full":
            self.num_rounds = 5
        else:
            self.num_rounds = 2

        self.on_post_generated = on_post_generated
        self.posts: List[Dict[str, Any]] = []
        self.post_counter = 0
        self._passerby_posted: set = set()  # 通りすがりエージェントの投稿済み追跡

        # 疑似日時（掲示板の書き込み時刻）
        self.base_time = datetime(2026, 3, 12, 9, 0, 0)
        self.time_offset = 0  # 分単位

        # 過去シミュレーション投稿キャッシュ（類似度チェック用）
        # sim_idはSimulationRunnerから外部注入される想定。Noneなら全体から取得
        self.sim_id: Optional[str] = None
        self._past_posts_cache: Dict[str, List[str]] = {}  # agent_name → contents

    # ------------------------------------------------------------------
    # 過去投稿キャッシュ & 類似度チェック
    # ------------------------------------------------------------------

    def _get_past_posts(self, agent_name: str) -> List[str]:
        """エージェントの過去シミュ投稿をキャッシュ付きで取得"""
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
        """今のシミュレーション内でそのエージェントが投稿した内容リストを返す"""
        return [p["content"] for p in self.posts if p.get("agent_name") == agent_name]

    def _check_and_maybe_regenerate(
        self,
        agent: OracleAgent,
        content: str,
        round_num: int,
        post_index: int,
        max_retry: int = 3,
        extra_candidates: Optional[List[str]] = None,
    ) -> str:
        """過去投稿・今シミュ内投稿（他エージェント含む）と類似していたら再生成（最大max_retry回）"""
        past_db = self._get_past_posts(agent.name)
        past_cur = self._get_current_sim_own_posts(agent.name)
        # 同一スレッド内の直近5投稿（他エージェント含む）もチェック対象に
        recent_all = [p["content"] for p in self.posts[-5:]]
        # 同一バッチ内投稿も含める
        batch_posts = extra_candidates if extra_candidates else []
        all_past = past_db + past_cur + recent_all + batch_posts

        if not all_past:
            return content

        for attempt in range(max_retry):
            score = _similarity_score(content, all_past)
            if score < 0.35:
                break
            # 類似している実際の投稿を最大2件フィードバックとして渡す
            similar_examples = sorted(
                all_past,
                key=lambda p: _ngram_jaccard(content, p),
                reverse=True,
            )[:2]
            forbidden_hint = "\n".join(f"- {s[:60]}" for s in similar_examples)
            print(f"  [SimilarityCheck] {agent.name} 類似検出 score={score:.2f} (attempt {attempt+1}) — 再生成")
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
    # メインループ
    # ------------------------------------------------------------------

    def _generate_thread_opener(self):
        """>>1 スレ立て投稿を生成してself.postsに追加する"""
        prompt = f"""あなたは5chの掲示板でスレを立てた人物です。
スレタイと議題の概要を>>1として書いてください。

【板名】{self.board_name}
【スレタイ】{self.thread_title}
【テーマ】{self.theme}
【議題/質問】{self.question}

━━━━ 絶対ルール ━━━━
■ 敬語禁止。タメ口・ぞんざいな口調のみ。
■ 3〜6行程度。長すぎない。
■ スレタイの背景・問題意識・議論してほしい内容を簡潔に書く。
■ 最後に「以下、議論どうぞ」「ではどうぞ」など一言添える。
■ 「1 ：」「>>1」などの番号は書かない（システムが付与する）。
■ JSON等の形式は不要。本文テキストのみ出力。
"""
        try:
            result = self.llm.chat(prompt)
            content = result.strip()
        except Exception as e:
            print(f"[BoardSim] スレ立て生成失敗: {e}")
            content = f"【{self.thread_title}】\nテーマ: {self.theme}\n議題: {self.question}\n以下、議論どうぞ。"

        post_time = self.base_time
        username = f"名無しさん＠{self.board_name}"
        post = {
            "num": 1,
            "agent_name": "スレ主",
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
        print(f"[BoardSim] >>1 スレ立て投稿生成完了")

        # リアルタイム emit コールバック
        if self.on_post_generated:
            self.on_post_generated(post)

    def run(self) -> str:
        """シミュレーションを実行し、掲示板ログ文字列を返す"""
        print(f"\n[BoardSim] 開始: {self.num_rounds}ラウンド, {len(self.agents)}エージェント")
        print(f"[BoardSim] 板: {self.board_name} | スレ: {self.thread_title}\n")

        # >>1: スレ立て投稿（テーマ概要を必ず書く）
        self._generate_thread_opener()

        for round_num in range(self.num_rounds):
            print(f"[BoardSim] Round {round_num + 1}/{self.num_rounds}")
            self._process_batch(round_num)

        print(f"[BoardSim] 完了: {self.post_counter}投稿生成\n")
        return self._format_thread()

    # ------------------------------------------------------------------
    # バッチ処理
    # ------------------------------------------------------------------

    def _build_posting_sequence(self, round_num: int, target_count: int) -> List[OracleAgent]:
        """べき乗則に基づいた投稿順序を生成（スタイル別頻度重み付き）"""
        # frequency → 1ラウンドの最大投稿数
        MAX_PER_ROUND = {"once": 1, "low": 1, "medium": 2, "high": 4}
        # frequency → 重み（高頻度ほど多く選ばれる）
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
                # 通りすがりはシミュレーション全体で1回のみ
                if freq == "once" and agent.name in self._passerby_posted:
                    continue
                count = agent_counts.get(agent.name, 0)
                if count >= MAX_PER_ROUND.get(freq, 2):
                    continue
                w = FREQ_WEIGHT.get(freq, 3)
                candidates.extend([agent] * w)

            if not candidates:
                break

            # 連続同一エージェント防止: 直前と同じエージェントを除いた候補を優先
            last_agent = sequence[-1] if sequence else None
            if last_agent is not None:
                non_repeat_candidates = [c for c in candidates if c.name != last_agent.name]
                # 代替候補があれば使う。全員同じ（= 1人しかいない）場合は仕方なく許容
                if non_repeat_candidates:
                    candidates = non_repeat_candidates

            agent = random.choice(candidates)
            sequence.append(agent)
            agent_counts[agent.name] = agent_counts.get(agent.name, 0) + 1

            p_style = getattr(agent, "posting_style", "emotional")
            freq = POSTING_STYLES.get(p_style, {}).get("frequency", "medium")
            if freq == "once":
                self._passerby_posted.add(agent.name)

            # バースト: レスバ戦士が即連投する（40%の確率）
            # ただし連続2回まで（3連投は禁止）
            if freq == "high" and random.random() < 0.4:
                cur = agent_counts.get(agent.name, 0)
                # 直前が同一エージェントなら連投しない
                prev = sequence[-2] if len(sequence) >= 2 else None
                already_consecutive = (prev is not None and prev.name == agent.name)
                if cur < MAX_PER_ROUND.get("high", 4) and len(sequence) < target_count and not already_consecutive:
                    sequence.append(agent)
                    agent_counts[agent.name] = cur + 1

        return sequence[:target_count]

    def _process_batch(self, round_num: int):
        """スタイル別頻度重み付きで投稿順を決定し、1エージェントずつ個別生成"""
        if self.scale == "mini":
            post_count_target = random.randint(6, 8)
        else:
            post_count_target = random.randint(12, 15)

        posting_agents = self._build_posting_sequence(round_num, post_count_target)

        i = 0
        while i < len(posting_agents):
            agent = posting_agents[i]
            post_data = self._generate_single_post(agent, round_num, i)

            if post_data is None:
                i += 1
                continue

            content = post_data.get("content", "").strip()
            # LLMが冒頭に >>N を出力することがある（anchor_to と二重になる）→ 除去
            content = re.sub(r'^>>\d+\s*', '', content).strip()
            if not content:
                i += 1
                continue

            self.post_counter += 1
            self.time_offset += random.randint(2, 15)
            post_time = self.base_time + timedelta(minutes=self.time_offset)

            username = f"名無しさん＠{self.board_name}"

            anchor_to = post_data.get("anchor_to")
            if anchor_to is not None:
                try:
                    anchor_to = int(anchor_to)
                    if anchor_to < 1 or anchor_to > self.post_counter - 1:
                        anchor_to = None
                except (ValueError, TypeError):
                    anchor_to = None

            emotion = post_data.get("emotion", "neutral")
            p_style = getattr(agent, "posting_style", "emotional")

            post = {
                "num": self.post_counter,
                "agent_name": agent.name,
                "username": username,
                "round_num": round_num,
                "timestamp": post_time.strftime("%Y/%m/%d %H:%M"),
                "action_type": "post",
                "anchor_to": anchor_to,
                "content": content,
                "emotion": emotion,
            }
            self.posts.append(post)

            # リアルタイムコールバック（定義されていれば呼ぶ）
            if self.on_post_generated:
                self.on_post_generated(post)

            self.memory.store(
                agent_id=agent.name,
                round_num=round_num,
                event_type="post",
                content=f"Round {round_num+1}: [{self.thread_title}] {content[:120]}",
                importance=0.7,
                related_agents=[a.name for a in self.agents if a.name != agent.name],
            )

            p_style = getattr(agent, "posting_style", "emotional")
            style_label = POSTING_STYLES.get(p_style, {}).get("label", p_style)
            print(f"  [{agent.name}/{style_label}] {content[:60]}...")

            i += 1

    def _generate_batch_posts(self, agents_batch: List[OracleAgent], round_num: int, start_index: int) -> List[Dict[str, Any]]:
        """2-3人分の投稿を1回のLLM呼び出しで生成"""
        recent_posts = self._get_recent_posts(8)

        agent_specs = []
        for j, agent in enumerate(agents_batch):
            p_style = getattr(agent, "posting_style", "emotional")
            style_info = POSTING_STYLES.get(p_style, {})
            style_label = style_info.get("label", "住人")
            style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
            anchor_rate = style_info.get("anchor_rate", 0.3)
            stance_pos = agent.stance.get("position", "中立") if isinstance(agent.stance, dict) else "中立"
            speech_str = "、".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
            tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
            # spec_lineには「内部ID」を使う（実名はcontentに漏れるのでここでは使わない）
            anon_id = f"住人{j+1:02d}"
            spec_line = f"{j+1}. {anon_id}（内部参照専用） | 立場:{stance_pos} | タイプ:{style_label} | {style_instruction}"
            if speech_str:
                spec_line += f" | 口癖:{speech_str}"
            if tactics_str:
                spec_line += f" | 議論戦略:{tactics_str}"
            agent_specs.append((agent.name, anon_id, spec_line))

        # agent_specsはタプル (agent.name, anon_id, spec_line) のリスト
        # agents_textにはanon_idを使い実名を渡さない
        agents_text = "\n".join(spec_line for _, _, spec_line in agent_specs)
        # 実名→anon_id のマッピング（後でname復元に使う）
        name_to_anon = {name: anon_id for name, anon_id, _ in agent_specs}
        anon_to_name = {anon_id: name for name, anon_id, _ in agent_specs}

        # >>1スレ立て投稿の直後（posts=1件）なら最初のレスは「>>1おつ」から始める
        extra_hint = ""
        if round_num == 0 and start_index == 0 and len(self.posts) == 1:
            extra_hint = "これはスレの最初のレス。「>>1おつ」から始めよ。\n"

        if len(agents_batch) == 1:
            agent = agents_batch[0]
            _, anon_id_single, spec_line_single = agent_specs[0]
            p_style = getattr(agent, "posting_style", "emotional")
            style_info = POSTING_STYLES.get(p_style, {})
            style_label = style_info.get("label", "住人")
            style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
            stance_pos = agent.stance.get("position", "中立") if isinstance(agent.stance, dict) else "中立"
            post_ctx = _extract_persona_sections(agent.persona, ["identity", "speech", "stance_detail", "tactics"])
            speech_str = "、".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
            tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
            spec_line_full = f"1. {anon_id_single} | 立場:{stance_pos} | タイプ:{style_label} | {style_instruction}"
            if speech_str:
                spec_line_full += f" | 口癖:{speech_str}"
            if tactics_str:
                spec_line_full += f" | 議論戦略:{tactics_str}"
            spec_line_full += f"\nペルソナ: {post_ctx}"
            # 自分の過去投稿（繰り返し防止）
            own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
            if own_posts:
                own_snippets = [f"- {p['content'][:100]}" for p in own_posts[-5:]]
                own_posts_hint = f"\n【{anon_id_single}の過去の投稿（同じ内容・フレーズは絶対禁止。全く異なる視点・切り口で書け）】\n" + "\n".join(own_snippets) + "\n"
            else:
                own_posts_hint = ""
            intro_line = f"次の人物が1投稿する。\n\n{spec_line_full}{own_posts_hint}"
        else:
            # 複数エージェントの場合も各自の過去投稿ヒントを追加
            own_posts_hints = []
            for agent, (_, anon_id_m, _) in zip(agents_batch, agent_specs):
                own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
                if own_posts:
                    own_snippets = [f"  - {p['content'][:80]}" for p in own_posts[-5:]]
                    own_posts_hints.append(f"【{anon_id_m}の過去投稿（繰り返し禁止・違う切り口で）】\n" + "\n".join(own_snippets))
            own_hints_str = ("\n\n" + "\n".join(own_posts_hints)) if own_posts_hints else ""
            intro_line = f"以下の{len(agents_batch)}人がそれぞれ1投稿する。\n\n{agents_text}{own_hints_str}"

        batch_prompt = f"""{intro_line}

板: {self.board_name} | 議題: {self.question}

【スレの流れ】
{recent_posts if recent_posts else "（まだ発言なし）"}

■絶対ルール:
- 日本語のみ。英語は一切使うな。
- 敬語禁止。タメ口のみ。
- 議題「{self.question}」の具体的な内容に必ず触れろ。
- 「マジかよ 草 ワロタ」「それな」だけの投稿禁止。議題について何か言え。
- 自分の過去投稿と同じ文言・フレーズの繰り返し禁止。毎回完全に違う切り口で書け。
- 前の投稿と同じフレーズの繰り返し禁止。全員違う内容を書け。
- 投稿内容に人名・固有名詞を書くな。匿名掲示板なので名前で呼ぶのは禁止。
- 冒頭フレーズを前回と絶対に変えること。同じ書き出しの繰り返し厳禁。毎回全く別の切り口から始めることを意識しろ。同じパターンの反論文1語目を変えただけの繰り返し厳禁。

{extra_hint}JSON配列で返せ（nameは住人IDのみ、contentに名前を含めるな）:
[{{"name":"住人ID（上記一覧から）","content":"投稿内容（名前を含めるな）","anchor_to":番号またはnull,"emotion":"neutral/excited/angry/amused/dismissive"}}]"""

        messages = [
            {"role": "system", "content": "5chの住民として日本語のみで投稿する。英語禁止。JSON配列のみ返す。投稿内容に人名を絶対に含めるな。"},
            {"role": "user", "content": batch_prompt},
        ]

        try:
            raw = self.llm.chat(messages, temperature=0.9)
            match = re.search(r'\[[\s\S]*?\]', raw)
            if match:
                posts = json.loads(match.group())
                # anon_id → 実名に復元してagent_nameを正しく設定
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
            print(f"  [BatchPost] バッチ生成失敗: {e} — 個別フォールバック")
            # フォールバック: 1人ずつ生成
            results = []
            for j, agent in enumerate(agents_batch):
                post = self._generate_single_post(agent, round_num, start_index + j)
                if post:
                    results.append(post)
            return results

    def _generate_single_post(self, agent: OracleAgent, round_num: int, post_index: int, forbidden_snippets: str = "") -> Optional[Dict[str, Any]]:
        """1エージェントの1投稿を生成（posting_style考慮）— フォールバック用"""
        recent_posts = self._get_recent_posts(8)

        p_style = getattr(agent, "posting_style", "emotional")
        style_info = POSTING_STYLES.get(p_style, {})
        style_label = style_info.get("label", "住人")
        style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
        anchor_rate = style_info.get("anchor_rate", 0.3)
        anchor_hint = _anchor_hint(anchor_rate)

        extra_hint = ""
        if round_num == 0 and post_index == 0 and len(self.posts) == 1:
            extra_hint = "これはスレの最初のレス。「>>1おつ」から始めよ。\n"

        # 自分の過去投稿を取得（繰り返し防止用）
        own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
        own_posts_hint = ""
        if own_posts:
            own_snippets = [f"- {p['content'][:80]}" for p in own_posts[-5:]]
            own_posts_hint = f"【自分の過去の投稿（これと違う内容を書け）】\n" + "\n".join(own_snippets) + "\n\n"
        if forbidden_snippets:
            own_posts_hint += f"【特にこれと似た内容を書くな（再生成）】\n{forbidden_snippets}\n\n"

        reply_ctx = _extract_persona_sections(agent.persona, ["trigger", "tactics", "hidden", "wound"])
        speech_str = "、".join(agent.speech_patterns[:3]) if hasattr(agent, 'speech_patterns') and agent.speech_patterns else ""
        tactics_str = agent.debate_tactics if hasattr(agent, 'debate_tactics') and agent.debate_tactics else ""
        extra_persona = ""
        if speech_str:
            extra_persona += f"口癖:{speech_str} "
        if tactics_str:
            extra_persona += f"議論戦略:{tactics_str} "
        if reply_ctx:
            extra_persona += f"ペルソナ:{reply_ctx}"

        messages = [
            {
                "role": "system",
                "content": "5chの住民として日本語のみで投稿する。英語禁止。JSONのみ返す。",
            },
            {
                "role": "user",
                "content": SINGLE_POST_PROMPT.format(
                    board_name=self.board_name,
                    question=self.question,
                    stance_position=agent.stance.get("position", "中立"),
                    style_label=style_label,
                    style_instruction=style_instruction,
                    anchor_hint=anchor_hint,
                    recent_posts=recent_posts if recent_posts else "（まだ発言なし）",
                    extra_hint=extra_hint + (f"{extra_persona}\n" if extra_persona else ""),
                    own_posts_hint=own_posts_hint,
                ),
            },
        ]

        try:
            raw = self.llm.chat(messages, temperature=0.9)
            # JSON抽出
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", raw, flags=re.IGNORECASE)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                data = json.loads(match.group(0))
                data["agent_name"] = agent.name
                return data
            else:
                print(f"  [{agent.name}] JSON抽出失敗: {raw[:100]}")
                return None
        except Exception as e:
            print(f"  [{agent.name}] 生成失敗: {e}")
            return None

    # ------------------------------------------------------------------
    # JSON配列パーサー
    # ------------------------------------------------------------------

    def _parse_posts_from_llm(self, content: str) -> List[Dict[str, Any]]:
        """LLM応答からJSON配列 [{...}] を抽出"""
        # コードブロックを除去
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", content, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()

        # [{...}] 形式のJSON配列を抽出（最初の [ から最後の ] まで）
        match = re.search(r'\[[\s\S]*\]', cleaned)
        if not match:
            print(f"[BoardSim] JSON配列が見つかりません。応答先頭200字: {content[:200]}")
            return []

        json_str = match.group(0)
        try:
            posts = json.loads(json_str)
            if isinstance(posts, list):
                return posts
        except json.JSONDecodeError:
            # 制御文字を除去して再試行
            json_str_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
            json_str_clean = re.sub(r"\s+", " ", json_str_clean)
            try:
                posts = json.loads(json_str_clean)
                if isinstance(posts, list):
                    return posts
            except json.JSONDecodeError as e:
                print(f"[BoardSim] JSON解析失敗: {e}. 先頭: {json_str[:200]}")

        return []

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    @staticmethod
    def _anon_id(agent_name: str) -> str:
        """エージェント名 → 5ch風匿名ID（8文字英数字）"""
        import hashlib
        h = int(hashlib.md5((agent_name + "oracle_salt").encode()).hexdigest(), 16)
        return format(h % (36 ** 8), "08x")  # 例: 01hmgtde

    def _get_recent_posts(self, n: int) -> str:
        """直近n件の発言を文字列化（5ch形式）— LLMへ渡すため本名を出さない"""
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
        """掲示板ログを5ch形式で整形— LLMへ渡すため本名を出さない"""
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
        lines.append(f"\n\n--- 総レス数: {self.post_counter} ---")
        return "\n".join(lines)
