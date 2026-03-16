"""2段階生成テスト（Ollama qwen3.5:4b）"""
import sys, os, json, re, time
sys.path.insert(0, os.path.dirname(__file__))

os.environ["ORACLE_LLM_BACKEND"] = "ollama"
os.environ["ORACLE_OLLAMA_MODEL"] = "qwen3.5:4b"

from core.llm_client import OracleLLMClient
llm = OracleLLMClient()

# ─── Step 1: 構造フィールドのみ（JSON小さく） ───
prompt1 = """テーマ「ChatGPTと大学教育」の5ch住民1人を生成せよ。

{
  "name": "日本人フルネーム",
  "age": 48,
  "gender": "male",
  "mbti": "INTJ",
  "bio": "80字以内のプロフィール",
  "profession": "職業詳細",
  "tone_style": "authority",
  "posting_style": "debater",
  "stance": {"position": "反対", "reason": "50字以内", "confidence": 0.8},
  "hidden_agenda": "40字以内",
  "emotional_wound": "40字以内",
  "information_bias": "信じる情報源",
  "speech_patterns": ["口癖1", "口癖2", "口癖3"],
  "debate_tactics": "30字以内",
  "social_position": "年収帯・世代・地域"
}

JSONのみ返せ。"""

print("=== Step 1: 構造フィールド生成 ===")
t0 = time.time()
raw1 = llm.chat([{"role": "user", "content": prompt1}], temperature=0.85)
print(f"時間: {time.time()-t0:.1f}秒")
print(raw1[:800])
print()

# Step1パース
try:
    m = re.search(r'\{[\s\S]*\}', raw1)
    profile = json.loads(m.group()) if m else {}
    print(f"パース: OK — {profile.get('name')}")
except Exception as e:
    print(f"パース失敗: {e}")
    profile = {"name": "田中俊介", "profession": "大学教授", "mbti": "INTJ", "stance": {"position": "反対"}}

# ─── Step 2: ペルソナ本文のみ（JSON制約なし）───
prompt2 = f"""以下のキャラクターの詳細な背景ストーリーを日本語で書け。
絶対に2000字以上書け。JSONは不要。文章だけ返せ。

キャラクター:
- 名前: {profile.get('name')}
- 職業: {profile.get('profession')}
- MBTI: {profile.get('mbti')}
- 立場: {profile.get('stance', {}).get('position')}
- テーマ: ChatGPTと大学教育

内容に必ず含めること:
1. 居住地・学歴・職歴（具体的に）
2. 性格と行動パターン（日常の過ごし方）
3. 議論スタイル（どう相手を攻撃するか）
4. 人生を変えた具体的なエピソード（1〜2個）
5. 信条・価値観
6. SNS・掲示板での投稿傾向"""

print("=== Step 2: ペルソナ本文生成（2000字目標）===")
t0 = time.time()
raw2 = llm.chat([{"role": "user", "content": prompt2}], temperature=0.9)
elapsed = time.time() - t0
print(f"時間: {elapsed:.1f}秒 | 文字数: {len(raw2)}字")
print()
print(raw2[:1000])
print("...")
print(raw2[-300:] if len(raw2) > 1300 else "")
