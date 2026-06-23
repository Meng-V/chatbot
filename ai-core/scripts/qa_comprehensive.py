#!/usr/bin/env python3
"""
qa_comprehensive.py -- the broad "everything a user might ask" sweep through
the REAL v2 stack, to find gaps before the librarian beta.

Complements the narrower harnesses:
  - qa_hard_knowledge.py  -- facts that must be exact (librarian/address/hours)
  - qa_soft_knowledge.py  -- conduct policies / closures / research-trap precision
  - adversarial_probe.py  -- injection / abuse / jailbreak

This one casts wide: borrowing & circulation, tech/equipment checkout,
printing/scanning/wifi, accounts & off-campus access, spaces & booking,
research help & citation, special collections, hours edge cases, directions/
parking, greetings/escalation, casual/typo phrasing, multi-question turns.

Each case has a cheap heuristic so the run ends with a short REVIEW list, but
the heuristic is only a hint -- read the flagged answers.

Costs real OpenAI tokens (~a couple dollars for the full set). Needs tunnels
up + DATABASE_URL + OPENAI_API_KEY in the repo-root .env.

Usage:  ai-core/.venv/bin/python scripts/qa_comprehensive.py [--only N] [--out f.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

POLICY_DOC = "docs.google.com/document/d/1zqdegdmo"  # lower-cased for matching

# kind: policy | not_policy | closed | liaison | refuse | greet | eyeball
CASES: list[tuple[str, str]] = [
    # --- greeting / smalltalk -------------------------------------------
    ("greet", "hi"),
    ("greet", "hello there"),
    ("greet", "good morning"),
    ("greet", "thanks!"),
    ("eyeball", "who are you?"),
    ("eyeball", "what can you help me with?"),

    # --- hours / access edge --------------------------------------------
    ("eyeball", "what time does the library close today?"),
    ("eyeball", "are you open right now?"),
    ("eyeball", "what are King library's hours this weekend?"),
    ("eyeball", "is the library open on Sunday?"),
    ("eyeball", "are you open on holidays?"),
    ("eyeball", "what are the summer hours?"),
    ("eyeball", "is King open 24 hours?"),
    ("eyeball", "what time does Wertz open tomorrow?"),
    ("eyeball", "when does Special Collections close?"),

    # --- locations / directions / parking -------------------------------
    ("eyeball", "where is King Library?"),
    ("eyeball", "what's the address of the Hamilton library?"),
    ("eyeball", "where can I park near the library?"),
    ("eyeball", "how do I get to the Middletown library?"),
    ("eyeball", "where are the bathrooms in King?"),

    # --- borrowing / circulation ----------------------------------------
    ("eyeball", "how long can I keep a book?"),
    ("eyeball", "how many books can I check out at once?"),
    ("eyeball", "how do I renew my books?"),
    ("eyeball", "do you charge late fees?"),
    ("eyeball", "what happens if I lose a library book?"),
    ("eyeball", "how do I place a hold on a book?"),
    ("eyeball", "can I get a book from another library?"),
    ("eyeball", "how does interlibrary loan work?"),
    ("eyeball", "where do I find course reserves for my class?"),
    ("eyeball", "can I return books at any campus?"),

    # --- tech / equipment checkout / printing ---------------------------
    ("eyeball", "can I check out a laptop?"),
    ("eyeball", "how long can I borrow a Chromebook?"),
    ("eyeball", "do you lend cameras?"),
    ("eyeball", "can I borrow a phone charger?"),
    ("eyeball", "do you have calculators to check out?"),
    ("eyeball", "how do I print something?"),
    ("eyeball", "how much does it cost to print?"),
    ("eyeball", "can I print in color?"),
    ("eyeball", "how do I print from my laptop?"),
    ("eyeball", "where can I scan documents?"),
    ("eyeball", "what's the wifi password?"),
    ("eyeball", "are there computers I can use?"),

    # --- accounts / off-campus access -----------------------------------
    ("eyeball", "how do I access databases from off campus?"),
    ("eyeball", "do I need a VPN to use library resources at home?"),
    ("eyeball", "how do I get a library card?"),
    ("eyeball", "can community members use the library?"),
    ("eyeball", "can alumni access the databases?"),

    # --- spaces / booking / makerspace ----------------------------------
    ("eyeball", "how do I reserve a study room?"),
    ("eyeball", "book a study room at king tomorrow 3-4pm"),
    ("eyeball", "is there a quiet place to study?"),
    ("eyeball", "where can I study in a group?"),
    ("eyeball", "does the library have a makerspace?"),
    ("eyeball", "can I use a 3D printer?"),
    ("eyeball", "how much does 3D printing cost?"),
    ("eyeball", "can I reserve a room at Hamilton?"),

    # --- research help / citation / databases ---------------------------
    ("eyeball", "how do I find peer-reviewed articles?"),
    ("eyeball", "I need help with my research paper"),
    ("eyeball", "how do I cite a source in APA?"),
    ("eyeball", "what database should I use for psychology?"),
    ("eyeball", "can I make an appointment with a librarian?"),
    ("eyeball", "who is the business subject librarian?"),
    ("eyeball", "I can't find the full text of an article"),
    ("eyeball", "do you have a citation tool like Zotero?"),
    ("eyeball", "how do I search the catalog?"),
    ("eyeball", "where do I find primary sources?"),

    # --- special collections / archives ---------------------------------
    ("eyeball", "how do I access special collections?"),
    ("eyeball", "do I need an appointment to see archives?"),
    ("eyeball", "do you have old Miami University yearbooks?"),

    # --- conduct policies (should -> policy doc) ------------------------
    ("policy", "can I eat in the library?"),
    ("policy", "is there a place I can take a phone call?"),
    ("policy", "can I bring my dog?"),
    ("policy", "can I reserve a space for a club meeting?"),
    ("policy", "can I bring food for a study group?"),

    # --- closed branches ------------------------------------------------
    ("closed", "where is the BEST library?"),
    ("closed", "is the music library still open?"),

    # --- research-context traps (should NOT -> policy doc) --------------
    ("not_policy", "I need articles about food deserts"),
    ("not_policy", "do you have books about dogs?"),
    ("not_policy", "find me research on alcohol use disorder"),

    # --- out-of-scope / boundaries --------------------------------------
    ("refuse", "what's the weather like today?"),
    ("refuse", "can you do my homework?"),
    ("refuse", "what's a good restaurant near campus?"),
    ("refuse", "who is the president of the university?"),
    ("refuse", "write me a poem about cats"),

    # --- escalation / frustration / human handoff -----------------------
    ("eyeball", "this isn't helping, I want to talk to a real person"),
    ("eyeball", "can I talk to a librarian?"),
    ("eyeball", "I have a complaint"),

    # --- casual / typo / terse phrasing ---------------------------------
    ("eyeball", "hrs?"),
    ("eyeball", "wifi pw"),
    ("eyeball", "how late u open"),
    ("eyeball", "stdy room king 2morrow"),
    ("eyeball", "where bathroom"),

    # --- multi-question in one turn -------------------------------------
    ("eyeball", "what time do you close and where can I print?"),
    ("eyeball", "who is the nursing librarian and can I book a room?"),
]


def _verdict(kind: str, answer: str, blob: str, refusal: bool, intent: str) -> tuple[str, str]:
    a = answer.lower()
    has_doc = POLICY_DOC in blob.lower() or POLICY_DOC in a
    if kind == "policy":
        return ("ok", "policy doc") if has_doc else ("REVIEW", "no facilities-policy doc link")
    if kind == "not_policy":
        return ("REVIEW", "research Q mis-routed to policy doc") if has_doc else ("ok", "not mis-routed")
    if kind == "closed":
        return ("ok", "says closed") if ("closed" in a or "permanently" in a) else ("REVIEW", "doesn't say closed")
    if kind == "liaison":
        return ("ok", "names liaison") if "@miamioh.edu" in a else ("REVIEW", "no librarian email")
    if kind == "refuse":
        handled = refusal or intent == "out_of_scope" or any(
            w in a for w in ("can't", "cannot", "not able", "outside", "focused on", "ask us"))
        return ("ok", "refused/redirected") if handled else ("REVIEW", "answered off-mission?")
    if kind == "greet":
        bad = refusal or intent == "out_of_scope"
        return ("REVIEW", "greeting treated as out-of-scope/refusal") if bad else ("ok", "greeted")
    return ("eyeball", "read it")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    from src.graph.v2_serving import build_v2_deps
    from src.graph.new_orchestrator import TurnRequest, run_turn

    print("building v2 deps (real classifier + backends + LLM)...", flush=True)
    deps = build_v2_deps()
    print(f"ready. running {len(CASES)} cases.\n", flush=True)

    cases = CASES[: args.only] if args.only else CASES
    out_f = open(args.out, "w") if args.out else None
    flagged: list[tuple[int, str, str, str]] = []

    for i, (kind, q) in enumerate(cases, 1):
        try:
            resp = run_turn(TurnRequest(user_message=q, conversation_id=f"comp-{i}"), deps)
            answer = (resp.answer or "").strip()
            srcs = resp.citations or []
            blob = " ".join(str(s.get("url", "")) for s in srcs)
            flag, why = _verdict(kind, answer, blob, bool(resp.is_refusal), str(resp.intent))
            mark = {"REVIEW": "⚠ REVIEW", "ok": "✓ ok", "eyeball": "· eyeball"}[flag]
            print("=" * 92)
            print(f"[{i}] {mark}  kind={kind}  intent={resp.intent}  refusal={resp.is_refusal}  -- {why}")
            print(f"Q: {q}")
            print(f"BOT: {answer}")
            if srcs:
                print("SRC: " + "  ".join(f"[{s.get('n')}] {s.get('url')}" for s in srcs))
            if flag == "REVIEW":
                flagged.append((i, kind, q, why))
            if out_f:
                out_f.write(json.dumps({
                    "i": i, "kind": kind, "q": q, "intent": str(resp.intent),
                    "refusal": bool(resp.is_refusal), "flag": flag, "why": why,
                    "answer": answer, "sources": blob,
                }) + "\n")
        except Exception as e:  # noqa: BLE001
            print("=" * 92)
            print(f"[{i}] ✗ ERROR  kind={kind}: {type(e).__name__}: {e}")
            flagged.append((i, kind, q, f"ERROR {type(e).__name__}: {e}"))
            if out_f:
                out_f.write(json.dumps({"i": i, "kind": kind, "q": q, "flag": "ERROR",
                                        "why": f"{type(e).__name__}: {e}"}) + "\n")

    if out_f:
        out_f.close()
    print("\n" + "#" * 92)
    print(f"# HEURISTIC REVIEW LIST -- {len(flagged)} / {len(cases)} (hints; read these first)")
    print("#" * 92)
    for i, kind, q, why in flagged:
        print(f"  [{i}] ({kind}) {q}\n        -> {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
