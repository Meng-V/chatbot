#!/usr/bin/env python3
"""
qa_hard_knowledge.py -- run a curated set of "hard knowledge" questions
through the REAL v2 stack (real kNN classifier + real backends + real
LLM) and print question / intent / answer / sources for librarian review.

This is the systematic version of "stumbling on a wrong answer like the
Wertz address" -- batch the categories that must be right (subject ->
librarian, course number, librarian-by-name, hours, location, per-building
services) and eyeball them all at once.

Costs real OpenAI tokens (cheap; ~cents for the default set). Needs the
tunnels up + DATABASE_URL + OPENAI_API_KEY in the repo-root .env.

Usage:  ai-core/.venv/bin/python scripts/qa_hard_knowledge.py [--only N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")


# (category, question, what a correct answer should contain) ----------------
CASES: list[tuple[str, str, str]] = [
    ("subject→librarian", "Who is the subject librarian for Marketing?",
     "Erica Freed / Abigail Morgan (Marketing liaison) + email"),
    ("subject→librarian", "Who do I contact for help with nursing research?",
     "the Nursing subject librarian (Oxford) + email"),
    ("course number", "Which librarian can help me with BIO 201?",
     "Biology liaison (Ginny Boehme) + email"),
    ("course number", "I need research help for ACC 221.",
     "Accountancy/Business liaison + email"),
    ("librarian by name", "What is Erica Freed's email address?",
     "freede@miamioh.edu"),
    ("hours", "What time does King Library close today?",
     "today's King hours from LibCal (live)"),
    ("location/address", "Where is the Gardner-Harvey Library?",
     "Middletown, 4200 N. University Blvd"),
    ("location/address", "What is the address of King Library?",
     "151 S. Campus Ave, Oxford, OH 45056"),
    ("per-building service", "Is there a MakerSpace at the Hamilton campus?",
     "REFUSE/redirect: MakerSpace is King (Oxford) only"),
    ("per-building service", "Does the King MakerSpace have a 3D printer?",
     "yes, 3D printers (from LibrarySpace.equipment)"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0,
                    help="run only the first N cases (0 = all)")
    args = ap.parse_args()

    from src.graph.v2_serving import build_v2_deps
    from src.graph.new_orchestrator import TurnRequest, run_turn

    print("building v2 deps (real classifier + backends + LLM)...", flush=True)
    deps = build_v2_deps()
    print("ready.\n", flush=True)

    cases = CASES[: args.only] if args.only else CASES
    for i, (cat, q, expected) in enumerate(cases, 1):
        try:
            resp = run_turn(TurnRequest(user_message=q, conversation_id=f"qa-{i}"), deps)
            answer = (resp.answer or "").strip()
            srcs = resp.citations or []
            print("=" * 80)
            print(f"[{i}] ({cat})  intent={resp.intent}  refusal={resp.is_refusal}")
            print(f"Q: {q}")
            print(f"EXPECT: {expected}")
            print(f"BOT: {answer}")
            if srcs:
                print("SOURCES:")
                for s in srcs:
                    print(f"   [{s.get('n')}] {s.get('url')}")
        except Exception as e:  # noqa: BLE001
            print("=" * 80)
            print(f"[{i}] ({cat})  ERROR: {type(e).__name__}: {e}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
