"""
Analyze a streaming JSONL written by `src.eval.run_eval --results-out PATH`.

Why a separate tool: run_eval prints summary numbers but the file has
RICH per-case data (clf_candidates, refusal triggers, cached tokens,
the full bot_answer) that's easier to slice with one helper than by
re-running the eval. Also: run_eval streams JSONL, so this works on a
partially-complete file (useful while the full run is still going).

Usage:
    # Default summary: aggregate + per-category PASS/FAIL table
    .venv/bin/python -m scripts.analyze_eval_results \\
        eval_results/full_eval_20260520.jsonl

    # Per-actual-intent breakdown
    .venv/bin/python -m scripts.analyze_eval_results PATH --by intent

    # List failures with judge verdict + reason
    .venv/bin/python -m scripts.analyze_eval_results PATH --fails

    # Drill into one case (full bot_answer, classifier candidates, etc.)
    .venv/bin/python -m scripts.analyze_eval_results PATH --id fs_makerspace_3d

    # Slowest 20 cases (where latency lives)
    .venv/bin/python -m scripts.analyze_eval_results PATH --slowest 20

Pass/fail mapping (matches the eval's own classification):
    PASS    = correct | refused_correctly
    PARTIAL = partial            (judged defensible but imperfect)
    FAIL    = wrong | refused_incorrectly | answered_should_have_refused
    SKIP    = no judge verdict (case didn't run far enough to be judged)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional


PASS_VERDICTS = {"correct", "refused_correctly"}
PARTIAL_VERDICTS = {"partial"}
FAIL_VERDICTS = {"wrong", "refused_incorrectly", "answered_should_have_refused"}


def _load(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # streaming write -- last line may be partial mid-run
                continue
    return rows


def _bucket(verdict: Optional[str]) -> str:
    if verdict is None or verdict == "":
        return "SKIP"
    if verdict in PASS_VERDICTS:
        return "PASS"
    if verdict in PARTIAL_VERDICTS:
        return "PARTIAL"
    if verdict in FAIL_VERDICTS:
        return "FAIL"
    return "OTHER"


def _summary(rows: list[dict]) -> None:
    n = len(rows)
    if n == 0:
        print("(no rows yet)")
        return

    buckets = Counter(_bucket(r.get("judge_verdict")) for r in rows)
    scope_ok = sum(1 for r in rows if r.get("scope_match"))
    intent_ok = sum(1 for r in rows if r.get("intent_match"))
    path_ok = sum(1 for r in rows if r.get("path_match"))
    cited = sum(1 for r in rows if (r.get("bot_citations_count") or 0) > 0)
    refusals = sum(1 for r in rows if r.get("bot_was_refusal"))

    total_in = sum(r.get("input_tokens", 0) or 0 for r in rows)
    total_cached = sum(r.get("cached_input_tokens", 0) or 0 for r in rows)
    total_out = sum(r.get("output_tokens", 0) or 0 for r in rows)
    cache_rate = (total_cached / total_in * 100) if total_in else 0

    latencies = sorted(r.get("latency_ms", 0) or 0 for r in rows)
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    print(f"Cases: {n}")
    print()
    print("Quality (judge verdict bucket):")
    for b in ("PASS", "PARTIAL", "FAIL", "SKIP", "OTHER"):
        c = buckets.get(b, 0)
        pct = c / n * 100 if n else 0
        print(f"  {b:8s}  {c:4d}  ({pct:5.1f}%)")
    print()
    print("Pipeline stages (per-row matches):")
    print(f"  scope_match    {scope_ok}/{n}  ({scope_ok/n*100:.1f}%)")
    print(f"  intent_match   {intent_ok}/{n}  ({intent_ok/n*100:.1f}%)")
    print(f"  path_match     {path_ok}/{n}  ({path_ok/n*100:.1f}%)")
    print()
    print("Refusals + citations:")
    print(f"  refusals       {refusals}/{n}")
    print(f"  cited answers  {cited}/{n - refusals}  (of non-refusal answers)")
    print()
    print("Tokens + cache:")
    print(f"  input  total   {total_in:,}")
    print(f"  cached total   {total_cached:,}  ({cache_rate:.1f}% cache hit)")
    print(f"  output total   {total_out:,}")
    print()
    print(f"Latency (ms): p50={p50}  p95={p95}")


def _by_dimension(rows: list[dict], dim: str) -> None:
    """Per-category (or per-actual-intent) PASS/PARTIAL/FAIL/SKIP table."""
    key = "category" if dim == "category" else "actual_intent"
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r.get(key) or "(none)"].append(r)

    label_w = max(len(k) for k in groups) if groups else 12
    label_w = max(label_w, len(key))
    print(f"{key:<{label_w}}   N    PASS  PART  FAIL  SKIP   pass%")
    print("-" * (label_w + 40))
    for k in sorted(groups):
        grp = groups[k]
        b = Counter(_bucket(r.get("judge_verdict")) for r in grp)
        n = len(grp)
        passed = b.get("PASS", 0)
        pct = passed / n * 100 if n else 0
        print(f"{k:<{label_w}} {n:4d}  {passed:4d}  {b.get('PARTIAL', 0):4d}  "
              f"{b.get('FAIL', 0):4d}  {b.get('SKIP', 0):4d}  {pct:5.1f}%")


def _list_fails(rows: list[dict]) -> None:
    fails = [r for r in rows if _bucket(r.get("judge_verdict")) == "FAIL"]
    if not fails:
        print("No FAIL verdicts.")
        return
    print(f"{len(fails)} FAIL cases:")
    for r in fails:
        qid = r.get("question_id", "?")
        cat = r.get("category", "?")
        v = r.get("judge_verdict", "?")
        trig = r.get("bot_refusal_trigger") or "-"
        ans = (r.get("bot_answer") or "").replace("\n", " ")[:100]
        print(f"  {qid:40s} cat={cat:20s} verdict={v:35s} trig={trig:25s}")
        print(f"    answer: {ans}")


def _drill(rows: list[dict], qid: str) -> None:
    matches = [r for r in rows if r.get("question_id") == qid]
    if not matches:
        print(f"No row with question_id={qid!r}")
        return
    r = matches[0]
    print(json.dumps(r, indent=2))


def _slowest(rows: list[dict], n: int) -> None:
    ordered = sorted(rows, key=lambda r: r.get("latency_ms", 0) or 0, reverse=True)
    for r in ordered[:n]:
        qid = r.get("question_id", "?")
        ms = r.get("latency_ms", 0)
        cat = r.get("category", "?")
        v = r.get("judge_verdict", "?")
        print(f"  {ms:6d}ms  {qid:40s}  cat={cat:18s}  verdict={v}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Slice a run_eval JSONL.")
    parser.add_argument("path", help="Path to results JSONL.")
    parser.add_argument("--by", choices=["category", "intent"], default=None,
                        help="Per-category or per-intent breakdown table.")
    parser.add_argument("--fails", action="store_true",
                        help="List FAIL cases with judge verdict + answer preview.")
    parser.add_argument("--id", default=None,
                        help="Drill into one case by question_id.")
    parser.add_argument("--slowest", type=int, default=0,
                        help="List the N slowest cases.")
    args = parser.parse_args(argv)

    if not Path(args.path).exists():
        print(f"file not found: {args.path}", file=sys.stderr)
        return 2

    rows = _load(args.path)

    if args.id:
        _drill(rows, args.id)
        return 0
    if args.fails:
        _list_fails(rows)
        return 0
    if args.slowest:
        _slowest(rows, args.slowest)
        return 0
    if args.by:
        _by_dimension(rows, args.by)
        return 0

    _summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
