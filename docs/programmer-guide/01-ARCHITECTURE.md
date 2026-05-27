# 01 — Architecture

> Read this first. Everything else makes more sense once you understand the turn pipeline.

## What the bot does

A user types a question in the chat widget on the Miami University Libraries website. The bot:

1. Figures out what kind of question it is (an "intent" — hours, room booking, librarian lookup, etc.)
2. Figures out which campus and which building the question is about ("scope")
3. Decides which tools to call to get the answer
4. Calls those tools (which hit live APIs like LibCal, or Postgres tables, or Weaviate vector search)
5. Asks an LLM (the "synthesizer") to write an answer using ONLY the evidence the tools returned
6. Validates the answer (every URL must exist, every email must come verbatim from a directory source, no fabricated facts)
7. Returns the answer with citation chips the user can click to verify

If at any step the bot cannot honestly answer, it refuses with a templated message ("I don't know — try Ask Us"). It does NOT make things up. This is the entire point of v2.

---

## High-level layout

```
┌──────────────────────────────────────────────────────────────┐
│  React UI (client/)                                          │
│  - Renders chat                                              │
│  - Renders citation chips [1] [2] that expand to URL+snippet │
│  - Hits /smartchatbot/socket.io/ for the chat connection     │
│  - Polls /health/live every 30s to check the bot is up       │
└──────────────────────────────────────────────────────────────┘
                              ↓ Socket.IO (websocket)
┌──────────────────────────────────────────────────────────────┐
│  FastAPI + Socket.IO (ai-core/src/main.py)                   │
│  - sio_v2 handler (registered on /smartchatbot/socket.io)    │
│  - For each incoming message → run_turn() in new_orchestrator│
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  The turn pipeline (ai-core/src/graph/new_orchestrator.py)   │
│  run_turn(request, deps) does these steps in order:          │
│                                                              │
│  1. resolve_scope(message)        → (campus, library)        │
│  2. intent_knn.classify(message)  → intent + confidence      │
│  3. capability_scope check        → maybe short-circuit refusal│
│  4. intent_capabilities check     → maybe POINT_TO_URL or REFUSE│
│  5. agent loop (run_agent)        → tool calls + evidence    │
│  6. synthesizer                   → answer + citations + confidence│
│  7. post_processor                → validate citations / URLs / emails│
│  8. response                      → back to UI               │
└──────────────────────────────────────────────────────────────┘
                              ↓ tools call out to
┌──────────────────────────────────────────────────────────────┐
│  Data layer                                                  │
│  - Postgres   : LibrarySpace_v2, Librarian, UrlSeen,         │
│                 ManualCorrection, Conversation, Message       │
│  - Weaviate   : Chunk (web pages + operator-gold chunks)      │
│  - LibCal API : live hours, room availability                │
│  - LibGuides API : subject librarian lookups                 │
│  - OpenAI    : agent + synth + judge LLMs, embeddings         │
└──────────────────────────────────────────────────────────────┘
```

---

## Step-by-step: what happens for one question

### Example: user types "What time does King close tonight?"

#### Step 1 — Scope resolution
File: `src/scope/resolver.py`

The resolver does substring matching against an alias table. "King" matches → `scope = {campus: "oxford", library: "king"}`.

If no match (e.g. "I have a question about books"), defaults to `{campus: "oxford", library: null}` — Oxford is the flagship campus default.

If the session originated from `ham.miamioh.edu` or `mid.miamioh.edu` (a regional campus referrer), default to that campus instead.

#### Step 2 — Intent classification
File: `src/router/intent_knn.py`

The kNN classifier:
- Embeds the user message with OpenAI `text-embedding-3-large` (cached after first lookup of identical text)
- Compares against ~5,400 pre-embedded labeled exemplars from `src/router/exemplars/*.jsonl`
- Returns the top-1 intent + the margin to top-2
- If margin < 0.05, marks `needs_clarification = true` and the orchestrator may ask the user to disambiguate

For "King closing time", the classifier returns `intent = "hours"` with high margin.

Intent labels live in `src/router/intent_knn.py` `_INTENT_REGISTRY` — about 32 intents total (hours, room_booking, subject_librarian, find_resource, account, out_of_scope, makerspace_3d, etc.).

**Cost:** 1 embedding call per turn (~$0.00001).

#### Step 3 — Capability scope check
File: `src/config/capability_scope.py`

A regex table (`LIMITATION_PATTERNS`) of "things the bot can't do" — pay fines, renew books, submit ILL, etc. Each pattern has an "action signal gate": the bot only short-circuits to a refusal if the user phrased it as a request to the bot (e.g. "can you renew for me", "submit this ILL") and NOT as an information question (e.g. "how do I renew?").

For "King closing time", no limitation matches → continue.

#### Step 4 — Intent capability check
File: `src/router/intent_capabilities.py`

A registry of per-intent tiers:
- **READY** (default) — agent loop runs
- **POINT_TO_URL** — short-circuit, return a canonical URL (e.g. find_resource → Primo)
- **REFUSE** — short-circuit with a templated refusal (e.g. out_of_scope → "I only handle library questions")

For `intent=hours`, the tier is READY → agent runs.

#### Step 5 — Agent loop
File: `src/agent/agent.py` + `src/prompts/agent_v1.py`

A single tool-calling LLM (`gpt-5.4-mini`) with these tools:

| Tool | What it does |
|---|---|
| `search_kb(query, scope)` | Hybrid Weaviate search (BM25 + vector). Returns chunks + provenance. |
| `lookup_librarian(subject\|name\|campus)` | Postgres + LibGuides API lookup. Returns librarian dicts. |
| `lookup_space(library\|name)` | Postgres LibrarySpace_v2 lookup. Returns address, phone, services_offered, equipment, libcal_id. |
| `get_hours(library, date)` | Live LibCal API. Returns formatted hours string. |
| `get_room_availability(library, date)` | Live LibCal API. Returns time slots. |
| `point_to_url(service)` | Returns canonical form/page URL for ILL, account, etc. |
| `validate_url(url)` | Checks Postgres UrlSeen allowlist. |

The agent's system prompt (Core Rule 6) tells it to PREFER specific tools by intent:
- `intent=hours → get_hours()`
- `intent=room_booking → get_room_availability()`
- `intent=subject_librarian → lookup_librarian()`
- `intent=location_directions → lookup_space()`

For King hours: agent calls `get_hours("king")` → LibCal returns this week's hours → agent terminates.

**Cost:** ~$0.005 per turn (1-3 LLM calls; cached prefix is most of the prompt).

#### Step 6 — Synthesizer
File: `src/synthesis/synthesizer.py` + `src/prompts/synthesizer_v1.py`

A separate LLM call (`gpt-5.4-mini`) with the evidence bundle the agent collected + the user's question. Returns structured JSON:

```json
{
  "answer": "King Library closes at 9:00pm tonight [1].",
  "citations": [
    {"n": 1, "url": "https://www.lib.miamioh.edu/about/locations/king-library/",
     "snippet": "Hours for week of ..."}
  ],
  "confidence": "high"
}
```

The synthesizer prompt enforces:
- Quote authoritative sources (LibCal hours, Postgres librarian contacts) **verbatim** — no paraphrasing
- Cite every factual sentence as `[n]`
- Default to King when no library named (DEFAULT-LIBRARY DISCIPLINE)
- Privacy: don't list multiple staff names
- No SSID, no print prices

**Cost:** ~$0.005 per turn.

#### Step 7 — Post-processor
File: `src/synthesis/post_processor.py`

Deterministic, code-level validation that **the synthesizer cannot weasel out of**:

1. **Domain typo normalizer** — `miamiohio.edu` → `miamioh.edu`, etc.
2. **Confidence gate** — if `confidence: "low"` or answer contains literal `REFUSAL`, downgrade to refusal
3. **Citation match** — every `[n]` in answer text must reference a citation in the array
4. **URL validation** — every URL in answer must be either in the citations OR in the `UrlSeen` allowlist
5. **Email faithfulness** — every email must appear verbatim in an evidence chunk (catches paraphrased contacts)
6. **Staff privacy** — 2+ distinct individual emails in one answer triggers refusal (roster dump prevention)
7. **Cross-campus mismatch** — citing a chunk from a different campus than scope.campus triggers refusal

If any check fails, the answer is replaced with a templated refusal with the trigger type recorded (`refusal_trigger="model_self_flagged"`, etc.).

#### Step 8 — Response back to UI
File: `src/graph/v2_serving.py`

The turn result is shaped into a Socket.IO event the UI knows how to render (answer text + citation chips array).

---

## The three storage tiers (and what goes where)

| Storage | What lives here | Why |
|---|---|---|
| **Postgres** | Librarians, library spaces, URL allowlist, manual corrections, conversation history, daily cost rollups, chunk provenance | Entity / relational data with stable identity. Looked up by name or ID, returns structured rows. |
| **Weaviate** | Web page chunks, operator-gold chunks, LibGuide page content | Unstructured prose. Searched by meaning (hybrid BM25 + vector). |
| **Live API** | LibCal hours, LibCal room availability, LibAnswers chat status, LibGuides librarian lookups | Changes intra-day. NEVER cache beyond ~5 minutes. Fetched on-demand per turn. |

Rule of thumb: if it changes more than once a week, it's live API. If it has a primary key, it's Postgres. Everything else is Weaviate.

---

## The "ManualCorrection" safety net

Librarians don't deploy code — they file corrections through a UI (or directly in Postgres). The bot reads `ManualCorrection` every turn:

| Action | Effect on retrieval |
|---|---|
| `suppress` chunk_id | That chunk is dropped from the evidence bundle |
| `replace` chunk_id with text | Chunk text is substituted before synthesis |
| `blacklist_url` | URL marked `isBlacklisted=true` in `UrlSeen`; synth/post-processor will refuse to cite |
| `pin` URL for query pattern | Pinned chunk injected at rank 1 for matching queries |

This means a librarian can fix a bad answer in 30 seconds without waiting for a developer deploy.

See [08-OPERATIONS.md](08-OPERATIONS.md) for the librarian-facing workflow.

---

## What v2 is NOT doing (intentional non-goals)

- **Multi-turn memory beyond conversation history** — the bot doesn't "learn" from past conversations. Conversation history is passed in the prompt; nothing is fine-tuned.
- **Actions on the user's behalf for ILL / renewals / fines / account changes** — these go to `point_to_url`. The bot returns the form URL with a one-line description. It never roleplays the official system.
- **Searching for specific books or articles** — that's Primo's job. Bot returns the Primo search URL.
- **Indexing the catalog** — Primo handles catalog search. We don't sync MARC records.
- **News and events** — explicitly excluded from the ETL (`/about/news-events/*` is filtered out). News content was a top source of v1 hallucinations.

---

## Deployment model: blue/green via timestamped build dirs

Production server (`ulblwebp20`) layout:

```
/opt/chatbot/
├── current → builds/20260527130232/   (symlink)
├── builds/
│   ├── 20260520093045/    # previous build
│   ├── 20260527130232/    # current
│   └── ...
└── ...
```

Each deploy creates a new timestamped directory (likely by CI). `current` symlink is atomically swapped to point at the new build. Rollback = swap symlink back + restart service. See [03-DEPLOYMENT.md](03-DEPLOYMENT.md).

The systemd service runs uvicorn pointing at `/opt/chatbot/current/...`. So a symlink swap + restart = full rollback.

---

## Why two orchestrators in the codebase

You will see both:
- `ai-core/src/graph/orchestrator.py` — the LEGACY v1 LangGraph router
- `ai-core/src/graph/new_orchestrator.py` — the v2 single-pipeline orchestrator

**Only v2 is used.** v1 lives on as dead code because:
1. Removing it would be a big diff (touches many imports)
2. It's a fallback if v2 needs an emergency revert (revert the cutover commit + frontend flag → v1 path serves traffic)
3. Some legacy `tools/` modules still reference v1 patterns

When you read v1 code, remember: it's not the production path.

---

## Reading order if you want to understand the codebase

1. `ai-core/src/graph/new_orchestrator.py` — the turn pipeline (start with `run_turn`)
2. `ai-core/src/agent/agent.py` — the tool-calling loop
3. `ai-core/src/synthesis/synthesizer.py` + `post_processor.py` — answer generation + validation
4. `ai-core/src/eval/real_backends.py` — tool backend implementations (extensive design comments)
5. `ai-core/src/router/intent_knn.py` — kNN classifier mechanics
6. `ai-core/src/prompts/*.py` — the prompts (mostly cached prefixes, read carefully)

Everything else is plumbing.
