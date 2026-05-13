"""
Pack the librarian-labeled v38 CSV into the JSONL the kNN classifier reads.

The librarian's labeling pass produced labeled_v38.csv with columns:
  utterance, tran_raw_2025, final_intent, suggested_intent_status,
  intent_confidence, needs_review, intent_reason

(Schema differs from the older build_exemplars_jsonl.py packer, which
read a simpler `utterance,suggested_intent,intent,source` shape.)

This packer:
  1. Validates final_intent against INTENTS (38-set).
  2. Filters by confidence + needs_review flags (default: keep high
     and medium; drop low + needs_review=TRUE -- those are the
     librarian's "second pass needed" rows).
  3. Writes exemplars.jsonl with the same {intent, utterance, source}
     shape the classifier loader expects.
  4. Reports per-intent counts + below-floor warnings.

Usage:
    python -m scripts.pack_labeled_v38                     # default filter
    python -m scripts.pack_labeled_v38 --include-low       # take everything
    python -m scripts.pack_labeled_v38 --include-flagged   # take needs_review=TRUE
    python -m scripts.pack_labeled_v38 --floor 20          # floor for warning

See plan: Layer 3 -> "Intent kNN classifier".
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_knn import INTENTS  # noqa: E402


_DEFAULT_INPUT = Path("ai-core/src/router/exemplars/labeled_v38.csv")
_DEFAULT_OUTPUT = Path("ai-core/src/router/exemplars/exemplars.jsonl")
_DEFAULT_FLOOR = 5


def _normalize_header(row: dict) -> dict:
    """Some CSVs have a UTF-8 BOM on the first column header."""
    out = {}
    for k, v in row.items():
        out[k.lstrip("﻿")] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--include-low", action="store_true",
        help="Include intent_confidence=low rows (default: drop).",
    )
    parser.add_argument(
        "--include-flagged", action="store_true",
        help="Include needs_review=TRUE rows (default: drop).",
    )
    parser.add_argument(
        "--floor", type=int, default=_DEFAULT_FLOOR,
        help=f"Warn if any intent is below N exemplars (default {_DEFAULT_FLOOR}).",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    valid_intents = set(INTENTS)
    kept: list[dict] = []
    dropped_low_conf = 0
    dropped_flagged = 0
    dropped_invalid_intent = 0
    dropped_invalid_status = 0
    dropped_empty = 0
    by_intent: dict[str, list[dict]] = {}

    with open(args.input, encoding="utf-8-sig") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            row = _normalize_header(row)
            utterance = (row.get("utterance") or "").strip()
            intent = (row.get("final_intent") or "").strip()
            confidence = (row.get("intent_confidence") or "").strip()
            needs_review = (row.get("needs_review") or "").strip().upper()
            status = (row.get("suggested_intent_status") or "").strip()
            reason = (row.get("intent_reason") or "").strip()
            source = (row.get("tran_raw_2025") or "labeled_v38").strip()

            if not utterance or not intent:
                dropped_empty += 1
                continue
            if intent not in valid_intents:
                dropped_invalid_intent += 1
                continue
            if status == "invalid":
                dropped_invalid_status += 1
                continue
            if confidence == "low" and not args.include_low:
                dropped_low_conf += 1
                continue
            if needs_review == "TRUE" and not args.include_flagged:
                dropped_flagged += 1
                continue

            kept.append({
                "intent": intent,
                "utterance": utterance,
                "source": source or "labeled_v38",
            })
            by_intent.setdefault(intent, []).append({
                "confidence": confidence,
                "reason": reason,
            })

    # Write JSONL
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(kept)} exemplars to {args.output}")
    print()
    print(f"Filter stats:")
    print(f"  dropped (empty utterance/intent): {dropped_empty}")
    print(f"  dropped (intent not in INTENTS):  {dropped_invalid_intent}")
    print(f"  dropped (status=invalid):         {dropped_invalid_status}")
    print(
        f"  dropped (low confidence):         {dropped_low_conf}"
        f"  [pass --include-low to keep]"
    )
    print(
        f"  dropped (needs_review=TRUE):      {dropped_flagged}"
        f"  [pass --include-flagged to keep]"
    )
    print()
    print(f"Per-intent counts:")

    below_floor = []
    for intent in INTENTS:
        n = len(by_intent.get(intent, []))
        if n == 0:
            tag = " (zero)"
            below_floor.append((intent, n))
        elif n < args.floor:
            tag = f" (below floor {args.floor})"
            below_floor.append((intent, n))
        else:
            tag = ""
        print(f"  {intent:<28s} {n:>5d}{tag}")

    if below_floor:
        print()
        print(f"Below floor of {args.floor}:")
        for intent, n in below_floor:
            print(f"  {intent}: {n}")
        return 1
    print()
    print(f"All {len(INTENTS)} intents at or above floor of {args.floor}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
