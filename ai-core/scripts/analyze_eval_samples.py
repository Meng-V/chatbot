"""Show concrete failure samples by bucket for root-cause inspection."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load_gold() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in Path("src/eval/golden_set.jsonl").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            q = json.loads(line)
            out[q["id"]] = q
        except json.JSONDecodeError:
            pass
    return out


def main() -> None:
    gold_by_id = load_gold()
    results = [json.loads(line) for line in open("eval_results.jsonl")]

    # Bucket: ILL/catalog/account false-positive refusals
    print("\n=== ILL / catalog_search / account false-positive refusals (gold = ANSWER) ===\n")
    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        if r.get("bot_was_refusal") and g.get("expected_outcome") == "answer":
            trig = r.get("bot_refusal_trigger") or ""
            if any(t in trig for t in ("interlibrary_loan", "catalog_search", "account_privacy", "renew_books", "place_holds", "course_reserves")):
                print(f"  [{g['intent']}] {r['question_id']}")
                print(f"    Q: {g['question']}")
                print(f"    trigger: {trig}")
                print(f"    expected_answer (excerpt): {(g.get('expected_answer') or '')[:150]}")
                print(f"    allowed_urls: {g.get('allowed_urls')}")
                print()

    # Bucket: out_of_scope cases bot ANSWERED
    print("\n=== out_of_scope answered (gold = REFUSAL) — first 12 ===\n")
    n = 0
    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        if not r.get("bot_was_refusal") and g.get("expected_outcome") == "refusal" and g.get("category") == "out_of_scope":
            print(f"  [{g['intent']}] {r['question_id']}")
            print(f"    Q: {g['question']}")
            print(f"    actual_intent={r.get('actual_intent')}  actual_path={r.get('actual_path')}")
            n += 1
            if n >= 12:
                break

    # Bucket: service questions where library defaulted to None
    print("\n\n=== 'service' category — gold=oxford/king but got oxford/None ===\n")
    n = 0
    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        if not r.get("scope_match") and g.get("category") == "service":
            print(f"  {r['question_id']}: {g['question']}")
            print(f"    gold={g['scope_campus']}/{g.get('scope_library')}  got={r['actual_scope_campus']}/{r.get('actual_scope_library')}")
            n += 1
            if n >= 8:
                break

    # Bucket: featured_service / circulation bot REFUSED instead of answered
    print("\n\n=== featured_service & circulation bot REFUSED (gold=ANSWER) ===\n")
    for r in results:
        g = gold_by_id.get(r["question_id"])
        if not g:
            continue
        if r.get("bot_was_refusal") and g.get("expected_outcome") == "answer" and g.get("category") in {"featured_service", "circulation"}:
            print(f"  [{g['category']}/{g['intent']}] {r['question_id']}")
            print(f"    Q: {g['question']}")
            print(f"    trigger: {r.get('bot_refusal_trigger')}")
            print()


if __name__ == "__main__":
    main()
