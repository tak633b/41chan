"""1エージェントのペルソナ生成テスト（バッチなし）"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.llm_client import OracleLLMClient

llm = OracleLLMClient()

prompt = """テーマ「ChatGPTと大学教育」の5ch住民ペルソナを1人生成せよ。

## キャラクター仕様
- 職業: 大学教授（48歳・男性）
- 口調: authority（「〜と考えます」「結論から申し上げると」）
- 立場: AI利用に慎重・批判的
- 投稿スタイル: debater

## 出力フォーマット（JSON1件のみ）
{
  "name": "日本人フルネーム",
  "age": 48,
  "gender": "male",
  "mbti": "INTJ",
  "bio": "プロフィール80字以内",
  "profession": "職業詳細",
  "tone_style": "authority",
  "posting_style": "debater",
  "persona": "2000字以上の詳細なキャラクター背景。居住地、学歴、経歴、性格、行動パターン、議論スタイル、重要な人生経験、信条を含める",
  "stance": {"position": "反対", "reason": "理由50字", "confidence": 0.8},
  "hidden_agenda": "本音40字",
  "emotional_wound": "トラウマ・コンプレックス40字",
  "information_bias": "信じる情報源・メディア偏向",
  "speech_patterns": ["口癖1", "口癖2", "口癖3"],
  "debate_tactics": "議論戦略30字",
  "social_position": "年収帯・世代・地域性"
}

JSONのみ返せ。説明不要。"""

print("=== ペルソナ生成テスト（qwen3.5:4b, 1エージェント） ===")
print("生成中...\n")

messages = [
    {"role": "system", "content": "JSONのみ返せ。説明不要。"},
    {"role": "user", "content": prompt},
]

import time
t0 = time.time()
raw = llm.chat(messages, temperature=0.85)
elapsed = time.time() - t0

print(f"【生成時間: {elapsed:.1f}秒】\n")
print("--- 生成結果（raw） ---")
print(raw[:3000])
print()

# JSON解析
import json, re
try:
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        data = json.loads(match.group())
        print("--- パース結果 ---")
        print(f"name: {data.get('name')}")
        print(f"persona chars: {len(data.get('persona', ''))}")
        print(f"persona[:500]: {data.get('persona','')[:500]}")
        print(f"emotional_wound: {data.get('emotional_wound')}")
        print(f"speech_patterns: {data.get('speech_patterns')}")
        print(f"debate_tactics: {data.get('debate_tactics')}")
        print(f"social_position: {data.get('social_position')}")
    else:
        print("JSON解析失敗 — JSONが見つからない")
except Exception as e:
    print(f"JSON解析エラー: {e}")
