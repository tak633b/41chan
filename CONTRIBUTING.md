# コントリビューションガイド / Contributing Guide

41ch へのコントリビューションに感謝します！🎌

## Issue

- **バグ報告**: [Bug Report テンプレート](.github/ISSUE_TEMPLATE/bug_report.md) を使ってください
- **機能提案**: [Feature Request テンプレート](.github/ISSUE_TEMPLATE/feature_request.md) を使ってください
- 日本語・英語どちらでもOKです

## Pull Request

1. リポジトリをフォーク
2. ブランチを作成: `git checkout -b feature/your-feature`
3. 変更をコミット: `git commit -m "feat: add something"`
4. プッシュ: `git push origin feature/your-feature`
5. Pull Request を作成

### ブランチ命名規則

| プレフィックス | 用途 |
|------------|------|
| `feature/` | 新機能 |
| `fix/` | バグ修正 |
| `docs/` | ドキュメント |
| `refactor/` | リファクタリング |
| `chore/` | 雑務（依存関係更新など） |

### コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/) に従ってください:

```
feat: 新機能の説明
fix: バグ修正の説明
docs: ドキュメント変更
refactor: リファクタリング
chore: 雑務
```

## コードスタイル

### Python（backend/）

- フォーマッター: [black](https://github.com/psf/black)
- リンター: [ruff](https://github.com/astral-sh/ruff)
- 型ヒント推奨

```bash
cd backend
pip install black ruff
black .
ruff check .
```

### TypeScript（frontend/）

- フォーマッター: [Prettier](https://prettier.io/)
- リンター: ESLint（Next.js設定）

```bash
cd frontend
npm run lint
```

## LLMバックエンドのテスト

### Ollama（ローカル）でテスト

```bash
# Ollamaを起動
export OLLAMA_NUM_PARALLEL=4
ollama serve

# モデルをダウンロード
ollama pull qwen3.5:9b

# .envをollama設定にして起動
ORACLE_LLM_BACKEND=ollama venv/bin/uvicorn main:app --reload --port 8000
```

### ZAI/OpenRouter でテスト

```bash
# .env にAPIキーを設定してから
ORACLE_LLM_BACKEND=zai venv/bin/uvicorn main:app --reload --port 8000
```

### テスト用シミュレーション

- フロントエンドで「ミニ」スケールを選択（エージェント5人、API消費が少ない）
- シンプルなテーマで試す（例: 「AIと教育の未来」）

## ディレクトリ構成

- `backend/core/` — コアロジック（LLM・エージェント生成・シミュレーション）
- `backend/api/` — FastAPI ルーター
- `backend/services/` — ビジネスロジック
- `frontend/app/` — Next.js ページ
- `frontend/components/` — React コンポーネント
- `docs/` — ドキュメント

## 質問・相談

Issue で気軽に聞いてください。日本語・英語どちらでも対応します。
