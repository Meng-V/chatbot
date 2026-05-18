"""
Offline clarification-gate calibrator.

WHY THIS EXISTS (credit-conservation tool): a full real-LLM eval run
costs ~$4. The clarification gate (`MARGIN_LOW`, plus an optional
high-confidence-score bypass) was found over-firing in round 1 -- 34
of 184 turns bounced to a "did you mean" chip, 18 of them when the
classifier had ALREADY picked the gold-correct intent. PR #60 lowered
MARGIN_LOW 0.05->0.03 as a conservative step and started persisting
the classifier's per-turn `clf_score / clf_margin / clf_candidates`
into eval_results.jsonl.

This script consumes that telemetry and SWEEPS candidate gate
settings offline, so the NEXT paid eval is a single decisive run that
auto-derives the calibrated threshold -- not 3-4 guess-and-re-run
iterations burning $4 each.

It is read-only and API-free: it only reads eval_results.jsonl (+ the
gold set for the true intent) and replays the EXACT gate arithmetic
from `intent_knn.classify()` (SCORE_FLOOR is imported, never
hard-coded) so the simulated outcome matches what the bot would
really do.

Usage:
    python -m src.eval.calibrate_clarify
    python -m src.eval.calibrate_clarify --results eval_results.jsonl \\
        --gold src/eval/golden_set.jsonl
    python -m src.eval.calibrate_clarify --emit-constant
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Single source of truth for the absolute-score floor. If NO exemplar
# is genuinely close, intent_knn returns out_of_scope with
# needs_clarification=False (a clean refusal, NOT a chip) -- the
# simulation must replicate that or the recommendation is wrong.
try:
    from src.router.intent_knn import SCORE_FLOOR
except Exception:  # noqa: BLE001 -- keep the analyzer runnable standalone
    SCORE_FLOOR = 0.50


# --- Data ----------------------------------------------------------------


@dataclass(frozen=True)
class Turn:
    """One eval row reduced to what the gate decision needs."""

    qid: str
    top_intent: str          # clf_candidates[0][0] -- raw classifier pick
    top_score: float         # clf_candidates[0][1] == clf_score
    margin: float            # clf_margin
    gold_intent: Optional[str]

    @property
    def correct_if_routed(self) -> Optional[bool]:
        if self.gold_intent is None:
            return None
        return self.top_intent == self.gold_intent


@dataclass(frozen=True)
class Stats:
    margin_low: float
    bypass_score: Optional[float]
    n: int
    floored: int          # score < SCORE_FLOOR -> out_of_scope refusal
    clarified: int        # bounced to a "did you mean" chip
    routed: int           # answered directly
    routed_correct: int
    routed_wrong: int
    wasted_clarify: int   # clarified though the top pick WAS gold-correct

    @property
    def clarify_rate(self) -> float:
        return self.clarified / self.n if self.n else 0.0

    @property
    def routed_wrong_rate(self) -> float:
        return self.routed_wrong / self.routed if self.routed else 0.0


# --- Loading -------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        try:
            rows.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return rows


def _gold_intent_map(gold_path: Optional[Path]) -> dict[str, str]:
    if not gold_path or not gold_path.exists():
        return {}
    out: dict[str, str] = {}
    for g in _load_jsonl(gold_path):
        gid, gi = g.get("id"), g.get("intent")
        if gid and gi:
            out[gid] = gi
    return out


def build_turns(
    results: list[dict], gold: dict[str, str]
) -> tuple[list[Turn], int]:
    """Return (turns_with_telemetry, n_rows_missing_telemetry).

    A row is usable only if PR #60's clf_* telemetry is present. Rows
    from a pre-#60 eval have clf_candidates=None -> skipped and
    counted so the caller can tell the operator to re-run.
    """
    turns: list[Turn] = []
    missing = 0
    for r in results:
        cands = r.get("clf_candidates")
        margin = r.get("clf_margin")
        if not cands or margin is None:
            missing += 1
            continue
        try:
            top_intent = str(cands[0][0])
            top_score = float(
                r.get("clf_score")
                if r.get("clf_score") is not None
                else cands[0][1]
            )
        except (IndexError, TypeError, ValueError):
            missing += 1
            continue
        qid = str(r.get("question_id", ""))
        turns.append(
            Turn(
                qid=qid,
                top_intent=top_intent,
                top_score=top_score,
                margin=float(margin),
                gold_intent=gold.get(qid),
            )
        )
    return turns, missing


# --- Simulation (replays intent_knn.classify gate arithmetic) ------------


def simulate(
    turns: list[Turn], margin_low: float, bypass_score: Optional[float]
) -> Stats:
    """Replay the gate for a candidate (margin_low, bypass_score).

    Mirrors intent_knn.classify() EXACTLY:
      * top_score < SCORE_FLOOR  -> out_of_scope, NOT a clarification.
      * else clarify iff margin < margin_low, UNLESS a bypass_score is
        set and top_score >= bypass_score (high-confidence -> route).
    """
    floored = clarified = routed = rc = rw = wasted = 0
    for t in turns:
        if t.top_score < SCORE_FLOOR:
            floored += 1
            continue
        bypass = bypass_score is not None and t.top_score >= bypass_score
        if t.margin < margin_low and not bypass:
            clarified += 1
            if t.correct_if_routed is True:
                wasted += 1
            continue
        routed += 1
        if t.correct_if_routed is True:
            rc += 1
        elif t.correct_if_routed is False:
            rw += 1
    return Stats(
        margin_low=margin_low,
        bypass_score=bypass_score,
        n=len(turns),
        floored=floored,
        clarified=clarified,
        routed=routed,
        routed_correct=rc,
        routed_wrong=rw,
        wasted_clarify=wasted,
    )


def sweep(turns: list[Turn]) -> list[Stats]:
    margins = [round(i * 0.01, 2) for i in range(0, 11)]  # 0.00..0.10
    bypasses: list[Optional[float]] = [None, 0.60, 0.65, 0.70, 0.75, 0.80]
    return [simulate(turns, m, b) for b in bypasses for m in margins]


def recommend(turns: list[Turn], baseline_margin: float) -> Stats:
    """Pick the setting that maximizes correct direct-routing WITHOUT
    increasing wrong direct-routing above the strictest-gate baseline.

    Rationale: a thin margin between two ADJACENT library topics is not
    user ambiguity (the agent handles it); a chip there is pure
    friction. But we must not start routing genuinely-ambiguous turns
    wrong. So the hard constraint is "routed_wrong must not exceed the
    baseline gate's routed_wrong"; among those, prefer the fewest
    needless chips (wasted_clarify), tie-break on lowest clarify_rate.
    """
    base = simulate(turns, baseline_margin, None)
    feasible = [
        s
        for s in sweep(turns)
        if s.routed_wrong <= base.routed_wrong
    ]
    feasible.sort(
        key=lambda s: (s.wasted_clarify, s.clarify_rate, s.margin_low)
    )
    return feasible[0] if feasible else base


# --- Reporting -----------------------------------------------------------


def per_intent_wasted(
    turns: list[Turn], margin_low: float, bypass_score: Optional[float]
) -> list[tuple[str, int]]:
    """Where are the REMAINING needless chips at the chosen setting?
    Actionable: a hot intent here wants more exemplars, not a looser
    threshold."""
    from collections import Counter

    c: Counter = Counter()
    for t in turns:
        if t.top_score < SCORE_FLOOR:
            continue
        bypass = bypass_score is not None and t.top_score >= bypass_score
        if t.margin < margin_low and not bypass and t.correct_if_routed is True:
            c[t.gold_intent or "(no gold)"] += 1
    return c.most_common()


def format_report(
    turns: list[Turn], missing: int, baseline_margin: float
) -> str:
    L: list[str] = []
    L.append("=== Clarification-gate calibration ===")
    L.append(
        f"usable turns: {len(turns)}  |  rows missing clf_* telemetry: "
        f"{missing}  |  SCORE_FLOOR={SCORE_FLOOR}"
    )
    if not turns:
        L.append("")
        L.append(
            "No classifier telemetry found. This is EXPECTED until an "
            "eval is run on main with PR #60 merged. Re-run "
            "`python -m src.eval.run_eval --with-real-llm --with-judge`, "
            "then re-run this analyzer -- it will then output the "
            "calibrated MARGIN_LOW in one pass (no extra paid runs)."
        )
        return "\n".join(L)

    n_gold = sum(1 for t in turns if t.gold_intent is not None)
    L.append(f"turns with gold intent joined: {n_gold}/{len(turns)}")
    if n_gold == 0:
        L.append(
            "WARNING: no gold intents joined (check --gold path / "
            "question_id<->id). Correctness columns will be 0."
        )

    base = simulate(turns, baseline_margin, None)
    L.append("")
    L.append(
        f"current gate (MARGIN_LOW={baseline_margin}, no bypass): "
        f"clarify={base.clarified} ({base.clarify_rate:.1%})  "
        f"routed={base.routed}  routed_wrong={base.routed_wrong}  "
        f"needless_chips={base.wasted_clarify}"
    )

    L.append("")
    L.append("sweep (m=MARGIN_LOW, S=bypass score; '-'=no bypass):")
    L.append(
        "  m     S     clarify  routed  r_correct  r_wrong  needless"
    )
    for s in sweep(turns):
        L.append(
            f"  {s.margin_low:<5} "
            f"{('-' if s.bypass_score is None else s.bypass_score):<5} "
            f"{s.clarified:>7}  {s.routed:>6}  {s.routed_correct:>9}  "
            f"{s.routed_wrong:>7}  {s.wasted_clarify:>8}"
        )

    rec = recommend(turns, baseline_margin)
    L.append("")
    L.append(
        "RECOMMENDED (max correct routing s.t. routed_wrong <= current "
        "gate):"
    )
    L.append(
        f"  MARGIN_LOW = {rec.margin_low}"
        + (
            ""
            if rec.bypass_score is None
            else f"  + high-confidence bypass at clf_score >= {rec.bypass_score}"
        )
    )
    L.append(
        f"  -> clarify {base.clarified}->{rec.clarified}, "
        f"needless chips {base.wasted_clarify}->{rec.wasted_clarify}, "
        f"routed_wrong {base.routed_wrong}->{rec.routed_wrong} "
        f"(constraint: <= {base.routed_wrong})"
    )
    hot = per_intent_wasted(turns, rec.margin_low, rec.bypass_score)
    if hot:
        L.append("")
        L.append(
            "Remaining needless chips by gold intent at the recommended "
            "setting (these want MORE EXEMPLARS, not a looser gate):"
        )
        for intent, k in hot:
            L.append(f"  {k:>3}  {intent}")
    return "\n".join(L)


# --- CLI -----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    _here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Calibrate the clarify gate.")
    ap.add_argument(
        "--results",
        type=Path,
        default=Path("eval_results.jsonl"),
        help="Path to eval_results.jsonl (default: ./eval_results.jsonl)",
    )
    ap.add_argument(
        "--gold",
        type=Path,
        default=_here / "golden_set.jsonl",
        help="Path to golden_set.jsonl (for the true intent join).",
    )
    ap.add_argument(
        "--baseline-margin",
        type=float,
        default=0.03,
        help="Current MARGIN_LOW to compare against (default 0.03 = PR #60).",
    )
    ap.add_argument(
        "--emit-constant",
        action="store_true",
        help="Print just the recommended MARGIN_LOW (and bypass) for "
        "pasting into intent_knn.py, nothing else.",
    )
    args = ap.parse_args(argv)

    if not args.results.exists():
        print(
            f"results file not found: {args.results}\n"
            "Run the eval first (it writes eval_results.jsonl), then "
            "re-run this analyzer.",
            file=sys.stderr,
        )
        return 2

    results = _load_jsonl(args.results)
    gold = _gold_intent_map(args.gold)
    turns, missing = build_turns(results, gold)

    if args.emit_constant:
        if not turns:
            print("MARGIN_LOW unchanged (no clf_* telemetry yet)")
            return 0
        rec = recommend(turns, args.baseline_margin)
        line = f"MARGIN_LOW = {rec.margin_low}"
        if rec.bypass_score is not None:
            line += f"  # + bypass: route when clf_score >= {rec.bypass_score}"
        print(line)
        return 0

    print(format_report(turns, missing, args.baseline_margin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Stats",
    "Turn",
    "build_turns",
    "recommend",
    "simulate",
    "sweep",
]
