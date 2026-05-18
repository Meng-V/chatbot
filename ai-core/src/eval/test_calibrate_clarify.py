"""
Offline tests for src.eval.calibrate_clarify.

Run: `python -m src.eval.test_calibrate_clarify` from ai-core/.

Fully synthetic -- no real eval_results.jsonl, no API. Verifies the
gate replay matches intent_knn semantics and the recommender's safety
constraint (never increase wrong direct-routing vs the current gate).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.calibrate_clarify import (
    SCORE_FLOOR,
    Turn,
    build_turns,
    format_report,
    recommend,
    simulate,
)


def _t(qid, top, score, margin, gold):
    return Turn(qid=qid, top_intent=top, top_score=score,
                margin=margin, gold_intent=gold)


def test_missing_telemetry_detected() -> None:
    rows = [{"question_id": "q1", "actual_intent": "hours"}]  # pre-#60
    turns, missing = build_turns(rows, {})
    assert turns == [] and missing == 1
    rep = format_report(turns, missing, 0.03)
    assert "No classifier telemetry" in rep and "PR #60" in rep


def test_build_turns_joins_gold() -> None:
    rows = [{
        "question_id": "q1",
        "clf_score": 0.71,
        "clf_margin": 0.02,
        "clf_candidates": [["tech_checkout", 0.71], ["adobe_access", 0.69]],
    }]
    turns, missing = build_turns(rows, {"q1": "tech_checkout"})
    assert missing == 0 and len(turns) == 1
    t = turns[0]
    assert t.top_intent == "tech_checkout" and t.gold_intent == "tech_checkout"
    assert t.correct_if_routed is True


def test_score_floor_excludes_from_gate() -> None:
    # Below SCORE_FLOOR -> out_of_scope refusal, never a chip.
    low = _t("q", "x", SCORE_FLOOR - 0.01, 0.0, "y")
    s = simulate([low], margin_low=0.03, bypass_score=None)
    assert s.floored == 1 and s.clarified == 0 and s.routed == 0


def test_clarify_vs_route_and_wasted() -> None:
    # margin < m and top==gold -> clarified AND wasted (needless chip).
    waste = _t("a", "hours", 0.70, 0.02, "hours")
    # margin >= m -> routed; top!=gold -> routed_wrong.
    wrong = _t("b", "hours", 0.70, 0.20, "room_booking")
    s = simulate([waste, wrong], margin_low=0.03, bypass_score=None)
    assert s.clarified == 1 and s.wasted_clarify == 1
    assert s.routed == 1 and s.routed_wrong == 1 and s.routed_correct == 0


def test_high_confidence_bypass_routes() -> None:
    # Thin margin but high score + bypass set -> route, not clarify.
    turn = _t("a", "hours", 0.82, 0.01, "hours")
    no_bypass = simulate([turn], 0.03, None)
    bypassed = simulate([turn], 0.03, 0.80)
    assert no_bypass.clarified == 1
    assert bypassed.clarified == 0 and bypassed.routed_correct == 1


def test_recommend_respects_routed_wrong_constraint() -> None:
    """Lowering the gate must not start routing genuinely-ambiguous
    turns wrong. A: needless chip (fixable). B: wrong, must stay
    clarified. C: stable correct route."""
    A = _t("A", "ill", 0.70, 0.025, "ill")              # correct, chipped
    B = _t("B", "ill", 0.70, 0.010, "circulation_basic")  # wrong, chipped
    C = _t("C", "hours", 0.80, 0.200, "hours")           # correct, routed
    turns = [A, B, C]
    base = simulate(turns, 0.03, None)
    assert base.wasted_clarify == 1 and base.routed_wrong == 0
    rec = recommend(turns, 0.03)
    # Best feasible: m=0.02 routes A (correct), keeps B clarified
    # (margin 0.01 < 0.02), so routed_wrong stays 0 and the needless
    # chip is gone.
    assert rec.routed_wrong <= base.routed_wrong
    assert rec.wasted_clarify == 0
    assert rec.margin_low == 0.02 and rec.bypass_score is None


def main() -> int:
    tests = [
        test_missing_telemetry_detected,
        test_build_turns_joins_gold,
        test_score_floor_excludes_from_gate,
        test_clarify_vs_route_and_wasted,
        test_high_confidence_bypass_routes,
        test_recommend_respects_routed_wrong_constraint,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
