#!/usr/bin/env python3
"""
qa_contacts_probe.py -- targeted "who do I contact for X" sweep through the
REAL v2 stack, to catch FABRICATED contacts.

Why: when the index has no authoritative staff/contact chunk for a service or
space, the synthesizer grabs the liaisons page and invents a plausible-but-
wrong contact (prod 2026-06-25: "I need help with Makerspace" -> wrong "Katie
Gibson"). Subject-librarian lookups returning a name+email are LEGIT; a
SERVICE / SPACE / DEPARTMENT question returning a specific person is the
fabrication risk to scrutinize.

The probe flags every answer that emits a specific @miamioh.edu contact so you
can eyeball whether it's real. It does NOT know ground truth -- verify flagged
names against the authoritative page (curl, don't trust a summary).

Costs real OpenAI tokens. Needs tunnels up + .env.

Usage:  ai-core/.venv/bin/python scripts/qa_contacts_probe.py [--out f.jsonl]
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

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@miamioh\.edu", re.IGNORECASE)

# kind: subject (name+email EXPECTED & legit) | service/space/dept/building/
# leadership/generic (a specific person is SUSPICIOUS -> verify)
CASES: list[tuple[str, str]] = [
    # --- subject liaisons (control: a name+email here is correct) ----------
    ("subject", "Who is the chemistry librarian?"),
    ("subject", "Who do I contact for nursing research?"),
    ("subject", "Who is the business subject librarian?"),

    # --- special roles already short-circuited (control) -------------------
    ("space", "Who is the MakerSpace librarian?"),
    ("space", "Who can help me with the MakerSpace?"),
    ("leadership", "Who is the dean of the libraries?"),
    ("subject", "Who is the music librarian?"),  # Barry Zaslow (building closed, liaison stays)

    # --- SERVICES (fabrication risk: no per-service liaison) ---------------
    ("service", "Who do I contact about interlibrary loan?"),
    ("service", "Who runs course reserves?"),
    ("service", "Who do I contact about a printing problem?"),
    ("service", "Who handles billing and fines questions?"),
    ("service", "Who do I contact about my library account?"),
    ("service", "Who manages the digital collections?"),
    ("service", "Who do I contact for accessibility services?"),
    ("service", "Who is in charge of data services?"),
    ("service", "Who handles open access and scholarly communication?"),
    ("service", "Who do I contact about a study room reservation problem?"),
    ("service", "Who do I contact for 3D printing help?"),
    ("service", "Who runs the citation help / citation managers?"),
    ("service", "Who do I contact about donating materials to the archives?"),
    ("service", "Who do I contact for tech equipment checkout?"),
    ("service", "Who handles software checkout like Adobe?"),

    # --- DEPARTMENTS / SPACES ---------------------------------------------
    ("space", "Who do I contact about Special Collections?"),
    ("space", "Who is in charge of University Archives?"),
    ("space", "Who runs the Howe Writing Center?"),
    ("space", "Who do I contact about the King Cafe?"),

    # --- BUILDINGS / per-campus staff -------------------------------------
    ("building", "Who works at King Library?"),
    ("building", "Who is the head of Wertz Art & Architecture Library?"),
    ("building", "Who do I contact at the Hamilton library?"),
    ("building", "Who staffs the Gardner-Harvey Library?"),

    # --- generic / ambiguous ----------------------------------------------
    ("generic", "Who can I talk to for help?"),
    ("generic", "I need to reach a librarian."),
    ("generic", "Who do I email with a research question?"),
]


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
    flagged: list[tuple[str, str, str, list[str]]] = []

    for i, (kind, q) in enumerate(CASES, 1):
        try:
            r = run_turn(TurnRequest(user_message=q, conversation_id=f"ct-{i}"), deps)
            ans = (r.answer or "").strip()
            emails = sorted(set(_EMAIL_RE.findall(ans)))
            # a specific contact on a non-subject question = scrutinize
            suspicious = bool(emails) and kind not in ("subject",)
            mark = "⚠ VERIFY" if suspicious else ("· named" if emails else "✓ deferred")
            print("=" * 90)
            print(f"[{i}] {mark}  kind={kind}  intent={r.intent}  stop={r.agent_stopped_reason}")
            print(f"Q: {q}")
            print(f"BOT: {ans[:320]}")
            if emails:
                print(f"EMAILS: {emails}")
            srcs = [str(s.get('url')) for s in (r.citations or [])]
            if srcs:
                print("SRC: " + "  ".join(srcs))
            if suspicious:
                flagged.append((kind, q, ans, emails))
            if out_f:
                out_f.write(json.dumps({
                    "i": i, "kind": kind, "q": q, "intent": str(r.intent),
                    "stop": r.agent_stopped_reason, "emails": emails,
                    "suspicious": suspicious, "answer": ans, "sources": srcs,
                }) + "\n")
        except Exception as e:  # noqa: BLE001
            print("=" * 90)
            print(f"[{i}] ✗ ERROR kind={kind}: {type(e).__name__}: {e}")

    if out_f:
        out_f.close()
    print("\n" + "#" * 90)
    print(f"# VERIFY THESE -- {len(flagged)} non-subject answers that emit a specific contact")
    print("#" * 90)
    for kind, q, ans, emails in flagged:
        print(f"  ({kind}) {q}\n     -> {emails}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
