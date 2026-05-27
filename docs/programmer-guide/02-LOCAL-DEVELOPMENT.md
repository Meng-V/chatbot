# 02 — Local Development Setup

> Goal: a fresh laptop, zero project context, can run the bot in 30 minutes.

## What you need before starting

| Requirement | Why | How to check |
|---|---|---|
| **Python 3.13+** | Backend | `python3 --version` |
| **Node.js 18+** | Frontend | `node --version` |
| **OpenAI API key** | LLM calls | You'll need a key with `gpt-5.4-mini` + `gpt-5.2` + `text-embedding-3-large` access |
| **SSH access to prod Postgres + Weaviate** | OR your own local instances | Ask Meng for tunnel credentials |
| **(optional) Postgres + Weaviate locally** | If you don't want the tunnel | docker-compose.weaviate.local.yml is in the repo root |

If you don't have the prod tunnel credentials AND don't want to run local Postgres/Weaviate, you can still develop with **stubs only** (eval with `--scope-only` or `--with-real-llm=false`). You won't be able to test live LibCal / real retrieval, but you can iterate on prompts and unit tests.

---

## Step-by-step

### 1. Clone the repo

```bash
git clone https://github.com/Meng-V/chatbot.git
cd chatbot
```

### 2. Set up the SSH tunnels (if using prod data)

The bot reaches Postgres on `127.0.0.1:5432` and Weaviate on `127.0.0.1:8888`. You need an SSH tunnel that forwards these from your prod (or staging) server:

```bash
# In a dedicated terminal — leave it running
ssh -L 5432:localhost:5432 -L 8888:localhost:8888 your-user@your-prod-host
```

Verify:
```bash
nc -z -w2 127.0.0.1 5432 && echo "Postgres OK"
nc -z -w2 127.0.0.1 8888 && echo "Weaviate OK"
```

Both should print `OK`. If not, the rest of this guide will fail with timeouts.

### 3. Set up `.env`

Copy `.env.example` to `.env` (root of repo, not inside ai-core):

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```bash
# Required
OPENAI_API_KEY=sk-proj-...
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/chatbot

# Weaviate (defaults work if tunnel is on 8888)
WEAVIATE_HOST=127.0.0.1
WEAVIATE_HTTP_PORT=8888
WEAVIATE_GRPC_PORT=8889
WEAVIATE_CHUNK_COLLECTION=Chunk_vv20260514_1929  # check prod for current value

# LibCal (production credentials; ask Meng if you need a sandbox)
LIBCAL_OAUTH_URL=https://muohio.libcal.com/api/1.1/oauth/token
LIBCAL_CLIENT_ID=...
LIBCAL_CLIENT_SECRET=...
LIBCAL_GRANT_TYPE=client_credentials
LIBCAL_HOUR_URL=https://muohio.libcal.com/api/1.1/hours
LIBCAL_ASKUS_ID=8876
# (more LibCal URLs — see existing .env.example)

# LibGuides
LIBAPPS_CLIENT_ID=...
LIBAPPS_CLIENT_SECRET=...

# Optional observability
SENTRY_DSN=
```

### 4. Set up the Python backend

```bash
cd ai-core
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

**Common pip pitfall:** if you see `ModuleNotFoundError: No module named 'starlette.requests'` later when starting the server, your starlette/fastapi versions don't match. Fix:
```bash
pip install --force-reinstall --no-cache-dir fastapi starlette
```

### 5. Set up Prisma (Python client)

Prisma's Python client needs to be generated:

```bash
cd ai-core
prisma generate
# If `prisma` command not found, try: python -m prisma generate
```

This creates the `prisma` Python package in your venv. Skipping this = `ModuleNotFoundError: No module named 'prisma'` at runtime.

> **Note on Prisma version drift:** the `npx prisma` CLI (Node.js, in `node_modules/`) can be a totally different version from the Python `prisma` package. If `npx prisma migrate status` fails with "url is no longer supported" — that's the Node CLI on Prisma 7, while the Python client is on Prisma 5/6. The Python backend doesn't use `npx`. Skip the npx-based commands; use the Python client.

### 6. Verify Python imports work

```bash
cd ai-core
.venv/bin/python -c "
from src.graph.new_orchestrator import run_turn
from src.eval.real_backends import build_eval_backends
print('✅ imports OK')
"
```

If this fails, fix the import error before continuing — it WILL break the rest.

### 7. Set up the frontend

```bash
cd ../client
npm install
```

Create `client/.env.development` if it doesn't exist:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

### 8. Run the backend locally

```bash
cd ai-core
.venv/bin/python -m src.main
# OR if you prefer the CLI:
.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload
```

You should see something like:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Check health:
```bash
curl -s http://localhost:8000/health/live
# Expected: {"status":"alive"}

curl -s http://localhost:8000/health/ready
# Expected: 200 if probes pass; lists which dependencies are reachable
```

### 9. Run the frontend locally

```bash
cd ../client
npm run dev
# Opens at http://localhost:5173 (Vite default)
```

The Vite dev server proxies API + Socket.IO to your local backend (see `vite.config.js`).

Open `http://localhost:5173/` in a browser. Ask a question. You should get an answer.

---

## Quick sanity test

After setup, in `ai-core/`:

```bash
# Run the scope-only eval (cheap, no LLM, ~10 seconds)
.venv/bin/python -m src.eval.run_eval --scope-only

# Expected:
# Eval results: 234 total questions (231 scope-eligible; 3 clarify-case...)
# Scope-resolver matches: 220+/231 (95+%)
```

If you get >95% scope match, your local setup is working.

To do a real-LLM smoke test of a few cases (~$0.50, ~3 min):

```bash
.venv/bin/python -m src.eval.run_eval \
  --with-real-llm --with-judge --filter hours \
  --results-out /tmp/smoke.jsonl
```

---

## Running unit tests

```bash
cd ai-core
.venv/bin/python -m pytest src/ -q
# Expected: 189+ passed, 1 warning
```

If tests fail, run with `-v` to see which:
```bash
.venv/bin/python -m pytest src/ -v 2>&1 | grep -E '(FAIL|ERROR|PASS)' | tail -30
```

---

## IDE setup (recommended)

- **VS Code / Cursor:** point the Python interpreter at `ai-core/.venv/bin/python` so import resolution works.
- **Pyright / Pylance:** add `ai-core/` to `python.analysis.extraPaths` so imports like `from src.graph...` resolve.

---

## Common local-dev pitfalls

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | You're not running from `ai-core/` directory. `cd ai-core` first. |
| `ModuleNotFoundError: No module named 'starlette.requests'` | Version drift. Run `pip install --force-reinstall starlette fastapi`. |
| `ModuleNotFoundError: No module named 'prisma'` | Run `prisma generate` in ai-core/. |
| `WeaviateConnectionError` | SSH tunnel for port 8888 isn't up. `nc -z 127.0.0.1 8888`. |
| `asyncpg.PostgresError: connection refused` | SSH tunnel for port 5432 isn't up. |
| `openai.AuthenticationError` | OPENAI_API_KEY missing or wrong in `.env`. |
| eval crashes after ~30 cases with `RuntimeError` | Postgres connection exhaustion. The `lookup_space` pool fix (commit 73c9897) should prevent this — make sure you're on latest main. |

More in [05-TROUBLESHOOTING.md](05-TROUBLESHOOTING.md).

---

## What to read after this

Once you can ask a question and get an answer locally:

1. **[01-ARCHITECTURE.md](01-ARCHITECTURE.md)** — what just happened end-to-end
2. **[04-API-REFERENCE.md](04-API-REFERENCE.md)** — Socket.IO message format
3. Pick a file from `ai-core/src/graph/new_orchestrator.py` and step through `run_turn` in your debugger to watch the pipeline execute.
