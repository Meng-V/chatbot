# 04 — API Reference

> How to talk to the bot from another application. Covers Socket.IO message shapes and the few HTTP endpoints.

The bot is primarily a Socket.IO server. The React UI in `client/` is the canonical consumer, but other apps can integrate by speaking the same protocol.

---

## Socket.IO endpoint

**URL:** `https://app.lib.miamioh.edu/smartchatbot/socket.io/` (production)
**URL:** `http://localhost:8000/smartchatbot/socket.io/` (local dev)

**Transport:** WebSocket primary, long-polling fallback. Engine.IO v4.

**Namespace:** root namespace (`/`). No custom namespaces.

### Client → Server events

#### `message`

Send a user question.

**Payload:**
```json
{
  "message": "What time does King Library close tonight?",
  "conversation_id": "conv-abc123",
  "session_origin_url": "https://www.lib.miamioh.edu/"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | yes | The user's text |
| `conversation_id` | string | yes | Stable per chat session; used to load history and log results |
| `session_origin_url` | string | no | Where the chat widget was loaded from. Used for regional-campus default scope (`ham.miamioh.edu` → hamilton default, etc.) |

### Server → Client events

#### `response`

The bot's answer.

**Payload (answer):**
```json
{
  "answer": "King Library closes at 9:00pm tonight [1].",
  "is_refusal": false,
  "refusal_trigger": null,
  "citations": [
    {
      "n": 1,
      "url": "https://www.lib.miamioh.edu/about/locations/king-library/",
      "snippet": "Hours for the week of 2026-05-27: Wednesday 7:30am-9:00pm..."
    }
  ],
  "confidence": "high",
  "intent": "hours",
  "scope": {"campus": "oxford", "library": "king"},
  "model_used": "gpt-5.4-mini",
  "tokens": {"input": 1450, "cached_input": 1200, "output": 35},
  "fired_corrections": [],
  "agent_stopped_reason": "clean",
  "latency_ms": 2150,
  "cited_chunk_ids": ["tool:get_hours:king"]
}
```

**Payload (refusal):**
```json
{
  "answer": "I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.",
  "is_refusal": true,
  "refusal_trigger": "model_self_flagged",
  "citations": [],
  "confidence": "low",
  "intent": "hours",
  "scope": {"campus": "hamilton", "library": "rentschler"},
  "model_used": "gpt-5.4-mini",
  "tokens": {"input": 1450, "cached_input": 1200, "output": 12},
  "fired_corrections": [],
  "agent_stopped_reason": "synth_low_confidence",
  "latency_ms": 1800,
  "cited_chunk_ids": []
}
```

| Field | Type | Notes |
|---|---|---|
| `answer` | string | Text to display. Refusals use templated messages from `refusal_templates.py`. |
| `is_refusal` | bool | UI should render handoff button / Ask Us prompt when true |
| `refusal_trigger` | string\|null | Why the bot refused. See "Refusal triggers" below. |
| `citations` | array | One per `[n]` in answer. Render as clickable chips. |
| `confidence` | "high"\|"medium"\|"low" | Synthesizer's self-assessment. "low" auto-downgrades to refusal in post-processor. |
| `intent` | string | The kNN classifier's verdict |
| `scope` | object | Resolved campus+library |
| `model_used` | string | Which LLM (gpt-5.4-mini default; gpt-5.2 escalation for hard cases) |
| `tokens` | object | For cost tracking |
| `fired_corrections` | array of int | IDs of any `ManualCorrection` rows that affected this turn |
| `agent_stopped_reason` | string | `clean` / `max_iters` / `loop_detected` / `tool_failures` / `synth_low_confidence` / `capability_limitation` etc |
| `cited_chunk_ids` | array of string | Provenance — joinable to `ChunkProvenance` Postgres table |

---

## Refusal triggers (full list)

| Trigger | When it fires |
|---|---|
| `out_of_scope` | kNN classified intent as out_of_scope (and the intent_capabilities REFUSE tier short-circuited) |
| `news_excluded` | Intent classified as events_news (we don't index news) |
| `account_privacy` | User asked about their personal account data (we can't access it) |
| `capability_limitation:check_account` | User asked us to look at their account state |
| `capability_limitation:renew_books` | User asked us to renew (action — point to MyAccount instead) |
| `capability_limitation:place_holds` | User asked us to place a hold |
| `capability_limitation:interlibrary_loan` | User asked us to submit an ILL |
| `capability_limitation:catalog_search` | User asked us to search the catalog (point to Primo) |
| `capability_limitation:course_reserves` | Faculty asked us to put a book on reserves |
| `capability_limitation:pay_fines` | User asked to pay fines through chat |
| `cross_campus_mismatch` | Bot's only evidence was from a different campus than the user's scope |
| `service_not_at_building` | E.g., MakerSpace asked about at Hamilton (only exists at King) |
| `model_self_flagged` | Synth returned `confidence: "low"` or literal `REFUSAL` token |
| `citation_invalid` | Post-processor caught a URL/email not in evidence or allowlist |
| `live_data_down` | LibCal / LibAnswers / Weaviate timed out |
| `website_feedback_handoff` | User reported a website bug — referred to web team |

The UI typically doesn't show these labels to the user, but they're useful for logging and for the librarian-review dashboard.

---

## HTTP endpoints

### `GET /health/live`

**Trivial liveness probe.** Use this for synthetic monitoring, load balancer health checks, and frontend "is the bot up" polling.

```bash
curl -s http://localhost:8000/health/live
# {"status":"alive"}
```

Response: 200 with `{"status":"alive"}` if the FastAPI worker is responsive. Doesn't touch any external dependency.

### `GET /health/ready`

**Readiness probe.** Hits configured dependency probes (Weaviate, Postgres, OpenAI). Returns 200 if all probes pass, else 503.

```bash
curl -s http://localhost:8000/health/ready
```

### `GET /health`

**Full external-API health check.** Pings OpenAI, Weaviate, LibCal, LibGuides, Google CSE, LibAnswers in parallel. Returns detailed status per service.

```bash
curl -s http://localhost:8000/health
```

**⚠️ Can be slow (>5s) when downstream services are warming up.** Don't use for frontend polling; use `/health/live` instead.

Response shape:
```json
{
  "status": "healthy" | "degraded" | "unhealthy",
  "services": {
    "database": {"status": "healthy"},
    "openai": {"status": "healthy"},
    "weaviate": {"status": "healthy"},
    "libcal": {"status": "healthy"},
    "libguides": {"status": "healthy"},
    "google_cse": {"status": "healthy"},
    "libanswers": {"status": "healthy"}
  },
  "memory": {"status": "healthy", "percent": 35},
  "cpu_percent": 12.3
}
```

### `GET /smoketest`

**Synthetic monitoring endpoint.** Runs a canned question end-to-end and asserts:
- A citation chip is returned
- It's not a refusal
- Total time < 8 seconds

Returns 200 if all asserts pass. Used by external pingers (UptimeRobot / BetterStack).

### `POST /ask`

**HTTP-only chat endpoint** (no streaming). Same shape as Socket.IO `message`, returns the same response shape synchronously.

```bash
curl -sX POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does King Library close?","conversation_id":"test-001"}'
```

Use for: scripting / monitoring / clients that don't want WebSocket. The Socket.IO path is preferred for UX (typing indicators, etc.).

---

## Authentication / authorization

Currently: **none**. The chat endpoint is open to anyone who can reach `app.lib.miamioh.edu`. This is intentional — the bot is a public-facing service.

The bot itself authenticates outbound calls:
- OpenAI: API key in `.env`
- LibCal: OAuth client credentials in `.env`
- LibGuides: OAuth client credentials in `.env`
- Postgres / Weaviate: connection strings in `.env`

`.env` is **not** checked into git. On prod, it lives at `/opt/chatbot/current/.env` (or wherever your deploy puts it) and must be readable by the user running uvicorn.

---

## Rate limiting

Not enforced at the application layer. nginx may rate-limit by IP. The bot's per-turn cost (~$0.01-0.02 OpenAI) and downstream rate limits (LibCal API has 5 RPS) are the practical caps.

If a user spams 100 questions, costs grow linearly. If you want to throttle, do it in nginx or add `slowapi` to FastAPI.

---

## Data privacy notes

What gets logged in Postgres (`Message` table):
- The user's question (verbatim)
- The bot's answer (verbatim)
- Intent, scope, citations, tokens, latency

What does NOT get logged:
- The user's IP address (unless nginx logs it separately)
- Any PII the user might paste into a question (we don't redact — assume users won't paste credit cards, but if they do, it goes in the DB)
- Any auth identifier — chat is anonymous

If a librarian needs to look up what the bot said to a specific student, they need a `conversation_id` from that session.

---

## Integration examples

### Python client (sync)

```python
import requests
r = requests.post(
    "https://app.lib.miamioh.edu/ask",
    json={"message": "King hours today?", "conversation_id": "test-001"},
    timeout=15,
)
data = r.json()
print(data["answer"])
for c in data["citations"]:
    print(f"  [{c['n']}] {c['url']}")
```

### Python client (Socket.IO async)

```python
import socketio
import asyncio

sio = socketio.AsyncClient()

@sio.on("response")
async def on_response(data):
    print(data["answer"])
    await sio.disconnect()

async def main():
    await sio.connect(
        "https://app.lib.miamioh.edu",
        socketio_path="/smartchatbot/socket.io/",
    )
    await sio.emit("message", {
        "message": "King hours today?",
        "conversation_id": "test-001",
    })
    await sio.wait()

asyncio.run(main())
```

### JS client (browser, the React UI's pattern)

```javascript
import { io } from 'socket.io-client';

const socket = io({
  path: '/smartchatbot/socket.io/',
});

socket.on('connect', () => {
  console.log('Connected');
  socket.emit('message', {
    message: 'King hours today?',
    conversation_id: 'test-001',
  });
});

socket.on('response', (data) => {
  console.log('Bot:', data.answer);
});
```
