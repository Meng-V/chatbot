# Operator Runbook — the new (v2-rebuild) surfaces

This is the "what's running today, how do I touch it" doc for the
**rebuild** surfaces shipped since the v3.1 legacy bot
(PRs #71–78, May 2026). It is intentionally narrow:

- **In scope:** the new HTTP endpoints, observability, rate limit,
  3-tier model config, admin review surface, cost rollup, ETL gate,
  hours date-window. The things an on-call needs to know to keep them
  alive and figure out what just broke.
- **Out of scope:** the legacy v3.1 serving path. That's documented
  under `docs/01-…` through `docs/12-…` and remains correct for what
  it covers. Today the legacy code still serves **100% of traffic**
  (`VITE_V2_ROLLOUT_PERCENT=0`). Until that changes, "operating the
  bot" largely means "operating the legacy bot via those docs."

Companion docs you should know about:

| Doc | When to read it |
|---|---|
| `ai-core/scripts/etl/FIRST_RUN.md` | Running the ETL prepare→approve→apply flow. |
| `ai-core/admin/README.md` | Standing up the Metabase v0 review interim. |
| `ai-core/docs/WEAVIATE_SERVER_DEPLOYMENT.md` | One-time Weaviate-server provisioning. |
| `docs/notes.md` | Personal notes / SSH tunnel hosts (qum's working file). |

---

## 1. New HTTP surfaces

All mounted from `ai-core/src/main.py`. They live alongside the legacy
endpoints, so reaching them does **not** turn on the v2 bot.

| Path | Purpose | When it appears |
|---|---|---|
| `GET /health/live` | Liveness — is the FastAPI worker responding? Always 200 if process is up. | Always. Use from load balancer. |
| `GET /health/ready` | Readiness — runs Weaviate / Postgres / OpenAI / LibCal probes + ETL freshness. 200 only if all pass. | Always. Use from k8s readiness or status page. |
| `GET /metrics` | Prometheus exposition (request rate, LLM token counts, cache-hit, refusal rate, tool latency). | Only if `prometheus-client` is installed. Otherwise serves a one-line sentinel. |
| `GET /smoketest` | End-to-end synthetic: pushes a canned question through the agent + asserts citation + non-refusal + latency. | Always. Wire to UptimeRobot / BetterStack hitting every 5 min. |
| `GET /admin/reviews` | List flagged conversations (thumb-down). | Only when `ADMIN_API_TOKEN` env var is set. Fail-closed. |
| `GET /admin/reviews/{id}` | Drill into one conversation (tokens, tools, citations, handoff). | Same gate. |
| `GET /admin/reviews/view` | Server-rendered HTML review page (auth = `?key=<token>`). | Same gate. Bookmarkable. |
| `GET/POST /librarian/ticket` | Staff "the bot answered this wrong" report form (added 2026-07-16). Auth = `?key=<LIBRARIAN_TICKET_CODE>` — a distributable staff code, NOT the admin token. Each submission is stored (`CorrectionTicket` table) and emailed to `ALERT_EMAIL_TO`. | Mounted with the admin block; the form 401s until `LIBRARIAN_TICKET_CODE` is set. |
| `GET /admin/` | **Operator hub** — one bookmarkable page linking every admin surface (tickets, reviews, corrections, cost, probes) with your key carried in each link. | `ADMIN_API_TOKEN` gate. |
| `GET /librarian/` | **Staff hub** — one page for library staff (ticket form + Ask Us). Distribute THIS link instead of individual URLs. | `LIBRARIAN_TICKET_CODE` gate. |
| `GET /admin/tickets/view` | Operator queue for those tickets, newest first, with open→reviewed→done status links and a ⚠️ marker on tickets whose alert email failed to send. | `ADMIN_API_TOKEN` gate. Bookmarkable. |

For the agent's own request/response endpoints, see the legacy docs —
those haven't moved.

### Auth note on `/admin/...`

The whole admin router is mounted **only** when `ADMIN_API_TOKEN` is
present in the environment. If it isn't, the routes do not exist
(404, not 401). That's deliberate: no token = no admin surface, no way
to brute force what isn't there.

When the token IS set, every request must include:

```
GET /admin/reviews
Authorization: Bearer <ADMIN_API_TOKEN>
```

…or for the HTML view, the token as a `?key=` query param so the URL
is bookmarkable in a librarian's browser:

```
https://<host>/admin/reviews/view?key=<ADMIN_API_TOKEN>
```

Rotate the token by setting a new value and restarting; there's no
session state to invalidate.

---

## 2. Environment variables (the new ones)

These are the env vars introduced by the rebuild. Legacy vars are
documented in `docs/07-ENVIRONMENT-VARIABLES.md`.

### Model selection (PR #74)

```env
LLM_MODEL_BASIC=gpt-5.4-mini       # default chat agent + synthesizer
LLM_MODEL_REASONING=gpt-5.4        # promoted for multi-hop / ambiguous
LLM_MODEL_CHEAP=gpt-5.4-nano       # LLM-as-judge in eval, light tasks
LLM_MODEL_EMBEDDING=text-embedding-3-large
LLM_ALLOW_TEMPERATURE_CHEAP=0      # opt-in: send temperature to nano
                                   # (gpt-5.4 family otherwise omits it)
```

The whole codebase reads through `src/config/models.py::resolve_model()`.
Changing a model identifier in one of these vars + restart updates
every call site. **Do not hard-code model strings.**

The `gpt-5.4` family is a reasoning family; per OpenAI docs we don't
send `temperature` to them by default. `supports_temperature(model)`
gates that. The `LLM_ALLOW_TEMPERATURE_CHEAP` knob exists because the
nano variant may accept temperature in some configs — leave at 0
unless you've tested it and have a measurable reason.

### Rate limit (PR #73)

```env
RATE_LIMIT_PER_IP_PER_MIN=20       # /ask + Socket.IO message events
RATE_LIMIT_MESSAGE_CHAR_CAP=4000   # reject longer messages outright
```

Both have safe defaults baked in. The limiter **fails open** on
internal errors — if Redis or the in-process store craters, traffic
flows; the on-call sees a WARN in logs. Pick the limit based on what
the upstream LLM rate limit lets you safely sustain.

### Admin surface (PR #76)

```env
ADMIN_API_TOKEN=...                # presence gates the entire router
                                   # generate with: openssl rand -hex 32
```

### Observability (PR #71)

```env
SENTRY_DSN=https://...             # backend errors → Sentry
SENTRY_ENVIRONMENT=production      # or staging / dev
```

If `SENTRY_DSN` is unset, the Sentry init is a no-op (no exception,
no log spam). Errors still print to stderr; nothing degrades.

---

## 3. Day-to-day tasks

### Run the offline test suite before merging anything

```bash
cd ai-core
bash scripts/run_offline_tests.sh
```

Exits non-zero if any of the offline-clean modules fail. The script
lists which modules are **integration-only** (need prisma / Weaviate /
OpenAI / Google CSE) at the bottom — those aren't run by the script;
run them by hand when their env is set up.

When you add a new test file, append it to the right list in
`scripts/run_offline_tests.sh` (sorted, one entry per line).

### Verify prompt caching still works

After editing any `src/prompts/*_v1.py` file (or changing the
`LLM_MODEL_*` env vars to a new model family), re-verify the cache:

```bash
cd ai-core
python -m scripts.verify_prompt_cache --prefix synthesizer_v1
python -m scripts.verify_prompt_cache --prefix agent_v1 --model gpt-5.4-mini
python -m scripts.verify_prompt_cache --prefix judge_v1 --model gpt-5.4-nano
python -m scripts.verify_prompt_cache --prefix clarifier_v1 --model gpt-5.4-mini
```

Each makes a small number of real OpenAI calls (~$0.005) and exits
non-zero if cache hit rate falls below 60%. The first call always
misses (cold start); the rate is computed on calls 2..N.

If a check fails, the byte-stability log in `src/prompts/builder.py`
will show which prefix changed call-to-call. Fix it before deploying
or expect the daily cost rollup to flag a regression within 24h.

See findings: `ai-core/src/eval/findings/2026-05-20_cache_hit_verification.md`

### Live-verify the v2 serving path

The v2 stack (rebuilt orchestrator behind `?v2=1`) is code-complete
but the round-trip is only verifiable against a real OpenAI +
Weaviate + Postgres. Before you raise `VITE_V2_ROLLOUT_PERCENT` above
0 for the first time, run:

```bash
cd ai-core
.venv/bin/python -m scripts.verify_v2_serving --host http://localhost:8000
```

What it checks (in order):

1. `GET /health/ready` → 200 (all dep probes pass)
2. `GET /smoketest` → 200 with citations and not refused
3. v2 socket connect to `/smartchatbot/v2/socket.io` succeeds
4. v2 socket send → response has `citations[]` and `confidence` keys
   (the additive v2 shape — proves the orchestrator wired up, not just
   the socket transport)
5. legacy socket still responds (wrap-safety guard — confirms the
   `socketio.ASGIApp` wrap in `main.py` didn't break the 100% path)

Exit 0 = safe to flip the rollout flag. Exit 1 = do NOT flip; read
the FAIL lines.

If your env doesn't have legacy creds (rare), pass `--skip-legacy`.
Default question is hours-class because hours questions are the most
LibCal-grounded and least likely to legitimately refuse; override
with `--question "..."` if you want to probe a specific intent.
### Run the full real-LLM + judge eval

This is the load-bearing quality measurement — 184 gold cases through
the v2 stack (classifier + retrieval + agent + synth + judge). Real
OpenAI, real Weaviate, real Postgres, real verdicts. ~20–30 minutes,
~$0.30–$0.50 per run (the per-case cost is ~20× cheaper than originally
budgeted; verified 2026-05-20).

**Prerequisites (all three must be true or the run dies at startup or
mid-flight with cryptic errors):**

```bash
# 1. Tunnels up (Weaviate on ulblwebp20, Postgres on ulblwebt04)
ssh -fN -L 8888:127.0.0.1:8888 -L 50051:127.0.0.1:50051 qum@ulblwebp20.lib.miamioh.edu
ssh -fN -L 5432:127.0.0.1:5432 qum@ulblwebt04.lib.miamioh.edu

# 2. Verify
nc -z -w2 127.0.0.1 8888 && nc -z -w2 127.0.0.1 50051 && nc -z -w2 127.0.0.1 5432 \
  && echo "ALL TUNNELS UP" || echo "TUNNEL MISSING"

# 3. OPENAI_API_KEY in .env (the project's resolve_model("basic") path will use it)
```

**Run it (note: `.venv/bin/python`, NOT system `python3` — prisma is
only installed in the venv):**

```bash
cd ai-core
.venv/bin/python -m src.eval.run_eval \
    --with-real-llm --with-judge \
    --results-out eval_results/full_eval_$(date +%Y%m%d).jsonl \
    2>&1 | tee eval_results/full_eval_$(date +%Y%m%d).log
```

Streams per-case JSONL while it runs, so an interrupted run still
leaves a partial-but-analyzable file behind.

**Analyze the results:**

```bash
# Aggregate summary (PASS/PARTIAL/FAIL by judge verdict, cache hit, latency)
.venv/bin/python -m scripts.analyze_eval_results eval_results/full_eval_YYYYMMDD.jsonl

# Per-category PASS/FAIL table
.venv/bin/python -m scripts.analyze_eval_results <jsonl> --by category

# Per-intent breakdown
.venv/bin/python -m scripts.analyze_eval_results <jsonl> --by intent

# List every FAIL case with judge verdict + answer preview
.venv/bin/python -m scripts.analyze_eval_results <jsonl> --fails

# Drill into one specific case (full bot_answer, classifier candidates, tokens)
.venv/bin/python -m scripts.analyze_eval_results <jsonl> --id fs_makerspace_3d

# The 20 slowest cases (where latency budget lives)
.venv/bin/python -m scripts.analyze_eval_results <jsonl> --slowest 20
```

The analyzer is tolerant of partial files — you can run it WHILE the
eval is still going to spot-check progress without disturbing the
streaming write.

**Expected ballpark numbers** (refine as more runs come in):

- PASS (correct + refused_correctly): aim for ≥ 75%
- Scope-resolver match: ≥ 95% (the resolver is rule-based, ought to be near-perfect)
- Cache hit rate: ≥ 60% across the whole run (first call cold-misses;
  steady state warms up after ~3 cases)
- p95 latency: < 30s per case (one slow case can spike this; spot-check
  --slowest 5 if it's high)

**Gotchas:**

- If startup errors with `Weaviate unreachable -- the SSH tunnel is
  down`, the runner is doing its job — re-run after the tunnel comes
  back. Don't try to bypass.
- If turn errors with `ModuleNotFoundError: No module named 'prisma'`,
  you're on system python; rerun with `.venv/bin/python`.
- A run produces ~$0.40 in OpenAI spend; the DailyCost rollup
  (`scripts.cost_rollup`) WILL show this as a spike. Tag the date in
  the cost dashboard so it's not flagged as anomaly.

### Weekly ETL refresh

See `ai-core/scripts/etl/FIRST_RUN.md` for the full prepare→approve→
apply gate flow. The TL;DR cycle is:

```bash
# Operator (Mon 9am after the Sun 2am cron prepares the diff)
.venv/bin/python -m scripts.etl.run_etl --phase prepare      # already cron'd
# … librarian opens the diff, signs the .approval token …
.venv/bin/python -m scripts.etl.run_etl --phase apply        # operator runs after sign-off
```

If the cron didn't run, the diff folder under `ai-core/data/diffs/`
shows no new entry for the week — that's your signal.

### Daily cost rollup (PR #77 — once merged)

Cron:

```cron
0 2 * * *   cd /path/to/ai-core && .venv/bin/python -m scripts.cost_rollup
```

Reads yesterday's `ModelTokenUsage` rows, multiplies by the verified
per-model price (in `scripts/cost_rollup.py::PRICE_PER_1M_TOKENS`),
upserts one `DailyCost` row per `(date, model, call_site)`.

Backfill:

```bash
.venv/bin/python -m scripts.cost_rollup --backfill 30   # last 30 days
.venv/bin/python -m scripts.cost_rollup --date 2026-04-22  # one day
```

The upsert is keyed on `(date, model, call_site)` so re-running for a
date you've already rolled up is a no-op, not a double-count. Verified
live on 2026-05-19 with `--date 2026-05-12` ran twice → exactly one row.

If you add a new model to `src/config/models.py` and don't add a row
to `PRICE_PER_1M_TOKENS`, the lock-in test
`scripts.test_cost_rollup::test_price_table_covers_models_in_use`
fails loudly in the offline runner. Don't deploy past that.

### Re-seed `LibrarySpace_v2`

If a librarian gives you updated `services_offered` truth or fixes a
URL in `scripts/seed_library_spaces_v2.py`:

```bash
cd ai-core
.venv/bin/python -m scripts.seed_library_spaces_v2
```

The seed is idempotent (`@@unique([campus, library])` upsert). 6 rows
total; running twice produces no duplicates. Last operator change was
PR #75 (capacity bumps + hours_source path).

### Look at flagged conversations

Once `ADMIN_API_TOKEN` is set:

- Librarian self-service: send them the URL
  `https://<host>/admin/reviews/view?key=<TOKEN>` and ask them to
  report any conversation by `message_id` + timestamp.
- API: `curl -H "Authorization: Bearer $ADMIN_API_TOKEN"
  https://<host>/admin/reviews`.

Both are read-only by design — the librarian flags, the operator
applies a `ManualCorrection` row by hand (the v0 path; the v1 UI is
post-launch work).

---

## 4. Common alerts and what to do

### `/health/ready` returns 503

Body is JSON listing which probe failed. Most likely:

- `weaviate`: Weaviate down. Check the SSH tunnel (ports 8888/50051
  to `ulblwebp20.lib.miamioh.edu`). Restart the tunnel; readiness
  recovers within one probe cycle.
- `postgres`: DB connection lost. Most likely the SSH tunnel to
  `ulblwebt04.lib.miamioh.edu` dropped. Restore the tunnel.
- `openai`: OpenAI API unreachable from this host. If their status
  page is green, it's network egress (firewall, proxy). If their
  status page is red, you can't fix it — let it drain.
- `etl_freshness > 8 days`: weekly cron hasn't completed. Read
  `data/diffs/` to confirm; if last diff is old, the cron job is
  broken; investigate the cron host, not the bot.

### `/smoketest` failing

The synthetic question went through and didn't return citations OR
returned a refusal OR took > 8s. This catches "everything looks
healthy individually but the chain is broken" (a stale OpenAI key,
broken adapter wiring, a deploy that didn't pick up new env). Read
the response body — it includes which assertion failed.

### Daily cost spike alert

A prompt regression (or accidental shell-loop) that tanks the cache
hit rate burns budget invisibly until the rollup notices. When the
1.5x trailing-7-day threshold trips:

1. Query the last 24h of `ModelTokenUsage`, sort by `cached_input_tokens
   / input_tokens` ascending. The call site at the bottom is your
   prefix-drift suspect.
2. Cross-check `src/prompts/builder.py` byte-stability log — every
   prefix mismatch logs the offending stable_id.

### Rate limiter logging WARN

The limiter fails open on internal errors. A burst of
`rate_limit_internal_error` WARNs means the limiter itself is broken
(in-process store corrupted, Redis down). Traffic is flowing; users
aren't blocked. Fix the limiter at convenience — don't page out.

---

## 5. What "deploy" actually does (today, May 2026)

Today there's no real deploy automation for the rebuild. Operationally
that means:

1. Merge PR to `main`.
2. SSH to the prod-ish host.
3. `git pull` in the deploy checkout.
4. `pip install -e .` if dependencies changed.
5. `prisma generate` if `prisma/schema.prisma` changed.
6. Restart the FastAPI worker.

The legacy bot continues to serve traffic the whole time — v2 routes
are reachable on the same process, just not used by the rollout flag
yet. So a botched rebuild deploy degrades the new surfaces (admin,
metrics, smoketest) but does not take the chat down.

When you flip `VITE_V2_ROLLOUT_PERCENT` above 0 in the client, that's
when "the chatbot is down" becomes a real risk from a rebuild deploy.
That flip is a deliberate, separately-reviewed change, not a side
effect of a code merge.

---

## 6. Where the rebuild stands (snapshot, 2026-05-19)

For the long version, see the **Robustness ladder** section of the
plan at `~/.claude/plans/i-am-a-web-breezy-prism.md`. Short version:

- **Threshold 1 (Architecture)** — done.
- **Threshold 2 (Internally usable)** — agent + synthesizer + scope +
  service guard land; you can hit the v2 endpoints from the API.
  Real-LLM eval validates quality (was blocked on OpenAI credit; user
  is refilling).
- **Threshold 3 (10% real-user flag)** — gated on: librarian sign-off
  for `services_offered` truth (Gap 3), wiring `RolloutFlag` to send
  traffic, +1 round of UAT.
- **Threshold 4 (Robust)** — Op 1 v1 React admin, Op 2 correction
  UI, full alerting on Op 3 metrics.

This doc covers operating what exists. The plan covers what's next.
