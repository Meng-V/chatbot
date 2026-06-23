#!/usr/bin/env python3
"""
qa_soft_knowledge.py -- batch the "soft knowledge" / weird-edge questions
through the REAL v2 stack (real kNN classifier + real backends + real LLM)
and auto-flag the suspicious answers for librarian review BEFORE launch.

Where qa_hard_knowledge.py covers the facts that must be exactly right
(librarian-by-name, address, hours), this covers the squishy stuff that's
the real beta risk: in-building conduct policies (food/alcohol/sleeping/
pets/noise), per-building services, the two CLOSED libraries (B.E.S.T. /
Amos Music), out-of-scope boundaries, and the research-context traps that
must NOT trip the facilities-policy short-circuit.

Each case carries a cheap heuristic check so the run ends with a short
"REVIEW THESE" list instead of 50 answers to eyeball. The heuristic is a
hint, not a verdict -- always read the flagged answers.

Costs real OpenAI tokens (~a dollar for the full set). Needs tunnels up +
DATABASE_URL + OPENAI_API_KEY in the repo-root .env.

Usage:  ai-core/.venv/bin/python scripts/qa_soft_knowledge.py [--only N]
        ai-core/.venv/bin/python scripts/qa_soft_knowledge.py --out soft.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

# The facilities & conduct policy Google Doc the policy short-circuit points at.
# Lower-cased so the substring check is case-insensitive (the doc ID has caps).
POLICY_DOC = "docs.google.com/document/d/1zqdegdmo"


# Heuristic kinds the run can auto-check:
#   "policy"     -> answer/sources SHOULD point to the facilities policy doc
#   "not_policy" -> research-context trap; should NOT route to the policy doc
#   "closed"     -> should say the branch is permanently closed
#   "liaison"    -> music *librarian* still exists (building closed != no liaison)
#   "refuse"     -> off-mission; should refuse or redirect, not answer confidently
#   "service"    -> per-building service answer; just eyeball (no auto-verdict)
#   "eyeball"    -> no reliable heuristic; read it
#
# (kind, question)
CASES: list[tuple[str, str]] = [
    # --- A. in-building conduct policy -> should route to the policy doc ----
    ("policy", "Can I eat in the library?"),
    ("policy", "Can I bring my coffee into King Library?"),
    ("policy", "Is food allowed in Wertz?"),
    ("policy", "Can I drink alcohol in the library?"),
    ("policy", "Can I bring beer to a study room?"),
    ("policy", "Can I sleep in the library overnight?"),
    ("policy", "Can I take a nap in a study room?"),
    ("policy", "Can I bring my dog to the library?"),
    ("policy", "Are pets allowed in King?"),
    ("policy", "How quiet do I have to be? Is there a silent floor?"),
    ("policy", "Can I bring balloons into the library?"),
    ("policy", "Can my kids come with me to the library?"),
    ("policy", "Can I put up flyers in the library?"),
    ("policy", "Can I sell my textbooks in the library lobby?"),
    ("policy", "Can I vape in the library?"),
    ("policy", "Can I bring a water bottle into the stacks?"),
    ("policy", "Am I allowed to ride my bike inside the building?"),
    ("policy", "Can I reserve a room for a birthday party?"),

    # --- A'. service / emotional-support animals (tricky boundary) ---------
    ("eyeball", "Can I bring my emotional support animal into the library?"),
    ("eyeball", "Are service dogs allowed in King?"),

    # --- B. per-building services (cross-campus) ---------------------------
    ("service", "Can I print at King?"),
    ("service", "Does the Gardner-Harvey Library have a 3D printer?"),
    ("service", "Where can I scan documents?"),
    ("service", "Can I check out a laptop?"),
    ("service", "Where are the group study rooms at King?"),
    ("service", "Can I reserve a study room at the Wertz Art & Architecture Library?"),
    ("service", "Do you have a color printer?"),

    # --- C. CLOSED libraries (B.E.S.T. / Amos Music) ----------------------
    ("closed", "Where is the BEST library?"),
    ("closed", "What are the hours for the B.E.S.T. Library?"),
    ("closed", "Is the music library open?"),
    ("closed", "Where do I find music scores now that Amos Music Library closed?"),
    ("liaison", "Who is the music subject librarian?"),

    # --- D. hours / access edge -------------------------------------------
    ("eyeball", "Is the library open right now?"),
    ("eyeball", "Can I get into King at 2am?"),
    ("eyeball", "Are the libraries open during finals week?"),

    # --- E. out-of-scope boundaries -> should refuse / redirect -----------
    ("refuse", "What's the weather in Oxford today?"),
    ("refuse", "Can you write my history essay for me?"),
    ("refuse", "Who won the Bengals game last night?"),
    ("refuse", "Tell me a joke."),
    ("refuse", "Solve this calculus problem for me: integral of x^2 dx."),

    # --- F. multi-question in one turn ------------------------------------
    ("eyeball", "Can I eat in the library, and what time does King close tonight?"),
    ("eyeball", "I need a quiet study room and a book about insomnia."),

    # --- G. research-context TRAPS -> must NOT trip the policy doc ---------
    ("not_policy", "I'm looking for a peer-reviewed article about alcohol abuse."),
    ("not_policy", "Do you have any books about dogs?"),
    ("not_policy", "I need scholarly sources on food insecurity in Ohio."),
    ("not_policy", "Can you help me find a journal article on pet therapy?"),
    ("not_policy", "Where can I find research on noise pollution?"),
]


def _verdict(kind: str, answer: str, sources_blob: str, refusal: bool) -> tuple[str, str]:
    """Return (flag, why). flag in {"ok", "REVIEW"}. Heuristic only."""
    a = answer.lower()
    has_doc = POLICY_DOC in sources_blob.lower() or POLICY_DOC in a
    if kind == "policy":
        return ("ok", "points to policy doc") if has_doc else \
            ("REVIEW", "policy question but NO facilities-policy doc link")
    if kind == "not_policy":
        return ("REVIEW", "research question WRONGLY routed to policy doc") if has_doc else \
            ("ok", "did not mis-route to policy doc")
    if kind == "closed":
        return ("ok", "says closed") if ("closed" in a or "permanently" in a) else \
            ("REVIEW", "CLOSED branch but answer doesn't say closed")
    if kind == "liaison":
        ok = ("zaslow" in a) or ("barry" in a)
        return ("ok", "names the music liaison") if ok else \
            ("REVIEW", "music librarian: should still name Barry Zaslow")
    if kind == "refuse":
        looks_handled = refusal or any(
            w in a for w in ("can't", "cannot", "not able", "outside", "i'm a library",
                             "library assistant", "librarian", "ask us", "help with library"))
        return ("ok", "refused/redirected") if looks_handled else \
            ("REVIEW", "off-mission question answered confidently?")
    return ("eyeball", "read it")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0, help="run only first N cases")
    ap.add_argument("--out", type=str, default="", help="also write JSONL here")
    args = ap.parse_args()

    from src.graph.v2_serving import build_v2_deps
    from src.graph.new_orchestrator import TurnRequest, run_turn

    print("building v2 deps (real classifier + backends + LLM)...", flush=True)
    deps = build_v2_deps()
    print("ready.\n", flush=True)

    cases = CASES[: args.only] if args.only else CASES
    out_f = open(args.out, "w") if args.out else None
    flagged: list[tuple[int, str, str, str]] = []

    for i, (kind, q) in enumerate(cases, 1):
        try:
            resp = run_turn(TurnRequest(user_message=q, conversation_id=f"soft-{i}"), deps)
            answer = (resp.answer or "").strip()
            srcs = resp.citations or []
            blob = " ".join(str(s.get("url", "")) for s in srcs)
            flag, why = _verdict(kind, answer, blob, bool(resp.is_refusal))
            mark = {"REVIEW": "⚠ REVIEW", "ok": "✓ ok", "eyeball": "· eyeball"}[flag]
            print("=" * 88)
            print(f"[{i}] {mark}  kind={kind}  intent={resp.intent}  refusal={resp.is_refusal}  -- {why}")
            print(f"Q: {q}")
            print(f"BOT: {answer}")
            if srcs:
                print("SOURCES: " + "  ".join(f"[{s.get('n')}] {s.get('url')}" for s in srcs))
            if flag == "REVIEW":
                flagged.append((i, kind, q, why))
            if out_f:
                out_f.write(json.dumps({
                    "i": i, "kind": kind, "q": q, "intent": resp.intent,
                    "refusal": bool(resp.is_refusal), "flag": flag, "why": why,
                    "answer": answer, "sources": blob,
                }) + "\n")
        except Exception as e:  # noqa: BLE001
            print("=" * 88)
            print(f"[{i}] ✗ ERROR  kind={kind}: {type(e).__name__}: {e}")
            flagged.append((i, kind, q, f"ERROR {type(e).__name__}"))

    if out_f:
        out_f.close()
    print("\n" + "#" * 88)
    print(f"# REVIEW LIST -- {len(flagged)} / {len(cases)} flagged by heuristic (read these)")
    print("#" * 88)
    for i, kind, q, why in flagged:
        print(f"  [{i}] ({kind}) {q}\n        -> {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
