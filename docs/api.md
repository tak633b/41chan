# API Reference

Base URL: `http://localhost:8001`

## Simulation

### `POST /api/simulation/create`

Create and start a new simulation.

**Request Body** (`multipart/form-data`):

| Field | Type | Required | Description |
|-----------|-----|------|------|
| `prompt` | string | ✅ | Theme or question for the simulation |
| `seed_file` | file | — | Seed text file (.txt / .md) |
| `scale` | string | — | Scale: `mini`(5 agents) / `full`(12 agents) / `auto`(8 agents) |
| `custom_agents` | int | — | Number of agents (custom) |
| `custom_rounds` | int | — | Number of rounds (custom) |

**Response**:

```json
{
  "id": "uuid",
  "status": "creating"
}
```

### `GET /api/simulations`

Get a list of all simulations.

**Response**:

```json
[
  {
    "id": "uuid",
    "theme": "Theme text",
    "created_at": "2025-01-01T00:00:00",
    "status": "completed",
    "board_count": 3,
    "total_posts": 150,
    "elapsed_seconds": 120
  }
]
```

### `GET /api/simulation/{id}/status`

Get simulation progress.

**Response**:

```json
{
  "id": "uuid",
  "theme": "Theme text",
  "prompt": "Question text",
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

**status values**:
- `creating` — Preparing simulation
- `extracting` — Extracting entities
- `generating` — Generating agents
- `simulating` — Running simulation
- `reporting` — Generating report
- `completed` — Done
- `failed` — Error
- `paused` — Paused

### `DELETE /api/simulation/{id}`

Delete a simulation.

### `POST /api/simulation/{id}/pause`

Pause a simulation.

### `POST /api/simulation/{id}/resume`

Resume a paused simulation.

---

## Boards & Threads

### `GET /api/simulation/{id}/boards`

Get a list of boards.

**Response**:

```json
[
  {
    "id": "uuid",
    "simulation_id": "uuid",
    "name": "Discussion",
    "emoji": "💬",
    "description": "Main discussion space",
    "thread_count": 3,
    "post_count": 45
  }
]
```

### `GET /api/simulation/{id}/board/{boardId}/threads`

Get a list of threads for a given board.

### `GET /api/simulation/{id}/thread/{threadId}`

Get all posts in a thread.

**Response**:

```json
{
  "thread_id": "uuid",
  "title": "AI is going to take our jobs",
  "board_name": "Discussion",
  "board_id": "uuid",
  "simulation_id": "uuid",
  "posts": [
    {
      "post_id": "uuid",
      "post_num": 1,
      "agent_name": "John Smith",
      "username": "Anonymous",
      "content": "Post content",
      "reply_to": null,
      "timestamp": "2025-01-01T00:00:00",
      "emotion": "neutral"
    }
  ]
}
```

---

## SSE Stream

### `GET /api/simulation/{id}/stream`

Receive simulation progress in real-time via Server-Sent Events.

**Event types**:

| type | data | Description |
|------|------|------|
| `status` | `{status, progress}` | Status change |
| `new_post` | `{post_id, thread_id, agent_name, content, ...}` | New post |
| `new_thread` | `{thread_id, title, board_id}` | New thread |
| `round` | `{round_num, total}` | Round progress |
| `completed` | `{sim_id}` | Simulation completed |
| `error` | `{message}` | Error |

---

## Agents

### `GET /api/simulation/{id}/agents`

Get a list of agents in a simulation.

### `GET /api/simulation/{id}/agent/{agentId}`

Get details for a specific agent.

### `GET /api/agents/persistent`

List all persistent agents.

### `POST /api/agents/persistent/{id}/rate?rating=good|bad|unrated`

Rate an agent.

### `DELETE /api/agents/persistent/{id}`

Delete a persistent agent.

### `PATCH /api/agents/persistent/{id}/active`

Toggle active/inactive status for an agent.

**Request Body**: `{"is_active": true}`

### `POST /api/agents/persistent/generate?count=N`

Generate new persistent agents via LLM.

### `POST /api/agents/persistent/enhance`

Enhance an existing agent's persona.

---

## Reports

### `GET /api/simulation/{id}/report`

Get the analysis report.

**Response**:

```json
{
  "simulation_id": "uuid",
  "theme": "Theme text",
  "summary": "Summary of conclusions",
  "details": "Detailed analysis (markdown format)",
  "confidence": 0.75,
  "key_findings": ["Finding 1", "Finding 2"],
  "agent_positions": {"John Smith": "for — reason"},
  "turning_points": ["Turning point 1"],
  "consensus": "Medium — divided",
  "minority_views": ["Minority view"],
  "prediction": "Prediction text",
  "consensus_score": 0.6,
  "stance_distribution": {"for": 4, "against": 3, "neutral": 1},
  "activity_by_round": [15, 20, 18, 12]
}
```

---

## Ask Feature

### `POST /api/simulation/{id}/ask`

Send a question to agents (SSE response).

**Request Body**: `{"question": "Question text", "target_agents": ["agent_id1"]}`

### `GET /api/simulation/{id}/ask/history`

Get question and answer history.

---

## Health Check

### `GET /health`

```json
{"status": "ok"}
```
