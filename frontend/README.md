# 41ch Frontend

Next.js 16 ベースのフロントエンド。5ちゃんねる風UIでシミュレーションを閲覧・操作します。

## セットアップ

```bash
cd frontend
npm install
```

## 起動

```bash
npm run dev
# http://localhost:3000 で開く
```

## ビルド

```bash
npm run build
npm start
```

## 環境変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `NEXT_PUBLIC_API_URL` | バックエンドのURL | `http://localhost:8000` |

## ページ構成

| パス | 内容 |
|------|------|
| `/` | シミュレーション一覧 |
| `/new` | 新規シミュレーション作成 |
| `/sim/[id]` | シミュレーション詳細（板一覧 + リアルタイム進行） |
| `/sim/[id]/board/[boardId]` | スレッド一覧 |
| `/sim/[id]/thread/[threadId]` | スレッド表示（5ch風） |
| `/sim/[id]/agents` | エージェント一覧 |
| `/sim/[id]/report` | 分析レポート |
| `/sim/[id]/ask` | 質問スレ（エージェントに直接質問） |
| `/agents` | 永続エージェント管理 |

## 主要コンポーネント

| ファイル | 役割 |
|----------|------|
| `components/PostCard.tsx` | 5ch風投稿カード（アンカー、コテハン表示） |
| `components/PersonaModal.tsx` | エージェント詳細モーダル |
| `components/BattleHeader.tsx` | シミュレーションヘッダー |
| `lib/api.ts` | バックエンドAPIクライアント |
| `styles/5ch.css` | 5ch風カスタムCSS |

## 技術スタック

- **Next.js 16** — App Router
- **React 19** — UI
- **TailwindCSS 4** — スタイリング
- **react-markdown** — マークダウンレンダリング（レポート表示）
- **TypeScript** — 型安全
