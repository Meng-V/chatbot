# 03 — Production Deployment Runbook

> **This is the file to send to ops / Rachel.** Self-contained, no project context required, every command is copy-paste ready.

## What this document covers

1. The normal deploy flow (pull main → restart)
2. Frontend deploys (when client/ code changes)
3. Database changes (Postgres + Weaviate)
4. Rollback procedures (4 options, ranked by speed/safety)
5. The 4 most common deploy-time errors and their fixes

## What this document assumes

- You have SSH root (or `sudo`) access to the prod server
- The repo is checked out somewhere reachable on prod (typical: `/opt/chatbot/current/`)
- The backend runs as a systemd service (typical: `smartchatbot-backend`)
- Nginx (or another reverse proxy) sits in front of the FastAPI backend

If anything in this assumption list is wrong on your prod, adjust the commands but the structure still applies.

---

## Quick reference: pre-deploy checklist

Before ANY production deploy:

```bash
# 1. Confirm you're SSH'd into the right server
ssh root@<your-prod-host>
hostname  # confirm it's prod, not staging

# 2. Confirm the chatbot path
ls -la /opt/chatbot/current/   # OR your install path

# 3. Confirm the backend service name
sudo systemctl list-units --type=service | grep -iE 'chatbot|smart'
# Note the exact service name (we'll call it $SERVICE below)

# 4. Confirm backend currently running + healthy
sudo systemctl status <service-name> --no-pager | head -10
curl -s http://localhost:8000/health/live
# Expected: Active: active (running); {"status":"alive"}
```

If health is failing BEFORE you deploy, do not proceed — fix the existing issue first.

---

## NORMAL DEPLOY: backend code change

When `ai-core/` has new commits on `main`.

```bash
# 1. SSH in
ssh root@<your-prod-host>
cd /opt/chatbot/current

# 2. Confirm you're on main + see what's coming
git status              # expected: "On branch main" + clean
git fetch origin main
git log --oneline HEAD..origin/main   # see new commits
git log --oneline -1                  # current commit

# 3. Pull
git pull origin main
git log --oneline -1                  # confirm new HEAD

# 4. Install any new Python dependencies (idempotent)
cd ai-core
source .venv/bin/activate
pip install -r requirements.txt

# 5. (Optional) Run unit tests as a final smoke test
.venv/bin/python -m pytest src/ -q 2>&1 | tail -5
# Expected: 189+ passed

# 6. Restart the backend
sudo systemctl restart <service-name>
sleep 5
sudo systemctl status <service-name> --no-pager | head -10
# Expected: Active: active (running), recent start time

# 7. Verify it's serving
curl -s http://localhost:8000/health/live
# Expected: {"status":"alive"}

# 8. Watch live log for a few seconds
sudo tail -f /var/log/smartchatbot_backend
# Press Ctrl-C after you see normal startup messages
```

**Time:** ~3-5 minutes for a typical backend-only deploy.

---

## FRONTEND DEPLOY: client/ code change

When `client/` has new commits. Requires Node.js + npm on prod (or build elsewhere and rsync the `dist/` folder).

```bash
# After pulling main (steps 1-3 above)
cd /opt/chatbot/current/client
npm install                       # idempotent; pulls any new dependencies
npm run build                     # produces client/dist/

# Then deploy client/dist/ to where the web server serves it from.
# This varies — common patterns:

# Pattern A: nginx serves from /var/www/chatbot/
sudo rsync -avz --delete client/dist/ /var/www/chatbot/

# Pattern B: served from inside the project itself
# (no copy needed — uvicorn or nginx serves /opt/chatbot/current/client/dist/)

# Pattern C: served via a separate CDN
# Upload client/dist/ to your CDN bucket
```

**No backend restart needed for frontend-only changes.**

After deploy, force-refresh a browser to pick up the new bundle (browsers cache the old `index-<hash>.js`).

---

## DATABASE CHANGES

### Postgres schema change

If `prisma/schema.prisma` was modified:

```bash
cd /opt/chatbot/current
npx prisma migrate deploy
# Generates and applies pending migrations
```

If you see "url is no longer supported" — the local Node Prisma CLI on prod has drifted to v7 while the project schema is v5/v6 format. Solution:
```bash
# Pin Prisma CLI to a compatible version
cd /opt/chatbot/current
npm install --save-dev prisma@5.22.0   # match the version in package.json
npx prisma migrate deploy
```

### Adding a row to a Postgres truth table (e.g., new library building)

```bash
# Source .env so DATABASE_URL is set
set -a; source /opt/chatbot/current/.env; set +a

# Use psql if available, else Python (asyncpg)
psql "$DATABASE_URL" <<'SQL'
INSERT INTO "LibrarySpace_v2" (...) VALUES (...);
SQL

# Or via Python:
/opt/chatbot/current/ai-core/.venv/bin/python <<'PY'
import os, asyncio, asyncpg
async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    await conn.execute("INSERT INTO ...")
    await conn.close()
asyncio.run(main())
PY
```

See [07-DATA-PIPELINE.md](07-DATA-PIPELINE.md) for the actual MakerSpace insert and other examples.

### Re-wiring operator-gold Weaviate chunks

When `ai-core/src/eval/golden_set*.jsonl` files are updated, the operator-gold chunks need to be re-inserted into Weaviate:

```bash
cd /opt/chatbot/current/ai-core
.venv/bin/python scripts/operator_wiring/wire_gold_to_weaviate.py
# Takes ~1-2 minutes, costs <$0.01 in OpenAI embeddings
# Idempotent: deletes prior operator-gold-* chunks, re-inserts fresh
```

If you see `FileNotFoundError: /Users/qum/.../.env`, the script has a hardcoded dev path. Patch:
```bash
sed -i 's|ROOT = Path("/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e")|ROOT = Path(__file__).resolve().parents[3]|' \
  ai-core/scripts/operator_wiring/wire_gold_to_weaviate.py
```

(Should be fixed in main upstream; this is a fallback if you hit the old version.)

---

## ROLLBACK procedures (in order of speed/safety)

### Option 1 — Symlink swap (fastest, 30 seconds, full rollback to prior build)

If your deploy uses timestamped build directories (the typical setup):

```bash
# Find the previous build dir
ls -lat /opt/chatbot/builds/ | head -5

# Swap the symlink atomically
sudo ln -sfn /opt/chatbot/builds/<PREVIOUS_TIMESTAMP>/ /opt/chatbot/current

# Restart
sudo systemctl restart <service-name>

# Verify
curl -s http://localhost:8000/health/live
```

Use this for: "the new deploy broke something, get prod working immediately, debug later."

### Option 2 — Git revert of a specific commit

If you can identify the bad commit but don't want to lose subsequent good commits:

```bash
cd /opt/chatbot/current
git log --oneline -10
git revert <bad-commit-sha> --no-edit   # creates a new commit that reverses the bad one
git push origin main                    # push the revert
sudo systemctl restart <service-name>
```

Use this for: "we know exactly which commit broke things; everything else is fine."

### Option 3 — Disable v2 entirely (emergency, last resort)

If v2 is fundamentally broken and you need v1 back. Requires the cutover commit `50963e6` to be reverted, AND the frontend `RolloutFlag.js` to be rolled back. This is messy because v1 architecturally hasn't been maintained.

```bash
# Revert the v2-cutover commit
cd /opt/chatbot/current
git revert 50963e6 --no-edit
git push origin main
sudo systemctl restart <service-name>
```

After this, v2 socket lives at `/smartchatbot/v2/socket.io/` (the old path) and v1 reclaims `/smartchatbot/socket.io/`. Frontend will start hitting v1 again. Requires nginx to be configured to forward both paths (it probably isn't anymore).

In practice, Option 1 is always preferred over Option 3.

### Option 4 — Hard rollback in Postgres

If a bad data change (e.g., bad MakerSpace insert) is causing the bot to error:

```bash
psql "$DATABASE_URL" <<'SQL'
DELETE FROM "LibrarySpace_v2" WHERE library = 'makerspace';
SQL
sudo systemctl restart <service-name>
```

---

## THE 4 most common deploy-time errors (and fixes)

### Error 1: `ModuleNotFoundError: No module named 'starlette.requests'`

**Cause:** pip resolved a starlette version that doesn't match the installed fastapi. Common after a fresh `pip install -r requirements.txt` on a server where pip's resolver picked weird versions.

**Fix:**
```bash
cd /opt/chatbot/current/ai-core
source .venv/bin/activate
pip install --force-reinstall --no-cache-dir fastapi starlette
sudo systemctl restart <service-name>
```

**Nuclear fix** if above doesn't work (5 minutes):
```bash
cd /opt/chatbot/current/ai-core
sudo systemctl stop <service-name>
mv venv venv.broken_$(date +%s)
python3.13 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
sudo systemctl start <service-name>
```

### Error 2: `Health check failed: timeout of 10000ms exceeded` in browser console

**Cause:** Frontend is hitting `/health` (heavy: 6 external probes) instead of `/health/live` (trivial). One of the external services is slow.

**Fix:** Make sure frontend is built from latest main (which uses `/health/live`). If still hitting `/health`, rebuild client/:
```bash
cd /opt/chatbot/current/client
git pull origin main
npm install
npm run build
# redeploy dist/
```

### Error 3: Browser shows `Firefox can't establish a connection to wss://...../smartchatbot/v2/socket.io/...`

**Cause:** Frontend was built with the OLD v2 path. After the 2026-05-27 cutover, v2 lives at the canonical `/smartchatbot/socket.io/` path (no `/v2/` prefix).

**Fix:** Rebuild frontend from latest main (which has `RolloutFlag.js` returning the canonical path) and clear browser localStorage of stale `smartchatbot_v2` values.

### Error 4: `openai.PermissionDeniedError: Error code: 403` mid-eval

**Cause:** OpenAI API key issue. Not a code bug.

**Diagnosis:**
- Check the key is still valid in the OpenAI dashboard
- Check the org billing isn't over quota
- Check the key has access to `gpt-5.4-mini` + `text-embedding-3-large`

**Not a deploy issue** — won't be fixed by restart. Update `OPENAI_API_KEY` in `.env` if rotated.

---

## After deploy: verify it actually works

Don't trust `Active: active (running)` alone. Do a real end-to-end test:

```bash
# 1. From the prod server, test the local API
curl -s http://localhost:8000/health/live
# Expected: {"status":"alive"}

curl -s http://localhost:8000/health/ready
# Expected: 200 + JSON with all probes passing

# 2. From your laptop browser (incognito), hit the public URL
# https://app.lib.miamioh.edu/smartchatbot/
# Ask: "What time does King Library close tonight?"
# Expected: a cited answer with [1] chip; clicking the chip opens
# the King Library page; the time matches LibCal's current data.

# 3. While testing, watch the live log
sudo tail -f /var/log/smartchatbot_backend
# Look for "orchestrator" / "intent_knn" / "get_hours" / "synthesis" — these are v2 signatures.
# If you see "[Fast Lane]" / "[LibCal Agent]" / "libcal_rooms" — that's v1, something is wrong.
```

---

## Logs to know

| Log file | What's in it |
|---|---|
| `/var/log/smartchatbot_backend` | Main app log: request flow, orchestrator decisions, LLM calls, tool calls. **The primary debug file.** |
| `/var/log/smartchatbot_backend.error.log` | stderr only: Python warnings (LangChain deprecations, etc.) + actual tracebacks if the worker crashes. |
| `journalctl -u <service-name> --since "10 min ago"` | systemd's view of the service. Shows start/restart events, kill signals. |

If you don't know what's wrong:
```bash
sudo journalctl -u <service-name> --since "10 min ago" --no-pager | tail -50
sudo tail -100 /var/log/smartchatbot_backend.error.log
```

---

## Cron jobs that matter

```cron
# /etc/cron.d/smart-chatbot

# Weekly ETL: pulls library website, builds librarian-approval diff (does NOT auto-apply)
0 2 * * 0 cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.etl.run_etl --phase prepare 2>&1 | logger -t etl-prepare

# Daily cost rollup: aggregates ModelTokenUsage into DailyCost
30 6 * * * cd /opt/chatbot/current/ai-core && .venv/bin/python -m scripts.cost_rollup 2>&1 | logger -t cost-rollup
```

If these aren't running on your prod:
```bash
sudo crontab -l    # see what's scheduled
# Or check /etc/cron.d/
ls -la /etc/cron.d/
```

---

## Emergency contacts / who to ping when

| Symptom | Who |
|---|---|
| Backend down, can't restart, no obvious fix | Meng (project owner) |
| Wrong answer reported by a user | Librarian team (file `ManualCorrection`) |
| OpenAI key issues / billing | IT / whoever owns OpenAI account |
| nginx / TLS / DNS | Sysadmin owning `app.lib.miamioh.edu` |
| Weaviate / Postgres issues | Whoever owns DB infra |

---

## What this guide is NOT

- Not a tutorial on Python, FastAPI, Socket.IO, React, or Postgres — assumed prerequisite knowledge.
- Not a deep dive on bot behavior — see [01-ARCHITECTURE.md](01-ARCHITECTURE.md).
- Not a guide to extending the bot's tools / intents — see [07-DATA-PIPELINE.md](07-DATA-PIPELINE.md) and source code.
- Not a security review — secrets management and access control are out of scope here.
