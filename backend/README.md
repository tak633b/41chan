# 41ch Backend

FastAPI ベースのバックエンドサーバー。

## セットアップ

```bash
cd backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env を編集
```

## 起動

```bash
venv/bin/uvicorn main:app --reload --port 8000
```

## 環境変数

[`.env.example`](.env.example) を `.env` にコピーして設定:

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `ORACLE_LLM_BACKEND` | LLMバックエンド | `ollama` |
| `ORACLE_ZAI_API_KEY` | ZAI APIキー | — |
| `ORACLE_ZAI_MODEL` | ZAIモデル | `glm-5` |
| `ORACLE_OLLAMA_MODEL` | Ollamaモデル | `qwen3.5:9b` |
| `OPENROUTER_API_KEY` | OpenRouter APIキー | — |
| `OPENROUTER_MODEL` | OpenRouterモデル | `nvidia/nemotron-3-super-120b-a12b:free` |

## モジュール構成

```
backend/
├── main.py                 # FastAPIアプリ（エントリポイント）
├── api/                    # APIルーター
│   ├── simulation.py       # シミュレーションCRUD
│   ├── board.py            # 板・スレッド取得
│   ├── stream.py           # SSEストリーミング
│   ├── report.py           # レポート取得
│   └── ask.py              # 質問機能
├── core/                   # コアモジュール
│   ├── llm_client.py       # LLM統一クライアント（ZAI/Ollama/OpenRouter）
│   ├── entity_extractor.py # シードテキスト → エンティティ抽出
│   ├── profile_generator.py # エンティティ → エージェントプロファイル生成
│   ├── board_simulator.py  # 5ch風投稿シミュレーション
│   ├── reporter.py         # 分析レポート生成（2段階）
│   ├── parameter_planner.py # シミュレーションパラメータ自動計画
│   └── memory_manager.py   # エージェント記憶管理（SQLite + ChromaDB）
├── services/               # ビジネスロジック
│   ├── simulation_runner.py # シミュレーション全体の実行制御
│   ├── board_generator.py  # 板・スレッド生成
│   └── question_handler.py # 質問処理
├── models/                 # Pydanticスキーマ
│   └── schemas.py
├── agents/                 # ストックエージェントデータ
│   └── stock_agents.json   # 事前定義済みエージェント
├── db/                     # データベース
│   └── database.py         # SQLite操作
└── requirements.txt        # Python依存パッケージ
```

## 主要モジュールの役割

### `core/llm_client.py` — LLMクライアント

ZAI / Ollama / OpenRouter を統一インターフェースで切替。自動リトライ、レート制限対応、`<think>` タグ除去を内蔵。

### `core/entity_extractor.py` — エンティティ抽出

シードテキストを分析し、関連する人物・組織・概念と争点を抽出。

### `core/profile_generator.py` — プロファイル生成

エンティティ情報から5ch住民のリアルなペルソナを生成。MBTI・口調・投稿スタイルの分散、日本人名の自動生成を行う。

### `core/board_simulator.py` — 掲示板シミュレーター

スレッド単位で5ch風の投稿を生成。アンカー返信、AA、ネットスラングなどリアルな掲示板文化を再現。

### `core/reporter.py` — レポーター

シミュレーション結果から2段階の分析レポートを生成。Step1で構造化データ（JSON）、Step2で詳細分析（マークダウン）。

### `core/memory_manager.py` — メモリマネージャー

エージェントの記憶をSQLiteで時系列管理。ChromaDB（オプション）によるセマンティック検索にも対応。

### `services/simulation_runner.py` — シミュレーション実行

バックグラウンドで非同期にシミュレーション全体を実行。SSEイベントキューを通じてフロントエンドにリアルタイム配信。

## 依存パッケージ

- `fastapi` — Webフレームワーク
- `uvicorn` — ASGIサーバー
- `openai` — OpenAI互換APIクライアント（ZAI/OpenRouter用）
- `pydantic` — データバリデーション
- `chromadb` — ベクトルDB（オプション）
- `python-multipart` — ファイルアップロード
