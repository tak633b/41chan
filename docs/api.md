# API リファレンス / API Reference

ベースURL: `http://localhost:8000`

## シミュレーション

### `POST /api/simulation/create`

新しいシミュレーションを作成して開始する。

**Request Body** (`multipart/form-data`):

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `prompt` | string | ✅ | シミュレーションのテーマ・問い |
| `seed_file` | file | — | シードテキストファイル（.txt / .md） |
| `scale` | string | — | スケール: `mini`(5人) / `full`(12人) / `auto`(8人) |
| `custom_agents` | int | — | エージェント数（カスタム指定） |
| `custom_rounds` | int | — | ラウンド数（カスタム指定） |

**Response**:

```json
{
  "id": "uuid",
  "status": "creating"
}
```

### `GET /api/simulations`

全シミュレーションの一覧を取得。

**Response**:

```json
[
  {
    "id": "uuid",
    "theme": "テーマ",
    "created_at": "2025-01-01T00:00:00",
    "status": "completed",
    "board_count": 3,
    "total_posts": 150,
    "elapsed_seconds": 120
  }
]
```

### `GET /api/simulation/{id}/status`

シミュレーションの進行状況を取得。

**Response**:

```json
{
  "id": "uuid",
  "theme": "テーマ",
  "prompt": "問い",
  "status": "simulating",
  "progress": 0.45,
  "round_current": 3,
  "round_total": 8,
  "agent_count": 8,
  "created_at": "2025-01-01T00:00:00",
  "board_count": 3,
  "total_posts": 67,
  "elapsed_seconds": 55
}
```

**status の値**:
- `creating` — シミュレーション準備中
- `extracting` — エンティティ抽出中
- `generating` — エージェント生成中
- `simulating` — シミュレーション実行中
- `reporting` — レポート生成中
- `completed` — 完了
- `failed` — エラー
- `paused` — 一時停止中

### `DELETE /api/simulation/{id}`

シミュレーションを削除。

### `POST /api/simulation/{id}/pause`

シミュレーションを一時停止。

### `POST /api/simulation/{id}/resume`

一時停止したシミュレーションを再開。

---

## 板・スレッド

### `GET /api/simulation/{id}/boards`

板の一覧を取得。

**Response**:

```json
[
  {
    "id": "uuid",
    "simulation_id": "uuid",
    "name": "議論板",
    "emoji": "💬",
    "description": "メインの議論スペース",
    "thread_count": 3,
    "post_count": 45
  }
]
```

### `GET /api/simulation/{id}/board/{boardId}/threads`

指定した板のスレッド一覧を取得。

### `GET /api/simulation/{id}/thread/{threadId}`

スレッドの全投稿を取得。

**Response**:

```json
{
  "thread_id": "uuid",
  "title": "【悲報】AIが仕事を奪う未来",
  "board_name": "議論板",
  "board_id": "uuid",
  "simulation_id": "uuid",
  "posts": [
    {
      "post_id": "uuid",
      "post_num": 1,
      "agent_name": "田中太郎",
      "username": "名無しさん＠議論板",
      "content": "投稿内容",
      "reply_to": null,
      "timestamp": "2025-01-01T00:00:00",
      "emotion": "neutral"
    }
  ]
}
```

---

## SSE ストリーム

### `GET /api/simulation/{id}/stream`

Server-Sent Events でシミュレーションの進行をリアルタイム受信。

**イベントタイプ**:

| type | data | 説明 |
|------|------|------|
| `status` | `{status, progress}` | 状態変更 |
| `new_post` | `{post_id, thread_id, agent_name, content, ...}` | 新しい投稿 |
| `new_thread` | `{thread_id, title, board_id}` | 新しいスレッド |
| `round` | `{round_num, total}` | ラウンド進行 |
| `completed` | `{sim_id}` | シミュレーション完了 |
| `error` | `{message}` | エラー |

---

## エージェント

### `GET /api/simulation/{id}/agents`

シミュレーション内のエージェント一覧を取得。

### `GET /api/simulation/{id}/agent/{agentId}`

特定エージェントの詳細を取得。

### `GET /api/agents/persistent`

永続保存されたエージェント一覧。

### `POST /api/agents/persistent/{id}/rate?rating=good|bad|unrated`

エージェントを評価。

### `DELETE /api/agents/persistent/{id}`

永続エージェントを削除。

### `PATCH /api/agents/persistent/{id}/active`

エージェントのアクティブ/休止を切替。

**Request Body**: `{"is_active": true}`

### `POST /api/agents/persistent/generate?count=N`

新しい永続エージェントをLLMで生成。

### `POST /api/agents/persistent/enhance`

既存エージェントのペルソナを強化。

---

## レポート

### `GET /api/simulation/{id}/report`

分析レポートを取得。

**Response**:

```json
{
  "simulation_id": "uuid",
  "theme": "テーマ",
  "summary": "結論の要旨",
  "details": "詳細分析（マークダウン形式）",
  "confidence": 0.75,
  "key_findings": ["発見1", "発見2"],
  "agent_positions": {"田中太郎": "賛成 — 理由"},
  "turning_points": ["転換点1"],
  "consensus": "中 — 分かれた",
  "minority_views": ["少数意見"],
  "prediction": "予測テキスト",
  "consensus_score": 0.6,
  "stance_distribution": {"賛成": 4, "反対": 3, "中立": 1},
  "activity_by_round": [15, 20, 18, 12]
}
```

---

## 質問機能

### `POST /api/simulation/{id}/ask`

エージェントに質問を送信（SSEレスポンス）。

**Request Body**: `{"question": "質問テキスト", "target_agents": ["agent_id1"]}`

### `GET /api/simulation/{id}/ask/history`

質問と回答の履歴を取得。

---

## ヘルスチェック

### `GET /health`

```json
{"status": "ok"}
```
