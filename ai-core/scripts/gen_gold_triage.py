"""Join eval_results.jsonl with the gold set -> a human triage doc.

Purpose: after a real-LLM eval, the headline number is contaminated
by a stale gold set (libraries genuinely close in intersession,
Middletown DOES have a makerspace, etc. -- repeatedly confirmed).
This emits one section per failing case with everything needed to
judge GOLD-vs-REALITY against the live Miami site, side by side:

    question | what GOLD currently claims | allowed_urls |
    what the BOT said | judge verdict | path | a HEURISTIC bucket

The bucket is only a sorting hint -- the human is the authority on
whether gold is stale. Run:

    python -m scripts.gen_gold_triage \
        --results eval_results.jsonl --out data/eval/gold_triage.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.golden_set import load_golden_set  # noqa: E402

# Verdicts that mean "the bot and the gold disagreed" -> worth a look.
_FAIL = {"wrong", "refused_incorrectly", "answered_should_have_refused"}


def _bucket(qid: str, cat: str, gold: str, row: dict) -> str:
    """HEURISTIC sort hint only. The human decides gold validity."""
    q = qid.lower()
    ans = (row.get("bot_answer") or "").lower()
    refused = row.get("bot_was_refusal")

    # Un-simulatable: gold wants a refusal because a live dep is
    # "down", but the eval can't inject that outage.
    if "libcal_down" in q or "_down_refusal" in q or "live_data" in q:
        return "UN_SIMULATABLE (fix the case/harness, not the bot)"

    # Known stale-gold clusters the operator has already confirmed.
    if cat == "hours" and not refused and ("closed" in ans or "open" in ans):
        return "LIKELY_GOLD_STALE (closed/intersession is real)"
    if "makerspace_middletown" in q or "middletown" in q and "makerspace" in ans:
        return "LIKELY_GOLD_STALE (Middletown TEC Lab confirmed real)"
    if "wertz" in q or "alias" in q:
        return "LIKELY_GOLD_STALE (alias resolution / intersession)"
    if cat in ("hours", "cross_campus") and not refused and row.get("bot_citations_count"):
        return "CHECK_GOLD (live data, cited -- verify vs site)"

    # Real-miss signals: clarification loop, or refused on in-corpus.
    if "i'm not sure which of these" in ans or "can you pick one" in ans:
        return "LIKELY_REAL_MISS (over-clarification loop)"
    if refused and row.get("bot_refusal_trigger") == "model_self_flagged":
        return "CHECK_REAL_MISS (refused; was evidence really absent?)"
    return "BORDERLINE (judge strictness? read both)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="eval_results.jsonl")
    ap.add_argument("--out", default="data/eval/gold_triage.md")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.results).read_text().splitlines() if l.strip()]
    gold = {g.id: g for g in load_golden_set()}
    fails = [r for r in rows if r.get("judge_verdict") in _FAIL]

    # Group by bucket, then category, for an efficient review pass.
    by_bucket: dict[str, list] = {}
    for r in fails:
        g = gold.get(r["question_id"])
        b = _bucket(
            r["question_id"], r.get("category", "?"),
            (g.expected_answer if g else ""), r,
        )
        by_bucket.setdefault(b, []).append((r, g))

    out = [
        f"# Gold-vs-reality triage — {len(fails)} disagreeing cases",
        "",
        f"From `{args.results}`. Verdicts: "
        + ", ".join(
            f"{v}={sum(1 for r in fails if r['judge_verdict']==v)}"
            for v in sorted({r["judge_verdict"] for r in fails})
        ),
        "",
        "**You are the authority on whether GOLD is stale.** The "
        "`bucket` is only a sort hint. For each: open the live Miami "
        "page, decide if the GOLD claim or the BOT answer matches "
        "reality, and correct the gold case if it's stale.",
        "",
    ]
    for bucket in sorted(by_bucket):
        cases = by_bucket[bucket]
        out.append(f"\n## {bucket} — {len(cases)}\n")
        for r, g in sorted(cases, key=lambda x: x[0].get("category", "")):
            out.append(f"### `{r['question_id']}`  ({r.get('category')})")
            out.append(
                f"- **verdict** {r['judge_verdict']} | "
                f"path_match={r.get('path_match')} | "
                f"cites={r.get('bot_citations_count')} | "
                f"refused={r.get('bot_was_refusal')}"
            )
            if g:
                out.append(f"- **Q:** {g.question}")
                out.append(
                    f"- **GOLD claims:** {g.expected_answer or '(none)'}"
                )
                if g.allowed_urls:
                    out.append(
                        f"- **allowed_urls:** {', '.join(g.allowed_urls)}"
                    )
                if g.notes:
                    out.append(f"- **gold notes:** {g.notes}")
            ans = (r.get("bot_answer") or "(no answer)").replace("\n", " ")
            out.append(f"- **BOT said:** {ans}")
            out.append("")

    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {len(fails)} cases -> {args.out}")
    for b in sorted(by_bucket):
        print(f"  {len(by_bucket[b]):3}  {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
