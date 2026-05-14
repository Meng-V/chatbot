"""
Empirical parameter sweep for the kNN classifier's threshold constants.

Today's defaults in src/router/intent_knn.py:
    SCORE_FLOOR = 0.50   # below: override to out_of_scope
    MARGIN_LOW  = 0.05   # below: flag needs_clarification
    MARGIN_HIGH = 0.10   # above: confident routing (not swept)

These were calibrated by eyeballing v1 baseline misses. This script
does the empirical version: classify every gold question across a
grid of (SCORE_FLOOR, MARGIN_LOW) values and report effective
accuracy (correct + would-clarify) for each cell.

Why effective accuracy:
  Strict accuracy = top-1 intent matches expected.
  Effective accuracy = correct OR (top-1 wrong AND margin <
    MARGIN_LOW). In production the orchestrator turns the second
    case into a clarification chip ("did you mean X or Y?") so it's
    recoverable, not a silent miss.

Cost / runtime:
  Zero -- all exemplar + gold-question embeddings are cached at
  data/eval/classifier_embeddings.json. The sweep just iterates
  cosine math + threshold checks.

Usage:
    python -m scripts.sweep_thresholds                  # default grid
    python -m scripts.sweep_thresholds --floor-min 0.45 --floor-max 0.55
    python -m scripts.sweep_thresholds --json           # machine-readable

See plan: Layer 3 -> "Confidence gates" -- the doc said "tuned values
from the plan" but never showed the sweep that justifies them.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Allow `python -m scripts.sweep_thresholds` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

import numpy as np  # noqa: E402

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402
from src.router.intent_knn import (  # noqa: E402
    Exemplar,
    load_exemplars_from_disk,
)

logger = logging.getLogger("sweep_thresholds")

_CACHE_PATH = _AI_CORE / "data" / "eval" / "classifier_embeddings.json"


# --- Vectorized classification ------------------------------------------
#
# The sweep evaluates ~25 (floor, margin) cells. Pure-Python cosine
# would take ~25 minutes. numpy turns it into one matrix multiply
# (~0.5s on a 184x5358x3072 product) plus per-cell threshold checks.


@dataclass
class _PrecomputedScores:
    """Per-gold-question top-1 intent + margin, independent of floor.

    The floor changes only the override-to-out_of_scope decision; the
    underlying per-intent ranking is the same. Precomputing this once
    lets each sweep cell evaluate in O(N) instead of O(N * exemplars).
    """
    top_intent: list[str]
    top_score: list[float]
    margin: list[float]


def _precompute_scores(
    exemplars: list[Exemplar],
    queries: list[tuple[GoldQuestion, list[float]]],
) -> _PrecomputedScores:
    """Run all (gold question, exemplar) cosine pairs in one numpy mul.

    Returns the per-question (top_intent, top_score, margin) -- the
    raw kNN output WITHOUT any score-floor override. The sweep then
    applies floor + margin thresholds per cell.
    """
    # Stack into matrices and normalize. text-embedding-3-large is
    # supposed to be L2-normalized by OpenAI but explicit
    # normalization is cheap insurance.
    exemplar_mat = np.asarray([ex.vector for ex in exemplars], dtype=np.float32)
    query_mat = np.asarray([qv for _q, qv in queries], dtype=np.float32)
    exemplar_mat /= np.linalg.norm(exemplar_mat, axis=1, keepdims=True) + 1e-12
    query_mat /= np.linalg.norm(query_mat, axis=1, keepdims=True) + 1e-12

    # (n_queries, n_exemplars) cosine matrix in one mul.
    sims = query_mat @ exemplar_mat.T  # shape: (Q, E)

    # Per-intent best score per query. Group exemplar columns by
    # intent and reduce-max within each group.
    intents = [ex.intent for ex in exemplars]
    unique_intents = sorted(set(intents))
    intent_to_idx = {i: k for k, i in enumerate(unique_intents)}
    # Column index = exemplar position; map each to its intent's row index.
    col_to_intent_idx = np.asarray(
        [intent_to_idx[i] for i in intents], dtype=np.int32
    )

    # per_intent_max[q, intent_idx] = best score for that intent.
    n_q = sims.shape[0]
    n_intent = len(unique_intents)
    per_intent_max = np.full((n_q, n_intent), -np.inf, dtype=np.float32)
    # np.maximum.at is unbuffered scatter-max -- handles duplicates
    # in col_to_intent_idx by taking the max per (q, intent).
    np.maximum.at(per_intent_max, (slice(None), col_to_intent_idx), sims)

    # Top-1 intent + score, runner-up score, margin.
    sorted_idx = np.argsort(-per_intent_max, axis=1)
    top_idx = sorted_idx[:, 0]
    runner_idx = sorted_idx[:, 1] if per_intent_max.shape[1] > 1 else top_idx
    top_score = per_intent_max[np.arange(n_q), top_idx]
    runner_score = (
        per_intent_max[np.arange(n_q), runner_idx]
        if per_intent_max.shape[1] > 1 else np.zeros(n_q, dtype=np.float32)
    )
    margin = top_score - runner_score
    top_intent_names = [unique_intents[i] for i in top_idx.tolist()]

    return _PrecomputedScores(
        top_intent=top_intent_names,
        top_score=top_score.tolist(),
        margin=margin.tolist(),
    )


def _apply_thresholds(
    pre: _PrecomputedScores,
    queries: list[tuple[GoldQuestion, list[float]]],
    score_floor: float,
    margin_low: float,
) -> tuple[int, int, int, int]:
    """Apply (floor, margin) to the precomputed scores. Returns
    (strict_correct, clarify_recovered, silent_wrong, false_clarify)."""
    strict = clarify = silent = false_clarify = 0
    for (q, _qv), top_intent, top_score, m in zip(
        queries, pre.top_intent, pre.top_score, pre.margin
    ):
        # Floor override matches the prod code in intent_knn.py.
        final_intent = "out_of_scope" if top_score < score_floor else top_intent
        narrow = m < margin_low
        if final_intent == q.intent:
            strict += 1
            if narrow:
                # Correct, but margin too narrow -> orchestrator
                # would ask user to disambiguate. UX cost.
                false_clarify += 1
        elif narrow:
            clarify += 1
        else:
            silent += 1
    return strict, clarify, silent, false_clarify


# --- Sweep loop ---------------------------------------------------------


@dataclass(frozen=True)
class _SweepCell:
    score_floor: float
    margin_low: float
    strict_correct: int
    clarify_recovered: int
    """Wrong top-1, margin < margin_low -> user disambiguates."""
    silent_wrong: int
    """Wrong top-1, margin >= margin_low -> silent failure."""
    false_clarify: int
    """Correct top-1, margin < margin_low -> bot needlessly asks
    "did you mean X or Y?" when top-1 was already right.
    This is the UX cost of widening MARGIN_LOW: more clarification
    prompts on questions the bot could have answered directly."""
    total: int

    @property
    def strict_pct(self) -> float:
        return 100 * self.strict_correct / self.total if self.total else 0.0

    @property
    def effective_pct(self) -> float:
        return (
            100 * (self.strict_correct + self.clarify_recovered) / self.total
            if self.total
            else 0.0
        )

    @property
    def false_clarify_pct(self) -> float:
        """% of CORRECT top-1 picks that would needlessly trigger a
        clarification prompt. The lower the better."""
        return (
            100 * self.false_clarify / self.strict_correct
            if self.strict_correct
            else 0.0
        )


def _hash_text(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _build_corpus() -> tuple[list[Exemplar], list[tuple[GoldQuestion, list[float]]]]:
    """Load exemplars + gold questions, attach cached vectors.

    Returns (exemplars_with_vectors, [(gold_question, query_vector), ...]).
    Misses (text not in cache) raise -- the sweep is meant to be
    cheap; if there are misses, run `scripts/eval_classifier_v38.py`
    first to populate the cache.
    """
    if not _CACHE_PATH.exists():
        raise RuntimeError(
            f"embedding cache not found at {_CACHE_PATH}. "
            f"Run `python -m scripts.eval_classifier_v38` once to "
            f"populate it (~75s, ~$0.05)."
        )
    cache: dict[str, list[float]] = json.loads(
        _CACHE_PATH.read_text(encoding="utf-8")
    )

    pairs = load_exemplars_from_disk()
    exemplars: list[Exemplar] = []
    misses = []
    for intent, text in pairs:
        h = _hash_text(text)
        if h not in cache:
            misses.append(text[:60])
            continue
        exemplars.append(Exemplar(intent=intent, text=text, vector=cache[h]))
    if misses:
        raise RuntimeError(
            f"{len(misses)} exemplar embeddings missing from cache; "
            f"first miss: {misses[0]!r}. "
            f"Run `python -m scripts.eval_classifier_v38 --no-cache` "
            f"to repopulate."
        )

    questions = load_golden_set()
    queries: list[tuple[GoldQuestion, list[float]]] = []
    for q in questions:
        h = _hash_text(q.question)
        if h not in cache:
            raise RuntimeError(
                f"gold question {q.id!r} embedding missing from cache. "
                f"Run `python -m scripts.eval_classifier_v38` to repopulate."
            )
        queries.append((q, cache[h]))
    return exemplars, queries


def sweep(
    score_floors: list[float],
    margin_lows: list[float],
) -> list[_SweepCell]:
    """Run the sweep. Returns one _SweepCell per (floor, margin) pair."""
    exemplars, queries = _build_corpus()
    logger.info(
        "sweeping %d cells x %d gold cases (%d exemplars, vectorized)",
        len(score_floors) * len(margin_lows), len(queries), len(exemplars),
    )

    # One numpy mul produces all (query, exemplar) cosines and per-
    # intent best scores. Sweep cells then just apply threshold
    # checks against these precomputed scores -- O(cells * queries)
    # instead of O(cells * queries * exemplars).
    pre = _precompute_scores(exemplars, queries)
    logger.info("scores precomputed; iterating threshold cells")

    cells: list[_SweepCell] = []
    for floor in score_floors:
        for margin in margin_lows:
            strict, clarify, silent, false_clarify = _apply_thresholds(
                pre, queries, floor, margin,
            )
            cells.append(_SweepCell(
                score_floor=floor,
                margin_low=margin,
                strict_correct=strict,
                clarify_recovered=clarify,
                silent_wrong=silent,
                false_clarify=false_clarify,
                total=len(queries),
            ))
    return cells


# --- Report -------------------------------------------------------------


def _find_nearest(cells: list[_SweepCell], floor: float, margin: float) -> _SweepCell:
    """Pick the cell whose (floor, margin) is closest to the target.
    Handles cases where production values aren't on the grid."""
    return min(
        cells,
        key=lambda c: (c.score_floor - floor) ** 2 + (c.margin_low - margin) ** 2,
    )


def _print_grid(cells: list[_SweepCell], current_floor: float, current_margin: float) -> None:
    """Render two 2D grids: effective accuracy + false-clarify rate."""
    floors = sorted({c.score_floor for c in cells})
    margins = sorted({c.margin_low for c in cells})
    by_pair = {(c.score_floor, c.margin_low): c for c in cells}

    print()
    print("Effective accuracy (correct + would-clarify) % by threshold:")
    print()
    print(f"  {'SCORE_FLOOR':<11s} ", end="")
    for m in margins:
        print(f"MARGIN={m:.2f}  ", end="")
    print()
    print("  " + "-" * (12 + len(margins) * 14))
    for f in floors:
        print(f"  {f:<11.2f}", end="")
        for m in margins:
            cell = by_pair[(f, m)]
            print(f"    {cell.effective_pct:>5.1f}%   ", end="")
        print()

    print()
    print("False-clarify rate (% of CORRECT answers that would "
          "needlessly trigger a 'did you mean' prompt -- lower is better):")
    print()
    print(f"  {'SCORE_FLOOR':<11s} ", end="")
    for m in margins:
        print(f"MARGIN={m:.2f}  ", end="")
    print()
    print("  " + "-" * (12 + len(margins) * 14))
    for f in floors:
        print(f"  {f:<11.2f}", end="")
        for m in margins:
            cell = by_pair[(f, m)]
            print(f"    {cell.false_clarify_pct:>5.1f}%   ", end="")
        print()


def _summarize(cells: list[_SweepCell], current_floor: float, current_margin: float) -> None:
    """Pick out the production cell + best candidates by different
    selection criteria, then recommend a change (or not)."""
    current = _find_nearest(cells, current_floor, current_margin)

    # "Best" depends on what we optimize for:
    #   - best_effective: pure effective accuracy (allows lots of clarifies)
    #   - best_balanced: effective - 0.5*false_clarify_pct (penalize spurious prompts)
    #   - best_strict: highest top-1 match rate
    best_effective = max(cells, key=lambda c: c.effective_pct)
    best_balanced = max(
        cells,
        key=lambda c: c.effective_pct - 0.5 * c.false_clarify_pct,
    )
    best_strict = max(cells, key=lambda c: c.strict_pct)

    print()
    print("Highlights:")
    print(
        f"  Current production (floor={current_floor:.2f}, margin={current_margin:.2f}):"
    )
    print(
        f"    strict={current.strict_pct:.1f}%  effective={current.effective_pct:.1f}%  "
        f"false_clarify={current.false_clarify_pct:.1f}%"
    )
    print(
        f"    correct={current.strict_correct} clarify={current.clarify_recovered} "
        f"silent_wrong={current.silent_wrong} false_clarify={current.false_clarify}"
    )

    def _line(label: str, c: _SweepCell) -> None:
        print(
            f"  {label} (floor={c.score_floor:.2f}, margin={c.margin_low:.2f}): "
            f"strict={c.strict_pct:.1f}%  effective={c.effective_pct:.1f}%  "
            f"false_clarify={c.false_clarify_pct:.1f}%"
        )

    _line("Best effective:    ", best_effective)
    _line("Best strict:       ", best_strict)
    _line("Best balanced:     ", best_balanced)
    print()
    print(
        "  (balanced score = effective - 0.5*false_clarify -- "
        "discourages widening MARGIN_LOW just to game effective acc)"
    )

    # Recommendation: only suggest a change if balanced improves
    # by >=1pp. Avoids churn over tiny differences and respects the
    # UX cost of more clarification prompts.
    cur_balanced = current.effective_pct - 0.5 * current.false_clarify_pct
    best_balanced_score = (
        best_balanced.effective_pct - 0.5 * best_balanced.false_clarify_pct
    )
    delta_balanced = best_balanced_score - cur_balanced
    print()
    if delta_balanced >= 1.0:
        print(
            f"  -> Recommendation: try "
            f"SCORE_FLOOR={best_balanced.score_floor:.2f}, "
            f"MARGIN_LOW={best_balanced.margin_low:.2f}. "
            f"Balanced score +{delta_balanced:.1f}pp."
        )
    else:
        print(
            f"  -> No threshold change recommended. "
            f"Current is within {delta_balanced:.1f}pp of best balanced "
            f"cell -- not worth churning."
        )


# --- Entrypoint ---------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--floor-min", type=float, default=0.40,
        help="Minimum SCORE_FLOOR to sweep (default 0.40).",
    )
    parser.add_argument(
        "--floor-max", type=float, default=0.60,
        help="Maximum SCORE_FLOOR to sweep (default 0.60).",
    )
    parser.add_argument(
        "--floor-step", type=float, default=0.05,
        help="SCORE_FLOOR grid spacing (default 0.05).",
    )
    parser.add_argument(
        "--margin-min", type=float, default=0.02,
        help="Minimum MARGIN_LOW to sweep (default 0.02).",
    )
    parser.add_argument(
        "--margin-max", type=float, default=0.10,
        help="Maximum MARGIN_LOW to sweep (default 0.10).",
    )
    parser.add_argument(
        "--margin-step", type=float, default=0.02,
        help="MARGIN_LOW grid spacing (default 0.02).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of human-readable grid (for plotting/dashboards).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Build the grid. `arange`-like but using a simple list to avoid
    # numpy dep + handle floating-point creep cleanly.
    def _grid(lo: float, hi: float, step: float) -> list[float]:
        out: list[float] = []
        v = lo
        while v <= hi + 1e-9:
            out.append(round(v, 4))
            v += step
        return out

    score_floors = _grid(args.floor_min, args.floor_max, args.floor_step)
    margin_lows = _grid(args.margin_min, args.margin_max, args.margin_step)

    cells = sweep(score_floors, margin_lows)

    if args.json:
        out = [
            {
                "score_floor": c.score_floor,
                "margin_low": c.margin_low,
                "strict_correct": c.strict_correct,
                "clarify_recovered": c.clarify_recovered,
                "silent_wrong": c.silent_wrong,
                "total": c.total,
                "strict_pct": c.strict_pct,
                "effective_pct": c.effective_pct,
            }
            for c in cells
        ]
        print(json.dumps(out, indent=2))
        return 0

    # Pull current production values from intent_knn so the report
    # marks them automatically -- no risk of a stale constant here.
    from src.router.intent_knn import MARGIN_LOW as _CUR_MARGIN
    from src.router.intent_knn import SCORE_FLOOR as _CUR_FLOOR
    _print_grid(cells, current_floor=_CUR_FLOOR, current_margin=_CUR_MARGIN)
    _summarize(cells, current_floor=_CUR_FLOOR, current_margin=_CUR_MARGIN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
