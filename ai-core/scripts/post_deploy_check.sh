#!/bin/bash
# post_deploy_check.sh -- post-restart smoke test (backlog C2).
#
# Run AFTER restarting the backend. Connects a REAL Socket.IO client and
# holds a TWO-turn conversation. Two turns is the whole point: the
# 2026-05-28 Responses-API 400 only fired on the SECOND user message
# (conversation-history shape), so a single-turn smoketest passed while
# every real user broke.
#
# Usage:
#   bash ai-core/scripts/post_deploy_check.sh            # prod (port 8081)
#   PORT=8000 bash ai-core/scripts/post_deploy_check.sh  # local
#
# Exit 0 = both turns answered sanely. Non-zero = deploy is bad.

ROOT="${ROOT:-/opt/chatbot/current}"
PORT="${PORT:-8081}"
PY="$ROOT/ai-core/venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/ai-core/.venv/bin/python"
BASE="http://localhost:$PORT"

echo "== post-deploy check against $BASE =="

# 0. liveness
LIVE=$(curl -s -m 5 "$BASE/health/live")
case "$LIVE" in
  *alive*) echo "  ✓ /health/live" ;;
  *) echo "  ✗ /health/live: '$LIVE' -- backend not up"; exit 1 ;;
esac

# 1-2. two-turn socket conversation (the real-user path)
PORT="$PORT" "$PY" - <<'PYEOF'
import os, sys, time
import socketio

BASE = f"http://localhost:{os.environ['PORT']}"
PATH = "smartchatbot/socket.io"
TIMEOUT = 90  # first turn may cold-start (classifier cache load)

sio = socketio.Client(reconnection=False)
replies: list[dict] = []

@sio.on("message")
def on_message(data):
    replies.append(data if isinstance(data, dict) else {"message": str(data)})

def wait_reply(n, deadline):
    while len(replies) < n and time.time() < deadline:
        time.sleep(0.5)
    return len(replies) >= n

def fail(msg):
    print(f"  ✗ {msg}")
    try: sio.disconnect()
    except Exception: pass
    sys.exit(1)

try:
    sio.connect(BASE, socketio_path=PATH, wait_timeout=15)
except Exception as e:
    fail(f"socket connect failed: {e}")
print("  ✓ socket connected")

# greeting may or may not arrive as a message event; don't require it.
base_count = len(replies)

# turn 1
sio.emit("message", {"message": "hello"})
if not wait_reply(base_count + 1, time.time() + TIMEOUT):
    fail("turn 1: no reply within timeout")
r1 = (replies[-1].get("message") or "")
if "encountered an error" in r1.lower():
    fail(f"turn 1 errored: {r1[:120]}")
print(f"  ✓ turn 1 replied: {r1[:70]!r}")

# turn 2 -- THE regression turn (conversation history now non-empty)
sio.emit("message", {"message": "what time does the library close today?"})
if not wait_reply(base_count + 2, time.time() + TIMEOUT):
    fail("turn 2: no reply within timeout")
r2 = replies[-1]
t2 = (r2.get("message") or "")
if "encountered an error" in t2.lower():
    fail(f"turn 2 errored (the 2nd-turn-history bug class): {t2[:120]}")
if not t2.strip():
    fail("turn 2: empty answer")
print(f"  ✓ turn 2 replied: {t2[:70]!r}")
print(f"  ✓ turn 2 citations: {len(r2.get('citations') or [])}, "
      f"tokens: {bool(r2.get('tokens'))}")

sio.disconnect()
print("  ✓ two-turn conversation OK")
PYEOF
RC=$?
[ $RC -ne 0 ] && { echo "== post-deploy check FAILED =="; exit $RC; }

echo "== post-deploy check PASSED =="
