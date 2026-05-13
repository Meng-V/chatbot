# kNN threshold sweep — `SCORE_FLOOR` × `MARGIN_LOW`

**Date:** 2026-05-13
**Command:** `python -m scripts.sweep_thresholds --floor-step 0.05 --margin-step 0.01`
**Cost:** zero — all embeddings cached, sweep is a single numpy matmul + 45 threshold-check cells.
**Runtime:** ~2 seconds end-to-end.

## What this measures

Three classifier thresholds today (`src/router/intent_knn.py`):

```python
SCORE_FLOOR = 0.50   # top-1 score below this -> out_of_scope override
MARGIN_LOW  = 0.05   # margin below this -> needs_clarification flag
MARGIN_HIGH = 0.10   # margin above this -> confident routing (not swept)
```

The values were calibrated by eyeballing v1 baseline misses (see
`2026-05-13_v38_classifier.md`). This sweep validates them empirically
against the corrected gold set (184 cases) and reports:

- **strict accuracy** — top-1 intent matches expected
- **effective accuracy** — strict + would-clarify (margin too narrow,
  orchestrator asks user)
- **false-clarify rate** — % of correct top-1 picks that needlessly
  trigger a clarification prompt. The UX cost of widening
  `MARGIN_LOW`.

## Effective accuracy by threshold

```
  SCORE_FLOOR MARGIN=0.02  MARGIN=0.03  MARGIN=0.04  MARGIN=0.05  MARGIN=0.06  MARGIN=0.07  MARGIN=0.08  MARGIN=0.09  MARGIN=0.10
  ------------------------------------------------------------------------------------------------------------------------------------------
  0.40            79.3%        79.9%        82.1%        83.2%        84.8%        85.9%        88.6%        90.8%        90.8%
  0.45            79.9%        79.9%        82.1%        83.2%        84.8%        85.9%        88.6%        90.8%        90.8%
  0.50            79.3%        79.9%        82.1%        83.2%        84.8%        85.9%        88.6%        90.8%        90.8%
  0.55            79.3%        79.9%        82.1%        83.2%        84.8%        85.9%        88.6%        90.8%        90.8%
  0.60            77.7%        78.3%        81.0%        82.1%        83.2%        84.8%        87.5%        90.2%        90.2%
```

## False-clarify rate

```
  SCORE_FLOOR MARGIN=0.02  MARGIN=0.03  MARGIN=0.04  MARGIN=0.05  MARGIN=0.06  MARGIN=0.07  MARGIN=0.08  MARGIN=0.09  MARGIN=0.10
  ------------------------------------------------------------------------------------------------------------------------------------------
  0.40             8.5%        11.5%        15.4%        19.2%        19.2%        23.1%        26.2%        30.0%        35.4%
  0.45             8.4%        12.2%        16.0%        19.8%        19.8%        23.7%        26.7%        30.5%        35.9%
  0.50             8.5%        11.5%        15.4%        19.2%        19.2%        23.1%        26.2%        30.0%        35.4%
  0.55             7.0%        10.2%        14.1%        18.0%        18.0%        21.9%        25.0%        28.9%        34.4%
  0.60             7.2%        10.4%        13.6%        17.6%        18.4%        21.6%        24.8%        28.0%        33.6%
```

## Interpretation

**`SCORE_FLOOR` matters very little in the 0.40–0.55 band.** Effective
accuracy is flat across these floor values for any given `MARGIN_LOW`.
The current 0.50 is fine. Bumping to 0.60 starts to hurt slightly
(-1.0pp effective) because a few real library questions with weak
matches get incorrectly routed to `out_of_scope`.

**`MARGIN_LOW` dominates the effective-vs-strict trade-off.** Widening
from 0.05 to 0.10:
- Effective accuracy: 83.2% → 90.8% (+7.6pp)
- Strict accuracy: 70.7% → 70.7% (unchanged — it's a coarsening, not
  a better top-1 pick)
- False-clarify rate: 19.2% → 35.4% (+16.2pp)

So the trade is "more conservative top-1 commitments → more
clarification prompts on correct answers". Whether that's worth it
depends on how annoying users find a "did you mean X or Y?" prompt.

## Recommendation

**Keep current defaults (SCORE_FLOOR=0.50, MARGIN_LOW=0.05) until we
have real traffic to A/B test against.** Rationale:

1. The 184-case gold set isn't big enough to overcome the 35%
   false-clarify cost at MARGIN_LOW=0.10. Real users see 1000s of
   questions; a 1-in-3 spurious-prompt rate would hurt trust faster
   than the +7.6pp recall would build it.
2. The orchestrator already handles narrow-margin cases reasonably
   — the agent's run-tools logic can disambiguate via context.
3. Tuning thresholds against gold-set effective accuracy directly
   incentivizes gaming the metric (widen margin → more clarifies
   → higher effective). A/B against real user satisfaction is the
   honest gate.

If a future iteration wants to tune empirically, the next step is to
add a `--margin-low` parameter to `intent_knn.classify` and run a
shadow-mode A/B for 1-2 weeks comparing thumb-up rate at
MARGIN_LOW=0.05 vs 0.07.

## Possible follow-up: per-intent margin

The sweep treats `MARGIN_LOW` as a global constant. Per-intent margin
(e.g., 0.02 for `out_of_scope`, 0.10 for `hours`) might give better
trade-offs but requires a different sweep shape. Out of scope for
this report.

## Reproducing

```sh
# From ai-core/
python -m scripts.sweep_thresholds                          # default grid
python -m scripts.sweep_thresholds --margin-step 0.01       # finer margin grid
python -m scripts.sweep_thresholds --json                   # machine-readable
```

The sweep depends on the embedding cache at
`data/eval/classifier_embeddings.json`. Run `scripts/eval_classifier_v38.py`
once first to populate it (~75 s, ~$0.05 one-time).
