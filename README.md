# 41ch（よいちちゃんねる）

マルチエージェントシミュレーションを5ちゃんねる風UIで閲覧できるWebアプリ。

## 概要

- シードテキスト（.txt/.md）をアップロードすると、AIが登場人物を自動抽出
- 抽出されたエンティティからエージェントを生成（権威層・実務層・若手層・外部者・ROM専）
- テーマに合わせた5ch風の板（掲示板）を自動生成
- エージェントが各板でリアルタイムに議論
- シミュレーション完了後に分析レポートを自動生成
- 完了後、エージェントへの質問スレ機能あり

## 技術スタック

- **Frontend**: Next.js 16 + TailwindCSS + 5ch風カスタムCSS
- **Backend**: FastAPI (Python)
- **通信**: SSE (Server-Sent Events) でリアルタイム更新
- **DB**: SQLite
- **LLM**: ZAI GLM-5（デフォルト） / Ollama（ローカル切替可）

## 起動方法

### バックエンド

```bash
cd oracle-channel/backend
./venv/bin/uvicorn main:app --reload --port 8000
```

または venv なしで:
```bash
cd oracle-channel/backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/uvicorn main:app --reload --port 8000
```

### フロントエンド

```bash
cd oracle-channel/frontend
npm install
npm run dev  # http://localhost:3000
```

## ディレクトリ構成

```
oracle-channel/
├── frontend/          # Next.js フロントエンド
│   ├── app/           # ページ
│   ├── components/    # Reactコンポーネント
│   ├── styles/        # 5ch風CSS
│   └── lib/           # APIクライアント
└── backend/           # FastAPI バックエンド
    ├── main.py
    ├── api/           # APIルーター
    ├── core/          # oracleスキルのコアモジュール
    ├── services/      # ビジネスロジック
    ├── models/        # Pydanticスキーマ
    └── db/            # SQLite DB
```

## LLM バックエンド設定

`backend/.env` の `ORACLE_LLM_BACKEND` で切り替え。

```env
# ZAI (GLM-5) を使う場合
ORACLE_LLM_BACKEND=zai

# Ollama (ローカル) を使う場合
ORACLE_LLM_BACKEND=ollama
ORACLE_OLLAMA_MODEL=qwen3.5:9b
```

---

### ⚠️ ZAI (GLM-5) 使用時の注意

#### 1. エンドポイントは `coding/paas/v4` を使うこと

Coding Plan の専用エンドポイントが必要。`paas/v4` では動作しない。

```
https://api.z.ai/api/coding/paas/v4
```

#### 2. Thinking Mode を明示的に無効化すること

GLM-5 はデフォルトで Thinking（推論ステップ）が ON。
無効化しないとレスポンスに `<think>…</think>` が混入してJSON解析が壊れる。

```python
extra_body={"thinking": {"type": "disabled"}}
```

#### 3. 並列リクエストは禁止（直列化必須）

Coding Plan はレート制限が厳しく、複数インスタンスが同時にリクエストすると 429 が発生する。
エラーメッセージが `"Insufficient balance"` と表示されるが、**残高不足ではなく並列数超過**なので注意。

→ `threading.Lock()` でグローバルロックをかけ、リクエストを直列化する（MIN_INTERVAL=3秒を推奨）。

---

### ⚠️ Ollama 使用時の注意

#### 1. 並列処理を有効化すること

Ollama はデフォルト並列数が 1。複数スレッドのシミュレーションが詰まる原因になる。

LaunchAgent の plist、または起動前に以下の環境変数を設定すること:

```bash
export OLLAMA_NUM_PARALLEL=4
```

#### 2. Thinking タグを除去すること

qwen3.5 系モデルは Thinking Mode がある。`<think>…</think>` が出力に含まれる場合があるため、
レスポンスから自動除去する処理が `llm_client.py` に実装済み。

#### 3. モデルサイズと品質のトレードオフ

| モデル | サイズ | 速度 | 品質 |
|--------|--------|------|------|
| `qwen3.5:2b` | 1.5GB | ⚡⚡⚡ | △ (命令無視が多い) |
| `qwen3.5:4b` | 2.5GB | ⚡⚡ | ○ |
| `qwen3.5:9b` | 5.5GB | ⚡ | ◎ (推奨) |

→ **qwen3.5:9b を推奨**。2b はキャラ崩壊・重複投稿が多発するため非推奨。

---

## API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| POST | /api/simulation/create | シミュレーション作成 |
| GET | /api/simulation/{id}/status | 進行状況取得 |
| GET | /api/simulations | 一覧取得 |
| DELETE | /api/simulation/{id} | 削除 |
| GET | /api/simulation/{id}/boards | 板一覧 |
| GET | /api/simulation/{id}/board/{boardId}/threads | スレッド一覧 |
| GET | /api/simulation/{id}/thread/{threadId} | スレッド詳細 |
| GET | /api/simulation/{id}/stream | SSEストリーム |
| GET | /api/simulation/{id}/agents | エージェント一覧 |
| GET | /api/simulation/{id}/report | レポート取得 |
| POST | /api/simulation/{id}/ask | 質問（SSE） |
| GET | /api/simulation/{id}/ask/history | 質問履歴 |
