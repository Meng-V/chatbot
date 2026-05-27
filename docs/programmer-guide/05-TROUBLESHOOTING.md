# 05 — Troubleshooting

> grep for your error message. Sections are titled after the symptom you'd type into Google.

## Section index

1. [Backend won't start](#1-backend-wont-start)
2. [Browser shows "Health check failed"](#2-browser-shows-health-check-failed)
3. [Browser shows "Firefox can't establish a connection to wss://"](#3-browser-shows-cant-establish-connection-to-wss)
4. [Bot refuses everything / gives "I don't have a reliable answer" too often](#4-bot-refuses-everything)
5. [Eval crashes with `RuntimeError` after ~30 cases](#5-eval-crashes-with-runtimeerror-after-30-cases)
6. [Eval reports `crash:AttributeError` on certain cases](#6-eval-reports-crashattributeerror-on-certain-cases)
7. [`openai.PermissionDeniedError: Error code: 403`](#7-openaipermissiondeniederror-error-code-403)
8. [Bot gives wrong phone number / made-up data](#8-bot-gives-wrong-phone-number-or-made-up-data)
9. [`npx prisma migrate status` fails with "url is no longer supported"](#9-npx-prisma-migrate-status-fails)
10. [`FileNotFoundError: /Users/qum/.../.env` when running operator scripts](#10-filenotfounderror-on-operator-scripts)
11. [LibCal returns nothing for a building that should have hours](#11-libcal-returns-nothing-for-a-building)
12. [SSH tunnel keeps dropping mid-eval](#12-ssh-tunnel-drops-mid-eval)
13. [Eval verdict number went down after a code change but bot looks fine](#13-eval-verdict-went-down-but-bot-looks-fine)

---

## 1. Backend won't start

### Symptom

```
sudo systemctl status smartchatbot-backend
... Active: failed (Result: exit-code) ...
```

Or running uvicorn directly produces a traceback.

### Diagnosis

```bash
# Get the actual error
sudo journalctl -u smartchatbot-backend --since "10 min ago" --no-pager | tail -40

# OR look at error log
sudo tail -100 /var/log/smartchatbot_backend.error.log
```

### Common causes

| Error in traceback | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'starlette.requests'` | fastapi/starlette version mismatch in venv | See [Error 1 in deployment guide](03-DEPLOYMENT.md#error-1-modulenotfounderror-no-module-named-starlettererequests) |
| `ModuleNotFoundError: No module named 'prisma'` | Prisma Python client not generated | `cd ai-core && prisma generate` |
| `ImportError: cannot import name 'X' from 'src.Y'` | Stale `__pycache__/` from old code, or missing migration | `find . -name __pycache__ -exec rm -rf {} +`, then restart |
| `asyncpg.exceptions.UndefinedColumnError` | Postgres schema doesn't match Prisma schema | Run `npx prisma migrate deploy`; if that fails, see Section 9 |
| `OSError: [Errno 98] Address already in use` | Another process is on the port | `sudo ss -tlnp \| grep 8000` to find it, then kill it |

---

## 2. Browser shows "Health check failed"

### Symptom

In browser DevTools console:
```
Health check failed: timeout of 10000ms exceeded (AxiosError ECONNABORTED)
```

The chat UI shows an "unhealthy" state even though typing a message might still work.

### Diagnosis

Two possible causes:

**A. Frontend is calling `/health` instead of `/health/live`**

This is the bug fixed by commits 4ec28ff + 302e5b6. The OLD frontend (built before May 27 2026) polls `/health`, which runs 6 external API checks in parallel and frequently exceeds 10s.

Check: in DevTools Network tab, look for the periodic XHR call. URL should be `/health/live`, returning ~10ms with `{"status":"alive"}`. If it's `/health` returning slowly, the frontend bundle is stale.

**Fix:** rebuild and redeploy frontend.

**B. The bot's `/health` endpoint really is slow**

If for some reason you intentionally call `/health` (ops dashboard, etc.) and it's slow, identify which downstream is slow:

```bash
time curl -s http://localhost:8000/health | python3 -m json.tool
```

The response will tell you which service is `"unhealthy"`. Most common culprits:
- **LibCal** — OAuth token refresh on cold start can take 3-5s
- **LibAnswers** — external API, sometimes slow
- **Weaviate** — if the SSH tunnel is flapping

---

## 3. Browser shows "can't establish connection to wss://...."

### Symptom

```
Firefox can't establish a connection to the server at wss://app.lib.miamioh.edu/smartchatbot/v2/socket.io/?EIO=4&transport=websocket
```

Note the `/v2/` in the path.

### Cause

Frontend bundle is OLD — built before the 2026-05-27 cutover when v2 was promoted to the canonical `/smartchatbot/socket.io/` path. The old bundle still routes to `/smartchatbot/v2/socket.io/` which no longer exists.

### Fix

**Step 1:** Rebuild frontend from latest main.
```bash
cd /opt/chatbot/current/client
git pull origin main
npm install
npm run build
# deploy client/dist/ to nginx-served path
```

**Step 2:** User must clear browser localStorage — the old `smartchatbot_v2` flag is sticky. In DevTools Console:
```javascript
localStorage.removeItem('smartchatbot_v2');
localStorage.removeItem('smartchatbot_v2_bucket');
location.reload();
```

Or just use an incognito window.

---

## 4. Bot refuses everything

### Symptom

Most or all answers come back as "I don't have a reliable answer to that. You can ask a librarian directly through Ask Us."

### Diagnosis

Check the backend log to see what trigger is firing:

```bash
sudo tail -200 /var/log/smartchatbot_backend | grep -E 'refusal_trigger|orchestrator: scope|orchestrator: intent'
```

### Common cases

| Refusal trigger | What's wrong |
|---|---|
| `model_self_flagged` (most common) | Synth got no useful evidence. Either tools failed, or scope mismatch dropped chunks, or LibCal/Weaviate is down. |
| `out_of_scope` | kNN classifier misroutes — see Section 13 for handling intent drift. |
| `cross_campus_mismatch` | Bot's evidence is from a different campus than user's scope. Either user phrasing is ambiguous, or scope resolver got it wrong. |
| `live_data_down` | A required live API (LibCal, etc.) is down. Check `/health`. |
| `citation_invalid` | Synth tried to emit a URL not in evidence — usually means search_kb returned thin results and synth was over-creative. |

### Common root cause: a tool isn't wired

The single most common bug in v2's history: a tool was declared in the agent's tool list, but its backend wasn't implemented OR was excluded from `_build_real_deps`'s registry. See Section 4 of this guide and the **Critical fact #2** in [00-INDEX.md](00-INDEX.md).

To confirm: `grep "registry.tools.pop" ai-core/src/eval/run_eval.py`. **Any tool name appearing in the pop list is invisible to the agent.** If you intended a tool to be available, remove it from that list.

---

## 5. Eval crashes with `RuntimeError` after ~30 cases

### Symptom

Eval log shows individual cases with `actual_path: "crash:RuntimeError"`. Often clusters around circulation / loan / renew / account intents.

### Cause

Postgres connection exhaustion. The `lookup_space` (or other DB-touching) tool was creating a fresh asyncpg connection per call without pooling. Over hundreds of cases, sockets accumulate faster than they're released, eventually exceeding Postgres `max_connections`.

### Fix

This was fixed in commit `73c9897` (pooling `lookup_space` with `asyncpg.create_pool(max_size=5)`). Make sure your branch contains that commit:

```bash
git log --all --oneline | grep 73c9897
# Should appear in main's history
```

If you're hitting this on a custom branch that doesn't have the fix: cherry-pick `73c9897` or add similar pooling to any DB-touching backend you've added.

---

## 6. Eval reports `crash:AttributeError` on certain cases

### Symptom

Cases like `news_nyt_access`, `fs_ill_fee` show `actual_path: "crash:AttributeError"`.

### Cause

Almost always one of:
- A tool result has a None value where a dict was expected (defensive code missing)
- Prisma model name mismatch (e.g., your code uses `client.urlseen` but the model is now called `client.url_seen`)

### Diagnosis

Re-run that specific case with verbose logging:
```bash
cd ai-core
.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.eval.inspect_turn import inspect
resp, _ = inspect('Are there fees for interlibrary loan?', print_trace=True)
print(resp.answer if not resp.is_refusal else resp.answer)
"
```

The traceback will tell you which line of which file crashed. Most likely a `.get()` was called on `None`.

---

## 7. `openai.PermissionDeniedError: Error code: 403`

### Symptom

Mid-eval or mid-request:
```
openai.PermissionDeniedError: Error code: 403
Error code: 403 - {'error': {...}}
```

### Cause

NOT a code bug. The OpenAI API is rejecting the call for one of:
- API key revoked or expired
- Billing issue (organization over quota)
- Key doesn't have permissions for the specific model
- IP/geographic restriction
- Abuse detection

Distinguish from rate-limiting: rate-limit is 429 Too Many Requests; 403 is permission.

### Diagnosis

```bash
# Test the key directly
.venv/bin/python -c "
import os
from pathlib import Path
for line in (Path('PROJECT_ROOT')/'.env').read_text().splitlines():
    if not line or line.startswith('#') or '=' not in line: continue
    k,_,v=line.partition('='); k=k.strip(); v=v.strip().strip('\"').strip(\"'\")
    if k and k not in os.environ: os.environ[k]=v
from openai import OpenAI
c = OpenAI()
print(c.embeddings.create(model='text-embedding-3-large', input='ping').data[0].embedding[:3])
"
```

If this prints a list, the key works. If it 403s, go to OpenAI dashboard:
- Check API keys page (revoked?)
- Check billing (over quota? card expired?)
- Check organization-level restrictions

### Fix

Replace `OPENAI_API_KEY` in `.env` with a new working key. Restart backend.

---

## 8. Bot gives wrong phone number or made-up data

### Symptom

Bot tells a user the library phone is something weird (a Dean's office line, etc.) when asked "What is the library phone number?".

### Cause

The agent isn't calling `lookup_space("king")` and instead is reading from `search_kb` chunks, which can contain individual office phone numbers from staff bio pages.

### Diagnosis

```bash
# Confirm lookup_space backend works
.venv/bin/python -c "
import os, sys, asyncio
from pathlib import Path
for line in (Path('PROJECT_ROOT')/'.env').read_text().splitlines():
    if not line or line.startswith('#') or '=' not in line: continue
    k,_,v=line.partition('='); k=k.strip(); v=v.strip().strip('\"').strip(\"'\")
    if k and k not in os.environ: os.environ[k]=v
sys.path.insert(0,'ai-core')
from src.eval.real_backends import _make_lookup_space
lookup = _make_lookup_space()
print(lookup({'library': 'king'}))
"
# Expected: a dict with phone='513-529-4141'
```

If this works, the backend is fine — the agent isn't choosing to use it. Check:
1. `grep "registry.tools.pop" ai-core/src/eval/run_eval.py` — is `lookup_space` in the pop list? If yes, that's the bug (remove it).
2. Read `agent_v1.py` Core Rule 6 — does it tell the agent to use `lookup_space` for `intent=location_directions`? It should.

This whole class of bug ate 4 retest rounds in May 2026. See commits `1ee4453`, `f07695e`, `aca0ded`, `73c9897`, `1de6dab`.

---

## 9. `npx prisma migrate status` fails

### Symptom

```
Error: Prisma schema validation - (get-config wasm)
Error code: P1012
error: The datasource property `url` is no longer supported in schema files.
Move connection URLs for Migrate to `prisma.config.ts` ...
```

### Cause

Prisma 7.x changed schema format. The `npx prisma` CLI auto-installed v7, but `prisma/schema.prisma` is still v5/v6 format with `url = env("DATABASE_URL")` directly.

### Fix

**Option A — Pin Prisma CLI to a compatible version:**
```bash
cd /opt/chatbot/current
npm install --save-dev prisma@5.22.0
npx prisma migrate deploy
```

**Option B — Skip `npx prisma` entirely.** The Python backend uses the Python `prisma` package (installed via `pip install prisma`), which is independent of the Node CLI version. The CLI is only needed for migrations.

If you just need to verify schema status without migrating, use:
```bash
.venv/bin/python -c "from prisma import Prisma; p = Prisma(); print('OK')"
```

---

## 10. FileNotFoundError on operator scripts

### Symptom

```
FileNotFoundError: [Errno 2] No such file or directory:
'/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e/.env'
```

When running `wire_gold_to_weaviate.py` or similar.

### Cause

The script has a hardcoded path to the original developer's worktree, set at the top of the file.

### Fix

```bash
sed -i 's|ROOT = Path("/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e")|ROOT = Path(__file__).resolve().parents[3]|' \
  ai-core/scripts/operator_wiring/wire_gold_to_weaviate.py
```

This makes `ROOT` auto-detect based on the script's actual location. Should also be patched upstream in a future commit.

---

## 11. LibCal returns nothing for a building

### Symptom

User asks "What time does MakerSpace close?" → bot says "King is open until 9pm" (not MakerSpace's specific hours).

### Cause

Two possibilities:
- **Most likely:** the LibCal ID for MakerSpace isn't mapped in `LibrarySpace_v2`. Check:
  ```bash
  psql "$DATABASE_URL" -c 'SELECT library, name, libcal_id FROM "LibrarySpace_v2" ORDER BY library;'
  ```
  Expected: makerspace row with `libcal_id = '11904'`. If missing or NULL, INSERT it (see [07-DATA-PIPELINE.md](07-DATA-PIPELINE.md)).

- **Less likely:** the agent isn't routing to `get_hours("makerspace")` and is using `get_hours("king")` instead. Check `agent_v1.py` Core Rule 6 — it should explicitly mention `makerspace` as a sub-space with its own LibCal ID.

### Verify the LibCal API works for that building

```bash
cd ai-core
.venv/bin/python -c "
import os, sys
from pathlib import Path
for line in (Path('PROJECT_ROOT')/'.env').read_text().splitlines():
    if not line or line.startswith('#') or '=' not in line: continue
    k,_,v=line.partition('='); k=k.strip(); v=v.strip().strip('\"').strip(\"'\")
    if k and k not in os.environ: os.environ[k]=v
sys.path.insert(0,'.')
from src.eval.real_backends import _make_get_hours
gh = _make_get_hours()
r = gh('makerspace')
print(r['success'], r.get('hours','')[:200])
"
```

If this prints `True` + actual hours, the LibCal mapping works — the agent isn't using it.

---

## 12. SSH tunnel drops mid-eval

### Symptom

Eval prints `Weaviate unreachable -- the SSH tunnel is down. Verify with nc -z -w2 127.0.0.1 8888` and aborts.

### Cause

Your laptop went to sleep, network blip, etc. SSH session was killed.

### Fix during run

The eval streams per-case results to disk per turn. So partial progress is preserved.

To resume from where it stopped (no re-paying for completed cases):

```bash
# After bringing tunnel back up:
.venv/bin/python -m src.eval.run_eval \
  --with-real-llm --with-judge \
  --skip-ids-in <existing-results-file>.jsonl \
  --results-out <new-results-file>.jsonl

# Then concatenate:
cat <existing>.jsonl <new>.jsonl > complete.jsonl
```

The `--skip-ids-in` flag (added in commit `73c9897`) reads question IDs from the existing file and skips them.

### Prevent in future

Use `autossh` instead of plain `ssh` for the tunnel, with `-M 0 -o ServerAliveInterval=30 -o ServerAliveCountMax=3`. It auto-reconnects.

---

## 13. Eval verdict went down but bot looks fine

### Symptom

You made a code change. Re-ran eval. Verdict dropped from 60% → 55%. But when you manually test the bot in the UI, the answers look fine.

### Cause

**Most likely: judge noise.** The LLM-as-judge mismarks ~15-30% of answers. Run-to-run variance is significant even without code changes. A 5pp drop with no real change in bot output is possible.

**Less likely: a real regression you didn't catch in unit tests.** Hand-review the cases that flipped.

### Methodology fix

Don't chase verdict numbers. Instead:

1. **Diff verdicts case-by-case** between two runs:
   ```bash
   .venv/bin/python -c "
   import json
   def load(f): return {json.loads(l)['question_id']: json.loads(l) for l in open(f) if l.strip()}
   a = load('before.jsonl')
   b = load('after.jsonl')
   for qid in a:
       va = a[qid].get('judge_verdict')
       vb = b.get(qid, {}).get('judge_verdict')
       if va != vb:
           print(f'{qid}: {va} -> {vb}')
   "
   ```

2. **Read the bot's actual answer for each flipped case.** Often the new answer is identical or better — judge just gave a different verdict.

3. **Hold to the "no-regression-on-priority-cases" gate, not absolute verdict.** Maintain a small list of must-not-regress cases (like the 6 v1 hallucination cases your colleague found) and assert THOSE pass. Verdict-on-everything is noise.

See [06-EVAL-AND-QUALITY.md](06-EVAL-AND-QUALITY.md) for the full anti-Goodhart methodology.

---

## When to ping for help

| You have | Try |
|---|---|
| Stack trace with a clear file:line | Read that file, especially comments — most modules have extensive design notes |
| Eval result file with weird verdicts | Run the analyze script, hand-review 5-10 cases |
| Backend won't start, nothing in logs | `strace`/`dtrace` the python process or run `uvicorn` foreground to see real-time output |
| Frontend has a JS error | Browser DevTools Console + Network tab; the bundle is minified but error messages usually identify the file |
| Truly stuck | Ping Meng. Don't loop on the same approach for >2 hours without re-evaluating direction. |

---

## What's NOT covered in this troubleshooting guide

- nginx config issues — those are in the ops team's domain
- TLS cert issues — same
- DNS issues — same
- Routing weirdness from the campus network — same
- Browser compatibility issues older than the past 2 years

For any of those, escalate to whoever owns prod infrastructure (probably IT, possibly Rachel).
