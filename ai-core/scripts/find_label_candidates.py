"""
Hunt the unlabeled rows in exemplars_for_labeling.csv for candidates
matching one or more keywords. Used during Tier 2 of the librarian
labeling pass to find ~20 examples per thin intent without manually
filtering in Excel/Sheets.

Usage:
    python ai-core/scripts/find_label_candidates.py --keyword renew
    python ai-core/scripts/find_label_candidates.py --keyword "my fines" --keyword "what i owe"
    python ai-core/scripts/find_label_candidates.py --keyword renew --suggest renewal
    python ai-core/scripts/find_label_candidates.py --regex "library\\s*session"
    python ai-core/scripts/find_label_candidates.py --recipe-renewal
    python ai-core/scripts/find_label_candidates.py --recipe-account

By default scans only rows where the `intent` column is empty (i.e.
rows the librarian hasn't labeled yet). Pass --include-labeled to
scan everything (useful for spot-checking already-labeled rows).

Output is plain CSV (`utterance,suggested_intent`) so the librarian
can paste it into the spreadsheet alongside the existing labeling
file -- or copy-paste directly back into the labeling CSV after
filling in the `intent` column.

Recipes for the thin intents are baked in (one CLI flag each) so the
librarian doesn't have to invent good keyword sets per intent. See
the RECIPES dict near the top.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional


_DEFAULT_INPUT = Path(
    "ai-core/src/router/exemplars/exemplars_for_labeling.csv"
)


# --- Recipes for thin intents -------------------------------------------
#
# Each recipe is a (suggested_intent, list_of_keywords_or_regexes)
# pair. The keywords cast a wide net; the librarian filters the
# results to the ones that actually fit. Tuned from the audit of the
# 4-year LibChat data.
#
# Add a new recipe by appending to RECIPES; the CLI exposes it as
# `--recipe-<name>` automatically.

RECIPES: dict[str, tuple[str, list[str]]] = {
    "renewal": (
        "renewal",
        ["renew", "extend my", "extend the due", "renew my book"],
    ),
    "loan_policy": (
        "loan_policy",
        ["loan period", "how long can i", "late fee", "overdue fee",
         "how long can i keep", "fines and fees", "borrowing period",
         "due date", "due back"],
    ),
    "account": (
        "account",
        ["my account", "my fines", "my fees", "what i owe",
         "how much do i owe", "books i have checked out",
         "my checkouts", "my balance"],
    ),
    "course_reserves": (
        "course_reserves",
        ["course reserve", "class reserve", "professor put",
         "on reserve", "reserve for my class",
         "reserve for my course", "textbook on reserve"],
    ),
    "space_info": (
        "space_info",
        ["lockers", "quiet floor", "silent study", "quiet study",
         "graduate reading", "faculty reading", "study area",
         "writing center", "where can i study", "espresso", "cafe",
         "food in the library", "drinks in the library"],
    ),
    "events_news": (
        "events_news",
        ["upcoming event", "library event", "exhibit", "library news",
         "lecture", "talk by", "workshop on"],
    ),
    "instruction_request": (
        "instruction_request",
        ["library session for", "library instruction",
         "teach my class", "teach my students", "schedule a class",
         "instruction session", "information literacy",
         "research workshop for"],
    ),
    "staff_lookup": (
        "staff_lookup",
        ["who is the dean", "dean of the library", "library director",
         "library administrator", "head of", "manager of",
         "supervisor of", "staff directory"],
    ),
    "subject_librarian": (
        "subject_librarian",
        ["subject librarian", "liaison", "librarian for my",
         "librarian for the", "subject specialist",
         "history librarian", "biology librarian", "psychology librarian",
         "nursing librarian", "business librarian", "english librarian",
         "music librarian", "engineering librarian"],
    ),
    "software_access": (
        "software_access",
        ["matlab", "spss", "nvivo", "stata", "tableau",
         "software on the computer", "what software",
         "software available", "is r installed", "install software"],
    ),
    "data_services": (
        "data_services",
        ["data analysis", "data viz", "data visualization", "gis",
         "statistics help", "stata help", "data services",
         "data management", "research data"],
    ),
    "research_consultation": (
        "research_consultation",
        ["research appointment", "research consultation",
         "meet with a librarian", "schedule a research",
         "appointment with", "appointment to meet",
         "schedule an appointment", "scholarly commons", "copyright",
         "open access publishing"],
    ),
    "digital_collections": (
        "digital_collections",
        ["digital collection", "digital exhibit", "online exhibit",
         "digital archive", "digitized"],
    ),
    "special_collections": (
        "special_collections",
        ["special collection", "university archives", "archivist",
         "rare book", "manuscript", "finding aid", "havighurst",
         "scua"],
    ),
    "out_of_scope": (
        "out_of_scope",
        # Random sample by definition; recipe finds questions that
        # CLEARLY aren't library-related. Librarian still has to
        # confirm; lots of edge cases.
        ["how do you", "what is the meaning", "homework help",
         "is this true", "can you help me with my essay",
         "write a paper", "summarize this", "translate this",
         "weather", "score of the", "definition of", "tell me about",
         "what's the recipe", "does the library know"],
    ),
    "cross_campus_comparison": (
        "cross_campus_comparison",
        ["all campuses", "every campus", "all libraries",
         "every miami library", "at all three", "compare the",
         "hamilton and middletown", "oxford and hamilton"],
    ),
}


# --- Core search ---------------------------------------------------------


def _row_unlabeled(row: dict) -> bool:
    return not (row.get("intent") or "").strip()


def search(
    csv_path: Path,
    *,
    keywords: list[str],
    regex: Optional[str],
    suggest: Optional[str],
    include_labeled: bool,
    limit: Optional[int],
) -> list[dict]:
    pattern = re.compile(regex, re.IGNORECASE) if regex else None
    keywords_lc = [k.lower() for k in keywords]

    results: list[dict] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not include_labeled and not _row_unlabeled(row):
                continue
            utt = row.get("utterance", "")
            utt_lc = utt.lower()
            hit = False
            if pattern and pattern.search(utt):
                hit = True
            elif keywords_lc and any(k in utt_lc for k in keywords_lc):
                hit = True
            if not hit:
                continue
            results.append({
                "utterance": utt,
                "suggested_intent": (
                    suggest
                    or row.get("suggested_intent", "")
                    or "(unknown)"
                ),
                "current_label": row.get("intent", ""),
                "source": row.get("source", ""),
            })
            if limit and len(results) >= limit:
                break
    return results


# --- CLI -----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--input", type=Path, default=_DEFAULT_INPUT,
        help="Path to exemplars_for_labeling.csv.",
    )
    parser.add_argument(
        "--keyword", action="append", default=[],
        help="Substring (case-insensitive) to match. Repeatable.",
    )
    parser.add_argument(
        "--regex", default=None,
        help="Regex (case-insensitive) to match. Beats --keyword.",
    )
    parser.add_argument(
        "--suggest", default=None,
        help="Override suggested_intent in output (e.g. --suggest renewal).",
    )
    parser.add_argument(
        "--include-labeled", action="store_true",
        help="Also scan rows that already have a librarian label.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N matches.",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Output CSV (utterance,suggested_intent). Default is "
        "human-readable [intent] utterance.",
    )
    parser.add_argument(
        "--list-recipes", action="store_true",
        help="Print every available recipe and the keywords each uses, "
        "then exit.",
    )

    # Auto-expose every recipe as `--recipe-<name>`.
    for recipe_name in RECIPES:
        parser.add_argument(
            f"--recipe-{recipe_name.replace('_', '-')}",
            dest=f"recipe_{recipe_name}",
            action="store_true",
            help=f"Use baked-in recipe for `{recipe_name}` "
                 f"({len(RECIPES[recipe_name][1])} keywords).",
        )

    args = parser.parse_args()

    if args.list_recipes:
        print("Available recipes:")
        print()
        for name in sorted(RECIPES):
            suggested, kws = RECIPES[name]
            print(f"  --recipe-{name.replace('_', '-')}")
            print(f"      suggests intent: {suggested}")
            print(f"      keywords:        {', '.join(kws)}")
            print()
        return 0

    # Resolve recipe -> keywords + suggest, if any.
    recipe_used: Optional[str] = None
    for recipe_name in RECIPES:
        if getattr(args, f"recipe_{recipe_name}", False):
            recipe_used = recipe_name
            suggested, kws = RECIPES[recipe_name]
            args.keyword = list(args.keyword) + kws
            if not args.suggest:
                args.suggest = suggested
            break  # one recipe at a time

    if not args.keyword and not args.regex:
        parser.error(
            "no search criteria. Pass --keyword, --regex, or one of "
            "the --recipe-* flags. Available recipes: "
            + ", ".join(sorted(RECIPES))
        )

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    results = search(
        args.input,
        keywords=args.keyword,
        regex=args.regex,
        suggest=args.suggest,
        include_labeled=args.include_labeled,
        limit=args.limit,
    )

    if recipe_used:
        print(
            f"# Recipe: {recipe_used} "
            f"({len(RECIPES[recipe_used][1])} keywords) -- "
            f"{len(results)} candidate(s)",
            file=sys.stderr,
        )
    else:
        print(f"# {len(results)} candidate(s) found", file=sys.stderr)

    if not results:
        return 0

    if args.csv:
        w = csv.DictWriter(
            sys.stdout, fieldnames=["utterance", "suggested_intent"]
        )
        w.writeheader()
        for r in results:
            w.writerow({
                "utterance": r["utterance"],
                "suggested_intent": r["suggested_intent"],
            })
    else:
        for r in results:
            tag = r["suggested_intent"]
            print(f"  [{tag:24s}]  {r['utterance']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
