# Miami University Libraries Smart Chatbot

AI chatbot for Miami University Libraries: answers questions about hours,
study-room booking, subject librarians, course reserves, interlibrary loan,
newspapers, MakerSpace, Special Collections, and more — grounded in
operator-verified library data, with live LibCal integration.

## Repository layout

| Path | What it is |
|---|---|
| `ai-core/` | Python backend: FastAPI app, orchestrator, agent + tools, eval harness |
| `ai-core/src/graph/new_orchestrator.py` | The turn pipeline: scope → intent → deterministic short-circuits → agent → synthesizer |
| `ai-core/src/eval/` | Gold set (234 cases), eval runner, LLM-as-judge (judge_v2) |
| `ai-core/docs/eval/` | Eval run reports, triage docs, gold-hygiene history |
| `client/` | React/Vite frontend (chat widget) |
| `prisma/` | Database schema (PostgreSQL via Prisma) |
| `docs/` | Developer + operator documentation (see [docs/README.md](docs/README.md)) |
| `docs/programmer-guide/` | Deep-dive architecture guide (00-INDEX.md) |
| `data/raw/` | Raw chat-transcript CSVs consumed by `ai-core/scripts/process_new_year_data.py` |
| `archived/` | Retired code kept for reference |

## Running in production

- The backend runs as **systemd service `chatbot.service`** (uvicorn on
  port 8081, auto-restart on failure). Weaviate runs in Docker
  (`ai-core/docker-compose.weaviate.yml`, port 8080).
- **Deploy**: `./build.sh` — installs backend deps, regenerates the Prisma
  client, builds the frontend, restarts the service.
- **Operator email alerts** (dependency down/recovered) are sent by
  `ai-core/src/observability/alerting.py`. On this AWS host they require an
  authenticated SMTP relay on port 587 — see the `ALERT_*` block in
  `.env.example` and [docs/09-SERVER-MONITORING.md](docs/09-SERVER-MONITORING.md).

## Quality / eval workflow

The measured quality loop lives in `ai-core`:

```bash
cd ai-core
.venv/bin/python -m eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/eval_results_$(date +%Y%m%d).jsonl
```

- Gold set: `ai-core/src/eval/golden_set.jsonl` — each case carries the
  operator's review history in its `notes` field (judge_v2 reads it).
- History and current numbers: see the dated reports in
  `ai-core/docs/eval/` (latest: judge_v2 run 2026-07-16, 74.4% judge-good,
  operator-estimated true rate ~93%).
- After changing gold or judge, re-run and commit the report + the
  per-case results JSONL next to it, so the next triage never loses data.

## Documentation map

- [docs/README.md](docs/README.md) — index of the numbered docs (setup,
  deployment, env vars, monitoring, clarification system…)
- [ai-core/docs/OPERATOR.md](ai-core/docs/OPERATOR.md) — operator runbook
  for the v2-rebuild surfaces
- [docs/programmer-guide/00-INDEX.md](docs/programmer-guide/00-INDEX.md) —
  architecture deep-dive
