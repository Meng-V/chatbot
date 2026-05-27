# 08 — Operations

> Ongoing care and feeding. Monitoring, librarian-facing workflows, scheduled jobs, weekly digests.

## What ops looks like, day to day

The bot is mostly self-running. The work you do is:
1. **Watch monitoring** — Sentry alerts, smoketest pinger, cost rollups
2. **Process librarian feedback** — when a librarian flags a wrong answer, file a `ManualCorrection`
3. **Maintain the weekly ETL** — review the diff before it auto-applies
4. **Rotate credentials** — periodic OpenAI / LibCal / LibGuides key refresh
5. **Re-run eval** when prompts or tools change

If you're doing more than that, something is going wrong. See [05-TROUBLESHOOTING.md](05-TROUBLESHOOTING.md).

---

## Monitoring stack

| Signal | Tool | What to watch |
|---|---|---|
| Backend exceptions | Sentry | Any new error type, especially in `v2_serving` or `new_orchestrator` |
| Synthetic uptime | `/smoketest` + UptimeRobot/BetterStack | 5-min pinger; alert if 3 consecutive fails |
| Health endpoints | `/health/ready` from load balancer | Should return 200; if not, route traffic away |
| Per-day costs | `DailyCost` Postgres table | Alert if >1.5× the 7-day average |
| User-facing bad answers | `ManualCorrection` Postgres table | If filings spike, the bot is degrading |
| Cache efficiency | `ModelTokenUsage.cached_input_tokens / input_tokens` | ≥60% steady-state |

### Useful Postgres queries

```sql
-- New ManualCorrection rows in last 24h
SELECT created_at, created_by, scope, target, action, reason
FROM "ManualCorrection"
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- Cache hit rate last 24h
SELECT
  SUM("cached_input_tokens")::float / NULLIF(SUM("input_tokens"), 0) * 100 AS cache_hit_pct,
  COUNT(*) AS turns
FROM "ModelTokenUsage"
WHERE "createdAt" > NOW() - INTERVAL '24 hours';

-- Refusal rate last 24h (v2 only)
SELECT
  COUNT(*) FILTER (WHERE "refusal_trigger" IS NOT NULL)::float / COUNT(*) * 100 AS refusal_rate_pct,
  COUNT(*) AS turns
FROM "Message"
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Top refusal triggers
SELECT "refusal_trigger", COUNT(*) AS n
FROM "Message"
WHERE created_at > NOW() - INTERVAL '7 days' AND "refusal_trigger" IS NOT NULL
GROUP BY 1 ORDER BY n DESC LIMIT 20;

-- Daily cost trend (last 30 days)
SELECT date, model, ROUND(usd::numeric, 2) AS usd
FROM "DailyCost"
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC, model;
```

---

## ManualCorrection workflow (librarian-facing)

This is the bot's safety net. When a librarian sees the bot give a wrong answer, they file a row in `ManualCorrection` and the bot honors it on the next turn — no deploy required.

### Schema

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'ManualCorrection';
```

```
id              SERIAL PRIMARY KEY
scope           TEXT    -- "url" | "chunk" | "intent" | "global"
target          TEXT    -- url, chunk_id, intent name, or "*"
action          TEXT    -- "suppress" | "replace" | "pin" | "blacklist_url"
replacement     TEXT    -- for action=replace: the corrected text
query_pattern   TEXT    -- for action=pin: regex matching user questions
reason          TEXT    -- required, no anonymous corrections
created_by      TEXT    -- librarian email
created_at      TIMESTAMP
expires_at      TIMESTAMP   -- forced 6-month review; default NOW()+180d
active          BOOLEAN     -- default true
```

### The 4 action types

#### `suppress` — drop a chunk from retrieval

When: a specific chunk has bad data, the underlying page is right but the chunk extracted poorly.

```sql
INSERT INTO "ManualCorrection" (scope, target, action, reason, created_by, expires_at, active)
VALUES (
  'chunk', 'c-abc123', 'suppress',
  'Chunk text says "open 24 hours" but King is not 24 hours — extraction error',
  'librarian@miamioh.edu',
  NOW() + INTERVAL '180 days', true
);
```

Effect: that `chunk_id` is excluded from `search_kb` results until the next ETL re-extracts and replaces.

#### `replace` — substitute chunk text

When: the page is wrong (and the website team is fixing it), but in the meantime you want the bot to give the right answer.

```sql
INSERT INTO "ManualCorrection" (scope, target, action, replacement, reason, created_by, expires_at, active)
VALUES (
  'chunk', 'c-def456', 'replace',
  'The ILL turnaround for journal articles is 2-3 business days, not 5-7 as the page currently states.',
  'Page is out of date; web team fixing in PR #123',
  'librarian@miamioh.edu',
  NOW() + INTERVAL '60 days', true
);
```

Effect: retrieval still returns the chunk, but with the replacement text + a "librarian-corrected" provenance marker shown in the citation chip.

#### `blacklist_url` — never cite a URL

When: a URL is dead, redirects to spam, or the page has wrong information that we can't get fixed.

```sql
INSERT INTO "ManualCorrection" (scope, target, action, reason, created_by, expires_at, active)
VALUES (
  'url', 'https://www.lib.miamioh.edu/about/old-page/', 'blacklist_url',
  'Page deleted by web team; should not be cited',
  'librarian@miamioh.edu',
  NOW() + INTERVAL '180 days', true
);
```

Effect: `UrlSeen.isBlacklisted = true`. The post-processor refuses any answer mentioning that URL.

#### `pin` — force a specific page at rank 1 for matching queries

When: bot keeps missing the canonical page for a common question.

```sql
INSERT INTO "ManualCorrection" (scope, target, action, query_pattern, reason, created_by, expires_at, active)
VALUES (
  'url', 'https://libguides.lib.miamioh.edu/citation/apa', 'pin',
  '(?i)\b(apa|cite|citation).*\b(format|style)\b',
  'Bot was returning generic citation guide; pin the APA-specific page',
  'librarian@miamioh.edu',
  NOW() + INTERVAL '180 days', true
);
```

Effect: when the user's question matches the regex, the pinned chunk is injected at rank 1 in `search_kb` results.

Use sparingly — over-pinning fights the retrieval system. If you're pinning often, the retrieval is broken; fix that instead.

### Review cycle

All corrections default to `expires_at = NOW() + 180 days`. When they expire:
- A weekly cron (TODO if not yet built) emails the `created_by` librarian: "your correction X is expiring; confirm or extend?"
- If not confirmed within 7 days, `active` flips to false (correction stops firing)

This prevents stale corrections from accumulating forever.

### Audit / fire counts

Every time a correction fires (suppresses / replaces / pins something during a turn), it's logged to the `Message` table's `fired_corrections` array. Periodic report:

```sql
-- Top-firing corrections last 7 days
SELECT
  c.id, c.target, c.action, c.reason, c.created_by,
  COUNT(*) AS fire_count
FROM "ManualCorrection" c
JOIN "Message" m ON c.id = ANY(m.fired_corrections)
WHERE m.created_at > NOW() - INTERVAL '7 days'
GROUP BY c.id, c.target, c.action, c.reason, c.created_by
ORDER BY fire_count DESC
LIMIT 20;
```

If one URL is being suppressed/replaced very often, the underlying page is the problem — escalate to the web team.

---

## Subject-librarian review queue

Reading every conversation the bot has is impossible. Instead, librarians review a filtered queue of conversations that touched their subject area.

The match logic (when implemented in the admin UI):
- Bot cited a `source_url` whose owning subject matches a `Librarian.subjects` row
- OR user message contains a course / dept / major code in this librarian's subjects
- OR conversation's `scope.campus` matches this librarian's `campus` (regional librarians see their campus's traffic by default)

### MVP without admin UI (Metabase / shared spreadsheet)

For phase-1 ops before a real admin UI exists, librarians use Metabase saved queries:

```sql
-- My subject's recent dialogs (librarian fills in their subject IDs)
SELECT m.id, m.created_at, m.user_message, m.bot_answer, m.cited_chunk_ids, m.refusal_trigger
FROM "Message" m
JOIN "ChunkProvenance" cp ON cp.chunk_id = ANY(m.cited_chunk_ids)
WHERE cp.source_url IN (SELECT url FROM "LibGuide" WHERE id IN (SELECT "libGuideId" FROM "LibGuideSubject" WHERE "subjectId" = <YOUR_SUBJECT_ID>))
  AND m.created_at > NOW() - INTERVAL '7 days'
ORDER BY m.created_at DESC
LIMIT 100;
```

Verdict submission: librarian adds a row to a shared Google Sheet with conversation ID + verdict. Periodically synced into a `LibrarianReview` Postgres table.

### Weekly digest email

`ai-core/scripts/digest_email.py` (run Monday 8 AM via cron):
- Per subject librarian: "you have N unreviewed conversations in your area this week; M had thumbs-down ratings; click [link]"
- Per regional librarian: same but filtered by `Librarian.campus`

If this isn't running on your prod, set up the cron.

---

## Scheduled jobs (cron)

```cron
# /etc/cron.d/smart-chatbot

# Weekly ETL prepare (Sunday 2 AM)
0 2 * * 0 cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.etl.run_etl --phase prepare 2>&1 | logger -t etl-prepare

# Daily cost rollup (6:30 AM)
30 6 * * * cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.cost_rollup 2>&1 | logger -t cost-rollup

# Weekly librarian digest (Monday 8 AM)
0 8 * * 1 cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.digest_email 2>&1 | logger -t digest-email

# Daily ManualCorrection expiry check (8 AM)
0 8 * * * cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.expire_corrections 2>&1 | logger -t expire-corrections
```

To verify cron is set up:
```bash
sudo crontab -l
ls -la /etc/cron.d/
sudo journalctl -t etl-prepare --since "30 days ago" --no-pager | tail -20
```

---

## Credential rotation

### OpenAI

1. Generate new key in OpenAI dashboard
2. Update `OPENAI_API_KEY` in `/opt/chatbot/current/.env`
3. Restart backend: `sudo systemctl restart smartchatbot-backend`
4. Verify with a smoke test
5. After confirming new key works, revoke old key

### LibCal / LibGuides OAuth

1. Get new client_id/client_secret from Springshare admin
2. Update `LIBCAL_CLIENT_*` / `LIBAPPS_CLIENT_*` in `.env`
3. Restart backend (OAuth tokens are cached in-process)
4. Verify with `curl http://localhost:8081/health` — LibCal section should be `"healthy"`

### Postgres password

1. Change password in Postgres
2. Update `DATABASE_URL` in `.env`
3. Restart backend

### .env file permissions

```bash
chmod 600 /opt/chatbot/current/.env
chown <service-user>:<service-user> /opt/chatbot/current/.env
```

Only the service user should be able to read it.

---

## Performance benchmarks (what's normal)

| Metric | Healthy range | Concerning if |
|---|---|---|
| `/health/live` p50 | <10ms | >50ms |
| `/health/live` p99 | <50ms | >200ms |
| Chat turn p50 | 2-5s | >10s |
| Chat turn p99 | 5-15s | >30s |
| OpenAI input tokens / turn | 1.5k-3k | >5k |
| Cache hit rate | 70-85% | <60% |
| Refusal rate | 15-25% | >40% |
| Per-day OpenAI cost (production traffic) | $5-30 | >$100 |
| New `ManualCorrection`/week | <10 | >30 |

If you're outside the healthy range, the next step depends:
- High latency → check Weaviate health, LibCal latency, OpenAI rate limits
- Low cache hit → prompt prefix is drifting; check `prompts/builder.py` byte-stability assertion
- High refusal rate → either the corpus is missing content, OR a recent prompt change made the bot too conservative
- High cost → check for prompt regression, tool-call retry loops, or traffic spike
- High correction count → bot quality is degrading; investigate which categories are misfiring

---

## Rolling back a bad day

If "everything is broken" on a Tuesday morning:

1. **Don't panic.** Symlink swap is always available (Option 1 in [03-DEPLOYMENT.md](03-DEPLOYMENT.md)).
2. **Roll back to last known good build:** `sudo ln -sfn /opt/chatbot/builds/<previous>/ /opt/chatbot/current && sudo systemctl restart smartchatbot-backend`.
3. **Verify:** `/smoketest` + sanity-check a few questions in the browser.
4. **Then debug:** what changed in the bad build? `git log` between the two timestamps.

Most "everything is broken" days are actually "one specific service is broken" days (OpenAI down, LibCal flaky, etc.). Distinguish:
- If `curl /health` shows a specific service as unhealthy → that's the issue, not our bot
- If `curl /health` is healthy but bot still misbehaves → it IS our bot, roll back

---

## Long-term operational TODOs

These are aspirational; some may already be done:

- [ ] Build the librarian admin UI (currently MVP via Metabase + spreadsheet)
- [ ] Cron the weekly digest email
- [ ] Cron the ManualCorrection expiry check
- [ ] Wire `/health/ready` into load balancer
- [ ] Set up Prometheus scrape of `/metrics` (if exposed)
- [ ] Per-month cost report email to project lead
- [ ] Quarterly eval suite refresh (re-run, compare to baseline, file regressions)
- [ ] Adversarial prompt-injection red-team pass
- [ ] Multi-tenant isolation (when we share infra with other apps)
- [ ] Per-user rate limiting (if abuse becomes an issue)
