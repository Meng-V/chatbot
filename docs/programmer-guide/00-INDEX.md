# Smart Chatbot v2 — Programmer's Guide

**Audience:** any engineer who needs to develop, deploy, troubleshoot, or extend the Miami University Libraries Smart Chatbot. Assumes you have read nothing else about this project.

**Status:** v2 (the rebuild). Replaces the original v1 LangGraph-based bot that was blocked from production launch in late 2025 due to hallucination issues. v2 was promoted to the only production handler on 2026-05-27.

---

## How to use this guide

Read in this order if you're new:

| File | Read when | Read time |
|---|---|---|
| [01-ARCHITECTURE.md](01-ARCHITECTURE.md) | Always first — what the bot is, what each layer does, how a question becomes an answer | 15 min |
| [02-LOCAL-DEVELOPMENT.md](02-LOCAL-DEVELOPMENT.md) | You want to run the bot on your laptop | 30 min (mostly waiting on `pip install`) |
| [03-DEPLOYMENT.md](03-DEPLOYMENT.md) | You're deploying to production. **Send this to Rachel for ops work.** | 20 min |
| [04-API-REFERENCE.md](04-API-REFERENCE.md) | You're integrating with the bot from another app (Socket.IO message shapes, etc.) | 10 min |
| [05-TROUBLESHOOTING.md](05-TROUBLESHOOTING.md) | Something is broken on prod or in dev | grep for your error |
| [06-EVAL-AND-QUALITY.md](06-EVAL-AND-QUALITY.md) | You changed bot behavior and want to measure impact | 20 min |
| [07-DATA-PIPELINE.md](07-DATA-PIPELINE.md) | You need to refresh the knowledge base from the library website, or add a new building to the truth table | 25 min |
| [08-OPERATIONS.md](08-OPERATIONS.md) | A librarian flagged a wrong answer; you're handling the ManualCorrection workflow | 10 min |

---

## Send this to a non-developer

If a librarian asks "how do I fix a wrong answer the bot gave?" — point them at [08-OPERATIONS.md](08-OPERATIONS.md), specifically the "ManualCorrection workflow" section. Everything else assumes some technical comfort.

If a sysadmin asks "how do I deploy?" — send them [03-DEPLOYMENT.md](03-DEPLOYMENT.md). It is self-contained and assumes prod SSH access but no project context.

---

## Critical facts (read at minimum, even if you skip everything else)

1. **The bot is "v2".** v1 still exists in the codebase as dead code (legacy `sio` Socket.IO handler), but every Socket.IO request is routed to v2. To re-enable v1, you would need to revert commit `50963e6` and the frontend RolloutFlag.

2. **Tools are wired in two places** — both must be done or the agent can't use them:
   - **Backend implementation** in `ai-core/src/eval/real_backends.py` (used by eval; mirrored by `ai-core/src/graph/v2_serving.py` for prod)
   - **Tool exposure** via `ai-core/src/eval/run_eval.py::_build_real_deps` — if a tool name appears in the `pop()` list there, the agent does NOT see that tool. **This trap cost us 2 rounds of debugging in May 2026.** See troubleshooting Section 4.

3. **`/health` is heavy, `/health/live` is cheap.** Frontend hits `/health/live` for liveness; ops dashboards / synthetic monitoring should hit `/health` for full-stack checks (it pings 6 external services).

4. **The eval verdict number is biased — use it for trends, not absolute quality.** The LLM-as-judge mismarks ~15-30% of answers. See [06-EVAL-AND-QUALITY.md](06-EVAL-AND-QUALITY.md) Section "Why verdict ≠ truth".

5. **Library data lives in two Postgres tables, both must be in sync:**
   - `LibrarySpace_v2` — canonical building truth (name, address, phone, LibCal ID, services)
   - `LibrarySpace` (v1) — used by the legacy `LocationService` (only relevant for the `get_hours` tool's name→ID mapping)
   - If you add a new building, add to BOTH. See [07-DATA-PIPELINE.md](07-DATA-PIPELINE.md).

6. **Anything with a LibCal ID MUST use the LibCal API.** Operator hard requirement. The agent's Core Rule 6 enforces this for hours queries. Mappings:
   ```
   king          → 8113
   wertz         → 8116
   special       → 8424
   makerspace    → 11904
   rentschler    → 9226    (Hamilton)
   gardner_harvey→ 9227    (Middletown)
   askus chat    → 8876    (in .env as LIBCAL_ASKUS_ID)
   sword         → (no LibCal tracking; not in API)
   ```

7. **Backend listens on port 8081 in production, 8000 in local dev (uvicorn default).** When commands in these docs say `http://localhost:8081`, that's prod. If you're on your laptop and uvicorn picked 8000, substitute. Health-check curl commands are written for prod (`:8081`).

---

## Repository layout (the parts that matter)

```
chatbot/
├── ai-core/                      # Python backend (FastAPI + Socket.IO)
│   ├── src/
│   │   ├── main.py               # ASGI app entry, mounts everything
│   │   ├── graph/
│   │   │   ├── new_orchestrator.py   # The v2 turn pipeline
│   │   │   ├── v2_serving.py         # Socket.IO bridge for v2
│   │   │   └── orchestrator.py       # LEGACY v1 — unused but loaded
│   │   ├── agent/                # Tool-calling agent
│   │   ├── synthesis/            # Synthesizer + post-processor (citation/URL/typo gates)
│   │   ├── router/
│   │   │   ├── intent_knn.py     # kNN intent classifier
│   │   │   ├── intent_capabilities.py  # Per-intent capability tier (POINT_TO_URL / REFUSE / READY)
│   │   │   └── exemplars/        # kNN training data
│   │   ├── scope/                # Campus/library resolution from user message
│   │   ├── tools/                # Live API tools (LibCal, LibGuides, etc.)
│   │   ├── tools_v2/             # New tool registry pattern (lookup_space, etc.)
│   │   ├── eval/                 # Eval harness + gold sets
│   │   │   ├── run_eval.py
│   │   │   ├── real_backends.py  # ← TOOL WIRING LIVES HERE
│   │   │   ├── golden_set.jsonl              # Main 234-case test suite
│   │   │   ├── golden_set_colleague_round1.jsonl  # 37-case external test
│   │   │   └── golden_set_merged_271.jsonl   # Combined for one-shot runs
│   │   ├── prompts/              # Cached prompt prefixes (agent, synth, judge)
│   │   ├── api/
│   │   │   ├── health.py         # /health (heavy — 6 external checks)
│   │   │   └── readiness_router.py # /health/live, /health/ready
│   │   └── config/
│   │       └── capability_scope.py  # LIMITATIONS regex table (refuse triggers)
│   ├── scripts/
│   │   ├── operator_wiring/
│   │   │   └── wire_gold_to_weaviate.py  # Inserts operator-gold chunks
│   │   └── generate_librarian_report.py  # Markdown report from eval results
│   └── requirements.txt
├── client/                       # React frontend (Vite)
│   └── src/
│       ├── App.jsx
│       ├── context/SocketContextProvider.jsx
│       └── services/RolloutFlag.js   # v2 flag resolver (now returns canonical path always)
├── prisma/
│   └── schema.prisma             # Database schema
└── docs/programmer-guide/        # ← you are here
```

---

## Glossary

| Term | Meaning |
|---|---|
| **v1** | Original chatbot, LangGraph-routed, 6 specialized agents. Dead code now. |
| **v2** | Current chatbot. Single tool-calling agent + structured synthesizer + post-processor. |
| **kNN classifier** | Intent classifier using embedding nearest-neighbor against ~5,400 labeled exemplars. No LLM. |
| **operator-gold chunks** | Weaviate chunks created from gold-set questions + verified answers. Highest-priority retrieval source. |
| **ManualCorrection** | Postgres table where librarians flag bad answers; bot reads this every turn to override / suppress / pin chunks. No deploy required. |
| **LibCal** | Springshare's library scheduling system. Source of truth for hours, room availability. We have OAuth credentials in `.env`. |
| **LibGuides** | Springshare's library guides system. Source of truth for subject librarians. API in `_bridge` pattern. |
| **Weaviate** | Vector DB on prod, port 8888. Holds prose chunks (web pages, LibGuide content). |
| **Postgres** | Primary RDB. Truth for librarians, library spaces, conversations, manual corrections, URL allowlist. |
| **Async bridge** | The pattern in `real_backends.py` (`_AsyncBridge`) — one persistent asyncio loop on a daemon thread so legacy tools' singleton clients (Prisma, LocationService) don't get orphaned. |
| **Operator** | The product owner (Meng). Approves design decisions, gold-set rewrites. |
| **Goodhart's Law** | When a measurement becomes a target, it ceases to be a good measurement. Applies to tuning prompts to chase eval verdicts. See [06-EVAL-AND-QUALITY.md](06-EVAL-AND-QUALITY.md). |

---

## When in doubt

1. Read [05-TROUBLESHOOTING.md](05-TROUBLESHOOTING.md) — most pain points are documented.
2. Run the eval (`/06-EVAL-AND-QUALITY.md`) — concrete behavior is easier to debug than reading code.
3. Check the comment headers in `ai-core/src/graph/new_orchestrator.py` and `ai-core/src/eval/real_backends.py` — they contain the deepest design rationale.
