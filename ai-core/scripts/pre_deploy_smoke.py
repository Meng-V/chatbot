#!/usr/bin/env python3
"""
pre_deploy_smoke.py -- RUN THIS BEFORE EVERY DEPLOY.

Why it exists: testing run_turn() directly (main thread) does NOT exercise
the real serving path, which is why prod kept breaking on things local
tests passed (D3 corrections loop-affinity; the 2nd-turn add_message
loop-affinity). This harness replicates the EXACT `_v2_message` flow from
main.py -- conversation-store writes/reads on the main loop + run_turn on
an executor thread (via handle_v2_message) + per-turn telemetry -- across
a MULTI-TURN conversation, the same thing post_deploy_check.sh does on
prod, but locally so problems surface before shipping.

It is a GATE: exits non-zero if any turn raises or the bot returns the
generic error/unavailable message. Run:

    ai-core/.venv/bin/python scripts/pre_deploy_smoke.py
"""
from __future__ import annotations
import sys, asyncio, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")
logging.basicConfig(level=logging.ERROR, format="%(message)s", stream=sys.stdout)
for n in ("httpx", "openai_calls", "springshare", "eval", "v2_serving"):
    logging.getLogger(n).setLevel(logging.CRITICAL)

# Multi-turn script: greeting (OOS), hours (agent), a follow-up WITH
# history (this is the turn that broke prod), a librarian lookup, and a
# booking opener. Each runs the full _v2_message path.
TURNS = [
    "hello",
    "what time does King Library close today?",
    "and what about tomorrow?",
    "who is the chemistry librarian?",
    "can I book a study room?",
]
_BAD = ("i encountered an error", "temporarily unavailable",
        "encountered an issue")


async def _run_one_turn(deps, conversation_id, text):
    """Faithful copy of main._v2_message's per-turn body (minus the
    socket emit): persist user msg, read history, handle via executor,
    persist assistant msg, persist telemetry."""
    from src.memory.conversation_store import (
        add_message, get_conversation_history, log_token_usage_v2,
    )
    from src.graph.v2_serving import handle_v2_message
    await add_message(conversation_id, "user", text)
    history = await get_conversation_history(conversation_id, limit=10)
    wire = await handle_v2_message(text, deps, conversation_id=conversation_id,
                                   conversation_history=history)
    msg = wire.get("message", "") or ""
    await add_message(conversation_id, "assistant", msg)
    tok = wire.get("tokens") or {}
    total = int(tok.get("input", 0)) + int(tok.get("output", 0))
    if total > 0:
        await log_token_usage_v2(
            conversation_id, model_name=str(wire.get("model_used") or "v2"),
            prompt_tokens=int(tok.get("input", 0)),
            completion_tokens=int(tok.get("output", 0)),
            total_tokens=total,
            cached_input_tokens=int(tok.get("cached_input", 0)),
            call_site="v2_turn",
        )
    return msg, wire.get("error")


async def main() -> int:
    from src.graph.v2_serving import build_v2_deps
    from src.memory.conversation_store import create_conversation
    print("building deps + warming (mirrors startup)...", flush=True)
    deps = build_v2_deps()
    conversation_id = await create_conversation()
    print(f"conversation {conversation_id}\n")
    failures = 0
    for i, text in enumerate(TURNS, 1):
        try:
            msg, err = await _run_one_turn(deps, conversation_id, text)
            low = msg.lower()
            bad = err or any(b in low for b in _BAD)
            tag = "FAIL" if bad else "ok"
            if bad:
                failures += 1
            print(f"[{tag}] turn {i}: {text}")
            print(f"        -> {msg[:140]}")
            if err:
                print(f"        -> error key: {err}")
        except Exception as e:
            failures += 1
            import traceback
            print(f"[FAIL] turn {i}: {text}\n        RAISED {type(e).__name__}: {e}")
            traceback.print_exc()
    print()
    if failures:
        print(f"❌ PRE-DEPLOY SMOKE FAILED: {failures}/{len(TURNS)} turns bad. "
              "DO NOT DEPLOY.")
        return 1
    print(f"✅ PRE-DEPLOY SMOKE PASSED: all {len(TURNS)} turns clean "
          "(real serving path, multi-turn). Safe to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
