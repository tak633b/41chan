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
必ずJSON配列のみで回答してください。"""


# 投稿スタイル別の具体的指示（必ず議題の内容に触れること）
STYLE_INSTRUCTIONS = {
    "info_provider": "議題について具体的な数字・事例・ニュースを挙げて説明する。「〜によると」「実際〜らしい」。3〜6行。",
    "debater":       ">>Nの意見の矛盾や弱点を具体的に指摘して反論。「いやそれは〜だろ」「〜が抜けてる」。1〜3行。",
    "joker":         "議題を茶化す・例え話にする。「〜みたいなもんだろ」「つまり〜ってことじゃんw」。真面目に答えない。",
    "questioner":    "議題について素朴な疑問を投げる。「そもそも〜ってどうなん？」「〜って実際どうよ」「ソースある？」",
    "veteran":       "「昔は〜だったんだよ」「にわか多すぎ」上から目線で議題への持論を語る。経験ベース。",
    "passerby":      "議題への率直な一言感想。「ふーん」「まあそうなるよな」「よくわからんけど大変そう」。1行で消える。",
    "emotional":     "議題への感情的リアクション。内容に必ず触れる。「え、マジで〜なの？やばくね」「〜って聞いてビビった」。短文だが中身あり。",
    "storyteller":   "「俺の知り合いが〜」「うちの会社では〜」議題に関連する体験談を語る。具体的なエピソード。中文。",
    "agreeer":       "直前の投稿の具体的な部分に同意する。「>>Nの〜って部分わかるわ」「〜はほんとそれ」。相手の内容を引用して同意。",
    "contrarian":    "多数派と逆の立場を取る。「みんな〜って言うけどさ、実際は〜だろ」「逆に考えると〜」。具体的な根拠付き。",
}

# アンカー率に応じたヒント
def _anchor_hint(anchor_rate: float) -> str:
    if anchor_rate >= 0.5:
        return "できるだけ>>Nでアンカーをつけて返信する。"
    elif anchor_rate >= 0.3:
        return "必要なら>>Nでアンカーをつける。"
    else:
        return "アンカーは使わなくてもOK。"


# 1人1ターン方式プロンプト（スタイル別）
SINGLE_POST_PROMPT = """【{agent_name}として投稿】
立場: {stance_position} | タイプ: {style_label}
{style_instruction}

板: {board_name} | 議題: {question}

【スレの流れ】
{recent_posts}

{own_posts_hint}{extra_hint}■絶対ルール: 日本語のみ。英語禁止。敬語禁止。議題の具体的な内容に触れること。自分の過去の投稿と違う切り口で書け。{anchor_hint}
JSON: {{"content":"投稿内容","anchor_to":番号またはnull,"emotion":"neutral/excited/angry/amused/dismissive"}}"""


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

        self.posts: List[Dict[str, Any]] = []
        self.post_counter = 0
        self._passerby_posted: set = set()  # 通りすがりエージェントの投稿済み追跡

        # 疑似日時（掲示板の書き込み時刻）
        self.base_time = datetime(2026, 3, 12, 9, 0, 0)
        self.time_offset = 0  # 分単位

    # ------------------------------------------------------------------
    # メインループ
    # ------------------------------------------------------------------

    def run(self) -> str:
        """シミュレーションを実行し、掲示板ログ文字列を返す"""
        print(f"\n[BoardSim] 開始: {self.num_rounds}ラウンド, {len(self.agents)}エージェント")
        print(f"[BoardSim] 板: {self.board_name} | スレ: {self.thread_title}\n")

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

            agent = random.choice(candidates)
            sequence.append(agent)
            agent_counts[agent.name] = agent_counts.get(agent.name, 0) + 1

            p_style = getattr(agent, "posting_style", "emotional")
            freq = POSTING_STYLES.get(p_style, {}).get("frequency", "medium")
            if freq == "once":
                self._passerby_posted.add(agent.name)

            # バースト: レスバ戦士が即連投する（40%の確率）
            if freq == "high" and random.random() < 0.4:
                cur = agent_counts.get(agent.name, 0)
                if cur < MAX_PER_ROUND.get("high", 4) and len(sequence) < target_count:
                    sequence.append(agent)
                    agent_counts[agent.name] = cur + 1

        return sequence[:target_count]

    def _process_batch(self, round_num: int):
        """スタイル別頻度重み付きで投稿順を決定し、2-3投稿バッチ生成"""
        if self.scale == "mini":
            post_count_target = random.randint(6, 8)
        else:
            post_count_target = random.randint(12, 15)

        posting_agents = self._build_posting_sequence(round_num, post_count_target)

        # 5人ずつバッチ生成（LLM呼び出し回数を1/5に削減）
        batch_size = 5
        i = 0
        while i < len(posting_agents):
            batch_agents = posting_agents[i:i+batch_size]
            batch_posts = self._generate_batch_posts(batch_agents, round_num, i)

            for bi, post_data in enumerate(batch_posts):
                agent = batch_agents[bi] if bi < len(batch_agents) else batch_agents[-1]
                content = post_data.get("content", "").strip()
                if not content:
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

                post = {
                    "num": self.post_counter,
                    "agent_name": agent.name,
                    "username": username,
                    "round_num": round_num,
                    "timestamp": post_time.strftime("%Y/%m/%d %H:%M"),
                    "action_type": "post",
                    "anchor_to": anchor_to,
                    "content": content,
                    "emotion": post_data.get("emotion", "neutral"),
                }
                self.posts.append(post)

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

            i += batch_size

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
            agent_specs.append(
                f"{j+1}. {agent.name} | 立場:{stance_pos} | タイプ:{style_label} | {style_instruction}"
            )

        agents_text = "\n".join(agent_specs)
        extra_hint = ""
        if round_num == 0 and start_index == 0:
            extra_hint = "1人目は「>>1おつ」から始める。\n"

        batch_prompt = f"""以下の{len(agents_batch)}人がそれぞれ1投稿する。

{agents_text}

板: {self.board_name} | 議題: {self.question}

【スレの流れ】
{recent_posts if recent_posts else "（まだ発言なし）"}

■絶対ルール:
- 日本語のみ。英語は一切使うな。
- 敬語禁止。タメ口のみ。
- 議題「{self.question}」の具体的な内容に必ず触れろ。
- 「マジかよ 草 ワロタ」「それな」だけの投稿禁止。議題について何か言え。
- 前の投稿と同じフレーズの繰り返し禁止。全員違う内容を書け。

{extra_hint}JSON配列で返せ:
[{{"name":"名前","content":"投稿内容","anchor_to":番号またはnull,"emotion":"neutral/excited/angry/amused/dismissive"}}]"""

        messages = [
            {"role": "system", "content": "5chの住民として日本語のみで投稿する。英語禁止。JSON配列のみ返す。"},
            {"role": "user", "content": batch_prompt},
        ]

        try:
            raw = self.llm.chat(messages, temperature=0.85)
            match = re.search(r'\[[\s\S]*?\]', raw)
            if match:
                posts = json.loads(match.group())
                return posts[:len(agents_batch)]
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

    def _generate_single_post(self, agent: OracleAgent, round_num: int, post_index: int) -> Optional[Dict[str, Any]]:
        """1エージェントの1投稿を生成（posting_style考慮）— フォールバック用"""
        recent_posts = self._get_recent_posts(8)

        p_style = getattr(agent, "posting_style", "emotional")
        style_info = POSTING_STYLES.get(p_style, {})
        style_label = style_info.get("label", "住人")
        style_instruction = STYLE_INSTRUCTIONS.get(p_style, "")
        anchor_rate = style_info.get("anchor_rate", 0.3)
        anchor_hint = _anchor_hint(anchor_rate)

        extra_hint = ""
        if round_num == 0 and post_index == 0:
            extra_hint = "最初の投稿なので「>>1おつ」から始める。\n"

        # 自分の過去投稿を取得（繰り返し防止用）
        own_posts = [p for p in self.posts if p.get("agent_name") == agent.name]
        own_posts_hint = ""
        if own_posts:
            own_snippets = [f"- {p['content'][:60]}" for p in own_posts[-3:]]
            own_posts_hint = f"【自分の過去の投稿（これと違う内容を書け）】\n" + "\n".join(own_snippets) + "\n\n"

        messages = [
            {
                "role": "system",
                "content": "5chの住民として日本語のみで投稿する。英語禁止。JSONのみ返す。",
            },
            {
                "role": "user",
                "content": SINGLE_POST_PROMPT.format(
                    agent_name=agent.name,
                    board_name=self.board_name,
                    question=self.question,
                    stance_position=agent.stance.get("position", "中立"),
                    style_label=style_label,
                    style_instruction=style_instruction,
                    anchor_hint=anchor_hint,
                    recent_posts=recent_posts if recent_posts else "（まだ発言なし）",
                    extra_hint=extra_hint,
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

    def _get_recent_posts(self, n: int) -> str:
        """直近n件の発言を文字列化（5ch形式）"""
        recent = self.posts[-n:] if len(self.posts) >= n else self.posts
        lines = []
        for p in recent:
            anchor = f" >>{p['anchor_to']}" if p.get("anchor_to") else ""
            lines.append(
                f">>{p['num']} {p['username']} (ID:{p['agent_name']}){anchor}\n"
                f"  {p['content'][:120]}"
            )
        return "\n".join(lines)

    def _format_thread(self) -> str:
        """掲示板ログを5ch形式で整形"""
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
            lines.append(
                f"\n{p['num']}: {p['username']} {p['timestamp']} ID:{p['agent_name']}"
                f"{anchor_str}\n  {p['content']}"
            )
        lines.append(f"\n\n--- 総レス数: {self.post_counter} ---")
        return "\n".join(lines)
