"""One-shot eval failure analyzer. Reads eval_results.jsonl + golden_set.jsonl
and prints a breakdown of failure types so we can prioritize fixes.

Run:
    python scripts/analyze_eval.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def load_gold() -> dict[str, dict]:
    gold_path = Path("src/eval/golden_set.jsonl")
    out: dict[str, dict] = {}
    for line in gold_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            q = json.loads(line)
            out[q["id"]] = q
        except json.JSONDecodeError:
            pass
    return out


def load_results() -> list[dict]:
    out = []
    with open("eval_results.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> None:
    gold_by_id = load_gold()
    results = load_results()

    print(f"Gold loaded: {len(gold_by_id)}, Results: {len(results)}\n")

    scope_fails = []
    intent_fails = []
    path_fails = []
    refusal_fp = []      # refused when should answer
    refusal_missed = []  # answered when should refuse

    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        if not r.get("scope_match") and g.get("expected_outcome") != "clarify":
            scope_fails.append((r, g))
        if r.get("intent_match") is False:
            intent_fails.append((r, g))
        if r.get("path_match") is False:
            path_fails.append((r, g))
        if r.get("bot_was_refusal") and g.get("expected_outcome") == "answer":
            refusal_fp.append((r, g))
        if not r.get("bot_was_refusal") and g.get("expected_outcome") == "refusal":
            refusal_missed.append((r, g))

    # --- Scope failures ---
    print(f"=== SCOPE failures: {len(scope_fails)} ===")
    sf_pairs: Counter = Counter()
    for r, g in scope_fails:
        exp = f"{g['scope_campus']}/{g.get('scope_library')}"
        act = f"{r['actual_scope_campus']}/{r.get('actual_scope_library')}"
        sf_pairs[(exp, act, g['category'])] += 1
    for (exp, act, cat), n in sf_pairs.most_common():
        print(f"  [{cat:25s}] gold={exp:30s} got={act:30s}  x{n}")
    print()

    # Sample scope failure questions
    print("--- Sample SCOPE failure questions (first 12) ---")
    for r, g in scope_fails[:12]:
        print(f"  [{g['category']}] {r['question_id']}")
        print(f"    Q: {g['question']}")
        print(f"    gold: {g['scope_campus']}/{g.get('scope_library')}  |  got: {r['actual_scope_campus']}/{r.get('actual_scope_library')}")
    print()

    # --- Intent failures ---
    print(f"=== INTENT failures: {len(intent_fails)} ===")
    intent_pairs: Counter = Counter()
    for r, g in intent_fails:
        intent_pairs[(g['intent'], r['actual_intent'], g['category'])] += 1
    for (exp, act, cat), n in intent_pairs.most_common(30):
        print(f"  [{cat:25s}] gold={exp:30s} got={act!s:30s}  x{n}")
    print()

    # Intent failure margin distribution
    margins = [r.get("clf_margin") for r, _ in intent_fails if r.get("clf_margin") is not None]
    if margins:
        margins_sorted = sorted(margins)
        n = len(margins_sorted)
        p25 = margins_sorted[n // 4]
        p50 = margins_sorted[n // 2]
        p75 = margins_sorted[3 * n // 4]
        low_margin = sum(1 for m in margins if m < 0.05)
        very_low = sum(1 for m in margins if m < 0.02)
        print(f"Intent-failure margin distribution: p25={p25:.3f} p50={p50:.3f} p75={p75:.3f}")
        print(f"  margins < 0.05: {low_margin}/{n}  ({100*low_margin/n:.0f}%)  <- weak top-1")
        print(f"  margins < 0.02: {very_low}/{n}  ({100*very_low/n:.0f}%)  <- nearly tied")
    print()

    # --- Path failures ---
    print(f"=== PATH failures: {len(path_fails)} ===")
    path_pairs: Counter = Counter()
    for r, g in path_fails:
        exp = "|".join(sorted(r.get("expected_path_set") or []))
        path_pairs[(exp, r.get("actual_path"), g['category'])] += 1
    for (exp, act, cat), n in path_pairs.most_common(30):
        print(f"  [{cat:25s}] gold-paths={exp:35s} got={act!s:25s}  x{n}")
    print()

    # --- Refusal stats ---
    print(f"=== REFUSAL false positives (bot refused, gold expected ANSWER): {len(refusal_fp)} ===")
    fp_triggers = Counter(r.get("bot_refusal_trigger") for r, _ in refusal_fp)
    for trig, n in fp_triggers.most_common():
        print(f"  trigger={trig!s:50s}  x{n}")
    fp_intents = Counter(g["intent"] for _, g in refusal_fp)
    for intent, n in fp_intents.most_common():
        print(f"  gold-intent={intent!s:30s}  x{n}")
    print()

    print(f"=== REFUSAL missed (bot answered, gold expected REFUSAL): {len(refusal_missed)} ===")
    missed_intents = Counter(g["intent"] for _, g in refusal_missed)
    for intent, n in missed_intents.most_common():
        print(f"  gold-intent={intent!s:30s}  x{n}")
    missed_cats = Counter(g["category"] for _, g in refusal_missed)
    for cat, n in missed_cats.most_common():
        print(f"  category={cat!s:30s}  x{n}")
    print()

    # --- Co-occurrence: how often does intent-fail co-occur with path-fail? ---
    intent_only = sum(1 for r, _ in intent_fails if r.get("path_match") is True)
    path_only = sum(1 for r, _ in path_fails if r.get("intent_match") is not False)
    both = sum(1 for r, _ in intent_fails if r.get("path_match") is False)
    print("=== Intent x Path co-occurrence ===")
    print(f"  intent fail AND path fail:  {both}")
    print(f"  intent fail, path OK:       {intent_only}")
    print(f"  intent OK, path fail:       {path_only}")
    print()

    # --- Per-category problem ranking ---
    cat_issues: dict[str, dict] = defaultdict(lambda: {"scope": 0, "intent": 0, "path": 0, "total": 0})
    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        c = g["category"]
        cat_issues[c]["total"] += 1
        if not r.get("scope_match") and g.get("expected_outcome") != "clarify":
            cat_issues[c]["scope"] += 1
        if r.get("intent_match") is False:
            cat_issues[c]["intent"] += 1
        if r.get("path_match") is False:
            cat_issues[c]["path"] += 1
    print("=== Category problem ranking (by sum of failure types) ===")
    ranked = sorted(
        cat_issues.items(),
        key=lambda kv: kv[1]["scope"] + kv[1]["intent"] + kv[1]["path"],
        reverse=True,
    )
    print(f"  {'category':25s} {'total':>6s} {'scope':>6s} {'intent':>7s} {'path':>5s}")
    for cat, d in ranked:
        print(f"  {cat:25s} {d['total']:>6d} {d['scope']:>6d} {d['intent']:>7d} {d['path']:>5d}")


if __name__ == "__main__":
    main()
