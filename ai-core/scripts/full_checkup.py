#!/usr/bin/env python3
"""
full_checkup.py -- one-process comprehensive runtime exam of the v2 bot.

Builds deps once, then runs: Springshare/OpenAI/DB/Weaviate API health,
a Q&A battery (hard knowledge / soft knowledge / refusal / out-of-scope /
confidence / multi-question), and a multi-turn study-room booking flow.
Prints a structured report with per-turn intent / refusal / confidence /
tokens / citations so the whole picture is visible at a glance.

Run: ai-core/.venv/bin/python scripts/full_checkup.py
"""
from __future__ import annotations
import sys, asyncio, logging, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")
logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
for noisy in ("httpx", "openai_calls", "springshare", "eval", "v2_serving"):
    logging.getLogger(noisy).setLevel(logging.ERROR)


def line(): print("-" * 78)


def main() -> int:
    from src.graph.v2_serving import build_v2_deps
    from src.graph.new_orchestrator import TurnRequest, run_turn

    print("building deps (real classifier + backends + LLM)...", flush=True)
    t0 = time.time()
    deps = build_v2_deps()
    print(f"deps ready in {time.time()-t0:.0f}s\n")

    # ---- 1. API HEALTH ----
    print("=" * 78); print("1. API HEALTH (Springshare + OpenAI + Postgres + Weaviate)"); line()
    from src.observability.springshare import check_springshare_health
    asyncio.run(check_springshare_health())
    # OpenAI
    try:
        from src.llm.client import embed
        _t = time.time(); embed("ping"); print(f"   OpenAI embeddings: OK ({int((time.time()-_t)*1000)}ms)")
    except Exception as e:
        print(f"   OpenAI: DOWN -- {e}")
    # Postgres
    try:
        import os, asyncpg
        async def _pg():
            c = await asyncpg.connect(os.environ["DATABASE_URL"]); await c.fetchval("SELECT 1"); await c.close()
        _t = time.time(); asyncio.run(_pg()); print(f"   Postgres: OK ({int((time.time()-_t)*1000)}ms)")
    except Exception as e:
        print(f"   Postgres: DOWN -- {e}")
    # Weaviate
    try:
        from src.utils.weaviate_client import get_weaviate_client
        wv = get_weaviate_client(); ok = wv.is_ready(); wv.close()
        print(f"   Weaviate: {'OK' if ok else 'NOT READY'}")
    except Exception as e:
        print(f"   Weaviate: DOWN -- {e}")

    # ---- 2. Q&A BATTERY ----
    BATTERY = [
        ("HARD", "Who is the chemistry librarian?"),
        ("HARD", "What time does King Library close today?"),
        ("HARD", "What is the address of the Gardner-Harvey Library?"),
        ("SOFT", "How do I print at the library?"),
        ("SOFT", "What is interlibrary loan and how do I use it?"),
        ("SOFT", "How many books can I check out and for how long?"),
        ("MULTI", "What are King's hours today and who is the biology librarian?"),
        ("REFUSE-OOS", "What was the score of the Bengals game last night?"),
        ("REFUSE-OOS", "Search the catalog for Moby Dick and tell me if it's available."),
        ("REFUSE-CAP", "What is the balance on my library account?"),
        ("REFUSE-PRIVACY", "What is the WiFi password at King Library?"),
        ("CONFIDENCE", "Does King Library have a meditation room on the 5th floor?"),
        ("CROSS", "Can I 3D print at any campus?"),
    ]
    print("\n" + "=" * 78); print("2. Q&A BATTERY (answer / refuse / confidence)"); line()
    for tag, q in BATTERY:
        try:
            r = run_turn(TurnRequest(user_message=q, conversation_id=f"qa-{tag}"), deps)
            flag = "REFUSED" if r.is_refusal else "answered"
            print(f"[{tag}] {q}")
            print(f"   -> {flag} | intent={r.intent} | conf={r.confidence}"
                  f" | trigger={r.refusal_trigger} | cites={len(r.citations)}"
                  f" | tok in/out={r.tokens.get('input')}/{r.tokens.get('output')}")
            print(f"   {r.answer[:200]}")
        except Exception as e:
            print(f"[{tag}] {q}\n   EXCEPTION: {type(e).__name__}: {e}")
        line()

    # ---- 3. BOOKING FLOW (multi-turn) ----
    print("\n" + "=" * 78); print("3. STUDY-ROOM BOOKING FLOW (multi-turn)"); line()
    conv = "booking-exam"; history: list[dict] = []
    booking_turns = [
        "Can I book a study room?",
        "King Library, tomorrow 2pm to 3pm",
        "My name is Test Student, email test@miamioh.edu",
    ]
    for msg in booking_turns:
        try:
            r = run_turn(TurnRequest(user_message=msg, conversation_id=conv,
                                     conversation_history=list(history)), deps)
            print(f"USER: {msg}")
            print(f"BOT ({r.intent}): {r.answer[:280]}")
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": r.answer})
        except Exception as e:
            print(f"USER: {msg}\n   EXCEPTION: {type(e).__name__}: {e}")
        line()
    print("(stopped before final confirm -- no real booking placed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
