#!/bin/bash
# preflight.sh -- pre-deploy environment check (backlog C1).
#
# Run ON THE SERVER (or locally) BEFORE restarting the backend. Every check
# here corresponds to a real "worked locally, broke on prod" incident from
# the 2026-05/06 beta launch: nginx not forwarding, the 332MB embedding
# cache lost by a clean build, starlette/fastapi version drift, prisma
# client not generated, missing .env keys, dead prompt URLs.
#
# Usage:
#   bash ai-core/scripts/preflight.sh                  # prod defaults
#   ROOT=/path/to/chatbot PORT=8000 bash preflight.sh  # local override
#
# Exit 0 = all green. Exit 1 = at least one ✗ (fix before restarting).

ROOT="${ROOT:-/opt/chatbot/current}"
PORT="${PORT:-8081}"
ENV_FILE="${ENV_FILE:-/opt/chatbot/shared/.env}"
[ -f "$ENV_FILE" ] || ENV_FILE="$ROOT/.env"
PY="$ROOT/ai-core/venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/ai-core/.venv/bin/python"

pass=0; fail=0
ok()   { echo "  ✓ $1"; pass=$((pass+1)); }
bad()  { echo "  ✗ $1"; fail=$((fail+1)); }

echo "== preflight: $ROOT (port $PORT) =="

# 1. runtimes + venv
[ -x "$PY" ] && ok "python venv: $PY" || bad "python venv missing under $ROOT/ai-core/{venv,.venv}"

# 2. critical imports (catches starlette/fastapi drift + missing deps)
if [ -x "$PY" ]; then
  if "$PY" -c "import fastapi, starlette, socketio, weaviate" 2>/dev/null; then
    ok "fastapi/starlette/socketio/weaviate import"
  else
    bad "core imports fail (try: pip install --force-reinstall fastapi starlette)"
  fi
  # 3. prisma client generated AND current with the schema. Import-only
  # checking is not enough: a client generated from an OLDER schema
  # imports fine but lacks the newer models (PRD 2026-07-14: the
  # LibrarySpace_v2 seed died with "'Prisma' object has no attribute
  # 'libraryspace_v2'" because the venv's client predated the 05-18
  # schema). Verify every model in schema.prisma exists on the client.
  SCHEMA="$ROOT/prisma/schema.prisma"
  [ -f "$SCHEMA" ] || SCHEMA="$ROOT/ai-core/schema.prisma"
  if env SCHEMA="$SCHEMA" "$PY" - <<'PYEOF' 2>/dev/null
import os, re, sys
from prisma import Prisma
db = Prisma()
src = open(os.environ["SCHEMA"], encoding="utf-8").read()
models = re.findall(r"^model\s+(\w+)", src, re.M)
missing = [m for m in models if not hasattr(db, m.lower())]
if missing:
    print("stale prisma client, missing models: " + ", ".join(missing))
    sys.exit(1)
PYEOF
  then
    ok "prisma client generated + current with schema ($(basename "$SCHEMA"))"
  else
    bad "prisma client stale or missing -- run: bash ai-core/scripts/ensure_prisma_client.sh (then restart)"
  fi
fi

# 4. embedding cache present and big (the 30-60s-hang-on-first-message guard)
CACHE="$ROOT/ai-core/data/eval/classifier_embeddings.json"
if [ -e "$CACHE" ]; then
  SZ=$(du -m "$(readlink -f "$CACHE" 2>/dev/null || echo "$CACHE")" 2>/dev/null | cut -f1)
  if [ "${SZ:-0}" -ge 100 ]; then ok "classifier embedding cache (${SZ}MB)"; else bad "embedding cache suspiciously small (${SZ:-0}MB)"; fi
else
  bad "classifier_embeddings.json missing -- symlink from /opt/chatbot/shared/ (see docs/DEPLOY-2026-06-09.md §4)"
fi

# 5. .env + required keys
if [ -f "$ENV_FILE" ]; then
  ok ".env: $ENV_FILE"
  for K in OPENAI_API_KEY DATABASE_URL WEAVIATE_HOST WEAVIATE_HTTP_PORT WEAVIATE_CHUNK_COLLECTION LIBCAL_CLIENT_ID; do
    grep -qE "^${K}=." "$ENV_FILE" && ok "env $K" || bad "env $K missing in $ENV_FILE"
  done
else
  bad ".env not found at /opt/chatbot/shared/.env or $ROOT/.env"
fi

# 6. data stores reachable
WV_PORT=$(grep -E '^WEAVIATE_HTTP_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2); WV_PORT=${WV_PORT:-8888}
nc -z -w3 127.0.0.1 "$WV_PORT" 2>/dev/null && ok "weaviate 127.0.0.1:$WV_PORT" || bad "weaviate unreachable on 127.0.0.1:$WV_PORT"
if [ -x "$PY" ]; then
  if env ENV_FILE="$ENV_FILE" "$PY" - <<'PYEOF' 2>/dev/null
import os, asyncio
from dotenv import load_dotenv; load_dotenv(os.environ["ENV_FILE"], override=True)
from prisma import Prisma
async def m():
    db=Prisma(); await db.connect(); await db.librarian.count(); await db.disconnect()
asyncio.run(m())
PYEOF
  then ok "postgres connect + query"; else bad "postgres unreachable / query failed (DATABASE_URL?)"; fi
fi

# 7. nginx forwards (prod only -- skipped if no nginx config present)
if [ -d /etc/nginx ]; then
  grep -rqs "smartchatbot" /etc/nginx && ok "nginx has smartchatbot config" || bad "nginx: no smartchatbot config found"
  grep -rqs "health" /etc/nginx && ok "nginx forwards /health" || bad "nginx: /health not proxied (frontend liveness will fail)"
fi

# 8. frontend dist present (citations/UI live in the bundle)
DIST="$ROOT/client/dist/index.html"
[ -f "$DIST" ] && ok "frontend dist built ($(date -r "$DIST" '+%Y-%m-%d %H:%M' 2>/dev/null))" || bad "client/dist missing -- run: cd client && npm ci && npm run build"

# 9. dead-URL guard over the prompt files
if [ -x "$PY" ]; then
  if (cd "$ROOT/ai-core" && PYTHONPATH="$ROOT/ai-core" "$PY" scripts/validate_prompt_urls.py >/dev/null 2>&1); then
    ok "prompt URLs all live (validate_prompt_urls)"
  else
    bad "dead URL in prompt files -- run scripts/validate_prompt_urls.py to see which"
  fi
fi

# 10. disk space
AVAIL=$(df -m "$ROOT" 2>/dev/null | awk 'NR==2{print $4}')
[ "${AVAIL:-0}" -ge 1024 ] && ok "disk ${AVAIL}MB free" || bad "low disk: ${AVAIL:-?}MB free"

# 11. deterministic short-circuits behave (greeting/policy/closures/makerspace/
# scholarly-comm/3D/follow-up/injection-backstop). Pure functions, no backends;
# standalone runner so it works without pytest in the prod venv. A regression
# here means a hard-knowledge answer silently broke.
if [ -x "$PY" ]; then
  if (cd "$ROOT/ai-core" && PYTHONPATH="$ROOT/ai-core" "$PY" src/graph/test_short_circuits.py >/dev/null 2>&1); then
    ok "deterministic short-circuits (test_short_circuits)"
  else
    bad "short-circuit regression -- run: python src/graph/test_short_circuits.py"
  fi
fi

echo "== preflight: $pass ok, $fail failed =="
[ "$fail" -eq 0 ]
