#!/usr/bin/env python3
"""
qa_routing_stress.py -- proactively hunt MISROUTES before librarians hit them.

The recurring prod failure this beta: an ambiguous keyword steals the route
(e.g. "3d printing in King" -> printing_wifi, not makerspace_3d), and the wrong
intent path then LOOPS, returns an EMPTY answer, REFUSES with "couldn't verify
my sources", or FABRICATES a contact. This probe fires many real phrasings at
the keyword-collision zones and auto-flags those failure signatures so they can
be fixed deterministically instead of discovered one screenshot at a time.

Failure signatures flagged:
  LOOP      -- agent_stopped_reason == loop_detected
  EMPTY     -- answer is blank / near-blank
  NO-CITE   -- the "I started to answer but couldn't verify my sources" refusal
  REFUSED   -- is_refusal on a question that looks like a real library ask
  FABRICATE -- a subject-liaison name on a NON-subject question (misapplication)

Costs real OpenAI tokens (~a couple dollars). Needs tunnels up + .env.

Usage:  ai-core/.venv/bin/python scripts/qa_routing_stress.py [--out f.jsonl]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

# Subject-liaison names (liaisons page, 2026-06-25). A NON-subject question that
# surfaces one of these is a possible misapplied-liaison fabrication.
_LIAISON_NAMES = [
    "Abigail Morgan", "Andrew Revelle", "Barry Zaslow", "Brien Withers",
    "Erica Freed", "Ginny Boehme", "Jenny Presnell", "Katie Gibson",
    "Kristen Adams", "Laura Birkenhauer", "Mark Dahlquist", "Megan Jaskowiak",
    "Stefanie Hilles",
]

# (expect_answer?, question) -- expect_answer True = a real library ask that
# SHOULD be answered (a refusal/loop/empty here is a bug). False = genuinely
# out-of-scope (a refusal is correct).
CASES: list[tuple[bool, str]] = [
    # --- 3D printing / makerspace, many phrasings (the printing-token trap) --
    (True, "I want to 3D print something at King"),
    (True, "how do I get something 3D printed"),
    (True, "is 3D printing free at the library"),
    (True, "can students use the 3D printers"),
    (True, "do you do 3D printing"),
    (True, "I have an STL file to print"),
    (True, "laser cutter at the library"),
    (True, "sewing machine in the makerspace"),
    (True, "what can I make in the makerspace"),

    # --- printing / scanning / copying (printing-token) --------------------
    (True, "how do I print double sided"),
    (True, "can I scan to email at King"),
    (True, "is there a copier at Wertz"),
    (True, "do you have a poster printer"),
    (True, "where do I pick up my prints"),
    (True, "how do I add money to my print account"),

    # --- "book" token: room booking vs find-a-book -------------------------
    (True, "I want to book a study room"),
    (True, "how do I find a book"),
    (True, "do you have this book in the library"),
    (True, "can I book a group room at King for 4 people"),
    (True, "where are the books on the second floor"),
    (True, "I'm looking for a specific book"),

    # --- "study" token -----------------------------------------------------
    (True, "where can I study late at night"),
    (True, "is there a silent study area"),
    (True, "do I need to reserve a study space"),

    # --- borrowing / checkout / renew --------------------------------------
    (True, "how do I borrow a book"),
    (True, "can I check out a book from another campus"),
    (True, "my book is overdue what do I do"),
    (True, "how do I renew online"),
    (True, "can I keep a laptop overnight"),

    # --- building + service combos (cross-campus collision) ----------------
    (True, "printing at the Hamilton library"),
    (True, "study rooms at Middletown"),
    (True, "does Wertz have a scanner"),
    (True, "computers at the Gardner-Harvey library"),
    (True, "wifi at King library"),

    # --- research / databases / citation -----------------------------------
    (True, "I need help starting my research"),
    (True, "what databases do you have for history"),
    (True, "how do I cite a website in MLA"),
    (True, "I can't access a database from home"),
    (True, "where do I find statistics for a paper"),

    # --- account / card / fines --------------------------------------------
    (True, "how do I get a guest library card"),
    (True, "I lost my library book what now"),
    (True, "do I owe any fines"),

    # --- special collections / archives ------------------------------------
    (True, "can I see a rare book"),
    (True, "how do I use the university archives"),

    # --- terse / typo / casual phrasings -----------------------------------
    (True, "3d print king?"),
    (True, "study room kng tmrw"),
    (True, "wifi"),
    (True, "printer near me"),
    (True, "scan docs where"),
    (True, "renew books"),

    # --- genuinely out of scope (a refusal here is CORRECT) ----------------
    (False, "what's the parking ticket appeal process"),
    (False, "when is spring break"),
    (False, "how do I register for classes"),
]


def _flags(expect: bool, answer: str, refusal: bool, intent: str, stop: str) -> list[str]:
    f: list[str] = []
    a = (answer or "").strip()
    al = a.lower()
    if stop == "loop_detected":
        f.append("LOOP")
    if len(a) < 25:
        f.append("EMPTY")
    if "couldn't verify my sources" in al or "started to answer but" in al:
        f.append("NO-CITE")
    if expect and (refusal or intent == "out_of_scope"):
        f.append("REFUSED")
    # liaison name on a non-subject question
    if intent not in ("subject_librarian",):
        for n in _LIAISON_NAMES:
            if n.lower() in al:
                f.append(f"FABRICATE?({n})")
                break
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    from src.graph.v2_serving import build_v2_deps
    from src.graph.new_orchestrator import TurnRequest, run_turn

    print("building v2 deps...", flush=True)
    deps = build_v2_deps()
    print(f"ready. {len(CASES)} cases.\n", flush=True)

    out_f = open(args.out, "w") if args.out else None
    flagged: list[tuple[str, list[str]]] = []

    for i, (expect, q) in enumerate(CASES, 1):
        try:
            r = run_turn(TurnRequest(user_message=q, conversation_id=f"rs-{i}"), deps)
            ans = (r.answer or "").strip()
            fl = _flags(expect, ans, bool(r.is_refusal), str(r.intent), str(r.agent_stopped_reason))
            mark = ("⚠ " + ",".join(fl)) if fl else "✓ ok"
            print("=" * 92)
            print(f"[{i}] {mark}  intent={r.intent}  stop={r.agent_stopped_reason}")
            print(f"Q: {q}")
            print(f"BOT: {ans[:240]}")
            if fl:
                flagged.append((q, fl))
            if out_f:
                out_f.write(json.dumps({
                    "i": i, "expect": expect, "q": q, "intent": str(r.intent),
                    "stop": str(r.agent_stopped_reason), "refusal": bool(r.is_refusal),
                    "flags": fl, "answer": ans,
                }) + "\n")
        except Exception as e:  # noqa: BLE001
            print("=" * 92)
            print(f"[{i}] ✗ ERROR: {type(e).__name__}: {e}")
            flagged.append((q, [f"ERROR:{type(e).__name__}"]))

    if out_f:
        out_f.close()
    print("\n" + "#" * 92)
    print(f"# FLAGGED -- {len(flagged)} / {len(CASES)} (loop / empty / no-cite / refused / fabricate)")
    print("#" * 92)
    for q, fl in flagged:
        print(f"  [{','.join(fl)}]  {q}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
