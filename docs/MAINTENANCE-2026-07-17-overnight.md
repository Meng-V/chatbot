# Overnight maintenance sweep — 2026-07-17

Full-repo audit after the legacy-path removal: version consistency, dead
code, live integrity of every surface, docs. Three real defects found and
fixed; every check green at the end.

## Defects found & fixed

### 1. Production never used the configured models (two stacked bugs)

`model_used` in live turns said `gpt-5.4-mini` / `gpt-5.2` even after the
.env upgrade to the gpt-5.6 tiers. Two independent causes, both fixed:

1. `run_turn()` had **hardcoded string defaults** (`model_basic="gpt-5.4-mini"`,
   `model_reasoning="gpt-5.2"`) and the serving path never passed models —
   so .env tiers only ever affected the eval harness. Defaults now resolve
   from `resolve_model()`.
2. `src/config/models.py` **snapshotted env values at import time**, and
   main.py's import chain pulled it in before `load_dotenv()` ran — so even
   resolve_model returned baked-in defaults in production. Fixed twice over:
   `resolve_model()` now reads the env var at call time, and main.py loads
   `.env` before any `src` import.

**Verified live**: a real socket turn now reports `model_used: gpt-5.6-luna`.
Also updated: `llm_triage.py` (hardcoded pre-rebuild `o4-mini` → basic tier),
stale model mentions in comments/docstrings, `.env.example`, docs/07.

### 2. v2 socket had no abuse/cost guard

The legacy `message` handler carried the rate limiter + input-size
validation; v2's handler never got them, and the legacy removal deleted the
only guarded entrance — leaving the public unauthenticated socket with
unlimited LLM calls. Ported `validate_message` + `check_rate` into
`_v2_message` (fail-open limiter, in-chat rejection message).
**Verified live**: 25-message burst → rate-limit rejections fire.

### 3. Operator hub linked a 404

`/admin/reviews/view` doesn't exist (the page is `/admin/review`). Fixed the
hub card + test; also relabeled the smoke-test card (both probes now hit v2)
and restored strict citation gating on `/smoketest`.

## Cleanup

- `main.py`: removed orphan imports left by the legacy removal
  (`AgentState`, `AgentLogger`, unused conversation-store/rate-limit
  symbols, `json`/`time`/`HTTPException`/`BaseModel`) and the dead
  `clean_response_for_frontend()` helper.
- Archived to `ai-core/archived/legacy_v31/`: `final_comprehensive_test.py`
  + `RUN_FINAL_TEST.sh` (drove the removed `/ask` endpoint).
- docs/07 rewritten around the model tiers (OPENAI_MODEL was still
  documented as `o4-mini`); `.env.example` tier values/comments refreshed;
  models.py price-table comment gained the 5.6 rows.

## Integrity check results (all green)

| Check | Result |
|---|---|
| 16 HTTP surfaces (health, probes, hubs, admin pages, forms) | 200s; auth-gated ones 401 without key |
| `/health/ready` probes | postgres, weaviate, openai, libcal, libguides all healthy |
| `/smoketest` (strict citations) | passed |
| Live socket turn | answer + citation, `model_used: gpt-5.6-luna` |
| Rate limit burst (25 msgs) | rejections fire, service stays up |
| Ticket + hub pages via nginx HTTPS | 200 |
| POST-only endpoints (`/ticket/create`, `/summarize-chat`) | mounted (405 on GET) |
| Prisma schemas (`prisma/` vs `ai-core/`) | model lists identical |
| Cost dashboard | renders backfilled data; nightly cron installed |
| Docker (weaviate, postgres) | up |
| Disk | 49% used |
| Test suite | 641 passed |

## Follow-ups (non-blocking)

- The four modules that snapshot `OPENAI_MODEL = resolve_model("basic")` at
  module level (summarize, rag_classifier, fact_grounding,
  query_understanding) now get correct values thanks to the early dotenv
  load, but call-time resolution there would be cleaner.
- Client still ships the v1 clarification-buttons UI; v2 never triggers it.
  Harmless dead weight — remove in a future client pass.
- `docs/programmer-guide/` not audited line-by-line tonight.
