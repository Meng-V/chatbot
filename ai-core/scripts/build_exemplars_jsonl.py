"""
Pack the librarian-labeled CSV into the JSONL the kNN classifier loads.

Input:  ai-core/src/router/exemplars/exemplars_for_labeling.csv
        (columns: utterance, suggested_intent, intent)
Output: ai-core/src/router/exemplars/exemplars.jsonl
        (one JSON object per line: {intent, utterance, source})

Validation rules (this script REFUSES to write if any fire):
  1. `intent` must be one of the 14 documented INTENTS in
     src/router/intent_knn.INTENTS. Typo => fail loud (no silent
     mislabels in the training data).
  2. utterance must be non-empty and <= 250 chars (matches cleaner).
  3. Each intent should have at least N exemplars (default 20). If any
     intent is below the floor, write the file but exit non-zero so
     CI / cron catches it.
  4. Duplicate utterances within an intent => warning (not fatal).

Run:
    python scripts/build_exemplars_jsonl.py \\
        --input ai-core/src/router/exemplars/exemplars_for_labeling.csv \\
        --output ai-core/src/router/exemplars/exemplars.jsonl

See plan: Layer 3 -> "Intent kNN classifier".
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_knn import INTENTS  # noqa: E402


MIN_PER_INTENT_FLOOR = 20


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("ai-core/src/router/exemplars/exemplars_for_labeling.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ai-core/src/router/exemplars/exemplars.jsonl"),
    )
    parser.add_argument(
        "--floor",
        type=int,
        default=MIN_PER_INTENT_FLOOR,
        help=f"Minimum exemplars per intent (default {MIN_PER_INTENT_FLOOR}).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    valid_intents = set(INTENTS)
    rows: list[dict] = []
    by_intent: dict[str, list[str]] = defaultdict(list)
    bad_intent_rows: list[tuple[int, str, str]] = []

    with open(args.input, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):  # +1 header
            utterance = (row.get("utterance") or "").strip()
            intent = (row.get("intent") or "").strip()
            if not intent:
                continue  # unlabeled rows are skipped (librarian can iterate)
            if not utterance:
                continue
            if len(utterance) > 250:
                bad_intent_rows.append((line_no, intent, "utterance > 250 chars"))
                continue
            if intent not in valid_intents:
                bad_intent_rows.append((line_no, intent, f"unknown intent {intent!r}"))
                continue
            rows.append({
                "intent": intent,
                "utterance": utterance,
                "source": "libchat_2025",
            })
            by_intent[intent].append(utterance)

    if bad_intent_rows:
        print(f"REFUSING to write -- {len(bad_intent_rows)} invalid rows:", file=sys.stderr)
        for line_no, intent, reason in bad_intent_rows[:20]:
            print(f"  line {line_no}: {reason} (intent={intent!r})", file=sys.stderr)
        print(f"\nValid intents: {sorted(valid_intents)}", file=sys.stderr)
        return 3

    # Coverage check
    below_floor = []
    for intent in INTENTS:
        n = len(by_intent.get(intent, []))
        if n < args.floor:
            below_floor.append((intent, n))

    # Write JSONL
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} exemplars to {args.output}")
    print()
    print("Per-intent counts:")
    for intent in INTENTS:
        n = len(by_intent.get(intent, []))
        flag = " " if n >= args.floor else " ⚠"
        print(f" {flag} {intent:30s} {n:4d}")

    # Dup check (within intent)
    for intent, utters in by_intent.items():
        dups = [u for u, c in Counter(utters).items() if c > 1]
        if dups:
            print(f"\nWarning: {len(dups)} duplicate utterance(s) in {intent}:")
            for d in dups[:5]:
                print(f"  - {d!r}")

    if below_floor:
        print()
        print(f"Below floor of {args.floor} exemplars -- file written but exiting nonzero:", file=sys.stderr)
        for intent, n in below_floor:
            print(f"  {intent}: {n}", file=sys.stderr)
        return 1

    print()
    print(f"All {len(INTENTS)} intents at or above floor of {args.floor}. Ready to ship.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
