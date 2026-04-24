"""
Eval-harness orchestrator: run every gold question through the bot,
score the result, and report.

This is a SKELETON. The bot orchestrator and synthesizer don't exist yet
(weeks 3-5 work). What's here:
  - Gold-set loading via golden_set.py.
  - Per-question result schema.
  - Scope-resolution check (PURE -- runs without the bot, exercises
    src/scope/resolver.py against every gold case TODAY).
  - Aggregate report shape so dashboards can be wired up.

The actual "ask the bot, ask the judge, score" loop is wired in once the
bot orchestrator + judge call site exist.

Usage:
    python -m src.eval.run_eval                       # run full set
    python -m src.eval.run_eval --filter cross_campus # one category
    python -m src.eval.run_eval --scope-only          # scope-resolver dry-run

See plan: timeline week 1 + Verification §2/§4/§6.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Allow running as a script.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402
from src.scope.resolver import resolve_scope  # noqa: E402

logger = logging.getLogger("eval")


@dataclass
class EvalResult:
    """One question's eval outcome."""

    question_id: str
    category: str
    # Scope check: did src/scope/resolver.py pick the expected scope?
    scope_match: bool
    actual_scope_campus: str
    actual_scope_library: Optional[str]
    # Bot output (None until the bot orchestrator is wired up).
    bot_answer: Optional[str] = None
    bot_was_refusal: Optional[bool] = None
    bot_citations_valid: Optional[bool] = None
    judge_verdict: Optional[str] = None  # "correct" | "partial" | "wrong" | refusal verdicts
    # Telemetry
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class EvalReport:
    """Aggregate of one eval run."""

    total: int = 0
    scope_matches: int = 0
    bot_called: int = 0
    by_judge_verdict: Counter = field(default_factory=Counter)
    by_category: dict[str, dict] = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)


def _check_scope(q: GoldQuestion) -> tuple[bool, str, Optional[str]]:
    """Run the scope resolver and report whether it matches the gold scope.

    Honors `needs_session_origin` on the gold question: if set, the
    resolver is called with that campus as the simulated session origin
    (as if the chat widget had loaded on ham/mid.miamioh.edu).
    """
    s = resolve_scope(
        q.question,
        session_origin_campus=q.needs_session_origin,  # type: ignore[arg-type]
    )
    matches = (
        s.campus == q.scope_campus
        and s.library == q.scope_library
    )
    return matches, s.campus, s.library


def run_eval(
    filter_category: Optional[str] = None,
    scope_only: bool = False,
) -> EvalReport:
    """Run the eval suite. Currently scope-only until bot is wired up."""
    questions = load_golden_set()
    if filter_category:
        questions = [q for q in questions if q.category == filter_category]

    # Scope-match accuracy is measured EXCLUDING clarify-outcome questions.
    # Those are ambiguous by design -- the resolver's scope is a starting
    # guess; the clarifier asks the user and the session scope updates
    # from the user's selection. Counting them would incentivize over-
    # fitting the resolver to handle inherent ambiguity.
    report = EvalReport(total=len(questions))
    scope_eligible = [q for q in questions if q.expected_outcome != "clarify"]

    for q in questions:
        scope_match, ac_campus, ac_lib = _check_scope(q)
        eligible = q.expected_outcome != "clarify"
        if scope_match and eligible:
            report.scope_matches += 1

        result = EvalResult(
            question_id=q.id,
            category=q.category,
            scope_match=scope_match,
            actual_scope_campus=ac_campus,
            actual_scope_library=ac_lib,
        )

        if not scope_only:
            # TODO: invoke the bot orchestrator + judge here once they exist.
            # For now, leave bot_* fields None.
            pass

        report.results.append(result)
        cat = report.by_category.setdefault(
            q.category, {"total": 0, "scope_matches": 0, "eligible": 0}
        )
        cat["total"] += 1
        if eligible:
            cat["eligible"] += 1
            if scope_match:
                cat["scope_matches"] += 1

    # Record the eligible count on the top-level report so the gate math
    # is honest: we pass/fail on eligible cases, not raw total.
    report.total = len(scope_eligible)
    return report


def _print_report(report: EvalReport, verbose: bool) -> None:
    all_n = len(report.results)
    eligible_n = report.total  # scope-eligible (excludes clarify cases)
    print()
    print(f"Eval results: {all_n} total questions "
          f"({eligible_n} scope-eligible; {all_n - eligible_n} clarify-case, excluded from gate)")
    print(f"  Scope-resolver matches: {report.scope_matches}/{eligible_n} "
          f"({100 * report.scope_matches / max(eligible_n, 1):.1f}%)")
    print()
    print("Per-category scope match rate (eligible only):")
    for cat, data in sorted(report.by_category.items()):
        eligible = data.get("eligible", data["total"])
        if eligible == 0:
            print(f"  {cat:25s}  (all clarify-case, skipped)")
            continue
        rate = 100 * data["scope_matches"] / eligible
        print(f"  {cat:25s}  {data['scope_matches']:3d}/{eligible:3d}  "
              f"({rate:5.1f}%)")

    if verbose:
        print()
        print("Scope mismatches:")
        for r in report.results:
            # Note: clarify-case mismatches are reported but don't fail
            # the gate. They surface here for debugging.
            if not r.scope_match:
                print(f"  {r.question_id}: got campus={r.actual_scope_campus} "
                      f"library={r.actual_scope_library}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the smart-chatbot eval suite.")
    parser.add_argument("--filter", help="Only run questions in this category.")
    parser.add_argument("--scope-only", action="store_true",
                        help="Only check src/scope/resolver.py; don't call the bot.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    report = run_eval(
        filter_category=args.filter,
        scope_only=args.scope_only,
    )
    _print_report(report, verbose=args.verbose)
    # Exit non-zero if scope match rate is below 90% -- conservative gate
    # so CI fails fast on alias regressions.
    rate = report.scope_matches / max(report.total, 1)
    return 0 if rate >= 0.90 else 1


if __name__ == "__main__":
    sys.exit(main())
