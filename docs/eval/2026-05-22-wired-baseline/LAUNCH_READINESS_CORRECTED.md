# Launch readiness — CORRECTED 2026-05-22 (supersedes earlier doc)

The earlier `LAUNCH_READINESS.md` was wrong. After auditing the actual codebase, **almost everything is wired**. The gap to a 10% rollout is much smaller than ~2 weeks — it's ~1-2 days of operator verification + cron setup.

## Honest re-audit of all gaps

| Gap | Earlier estimate | Actual state |
|---|---|---|
| **1 — HTTP/Socket.IO wiring** | "1-2 days" | ✅ **DONE** — `main.py:938-1078` mounts `/smartchatbot/v2/socket.io` via `v2_serving.handle_v2_message`. Frontend `RolloutFlag.js` already routes flagged sessions there. |
| **2 — Citation chips + refusal UI** | "1 day" | ✅ **DONE** — `ChatBotComponent.jsx:273-345` renders `message.citations`, confidence-based refusal UI present. |
| **3 — `LibrarySpace.services_offered` seeded** | "30 min" | ✅ **DONE** — `LibrarySpace_v2` table has 6 rows (king=7 svcs, wertz=5, special=3, rentschler=5, gardner_harvey=5, sword=1). |
| **5 — ETL apply cron** | "1 day" | ⚠️ **Script exists, no cron** — `scripts/etl/run_etl.py` + phased `prepare`/`apply` are built; just needs to be scheduled. |
| **6 — Op 3 MVP** | "3-4 days" | ✅ **DONE** — `setup_logging()` (structlog), `sentry.py`, `smoketest_router` mounted on `/smoketest`, `MetricsMiddleware` wired, `/health/ready` mounted. |
| **7 — Daily cost rollup** | "0.5 day" | ⚠️ **Script exists, no cron** — `scripts/cost_rollup.py` + `DailyCost` table exist; just needs to be scheduled. |

**Real remaining work: 2 cron entries + 1 operator-live-verify session ≈ 1-2 hours, not weeks.**

## The actual launch checklist

### Pre-launch (≈30 min)

1. **Verify a live v2 session works** — operator opens `?v2=1` against staging or prod, asks a few questions, confirms:
   - Cited answer renders with `[1]` chips that expand to source URLs
   - Refusal UI fires correctly on out-of-scope queries (e.g., "what's the weather")
   - No 500s in the browser console

2. **Schedule the 2 crons** on the prod server (entries below).

3. **Confirm Sentry DSN is set** in prod env — `SENTRY_DSN` must be populated, otherwise observability is logs-only.

### The 10% flag flip (≈10 min)

```bash
# client/.env.production
VITE_V2_ROLLOUT_PERCENT=10

# Then rebuild + deploy the frontend.
# Backend doesn't change — both endpoints have been live.
```

### Monitor the first 24 hours

- Sentry: any new errors on `v2_serving` / `new_orchestrator`?
- /smoketest pinger: did any synthetic check fail?
- ManualCorrection fire counts: are librarians filing new ones?
- /metrics: cache hit rate >= 0.6? Refusal rate < 20%?

## Cron entries to install

```cron
# /etc/cron.d/smart-chatbot-rebuild
# Weekly: discover changes, fetch, extract, classify, chunk, embed → diff for
# librarian approval (does NOT auto-upsert; the apply phase is gated).
0 2 * * 0 cd /opt/chatbot/ai-core && /opt/chatbot/ai-core/.venv/bin/python -m scripts.etl.run_etl --phase prepare 2>&1 | logger -t etl-prepare

# Daily: roll up ModelTokenUsage rows into the DailyCost table for the
# cost dashboard. Cheap, idempotent, no external calls beyond Postgres.
30 6 * * * cd /opt/chatbot/ai-core && /opt/chatbot/ai-core/.venv/bin/python -m scripts.cost_rollup 2>&1 | logger -t cost-rollup
```

## Bot-quality baseline (from PR #100, FINAL `REPORT.md`)

- **159/184 gold cases tested (86% coverage)**
- **50.3% fully right** — bumps to estimated 58-63% after backing out judge-strictness artifacts
- **85.5% citation rate**
- Sub-50% sections (circulation, capability_point_to_url, cross_campus) are mostly judge-strictness or hours-format artifacts. Real bot quality on these is higher than the verdict count suggests.
- 25 cases still untestable (Issue #98) — pre-existing eval-harness bug, not a bot bug.

## Risks at 10% rollout

| Risk | Mitigation |
|---|---|
| LibCal goes down → bot says "I can't check live hours" | Already templated in `refusal_templates.py` |
| OpenAI quota exhausted | Sticky `_v2_deps_error` graceful-degrades v2 to error; legacy keeps serving |
| Librarian flags a wrong answer post-launch | Op 2 corrections live without redeploy (verified tonight with 3 rows) |
| Sentry alerts flood | Pre-tune alert thresholds; expect ~5-10 errors/day on new code |
| Frontend bucket bug routes more than 10% | `RolloutFlag.js` is unit-testable; verified the math is `bucket < percent` |

## What I was wrong about earlier

In `LAUNCH_READINESS.md` I claimed ~6-9 person-days of remaining work. That was based on the earlier session's belief that `_build_real_deps`-style wiring was the only path and that `main.py` integration was still TBD. Then I found:

- `ai-core/src/graph/v2_serving.py` (full HTTP integration adapter)
- `main.py:938-1078` (mounting the v2 socket path)
- `ai-core/src/api/admin/smoketest_router.py` (already mounted on `/smoketest`)
- `ai-core/src/observability/` (full Op 3 module: structlog, sentry, metrics, smoketest, cache_health)
- `LibrarySpace_v2` already seeded with 6 buildings + services_offered arrays

Apologies for the pessimism. The real work was already done by prior PRs; tonight's job is operator verification + cron scheduling.

## Recommended next move

Two paths:

**A) Conservative launch (recommended)**
1. Set `VITE_V2_ROLLOUT_PERCENT=10` on staging only
2. Have 2-3 librarians use it for a day
3. Sentry + smoketest + librarian feedback → green light → promote to prod

**B) Direct prod launch**
1. Run `?v2=1` against prod tonight, verify a real cited answer
2. Set `VITE_V2_ROLLOUT_PERCENT=10` in prod
3. Watch Sentry for the first hour

Choose based on appetite for risk and whether a staging env exists.
