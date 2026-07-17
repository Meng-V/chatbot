# AI-Core Backend

**Last Updated:** July 18, 2026

The Python/FastAPI backend of the Miami University Libraries Smart
Chatbot — the v2 rebuild, the only serving path since 2026-07-17.
(The old README described the retired LangGraph/v3.1 stack; it is
archived at `archived/legacy_v31/ai-core-README.md`.)

## What lives here

| Path | What it is |
|---|---|
| `src/main.py` | FastAPI app + the v2 Socket.IO handlers (rate-limited), probe/admin mounting |
| `src/graph/new_orchestrator.py` | `run_turn()`: scope → intent → deterministic short-circuits → agent → synthesizer |
| `src/graph/v2_serving.py` | Wire adapter between the socket handler and `run_turn` |
| `src/agent/`, `src/synthesis/` | Agent loop (tools) and citation-enforcing synthesizer |
| `src/router/` | kNN intent classifier + intent capabilities + exemplars |
| `src/config/models.py` | Model tiers — resolved from env at CALL time; never hard-code model ids |
| `src/api/` | health/readiness/metrics, LibAnswers ticket, summarize, admin/* (reviews, corrections, cost, tickets, hubs, smoketest) |
| `src/observability/` | alerting (operator email), Sentry, request ids, metrics |
| `src/eval/` | 234-case gold set, eval runner, judge_v2 |
| `scripts/` | ETL, cost rollup, exemplar tooling, ops utilities |
| `docs/` | OPERATOR.md runbook, eval reports (`docs/eval/`), canonical facts |
| `archived/` | Retired code (`legacy_v31/` = the removed v3.1 stack) |

## Run it

Production: systemd `chatbot.service` → uvicorn `src.main:app_sio` on
port 8081. Deploy with the repo-root `./build.sh`. Local dev:
repo-root `./local-auto-start.sh`.

```bash
# tests (offline, no API keys needed)
.venv/bin/python -m pytest src -q

# full eval (real LLM + judge; ~$7 — coordinate with the operator)
.venv/bin/python -m eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/eval_results_$(date +%Y%m%d).jsonl
```

## How a turn works / operations / env vars

See the current docs — they are short and accurate:

- [../docs/01-SYSTEM-OVERVIEW.md](../docs/01-SYSTEM-OVERVIEW.md) — architecture
- [../docs/02-ENVIRONMENT-VARIABLES.md](../docs/02-ENVIRONMENT-VARIABLES.md) — configuration
- [docs/OPERATOR.md](docs/OPERATOR.md) — runbook (endpoints, tasks, alerts)
- [../docs/05-DEPLOYMENT-GUIDE.md](../docs/05-DEPLOYMENT-GUIDE.md) — deploy/rollback
