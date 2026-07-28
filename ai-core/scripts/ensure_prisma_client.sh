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
# Two schemas, two jobs. The ROOT schema is the source of truth for what
# SHOULD exist, so it is what we check against. But it is the
# TypeScript-side schema: its datasource block has no `url`, so
# generating from it dies with 'Argument "url" is missing in data source
# block "db"'. The Python client must be generated from the ai-core copy,
# which carries the url + the prisma-client-py generator config. Before
# this split, drift was DETECTED and the auto-fix then failed (found
# 2026-07-28 while adding the field-level check below).
SCHEMA="$ROOT/prisma/schema.prisma"
[ -f "$SCHEMA" ] || SCHEMA="$ROOT/ai-core/schema.prisma"
GEN_SCHEMA="$ROOT/ai-core/schema.prisma"
[ -f "$GEN_SCHEMA" ] || GEN_SCHEMA="$SCHEMA"

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

# FIELDS too, not just models. Checking models alone reported "in sync"
# after `Librarian.alternateName` was added (2026-07-28) -- the column
# existed in Postgres, the model existed on the client, and every read of
# the new field silently came back absent. That is the same class of
# failure this script was written for, one level down.
from prisma import models as _pm
nfields = 0
missing_fields = []
extra_fields = []
for block in re.finditer(r"^model\s+(\w+)\s*\{(.*?)^\}", src, re.M | re.S):
    mname, body = block.group(1), block.group(2)
    cls = getattr(_pm, mname, None)
    if cls is None or not hasattr(cls, "model_fields"):
        continue          # relation-only or unmapped model; models check covers it
    known = set(cls.model_fields)
    declared: set = set()
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("//", "/", "@@")):
            continue
        m = re.match(r"(\w+)\s+\S", line)
        if not m:
            continue
        nfields += 1
        declared.add(m.group(1))
        if m.group(1) not in known:
            missing_fields.append(f"{mname}.{m.group(1)}")
    extra_fields += [f"{mname}.{f}" for f in sorted(known - declared)]
if missing_fields:
    print("missing fields: " + ", ".join(missing_fields))
    sys.exit(1)
if extra_fields:
    # The MIRROR failure, and the nastier one: a client field with no
    # column. Prisma SELECTs every field of a model, so ONE stale extra
    # field makes every read of that table raise DataError -- not just
    # reads of the field. Seen 2026-07-28 after a schema was rolled back
    # without regenerating. Regenerating is the fix for this direction
    # too, so treat it as drift.
    print("stale client fields (no longer in schema): "
          + ", ".join(extra_fields))
    sys.exit(1)
print(f"all {len(models)} models and {nfields} fields match the "
      f"generated client")
PYEOF
}

echo "== ensure_prisma_client: $SCHEMA =="
if OUT=$(check); then
  echo "  ✓ in sync -- $OUT"
  exit 0
fi
echo "  ! drift detected ($OUT) -- regenerating..."

[ -x "$PRISMA" ] || { echo "✗ prisma CLI not found at $PRISMA"; exit 1; }
# `prisma generate` shells out to the generator BINARY named in the
# schema ("prisma-client-py"), resolved via PATH -- which a `sudo -u`
# invocation doesn't have. Prepend the venv bin dir so it resolves
# (PRD 2026-07-14: '/bin/sh: prisma-client-py: command not found').
PATH="$(dirname "$PY"):$PATH" "$PRISMA" generate --schema "$GEN_SCHEMA"

if OUT=$(check); then
  echo "  ✓ regenerated -- $OUT"
  echo "  NOTE: restart the backend so the running process picks up the new client."
else
  echo "  ✗ still stale after generate ($OUT)"
  echo "    Most likely the ai-core schema copy is behind the root one."
  echo "    Run:  ./local-auto-start.sh --sync-prisma   then re-run this."
  exit 1
fi
