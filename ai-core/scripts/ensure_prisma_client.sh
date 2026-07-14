#!/bin/bash
# ensure_prisma_client.sh -- keep the generated Prisma Python client in
# sync with prisma/schema.prisma. PERMANENT fix for the 2026-07-14 PRD
# incident: the deploy reused the venv across builds, nothing re-ran
# `prisma generate` after a schema change, and the stale client blew up
# on the LibrarySpace_v2 model ("'Prisma' object has no attribute
# 'libraryspace_v2'").
#
# Behavior:
#   * Detects drift by checking that every `model X` in schema.prisma
#     exists as an attribute on the generated client.
#   * In sync  -> prints ok, exit 0, touches nothing (safe to run every
#     deploy).
#   * Drifted  -> runs `prisma generate` inside the app venv, then
#     re-verifies.
#
# Usage (run as the service user so the prisma binary cache is writable):
#   sudo -u smartchatbot bash /opt/chatbot/current/ai-core/scripts/ensure_prisma_client.sh
#   ROOT=/path/to/chatbot bash ai-core/scripts/ensure_prisma_client.sh   # override
#
# Wire it into the deploy right after `pip install -r requirements.txt`
# and BEFORE preflight.sh (whose check #3 now fails hard on drift).

set -euo pipefail

ROOT="${ROOT:-/opt/chatbot/current}"
PY="$ROOT/ai-core/venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/ai-core/.venv/bin/python"
PRISMA="$(dirname "$PY")/prisma"
SCHEMA="$ROOT/prisma/schema.prisma"
[ -f "$SCHEMA" ] || SCHEMA="$ROOT/ai-core/schema.prisma"

[ -x "$PY" ]     || { echo "✗ venv python not found under $ROOT/ai-core"; exit 1; }
[ -f "$SCHEMA" ] || { echo "✗ schema.prisma not found under $ROOT"; exit 1; }

check() {
  env SCHEMA="$SCHEMA" "$PY" - <<'PYEOF'
import os, re, sys
try:
    from prisma import Prisma
except Exception as e:
    print(f"client import failed: {e}")
    sys.exit(1)
db = Prisma()
src = open(os.environ["SCHEMA"], encoding="utf-8").read()
models = re.findall(r"^model\s+(\w+)", src, re.M)
missing = [m for m in models if not hasattr(db, m.lower())]
if missing:
    print("missing models: " + ", ".join(missing))
    sys.exit(1)
print(f"all {len(models)} schema models present on the generated client")
PYEOF
}

echo "== ensure_prisma_client: $SCHEMA =="
if OUT=$(check); then
  echo "  ✓ in sync -- $OUT"
  exit 0
fi
echo "  ! drift detected ($OUT) -- regenerating..."

[ -x "$PRISMA" ] || { echo "✗ prisma CLI not found at $PRISMA"; exit 1; }
"$PRISMA" generate --schema "$SCHEMA"

if OUT=$(check); then
  echo "  ✓ regenerated -- $OUT"
  echo "  NOTE: restart the backend so the running process picks up the new client."
else
  echo "  ✗ still stale after generate ($OUT) -- investigate (schema copied? venv writable?)"
  exit 1
fi
