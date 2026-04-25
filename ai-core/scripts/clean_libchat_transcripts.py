"""
Clean LibChat transcript exports into a labeling-ready CSV for the
intent-kNN classifier exemplar set.

Run:
    python scripts/clean_libchat_transcripts.py \\
        --input /path/to/tran_raw_2025.csv \\
        --output ai-core/src/router/exemplars/exemplars_for_labeling.csv

Pipeline:
  1. Read the LibChat CSV (the export schema as of 2025).
  2. Pull `Initial Question` (the first user message of each session --
     exactly what the kNN classifier sees at routing time).
  3. Strip PII: emails, phone numbers, Bronco IDs, MUnetIDs.
  4. Reject rows that are too short (< 10 chars), too long (> 250 chars),
     or that look like account-help boilerplate the bot must NOT answer.
  5. Normalize whitespace; dedupe by lowercased-stripped form.
  6. Run keyword-based PRE-LABELING to give the librarian a head start.
     Output column `suggested_intent` is the heuristic guess; `intent`
     is left blank for the human to fill (override or accept).
  7. Write a CSV with three columns:
        utterance,suggested_intent,intent
     Plus a coverage-report markdown to ./labeling_coverage_report.md
     so the librarian can see how many candidates per intent.

The librarian then opens the CSV, fills in the `intent` column (accept
suggestion = copy from suggested_intent, override = type their own),
saves. A second script `build_exemplars_jsonl.py` (TODO when labeling
is done) consumes that file into ai-core/src/router/exemplars/exemplars.jsonl.

See plan: Layer 3 -> "Intent kNN classifier".
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


# --- PII patterns ---------------------------------------------------------
#
# Drop entire row if any of these appear. These are the patterns we WILL
# see in real LibChat data; the bot's classifier should never train on
# them and the eval set must never log them.

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
# Miami student/employee IDs are 8 digits. Stricter form: starts with
# +<digit><7 more> -- avoids matching course numbers like "BIO 115".
_BRONCO_ID_RE = re.compile(r"\b[89]\d{7}\b")
# MUnetID == Miami's user account names; usually 6-8 chars + numbers.
# If the user is asking about "my account smith21" -> drop. We're
# conservative here: only flag if "munetid" or "my account" appears AND
# a token that looks like a username.
_ACCOUNT_BOILERPLATE_RE = re.compile(
    r"\b(my account|my login|reset (my )?password|my munetid|munet id|my id (number|card))\b",
    re.IGNORECASE,
)

# Hard-reject phrases: these are out-of-scope for the bot AND usually
# wrap PII anyway (account-help / fines / patron-record questions).
# Rather than label them out_of_scope, drop them entirely so the
# `out_of_scope` cluster trains on cleaner negatives (catalog searches,
# sports scores, etc.) rather than account-help noise.
_HARD_REJECT_PHRASES = (
    "i can't log in",
    "i cannot log in",
    "my account is locked",
    "forgot my password",
    "password reset",
    "i was charged",
    "remove the fine",
    "remove a fine",
    "waive the fine",
    "my fines",
)

# Length bounds. Tuned to drop greetings and multi-question paragraphs
# while keeping the sweet spot the kNN learns best from.
MIN_LEN = 10
MAX_LEN = 250


# --- Greeting filter ------------------------------------------------------
#
# "Hi", "Hello", "Anyone there?" -- not useful for the classifier.

_GREETING_RE = re.compile(
    r"^(hi|hello|hey|good (morning|afternoon|evening)|"
    r"anyone there|anybody there|is anyone here|is anyone there)\b[\s!?.,]*$",
    re.IGNORECASE,
)


# --- Keyword pre-labeling -------------------------------------------------
#
# Maps each of the 14 intents to a list of (keyword, weight) tuples.
# The PRE-LABELER picks the highest-scoring intent. Ties or zero score
# -> "unknown" (librarian must pick).
#
# This is intentionally rough -- it's a head start for the librarian,
# NOT the actual classifier. Kept readable so the librarian can
# eyeball "did the keyword guess get this right" without reading code.

_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "hours": [
        ("hours", 2.0), ("open", 1.0), ("close", 1.0), ("when does", 1.5),
        ("what time", 1.5), ("closed", 1.0), ("opening time", 2.0),
        ("closing time", 2.0), ("today", 0.5), ("tonight", 0.7),
        ("weekend", 0.7), ("sunday", 0.7),
    ],
    "room_booking": [
        ("book a room", 3.0), ("reserve a room", 3.0), ("study room", 2.0),
        ("group study", 2.0), ("book a study", 3.0), ("reserve a study", 3.0),
        ("room reservation", 2.5), ("conference room", 2.0),
    ],
    "librarian_lookup": [
        ("subject librarian", 3.0), ("liaison", 2.5), ("librarian for", 2.5),
        ("who is the librarian", 3.0), ("contact a librarian", 2.0),
        ("subject specialist", 2.0),
    ],
    "service_howto": [
        ("how do i print", 3.0), ("printing", 1.5), ("scan", 1.5),
        ("scanner", 2.0), ("wifi", 2.0), ("wi-fi", 2.0), ("password",  0.0),  # password handled by reject
        ("how do i", 0.5),
    ],
    "policy_question": [
        ("loan period", 3.0), ("how long can i", 2.0), ("renew", 1.5),
        ("food in the library", 2.0), ("can i bring", 1.0),
        ("policy", 1.0), ("rules", 1.0), ("late fee", 2.0),
    ],
    "adobe_access": [
        ("adobe", 3.0), ("photoshop", 3.0), ("illustrator", 3.0),
        ("indesign", 3.0), ("premiere", 2.5), ("acrobat", 2.5),
        ("creative cloud", 3.0), ("after effects", 2.5),
    ],
    "ill_request": [
        ("interlibrary loan", 3.0), ("ill ", 2.5), (" ill?", 2.5),
        ("ohiolink", 2.5), ("borrow from another", 2.5),
        ("from another library", 2.5), ("from another university", 2.5),
        ("get a book from", 1.5), ("request a book", 1.5),
        ("article delivery", 2.5),
    ],
    "makerspace_info": [
        ("makerspace", 3.0), ("maker space", 3.0), ("3d printer", 3.0),
        ("3d printing", 3.0), ("vinyl cutter", 3.0),
        ("sewing machine", 2.5), ("laser cutter", 3.0),
    ],
    "special_collections": [
        ("special collections", 3.0), ("archives", 2.0), ("archivist", 2.5),
        ("rare book", 2.5), ("manuscript", 2.0), ("finding aid", 3.0),
        ("havighurst", 3.0), ("scua", 2.0),
    ],
    "digital_collections": [
        ("digital collection", 3.0), ("digital exhibit", 3.0),
        ("online exhibit", 2.5), ("digital archive", 2.5),
    ],
    "newspapers": [
        ("new york times", 3.0), ("nyt", 2.0), ("wall street journal", 3.0),
        ("wsj", 2.0), ("newspaper", 2.0), ("cincinnati enquirer", 3.0),
        ("washington post", 2.5), ("financial times", 2.5),
    ],
    "cross_campus_comparison": [
        ("all campuses", 3.0), ("every campus", 3.0),
        ("all libraries", 2.5), ("every miami library", 3.0),
        ("hamilton and middletown", 2.0), ("oxford and hamilton", 2.0),
    ],
    "human_handoff": [
        ("talk to a person", 3.0), ("talk to a human", 3.0),
        ("talk to someone", 2.5), ("speak to a librarian", 2.5),
        ("real person", 2.5),
    ],
    # out_of_scope is never auto-suggested -- librarian decides.
}


def _strip_pii(s: str) -> str:
    """Mask emails, phones, IDs in the utterance text. Used after the
    drop check -- if PII is present we drop the row, but if a row
    SLIPS THROUGH (e.g. partial email), we mask before writing."""
    s = _EMAIL_RE.sub("[EMAIL]", s)
    s = _PHONE_RE.sub("[PHONE]", s)
    s = _BRONCO_ID_RE.sub("[ID]", s)
    return s


def _has_pii(s: str) -> bool:
    if _EMAIL_RE.search(s):
        return True
    if _PHONE_RE.search(s):
        return True
    if _BRONCO_ID_RE.search(s):
        return True
    if _ACCOUNT_BOILERPLATE_RE.search(s):
        return True
    return False


def _is_hard_reject(s: str) -> bool:
    lower = s.lower()
    return any(p in lower for p in _HARD_REJECT_PHRASES)


def _is_greeting(s: str) -> bool:
    return bool(_GREETING_RE.match(s.strip()))


def _normalize(s: str) -> str:
    """Trim, collapse whitespace, normalize newlines to spaces."""
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _suggest_intent(utterance: str) -> Optional[str]:
    """Pick the highest-scoring intent by keyword match, or None."""
    lower = utterance.lower()
    scores: dict[str, float] = defaultdict(float)
    for intent, words in _KEYWORDS.items():
        for kw, weight in words:
            if kw in lower:
                scores[intent] += weight
    if not scores:
        return None
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] < 1.0:
        return None
    return best[0]


def clean(input_path: Path, output_path: Path, report_path: Path) -> None:
    """Run the cleaning pipeline and write the labeling-ready CSV."""
    raw_count = 0
    drop_short = 0
    drop_long = 0
    drop_pii = 0
    drop_hard_reject = 0
    drop_greeting = 0
    drop_dup = 0

    seen: set[str] = set()
    rows_out: list[dict] = []

    with open(input_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_count += 1
            iq = (row.get("Initial Question") or "").strip()
            if not iq:
                continue

            iq = _normalize(iq)

            # Hard length bounds
            if len(iq) < MIN_LEN:
                drop_short += 1
                continue
            if len(iq) > MAX_LEN:
                drop_long += 1
                continue

            # Greeting filter
            if _is_greeting(iq):
                drop_greeting += 1
                continue

            # PII filter (whole-row drop)
            if _has_pii(iq):
                drop_pii += 1
                continue

            # Hard-reject phrases (account help etc.)
            if _is_hard_reject(iq):
                drop_hard_reject += 1
                continue

            # Belt-and-suspenders mask in case anything slipped through
            iq_clean = _strip_pii(iq)

            # Dedup by lowercased + alphanum-only signature so
            # punctuation / case differences don't fragment the dedup.
            sig = re.sub(r"[^a-z0-9 ]", "", iq_clean.lower())
            if sig in seen:
                drop_dup += 1
                continue
            seen.add(sig)

            suggested = _suggest_intent(iq_clean) or ""
            rows_out.append({
                "utterance": iq_clean,
                "suggested_intent": suggested,
                "intent": "",
            })

    # Write the labeling CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["utterance", "suggested_intent", "intent"])
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    # Coverage report
    by_intent = Counter(r["suggested_intent"] or "(unknown)" for r in rows_out)
    lines = [
        f"# LibChat exemplar cleaning report",
        "",
        f"- Input file:  `{input_path.name}`",
        f"- Raw rows:    **{raw_count}**",
        f"- Kept after cleaning: **{len(rows_out)}**",
        "",
        "## Drops",
        f"- too short (<{MIN_LEN} chars): {drop_short}",
        f"- too long (>{MAX_LEN} chars):  {drop_long}",
        f"- greetings:                    {drop_greeting}",
        f"- contained PII (drop whole):   {drop_pii}",
        f"- account-help hard reject:     {drop_hard_reject}",
        f"- duplicate of an earlier row:  {drop_dup}",
        "",
        "## Suggested-intent distribution (heuristic, librarian overrides)",
        "",
        "| Suggested intent | Count |",
        "|---|---|",
    ]
    for intent, count in by_intent.most_common():
        lines.append(f"| `{intent}` | {count} |")
    lines.extend([
        "",
        "## Next step",
        "",
        f"1. Open `{output_path.name}` in a spreadsheet.",
        "2. For each row, fill in the `intent` column. Accept the "
        "suggestion = copy from `suggested_intent`. Override if wrong.",
        "3. Use these labels (anything else = typo, will fail validation):",
        "   `hours`, `room_booking`, `librarian_lookup`, `service_howto`,",
        "   `policy_question`, `adobe_access`, `ill_request`,",
        "   `makerspace_info`, `special_collections`, `digital_collections`,",
        "   `newspapers`, `cross_campus_comparison`, `human_handoff`,",
        "   `out_of_scope`",
        "4. Aim for ~50 per intent (more is fine). Rows you can't classify",
        "   confidently can be dropped (delete the row) -- partial labeling",
        "   is FINE; we'd rather have 600 confident labels than 2300 noisy ones.",
        "5. Save and send back; a follow-up script will pack the labeled",
        "   CSV into `ai-core/src/router/exemplars/exemplars.jsonl`.",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # Stdout summary
    print(f"Read {raw_count} raw rows.")
    print(f"Wrote {len(rows_out)} cleaned rows to {output_path}")
    print(f"Coverage report: {report_path}")
    print()
    print("Drops:")
    print(f"  short:        {drop_short}")
    print(f"  long:         {drop_long}")
    print(f"  greetings:    {drop_greeting}")
    print(f"  PII:          {drop_pii}")
    print(f"  hard-reject:  {drop_hard_reject}")
    print(f"  duplicates:   {drop_dup}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ai-core/src/router/exemplars/exemplars_for_labeling.csv"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("ai-core/src/router/exemplars/labeling_coverage_report.md"),
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    clean(args.input, args.output, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
