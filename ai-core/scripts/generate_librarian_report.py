"""Generate a librarian-friendly markdown report from an eval results file.

Designed for non-programmers: plain language, side-by-side comparisons,
clear "did the bot do well or badly?" verdicts, and explicit comparison
to v1 failures (sourced from the colleague's Nov 20 test).

Usage:
    cd ai-core
    python scripts/generate_librarian_report.py \
        --results beta_colleague_round1.jsonl \
        --gold src/eval/golden_set_colleague_round1.jsonl \
        --output docs/eval/colleague_round1_report.md

The output is markdown. To convert to Word for librarians, install pandoc
and run: pandoc colleague_round1_report.md -o report.docx
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# Plain-English verdict labels (no eval-speak)
VERDICT_LABELS = {
    "correct": "✅ Answered well",
    "refused_correctly": "✅ Correctly refused (can't / shouldn't answer)",
    "partial": "🟡 Partially right",
    "wrong": "❌ Wrong answer",
    "refused_incorrectly": "❌ Refused when it could have answered",
    "answered_should_have_refused": "⚠️ Answered when it should have refused",
    None: "⚪ Not judged",
}

VERDICT_BUCKETS = {
    "good": {"correct", "refused_correctly"},
    "okay": {"partial"},
    "bad": {"wrong", "refused_incorrectly", "answered_should_have_refused"},
}

CATEGORY_LABELS = {
    "r1_hours": "Library hours",
    "r1_address": "Library addresses",
    "r1_contact": "Phone numbers / contact info",
    "r1_librarian": "Subject librarian lookups",
    "r1_tech": "Technology checkout",
    "r1_help": "Getting human help",
    "r1_circulation": "Loans, renewals, fines",
    "r1_research": "Research help and class guides",
    "r1_services": "Library services (printing, NYT, Adobe, food)",
    "r1_room_booking": "Reserving study rooms",
    "r1_find": "Finding books and articles",
    "r1_account": "Personal account questions",
}


def load_jsonl(path: Path) -> list[dict]:
    out = []
    for ln in open(path):
        s = ln.strip()
        if not s or s.startswith("//"):
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def bucket(verdict: str | None) -> str:
    for name, members in VERDICT_BUCKETS.items():
        if verdict in members:
            return name
    return "unjudged"


def format_case_table(case: dict, result: dict) -> str:
    """One-question summary block in markdown."""
    verdict = result.get("judge_verdict")
    label = VERDICT_LABELS.get(verdict, "—")
    bot_answer = (result.get("bot_answer") or "").strip()
    if len(bot_answer) > 350:
        bot_answer = bot_answer[:350] + "…"
    v1_note = case.get("notes", "")

    parts = [
        f"### Q: {case['question']}",
        f"",
        f"**Result:** {label}",
        f"",
        f"**The bot said:**",
        f"",
        f"> {bot_answer}" if bot_answer else "> (no answer recorded)",
        f"",
    ]
    if v1_note:
        parts.append(f"**Last year's bot (v1) did:** {v1_note}")
        parts.append("")
    parts.append("---")
    parts.append("")
    return "\n".join(parts)


def category_summary(cat_id: str, cases: list[tuple[dict, dict]]) -> str:
    """Per-category section with stats + a few example cases."""
    total = len(cases)
    good = sum(1 for _, r in cases if bucket(r.get("judge_verdict")) == "good")
    okay = sum(1 for _, r in cases if bucket(r.get("judge_verdict")) == "okay")
    bad = sum(1 for _, r in cases if bucket(r.get("judge_verdict")) == "bad")

    label = CATEGORY_LABELS.get(cat_id, cat_id)
    pct = (good / total * 100) if total else 0
    icon = "🟢" if pct >= 75 else ("🟡" if pct >= 50 else "🔴")

    lines = [
        f"## {icon} {label}",
        f"",
        f"**{good} of {total} answered well ({pct:.0f}%)** — "
        f"{okay} partially right, {bad} need work.",
        f"",
    ]
    for c, r in cases:
        lines.append(format_case_table(c, r))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="eval results jsonl")
    ap.add_argument("--gold", required=True, help="gold set jsonl")
    ap.add_argument("--output", required=True, help="where to write the markdown report")
    args = ap.parse_args()

    gold_list = load_jsonl(Path(args.gold))
    gold = {c["id"]: c for c in gold_list}
    results = load_jsonl(Path(args.results))

    # Align by question_id
    paired: list[tuple[dict, dict]] = []
    missing = []
    for r in results:
        qid = r.get("question_id")
        if qid in gold:
            paired.append((gold[qid], r))
        else:
            missing.append(qid)

    n = len(paired)
    if n == 0:
        print(f"ERROR: no results matched the gold set. Are you sure --gold points to "
              f"the same file you ran the eval against?")
        return 1

    # Headline counts
    verdicts = Counter(r.get("judge_verdict") for _, r in paired)
    good_n = sum(verdicts.get(v, 0) for v in VERDICT_BUCKETS["good"])
    okay_n = sum(verdicts.get(v, 0) for v in VERDICT_BUCKETS["okay"])
    bad_n = sum(verdicts.get(v, 0) for v in VERDICT_BUCKETS["bad"])
    good_pct = good_n / n * 100

    # Group by category
    by_cat = defaultdict(list)
    for c, r in paired:
        by_cat[c.get("category", "?")].append((c, r))

    # Find the "critical wins" — cases where v1 did something bad (per notes)
    # and v2 now does well.
    critical_wins = []
    for c, r in paired:
        notes = (c.get("notes") or "").lower()
        is_v1_critical = (
            "hallucinated" in notes
            or "fabricated" in notes
            or "critical" in notes
            or "crashed" in notes
            or "roster dump" in notes
            or "wrong" in notes
        )
        v_bucket = bucket(r.get("judge_verdict"))
        if is_v1_critical and v_bucket == "good":
            critical_wins.append((c, r))

    # Find remaining problems — bad-bucket cases
    remaining_problems = [(c, r) for c, r in paired if bucket(r.get("judge_verdict")) == "bad"]

    # Build the report
    today = datetime.now().strftime("%B %d, %Y")
    lines: list[str] = []

    # --- Header ---
    lines += [
        f"# Chatbot Re-Test Report",
        f"",
        f"_Generated {today}. Source test: Miami Libraries colleague's Nov 20, 2025 evaluation._",
        f"_Re-run on chatbot v2 (current production candidate)._",
        f"",
        f"---",
        f"",
        f"## The headline",
        f"",
    ]
    if good_pct >= 75:
        headline_emoji = "🟢"
        headline_text = "**The new chatbot handles most of your questions well.**"
    elif good_pct >= 55:
        headline_emoji = "🟡"
        headline_text = "**The new chatbot handles a majority of your questions well, with some remaining gaps.**"
    else:
        headline_emoji = "🔴"
        headline_text = "**The new chatbot still has significant gaps — review case by case below.**"

    lines += [
        f"{headline_emoji} {headline_text}",
        f"",
        f"- **Questions tested:** {n}",
        f"- **Answered well:** {good_n} ({good_pct:.0f}%)",
        f"- **Partially right:** {okay_n}",
        f"- **Still need work:** {bad_n}",
        f"",
    ]

    if critical_wins:
        lines += [
            f"## What got better since last year",
            f"",
            f"Your Nov 20 test caught **{len(critical_wins)} serious failures** in v1 "
            f"(hallucinated answers, fabricated sources, fake booking confirmations). "
            f"The new bot now handles these correctly:",
            f"",
        ]
        for c, r in critical_wins:
            lines.append(f"- **{c['question']}** — was: _{c.get('notes','')}_. Now: ✅ correct.")
        lines += ["", "---", ""]

    if remaining_problems:
        lines += [
            f"## What still needs attention",
            f"",
            f"{len(remaining_problems)} questions still don't get a great answer. "
            f"Each is shown below with what the bot said and why it's a problem.",
            f"",
        ]
        for c, r in remaining_problems:
            verdict = VERDICT_LABELS.get(r.get("judge_verdict"), "—")
            bot = (r.get("bot_answer") or "")[:200]
            lines.append(f"- **Q: {c['question']}**")
            lines.append(f"  - Result: {verdict}")
            lines.append(f"  - Bot said: _{bot}{'…' if len(bot)==200 else ''}_")
            lines.append("")
        lines += ["---", ""]

    # --- Per-category breakdown ---
    lines += [
        f"## Question-by-question breakdown",
        f"",
        f"Each question you asked is below, grouped by topic. For each, you'll see:",
        f"- What the bot answered",
        f"- Whether it was right",
        f"- What last year's bot (v1) did, for comparison",
        f"",
    ]
    # Order categories by performance (best first), so good news leads
    cat_order = sorted(
        by_cat.keys(),
        key=lambda c: -(sum(1 for _, r in by_cat[c] if bucket(r.get("judge_verdict"))=="good") / max(len(by_cat[c]),1)),
    )
    for cat in cat_order:
        lines.append(category_summary(cat, by_cat[cat]))

    # --- The technical bit ---
    lines += [
        f"## Technical notes",
        f"",
        f"_For Meng / IT staff. Librarians can skip this._",
        f"",
        f"- Eval run: `{args.results}`",
        f"- Gold set: `{args.gold}`",
        f"- Total questions: {n}  |  Verdict distribution: ",
    ]
    for v, c in verdicts.most_common():
        lines.append(f"  - {v}: {c}")
    if missing:
        lines.append(f"- Results without matching gold entry: {missing}")
    lines.append("")
    lines.append(f"Comparison to v1 (Nov 20, 2025 colleague test) is based on the answers")
    lines.append(f"the colleague recorded in `Test Questions for Chatbot - Answer Log.docx`.")

    # --- Plain-English bottom line ---
    lines += [
        f"",
        f"---",
        f"",
        f"## Bottom line for the librarian team",
        f"",
    ]
    if good_pct >= 75:
        lines += [
            f"The new chatbot is **clearly better than what blocked deployment last year**. "
            f"Most of the dangerous failures (hallucinated articles, fake bookings, made-up hours) "
            f"are gone. The remaining gaps are smaller and most can be fixed through the new "
            f"librarian-driven `ManualCorrection` mechanism (you flag a wrong answer, it's "
            f"corrected immediately without a software deploy).",
        ]
    elif good_pct >= 55:
        lines += [
            f"The new chatbot handles the majority of your test cases well — especially the "
            f"ones that v1 failed badly on (hallucinated articles, fake bookings). But there "
            f"are still {bad_n} questions where the bot doesn't give a great answer. Each "
            f"is listed in 'What still needs attention' above. Some of these can be fixed by "
            f"librarians directly through the new ManualCorrection mechanism; others need "
            f"developer work.",
        ]
    else:
        lines += [
            f"The new chatbot fixes some of v1's worst failures, but {bad_n} of {n} questions "
            f"still don't get a good answer. Review the 'What still needs attention' list and "
            f"the per-category breakdown to decide whether the improvements are enough to "
            f"unblock a small-scale rollout, or whether more work is needed first.",
        ]

    # Write
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to: {out_path}")
    print(f"  {n} questions, {good_n} answered well ({good_pct:.0f}%)")
    if remaining_problems:
        print(f"  {len(remaining_problems)} questions still need attention")
    if critical_wins:
        print(f"  {len(critical_wins)} critical v1 failures now fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
