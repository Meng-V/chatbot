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
# Grounded in lib.miamioh.edu/use/ and /research/ -- 28 intents that
# match the real service taxonomy. The previous coarse 14-intent set
# wrongly bucketed "will I get a confirmation when I place a hold" as
# `ill_request`, because the heuristic conflated "request a book" with
# "interlibrary loan".
#
# Distinctions that matter and how the heuristic enforces them:
#
#   - `circulation_basic` covers REQUESTS / HOLDS / CHECKOUT
#     CONFIRMATIONS for items Miami OWNS. Phrasings: "place a hold",
#     "request a book", "did my request go through", "confirmation",
#     "pick up at the library".
#   - `interlibrary_loan` is ONLY for items Miami DOESN'T own --
#     OhioLINK, ILLiad, WorldCat, "another library", "another
#     university". Generic "request a book" alone is NOT enough --
#     we require an explicit "another"/"OhioLINK"/"WorldCat" signal.
#   - `course_reserves` covers "professor put on reserve", "course
#     reserves" -- distinct from circulation because reserves have
#     short 2h/3h loan periods.
#   - `find_resource` is "do you have X book/article/journal" --
#     catalog search, distinct from circulation actions.
#   - `loan_policy` is the META question (how long, late fees,
#     renewal policy), distinct from `account` (MY checkouts) and
#     `renewal` (renew THIS book).
#
# Each tuple is (substring, weight). Negative weights work as
# false-positive defenses (e.g., "miami" near "hold" boosts
# circulation_basic but suppresses interlibrary_loan).

_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    # --- Lookup ---
    "hours": [
        ("hours", 2.0), ("when does", 1.8), ("when is the library open", 3.0),
        ("what time", 1.8), ("opening time", 2.5), ("closing time", 2.5),
        ("close tonight", 2.0), ("open today", 1.5), ("open tomorrow", 1.5),
        ("open sunday", 1.5), ("open weekend", 1.5),
        ("library open", 2.0), ("still open", 2.0),
    ],
    "location_directions": [
        ("where is", 1.5), ("how do i get to", 2.5), ("address of", 2.0),
        ("parking", 2.0), ("directions to", 2.5), ("how to find", 1.5),
        ("which floor", 1.5), ("what floor", 1.5),
    ],
    "staff_lookup": [
        ("who is the dean", 3.0), ("dean of the library", 3.0),
        ("who works at", 1.5), ("staff directory", 3.0),
        ("contact a librarian", 2.0), ("email of the", 1.5),
        ("phone number for", 1.5),
    ],
    "subject_librarian": [
        ("subject librarian", 3.0), ("liaison", 2.5),
        ("librarian for", 2.5), ("subject specialist", 2.5),
        ("who is the librarian for", 3.0), ("history librarian", 3.0),
        ("biology librarian", 3.0), ("psychology librarian", 3.0),
        ("nursing librarian", 3.0), ("business librarian", 3.0),
    ],

    # --- Borrow / circulation ---
    # CRITICAL: this bucket catches the "did my hold work" / "will I
    # get a confirmation" questions that were wrongly going to ILL.
    "circulation_basic": [
        ("place a hold", 3.0), ("put a hold", 3.0), ("place hold", 2.5),
        ("request a book", 2.5), ("request a copy", 2.5),
        ("book request", 2.0), ("hold on a book", 3.0),
        ("hold on the book", 3.0), ("get a confirmation", 2.5),
        ("get confirmation", 2.5), ("did my request", 3.0),
        ("did the request go through", 3.0), ("hold went through", 3.0),
        ("notified when", 1.5), ("when my book", 1.5),
        ("when the book is ready", 3.0), ("when my hold", 3.0),
        ("ready for pickup", 2.5), ("ready to pick up", 2.5),
        ("pick up my", 1.5), ("pickup my", 1.5),
        ("checkout a book", 2.0), ("check out a book", 2.0),
        ("how do i borrow", 2.0), ("how to borrow", 2.0),
        ("how does borrowing", 2.5),
        # Borrow fulfillment options under /use/borrow/
        ("home delivery", 3.0), ("curbside pickup", 3.0),
        ("department delivery", 3.0), ("dorm delivery", 3.0),
        ("storage request", 2.5), ("from storage", 2.5),
        ("sw depository", 2.5), ("southwest depository", 2.5),
    ],
    "renewal": [
        ("renew my book", 3.0), ("renew my checkout", 3.0),
        ("can i renew", 2.5), ("how do i renew", 2.5),
        ("extend the due date", 3.0), ("extend my checkout", 3.0),
        ("renewal", 1.5),  # note: lower weight to avoid loan_policy collision
    ],
    "loan_policy": [
        ("loan period", 3.0), ("how long can i keep", 3.0),
        ("how long can i borrow", 3.0), ("how long can i check out", 3.0),
        ("late fee", 3.0), ("overdue fee", 3.0), ("fines and fees", 2.5),
        ("checkout period", 2.5), ("borrowing period", 2.5),
        ("due date policy", 3.0),
    ],
    "account": [
        ("my account", 2.5), ("my fines", 3.0), ("my fees", 2.5),
        ("how much do i owe", 3.0), ("what i owe", 2.5),
        ("books i have checked out", 3.0), ("my checkouts", 3.0),
        ("my borrowed books", 3.0), ("library balance", 2.5),
        ("see my account", 2.5),
    ],
    # REAL ILL only. Generic "request a book" alone is insufficient --
    # we require an explicit "other library" / OhioLINK / WorldCat /
    # "you don't have" signal.
    "interlibrary_loan": [
        ("interlibrary loan", 3.0), ("inter-library loan", 3.0),
        ("inter library loan", 3.0), ("ohiolink", 3.0),
        ("ohio link", 3.0),  # users often type with a space
        ("worldcat", 3.0), ("world cat", 3.0),  # same: with space
        ("illiad", 3.0),
        ("from another library", 3.0), ("from another university", 3.0),
        ("from a different library", 2.5), ("from another school", 2.5),
        ("don't have it", 1.5), ("you don't have", 1.5),
        ("not at miami", 2.0), ("miami doesn't have", 3.0),
        ("not in your collection", 2.5), ("miami doesn't own", 3.0),
        ("article delivery", 3.0), ("ill request", 3.0),
        ("ill book", 2.5), ("borrow from another", 3.0),
    ],
    "course_reserves": [
        ("course reserve", 3.0), ("class reserve", 2.5),
        ("on reserve for my class", 3.0), ("reserve for my course", 3.0),
        ("professor put on reserve", 3.0),
        ("textbook on reserve", 3.0), ("textbook for my class", 1.5),
        ("reserve textbook", 3.0),
    ],
    "find_resource": [
        ("do you have a book", 2.5), ("do you have the book", 2.5),
        ("do you have an article", 2.5), ("do you have access to",  2.5),
        ("looking for a book", 2.0), ("looking for an article", 2.0),
        ("can i find", 1.5), ("where can i find", 1.5),
        ("call number", 2.5), ("does the library have", 2.5),
        ("is this book in", 2.0), ("how do i find a book", 2.5),
    ],

    # --- Spaces ---
    "room_booking": [
        ("book a room", 3.0), ("reserve a room", 3.0),
        ("book a study room", 3.0), ("reserve a study room", 3.0),
        ("study room reservation", 3.0), ("room reservation", 2.5),
        ("group study room", 3.0), ("conference room reservation", 2.5),
        ("schedule a room", 2.5),
    ],
    "space_info": [
        ("quiet floor", 2.5), ("silent study", 2.5), ("quiet study", 2.5),
        ("group study area", 2.5), ("graduate reading room", 3.0),
        ("graduate study", 2.0), ("faculty reading room", 3.0),
        ("howe writing center", 3.0), ("writing center", 2.5),
        ("where can i study", 2.0),
    ],
    "makerspace_3d": [
        ("makerspace", 3.0), ("maker space", 3.0),
        ("3d printer", 3.0), ("3d printing", 3.0),
        ("vinyl cutter", 3.0), ("sewing machine", 2.5),
        ("laser cutter", 3.0), ("button maker", 2.5),
    ],

    # --- Technology ---
    "printing_wifi": [
        ("how do i print", 3.0), ("printing", 1.5),
        ("printer", 2.0), ("scan", 1.8), ("scanner", 2.5),
        ("photocopy", 2.5), ("copy a", 1.5), ("copier", 2.5),
        ("wifi", 2.5), ("wi-fi", 2.5),
        ("print from my laptop", 3.0), ("print from my phone", 3.0),
        ("color print", 2.5), ("color printing", 3.0),
    ],
    "tech_checkout": [
        ("checkout a laptop", 3.0), ("check out a laptop", 3.0),
        ("borrow a laptop", 3.0), ("loan a laptop", 2.5),
        ("chromebook", 3.0), ("borrow a charger", 3.0),
        ("checkout a charger", 3.0), ("borrow a calculator", 3.0),
        ("borrow a camera", 3.0), ("camera tripod", 2.5),
        ("ipad pro", 2.5), ("apple pencil", 2.5),
        ("equipment checkout", 3.0), ("rent a laptop", 2.5),
    ],
    "software_access": [
        ("software available", 2.5), ("what software", 2.0),
        ("matlab", 2.5), ("spss", 2.5), ("nvivo", 2.5),
        ("software on library computer", 3.0),
        ("software checkout", 3.0), ("install software", 2.0),
    ],
    "adobe_access": [
        ("adobe", 3.0), ("photoshop", 3.0), ("illustrator", 3.0),
        ("indesign", 3.0), ("premiere pro", 3.0), ("premiere", 1.5),
        ("acrobat pro", 3.0), ("creative cloud", 3.0),
        ("after effects", 2.5), ("lightroom", 2.5),
    ],

    # --- Research ---
    "databases": [
        ("database", 2.0), ("databases", 2.5), ("a-z list", 2.5),
        ("find articles", 2.5), ("find an article", 2.5),
        ("scholarly articles", 2.5), ("peer reviewed", 2.5),
        ("peer-reviewed", 2.5), ("jstor", 3.0), ("ebsco", 3.0),
        ("proquest", 3.0), ("e-resources", 2.5),
    ],
    "citation_help": [
        ("apa citation", 3.0), ("mla citation", 3.0), ("chicago citation", 3.0),
        ("apa format", 2.5), ("mla format", 2.5), ("citation generator", 3.0),
        ("how to cite", 3.0), ("citing sources", 2.5),
        ("zotero", 3.0), ("endnote", 3.0), ("mendeley", 3.0),
        ("bibliography", 2.0), ("works cited", 2.5),
    ],
    "research_consultation": [
        ("research appointment", 3.0), ("research consultation", 3.0),
        ("research help", 2.0), ("meet with a librarian", 3.0),
        ("meet with the librarian", 3.0),
        ("schedule a research", 3.0), ("copyright", 2.0),
        ("scholarly commons", 3.0), ("publish my", 1.5),
        ("research workshop", 3.0),
        ("appointment with", 1.5), ("appointment to meet", 2.5),
        ("schedule an appointment", 2.0),
    ],
    "data_services": [
        ("data services", 3.0), ("gis", 2.5), ("data analysis", 2.5),
        ("data visualization", 3.0), ("data viz", 3.0),
        ("statistical analysis", 2.5), ("python help", 2.0),
        ("r programming", 2.0), ("data management", 2.5),
    ],
    "digital_collections": [
        ("digital collection", 3.0), ("digital exhibit", 3.0),
        ("digital archive", 2.5), ("online exhibit", 2.5),
        ("digitized", 2.0),
    ],
    "special_collections": [
        ("special collections", 3.0), ("university archives", 3.0),
        ("archivist", 2.5), ("rare book", 2.5), ("manuscript", 2.0),
        ("finding aid", 3.0), ("havighurst", 3.0), ("scua", 2.5),
    ],
    "newspapers": [
        ("new york times", 3.0), ("nyt", 2.0),
        ("wall street journal", 3.0), ("wsj", 2.0),
        ("newspaper", 2.0), ("newspapers", 2.5),
        ("cincinnati enquirer", 3.0), ("washington post", 2.5),
        ("financial times", 2.5), ("the economist", 2.5),
    ],

    # --- Other ---
    "events_news": [
        ("upcoming event", 3.0), ("library event", 2.5),
        ("exhibit", 2.0), ("library news", 2.5),
        ("workshop", 1.5), ("attending the", 1.5),
    ],
    "instruction_request": [
        ("library instruction", 3.0), ("instruction session", 3.0),
        ("teach my class", 2.5), ("schedule a class visit", 3.0),
        ("library session for my course", 3.0),
        ("information literacy", 2.5),
    ],
    "cross_campus_comparison": [
        ("all campuses", 3.0), ("every campus", 3.0),
        ("all libraries", 2.5), ("every miami library", 3.0),
        ("at all three", 2.5),
        ("hamilton and middletown", 2.0), ("oxford and hamilton", 2.0),
    ],
    "human_handoff": [
        ("talk to a person", 3.0), ("talk to a human", 3.0),
        ("talk to someone", 2.5), ("speak to a librarian", 2.5),
        ("real person", 2.5), ("not a bot", 2.5),
        ("can i speak", 1.5),
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


# Phrases that DEFINITIVELY signal real ILL (Miami doesn't own the
# item). If none of these appear, ILL must NOT win even when an
# ambiguous "request a book" matched -- the older heuristic's biggest
# false-positive class.
_ILL_REQUIRED_SIGNALS = (
    "interlibrary loan", "inter-library loan", "inter library loan",
    "ohiolink", "worldcat", "illiad", "ill request", "ill book",
    "another library", "another university", "different library",
    "another school", "not at miami", "miami doesn't have",
    "miami does not have", "miami doesn't own", "you don't have",
    "borrow from another", "from another", "article delivery",
    "lending service",
)

# Phrases that strongly indicate the question is about a Miami-owned
# item (place a hold, request from our catalog) -- when these appear,
# we boost circulation_basic to defend against `request a book` being
# misread as ILL.
_CIRCULATION_STRONG_SIGNALS = (
    "place a hold", "put a hold", "place hold",
    "did my request", "did the request",
    "hold went through", "get a confirmation", "get confirmation",
    "when my hold", "when the book is ready", "ready for pickup",
    "ready to pick up",
)


def _suggest_intent(utterance: str) -> Optional[str]:
    """Pick the highest-scoring intent by keyword match, or None.

    Two disambiguation rules layered on the raw scoring:

    1. ILL false-positive guard: if `interlibrary_loan` would win but
       the message has NO definitive ILL signal (no "OhioLINK",
       "another library", etc.), suppress it. Generic "request a book"
       is a circulation question, not ILL.
    2. Circulation override: if any strong circulation signal fires
       ("place a hold", "did my request", "get a confirmation"),
       circulation_basic wins over interlibrary_loan regardless of
       raw scores. This catches the "will I get a confirmation when I
       place a hold" class explicitly.
    """
    lower = utterance.lower()
    scores: dict[str, float] = defaultdict(float)
    for intent, words in _KEYWORDS.items():
        for kw, weight in words:
            if kw in lower:
                scores[intent] += weight
    if not scores:
        return None

    # --- Rule 2: hard circulation override ---
    if any(sig in lower for sig in _CIRCULATION_STRONG_SIGNALS):
        # If circulation got any score at all, it wins. Documents the
        # explicit "did my hold work" path the librarian flagged.
        if scores.get("circulation_basic", 0) > 0:
            return "circulation_basic"

    # --- Rule 1: ILL needs a definitive signal ---
    if scores.get("interlibrary_loan", 0) > 0 and not any(
        sig in lower for sig in _ILL_REQUIRED_SIGNALS
    ):
        # Suppress ILL; let the next-best intent win (or fall through
        # to unknown if nothing else scored).
        del scores["interlibrary_loan"]
        if not scores:
            return None

    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] < 1.0:
        return None
    return best[0]


def clean(input_paths: list[Path], output_path: Path, report_path: Path) -> None:
    """Run the cleaning pipeline across one or more LibChat exports and
    write a unified labeling-ready CSV.

    Multiple inputs are concatenated and dedup is global -- a row that
    appears in 2024 AND 2025 is kept once. The `source` column tracks
    which file(s) it came from for traceability.
    """
    raw_count = 0
    drop_short = 0
    drop_long = 0
    drop_pii = 0
    drop_hard_reject = 0
    drop_greeting = 0
    drop_dup = 0

    seen: dict[str, dict] = {}  # signature -> row (so we can update sources)

    for input_path in input_paths:
        source_label = input_path.stem  # e.g. "tran_raw_2024"
        with open(input_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_count += 1
                iq = (row.get("Initial Question") or "").strip()
                if not iq:
                    continue

                iq = _normalize(iq)

                if len(iq) < MIN_LEN:
                    drop_short += 1
                    continue
                if len(iq) > MAX_LEN:
                    drop_long += 1
                    continue

                if _is_greeting(iq):
                    drop_greeting += 1
                    continue

                if _has_pii(iq):
                    drop_pii += 1
                    continue

                if _is_hard_reject(iq):
                    drop_hard_reject += 1
                    continue

                iq_clean = _strip_pii(iq)
                sig = re.sub(r"[^a-z0-9 ]", "", iq_clean.lower())

                if sig in seen:
                    drop_dup += 1
                    # Track that this utterance also appeared in this source.
                    existing_sources = seen[sig]["source"]
                    if source_label not in existing_sources.split(","):
                        seen[sig]["source"] = existing_sources + "," + source_label
                    continue

                suggested = _suggest_intent(iq_clean) or ""
                seen[sig] = {
                    "utterance": iq_clean,
                    "suggested_intent": suggested,
                    "intent": "",
                    "source": source_label,
                }

    rows_out = list(seen.values())

    # Write the labeling CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["utterance", "suggested_intent", "intent", "source"],
        )
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    # Coverage report
    by_intent = Counter(r["suggested_intent"] or "(unknown)" for r in rows_out)
    lines = [
        f"# LibChat exemplar cleaning report",
        "",
        f"- Input files: {', '.join(f'`{p.name}`' for p in input_paths)}",
        f"- Raw rows (total across inputs): **{raw_count}**",
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
        "3. Valid labels (28 intents, anything else fails validation):",
        "",
        "   **Lookup:**",
        "   `hours`, `location_directions`, `staff_lookup`, `subject_librarian`",
        "",
        "   **Borrow / circulation:**",
        "   `circulation_basic` (Miami-owned holds/requests/confirmations),",
        "   `renewal`, `loan_policy`, `account` (my checkouts/fines),",
        "   `interlibrary_loan` (OhioLINK / WorldCat / another library ONLY),",
        "   `course_reserves`, `find_resource` (\"do you have X\" -> catalog)",
        "",
        "   **Spaces:** `room_booking`, `space_info`, `makerspace_3d`",
        "",
        "   **Technology:** `printing_wifi`, `tech_checkout`,",
        "   `software_access`, `adobe_access`",
        "",
        "   **Research:** `databases`, `citation_help`,",
        "   `research_consultation`, `data_services`,",
        "   `digital_collections`, `special_collections`, `newspapers`",
        "",
        "   **Other:** `events_news`, `instruction_request`,",
        "   `cross_campus_comparison`, `human_handoff`, `out_of_scope`",
        "",
        "4. Aim for ~30-50 per intent (more is fine). Rows you can't classify",
        "   confidently can be dropped (delete the row) -- partial labeling",
        "   is FINE; 600 confident labels beats 2300 noisy ones.",
        "5. **Watch for these common heuristic mistakes:**",
        "   - `interlibrary_loan` should NOT match \"place a hold\" or",
        "     \"will I get a confirmation\" -- those are `circulation_basic`.",
        "     ILL is ONLY for items Miami doesn't own (OhioLINK / WorldCat).",
        "   - `databases` boosts on the word \"database\" but the question",
        "     might really be `find_resource` (\"do you have...\") or",
        "     `research_consultation` (\"help me search\").",
        "   - `find_resource` and `databases` overlap a lot; pick the more",
        "     specific (looking for ONE book = `find_resource`, looking for",
        "     articles broadly = `databases`).",
        "6. Save and send back; `build_exemplars_jsonl.py` packs the",
        "   labeled CSV into `ai-core/src/router/exemplars/exemplars.jsonl`.",
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
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        required=True,
        help="One or more LibChat CSV exports (multi-year inputs are merged + globally deduped).",
    )
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

    missing = [p for p in args.input if not p.exists()]
    if missing:
        for p in missing:
            print(f"input not found: {p}", file=sys.stderr)
        return 2

    clean(args.input, args.output, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
