"""
Audit + correct labels in exemplars.jsonl.

Two modes:

  list     Print N samples per intent for eyeball review. Read-only.
  drop     Remove rows by utterance match (regex / substring). Useful
           for purging known false positives.
  relabel  Change the intent of rows matching a pattern to a new
           intent. Used when an intent's keyword space changed.

The librarian uses `list` to spot-check; the operator uses `drop` /
`relabel` to surgically clean up after spotting bad rows.

Usage:
    python -m scripts.label_qa list
    python -m scripts.label_qa list --intent newspapers --samples 20
    python -m scripts.label_qa drop --match "Foundations of Global Health"
    python -m scripts.label_qa drop --intent events_news --regex "exhibition from"
    python -m scripts.label_qa relabel \\
        --match "checkout not available at all" \\
        --to circulation_basic
    python -m scripts.label_qa stats

Flags:
  --intent <name>  Restrict to one intent (list / drop / relabel)
  --regex <pat>    Match by regex (case-insensitive)
  --match <str>    Match by exact substring (case-sensitive)
  --to <intent>    Target intent for `relabel`
  --samples N      Sample size per intent for `list` (default 5)
  --dry-run        Don't modify the JSONL; just show what would change

Always operates on the JSONL in place. Make a backup if you're worried.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow `python -m scripts.label_qa` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_knn import INTENTS  # noqa: E402


_DEFAULT_PATH = Path("ai-core/src/router/exemplars/exemplars.jsonl")


def _load(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            rows.append(json.loads(line))
    return rows


def _save(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _row_matches(
    row: dict,
    *,
    intent: str | None = None,
    regex: re.Pattern | None = None,
    substring: str | None = None,
) -> bool:
    if intent and row.get("intent") != intent:
        return False
    utt = row.get("utterance", "")
    if substring is not None and substring not in utt:
        return False
    if regex is not None and not regex.search(utt):
        return False
    return True


# --- list ----------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    rows = _load(args.input)
    by_intent: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if args.intent and row.get("intent") != args.intent:
            continue
        by_intent[row["intent"]].append(row["utterance"])
    if not by_intent:
        print(f"No rows matching --intent={args.intent!r}")
        return 0
    intents_sorted = sorted(by_intent) if args.intent else INTENTS
    for intent in intents_sorted:
        utts = by_intent.get(intent, [])
        if not utts:
            continue
        print(f"=== [{intent}] ({len(utts)}) ===")
        for utt in utts[: args.samples]:
            preview = utt if len(utt) <= 140 else utt[:137] + "..."
            print(f"  - {preview}")
        if len(utts) > args.samples:
            print(f"  ... and {len(utts) - args.samples} more")
        print()
    return 0


# --- stats ---------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> int:
    rows = _load(args.input)
    counts: Counter = Counter(r["intent"] for r in rows)
    print(f"Total: {len(rows)} exemplars across {len(counts)} intents")
    print()
    for intent in INTENTS:
        n = counts.get(intent, 0)
        flag = ""
        if n == 0:
            flag = " (zero coverage)"
        elif n < 5:
            flag = " (thin)"
        elif n < 20:
            flag = " (modest)"
        print(f"  {intent:<28s} {n:>4d}{flag}")
    return 0


# --- drop ----------------------------------------------------------------


def cmd_drop(args: argparse.Namespace) -> int:
    rows = _load(args.input)
    rx = re.compile(args.regex, re.IGNORECASE) if args.regex else None
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        if _row_matches(row, intent=args.intent, regex=rx, substring=args.match):
            dropped.append(row)
        else:
            kept.append(row)
    print(f"Would drop {len(dropped)} row(s):")
    for r in dropped[:20]:
        u = r["utterance"]
        u = u if len(u) <= 100 else u[:97] + "..."
        print(f"  [{r['intent']}] {u}")
    if len(dropped) > 20:
        print(f"  ... and {len(dropped) - 20} more")
    if args.dry_run:
        print("--dry-run: not writing.")
        return 0
    if not dropped:
        print("Nothing to drop.")
        return 0
    _save(args.input, kept)
    print(f"\nDropped. New total: {len(kept)} exemplars.")
    return 0


# --- relabel -------------------------------------------------------------


def cmd_relabel(args: argparse.Namespace) -> int:
    if not args.to:
        print("--to <intent> is required for relabel", file=sys.stderr)
        return 2
    if args.to not in INTENTS:
        print(
            f"--to={args.to!r} is not a valid intent. Valid: {sorted(INTENTS)}",
            file=sys.stderr,
        )
        return 2
    rows = _load(args.input)
    rx = re.compile(args.regex, re.IGNORECASE) if args.regex else None
    changed: list[tuple[str, str, str]] = []  # (utterance, old, new)
    for row in rows:
        if not _row_matches(
            row, intent=args.intent, regex=rx, substring=args.match,
        ):
            continue
        old = row.get("intent", "")
        if old == args.to:
            continue
        changed.append((row["utterance"], old, args.to))
        row["intent"] = args.to
    print(f"Would relabel {len(changed)} row(s) -> {args.to!r}:")
    for utt, old, new in changed[:20]:
        u = utt if len(utt) <= 100 else utt[:97] + "..."
        print(f"  [{old} -> {new}]  {u}")
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")
    if args.dry_run:
        print("--dry-run: not writing.")
        return 0
    if not changed:
        print("Nothing changed.")
        return 0
    _save(args.input, rows)
    print(f"\nRelabeled. Total: {len(rows)} exemplars.")
    return 0


# --- CLI wiring ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit + correct labels in exemplars.jsonl."
    )
    parser.add_argument(
        "--input", type=Path, default=_DEFAULT_PATH,
        help="Path to exemplars.jsonl (default: %(default)s).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Sample rows per intent.")
    p_list.add_argument("--intent", help="Restrict to one intent.")
    p_list.add_argument("--samples", type=int, default=5)
    p_list.set_defaults(func=cmd_list)

    p_stats = sub.add_parser("stats", help="Per-intent counts.")
    p_stats.set_defaults(func=cmd_stats)

    p_drop = sub.add_parser("drop", help="Remove rows matching a pattern.")
    p_drop.add_argument("--intent", help="Restrict to one intent.")
    p_drop.add_argument("--match", help="Substring to match (case-sensitive).")
    p_drop.add_argument("--regex", help="Regex (case-insensitive).")
    p_drop.add_argument("--dry-run", action="store_true")
    p_drop.set_defaults(func=cmd_drop)

    p_relabel = sub.add_parser("relabel", help="Change intent of matching rows.")
    p_relabel.add_argument("--intent", help="Restrict to one intent.")
    p_relabel.add_argument("--match", help="Substring (case-sensitive).")
    p_relabel.add_argument("--regex", help="Regex (case-insensitive).")
    p_relabel.add_argument("--to", required=True, help="Target intent.")
    p_relabel.add_argument("--dry-run", action="store_true")
    p_relabel.set_defaults(func=cmd_relabel)

    args = parser.parse_args(argv)
    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2
    return args.func(args)


__all__ = ["main", "cmd_list", "cmd_stats", "cmd_drop", "cmd_relabel"]


if __name__ == "__main__":
    sys.exit(main())
