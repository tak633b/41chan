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
- **LLM**: ZAI GLM-4.7

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
