# The $100/month ceiling: how it is enforced

Operator decision, 2026-08-04. One hundred dollars a month, split into two
purses that fail differently and so are controlled differently:

| purse | amount | who spends it | control |
|---|---|---|---|
| students | **$75** | the running service | throttled in four stages |
| eval | **$25** | `run_eval` during development | refused once empty |

## Why a daily line, not just a monthly one

Measured on 2026-08-04: one client at the default rate limit (20 messages
per minute) can issue **28,800 messages a day**. On `gpt-5.6-terra` at
$0.01379 per call that is **$397 a day** — the entire monthly ceiling in
about six hours.

A ceiling checked at the end of the month is not a control. The guard runs
every 15 minutes and compares against `$75 / days-in-month` as well as
against the monthly total. In a 31-day month that daily line is **$2.42**.

## Why the service degrades before it denies

`gpt-5.6-terra` costs **21× `gpt-5.6-luna` per call** ($0.01379 vs
$0.00066, measured over 1,054 calls). Forcing everything to luna therefore
removes about 95% of the spend while every feature keeps working — hard
questions are answered less well, but they are answered.

For scale: in August 2026, terra was **15% of calls and 83% of cost**.

So model downgrade sits two rungs below refusing students, and refusal has
**no daily trigger at all** — only an exhausted monthly purse can take the
service away.

## The four stages

| level | trigger (either one) | what changes for students |
|---|---|---|
| 0 normal | — | nothing |
| 1 `alert` | day ≥ 1× line, or month ≥ 70% ($52.50) | nothing — email only |
| 2 `cheap_model` | day ≥ 1.5× ($3.63), or month ≥ 85% ($63.75) | reasoning model forced to luna |
| 3 `tightened` | day ≥ 2.5× ($6.05), or month ≥ 95% ($71.25) | rate limit 20→6/min, turns 80→20 |
| 4 `refusing_new` | month ≥ 100% ($75.00) | new conversations declined, pointed at Ask Us; open ones finish |

Escalation is immediate. **Recovery needs 10% clearance below the trigger
and steps down one rung at a time** — otherwise the guard flaps across a
threshold every 15 minutes and emails on each crossing.

A state file from a previous month is treated as normal: the purse refills
at midnight on the 1st.

## Two deliberate design choices you should know about

**It fails OPEN.** If `budget_state.json` is missing or corrupt, the
service runs normally and logs an error. A bot that refuses every student
because of a JSON typo is worse than one that overspends for the fifteen
minutes until the next guard run. The report says so loudly when the state
file is missing or stale.

**A stale state keeps its level** rather than reverting to normal, so a
broken cron cannot quietly un-throttle a runaway month.

## Files

| path | what |
|---|---|
| `ai-core/src/config/budget.py` | the numbers, the ladder, the state file |
| `ai-core/src/observability/spend_ledger.py` | reads both purses; records eval spend |
| `ai-core/scripts/budget_guard.py` | every 15 min: decide the level, alert on change |
| `ai-core/scripts/budget_report.py` | the monthly report |
| `ai-core/scripts/eval_budget_gate.py` | refuses an eval run that would breach $25 |
| `/opt/chatbot/data/budget_state.json` | current level — the service reads this |
| `/opt/chatbot/data/budget_events.jsonl` | append-only history of level changes |

## Commands

Check where we stand, change nothing:

```bash
cd /opt/chatbot/ai-core && set -a && . /opt/chatbot/.env && set +a && .venv/bin/python scripts/budget_guard.py --dry-run
```

Read the current level as the service sees it:

```bash
cd /opt/chatbot/ai-core && .venv/bin/python scripts/budget_guard.py --show
```

The monthly report:

```bash
cd /opt/chatbot/ai-core && set -a && . /opt/chatbot/.env && set +a && .venv/bin/python scripts/budget_report.py
```

Report as a web page, plus email:

```bash
cd /opt/chatbot/ai-core && set -a && . /opt/chatbot/.env && set +a && .venv/bin/python scripts/budget_report.py --html /tmp/budget.html --email
```

Before an eval run:

```bash
cd /opt/chatbot/ai-core && set -a && . /opt/chatbot/.env && set +a && .venv/bin/python scripts/eval_budget_gate.py --status
```

## Overriding on purpose

Every number is an environment variable, so raising a line is a deliberate,
recorded act rather than a code edit:

```
BUDGET_MONTHLY_SERVING_USD=75
BUDGET_MONTHLY_EVAL_USD=25
BUDGET_EVAL_RUN_ESTIMATE_USD=6
BUDGET_TIGHTENED_RATE_MAX=6
BUDGET_TIGHTENED_MAX_TURNS=20
BUDGET_RECOVERY_MARGIN=0.10
```

To clear a level immediately after fixing the cause, run the guard: it
recomputes from actual spend and will step down if the numbers allow it.
To force normal now, delete the state file — but the next guard run will
re-derive the real level 15 minutes later.

## What to do when it escalates

The report's section 2 exists to answer **which number moved**, because
cost is `volume × model mix × (1 − cache rate)` and those three fail
independently.

1. **Cache rate fell, volume flat** — a prompt prefix drifted. This is the
   silent one: it multiplied measured terra spend by 2.7× with no traffic
   change. Fixing it costs students nothing, so fix it first.
2. **terra's share of calls rose** — something is routing easy questions to
   the expensive model. Check the router before touching the ceiling.
3. **Volume rose from one client** — that is abuse, not demand. Level 3
   handles it; confirm against the rate-limit abuse alert.
4. **Volume rose across many clients** — that is real demand, and it is the
   good problem. Raise the line rather than degrade the service.

## What this does not cover

The `text-embedding-3-large` calls made during a corpus rebuild are not in
`ModelTokenUsage` and so are not in either purse. A full rebuild is
infrequent and cheap relative to $100, but it is real spend and it is
invisible here. Do not treat these two purses as the whole OpenAI invoice.

## After 2026-09-04: the split changes

The operator's last working day before parental leave is 2026-09-04.
Development stops, so the eval purse shrinks and the money goes back to
students. One env change, no code:

```
BUDGET_MONTHLY_EVAL_USD=5
BUDGET_MONTHLY_SERVING_USD=95
```

The ceiling stays $100. The daily student line rises from $2.42 to $3.17 in
a 30-day month, and every rung on the ladder moves with it automatically.

## Related controls added at the same time

| control | file | what it bounds |
|---|---|---|
| Booking caps | `src/observability/booking_quota.py` | 2 rooms per conversation, 2 per email per day, **through this bot only** |
| Alert tiers | `src/observability/incident_alerts.py` | only `health` and `budget_exhausted` interrupt a person; the rest go to `scripts/alert_digest.py` |
| Eval purse gate | `src/eval/run_eval.py` | refuses a run that would breach the $25, before it spends |

## The external watchdog

`ai-core/scripts/liveness_watchdog.py`, every 5 minutes from cron.

Everything else that monitors this service runs **inside** it and dies with
it. `Restart=always` covers an ordinary crash, but `StartLimitBurst=5` /
`StartLimitIntervalSec=60` mean that five failed starts in a minute make
systemd **stop retrying** — and then the bot is off, nothing is bringing it
back, and nobody is told, because the process that would have sent the mail
is the one that died.

- Alive = **HTTP 200 from `/health`**, not "the port accepts a connection"
  (uvicorn can be listening while the app is wedged).
- Alerts on **transitions only**, after 2 consecutive failures, so a slow
  response during a restart mails nobody. Recovery is mailed too.
- `--try-restart` makes **one** recovery attempt when systemd has given up,
  at most once per 30 minutes, and says in the mail what it did. Without the
  flag it only reports.

## Load test, 2026-08-04 (no-cost run)

Ramped concurrency against `/health` and socket connects only — no chat
messages, so no model spend. Aborts if available memory drops below 350MB
(this box lost 19,972 freshly embedded chunks to an OOM on 2026-07-29).

**Memory was never the limit.** The service peaked at 1,799MB against a
2,500MB cgroup ceiling and available memory stayed above 1GB throughout.

**What it found instead:** `/health` ran live dependency probes on *every*
request, including an outbound call to api.openai.com — 2,155ms per hit, and
nginx exposes it publicly and unauthenticated (`location /health`), outside
the chat rate limiter. 2,000 requests left the service unresponsive for 90
seconds. That is amplification from a single curl loop.

Fixed by caching probe results for 30s (`HEALTH_PROBE_TTL_S`):

| | before | after |
|---|---|---|
| `/health` first hit | 2,155ms | 705ms |
| `/health` repeat hit | 2,155ms | **103ms** |
| throughput | 6.7 rps | **9.5 rps** |
| 1,000 reqs @ conc 100 | 232 ok / 768 timeout | **1000 ok / 0 timeout** |
| recovery after 2,000 reqs | 90s | **20s** |

Failures are cached too, on purpose: a dependency that is down will still be
down a second later, and re-probing per request is the amplification this
exists to stop.

**Still the ceiling:** ~200 concurrent HTTP requests saturates the single
uvicorn worker regardless. That is a capacity fact, not a bug — worth knowing
before a launch, and the reason `/health/live` (1.8ms, no dependencies) is
what the watchdog polls.
