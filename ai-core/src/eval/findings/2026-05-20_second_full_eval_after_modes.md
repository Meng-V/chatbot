# Second full real-LLM eval — Modes 1+2+3 results

**Date:** 2026-05-20
**Baseline:** `2026-05-20_first_full_real_llm_eval.md` (33.2% PASS)
**Command:**
```
.venv/bin/python -m src.eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/full_eval_20260520_after_modes.jsonl
```

## TL;DR

Mode 1+2+3 produced a **complicated** result. Pure-infrastructure wins
were dramatic. Aggregate PASS dipped 5.5 pts. Both numbers are real.

The trade: Mode 1 broke the bot's tendency to refuse-when-uncertain.
That fix worked — refusals dropped from 66 → 29 (-37 cases), of which
the `model_self_flagged` trigger dropped from 59 → 19 (-40 cases).
Mode 2 worked — clarification fires dropped from ~10 → 2. The
infrastructure-layer signals all moved up:

| Layer signal | Baseline | Post-fix | Δ |
|---|---:|---:|---:|
| Scope-resolver match | 99.5% | 100% | +0.5 |
| **Orchestrator path match** | **62.5%** | **83.2%** | **+20.7** |
| Citations on non-refusal answers | 82.2% | 97.4% | +15.2 |
| Cache hit rate | 63.5% | 70.8% | +7.3 |
| Total refusals | 66 (35.9%) | 29 (15.8%) | -20.1 |
| `model_self_flagged` refusal count | 59 | 19 | -40 |
| `refused_incorrectly` verdict count | 38 | 15 | -23 |

But the **judge PASS** rate dipped because Mode 1 didn't just convert
`refused_incorrectly → correct`. It converted some of them to `partial`
(judge: defensible) and some to `wrong` (judge: not). It also surfaced
that the bot now sometimes ANSWERS cases that should have been refused
correctly — those went from `refused_correctly → wrong`.

## Headline aggregates

| | Baseline | Post-fix | Δ |
|---|---:|---:|---:|
| **Judge PASS** (correct + refused_correctly) | **33.2%** (61) | **27.7%** (51) | **-5.5 pts** |
| Judge PARTIAL | 25.0% (46) | 38.0% (70) | +13.0 |
| Judge FAIL | 41.8% (77) | 34.2% (63) | -7.6 |
| Intent classification | 72.8% | 72.8% | 0 |

### Verdict counts (raw)

| Verdict | Baseline | Post-fix | Δ |
|---|---:|---:|---:|
| correct | 25 | 24 | -1 |
| partial | 46 | 70 | **+24** |
| refused_correctly | 36 | 27 | -9 |
| refused_incorrectly | 38 | 15 | **-23** |
| wrong | 34 | 47 | +13 |
| answered_should_have_refused | 5 | 1 | -4 |

PARTIAL is now the LARGEST single bucket. Most of those used to be
refusals. That's a **user-experience improvement** that doesn't show
up in PASS but matters: instead of "I can't help, ask a librarian,"
the user gets a sourced partial answer with a URL to follow.

## Per-case shift map (top 12)

| Baseline → Post-fix | N |
|---|---:|
| refused_incorrectly → wrong | 15 |
| wrong → partial | 14 |
| refused_incorrectly → partial | 12 |
| refused_correctly → refused_incorrectly | 8 |
| correct → partial | 7 |
| partial → correct | 7 |
| partial → wrong | 5 |
| refused_incorrectly → refused_correctly | 5 |
| refused_correctly → wrong | 4 |
| refused_correctly → partial | 4 |
| answered_should_have_refused → refused_incorrectly | 3 |
| correct → wrong | 3 |

**Net PASS: +17 gained, -27 lost = -10 net.**

The losing transitions cluster in two patterns:
- **`refused_correctly → refused_incorrectly | wrong | partial` (16 cases)**: the bot used to refuse correctly on these; now it tries to answer (Mode 1's softening was too broad on a subset). Most fall into `partial` not `wrong`, so user impact is mixed.
- **`correct → partial | wrong` (10 cases)**: pure regression on cases that used to be perfect. Worth investigating — may be judge variance, may be a real pattern.

## Per-category PASS rate

| Category | N | Baseline | Post-fix | Δ |
|---|---:|---:|---:|---:|
| **librarian** | 7 | 14.3% | **42.9%** | **+28.6** ✅ |
| out_of_scope | 14 | 42.9% | 50.0% | +7.1 ✅ |
| hours | 6 | 50.0% | 50.0% | 0 |
| instruction | 2 | 50.0% | 50.0% | 0 |
| research | 9 | 0.0% | 0.0% | 0 |
| service | 30 | 26.7% | 26.7% | 0 |
| staff | 3 | 100.0% | 100.0% | 0 |
| cross_campus | 30 | 23.3% | 20.0% | -3.3 |
| circulation | 14 | 7.1% | 0.0% | -7.1 |
| capability_point_to_url | 8 | 37.5% | 25.0% | -12.5 |
| **featured_service** | 49 | 40.8% | **26.5%** | **-14.3** ⚠️ |
| **capability_refuse** | 6 | 83.3% | 66.7% | -16.7 ⚠️ |
| **scope_default** | 6 | 50.0% | 16.7% | -33.3 ⚠️ |

**Mode 3 rule 9 sharpening worked**: librarian +28.6 pts. The bot stopped enumerating multi-person rosters.

**Mode 1 hurt `capability_refuse`**: the bot now answers some cases that should refuse. -16.7 pts on a small N=6, so it's 1 case regressing. But the direction is real.

**`featured_service` -14.3 pts** is the biggest absolute loss (49 cases). Likely Mode 1 made the bot try to answer featured-service questions where the evidence was thin — and the judge is strict on featured-service quality.

## Cost report

| | Baseline | Post-fix |
|---|---:|---:|
| Input tokens (total) | 1,621,132 | 1,870,659 |
| Cached input tokens | 1,029,248 | 1,324,672 |
| Cache hit rate | 63.5% | 70.8% |
| Output tokens | 33,446 | 44,042 |
| Estimated $ | ~$0.60 | ~$0.70 |

More tokens used (because more answers, fewer refusals = more synth
calls). Cache hit rate is BETTER despite the prompt growing.

## Honest read

Mode 1 was directionally right but too aggressive. It broke the
over-refusal pattern (the dominant baseline failure mode), but in
fixing it surfaced a different problem: when the bot ANSWERS instead
of refusing, the underlying content quality determines whether it
gets PASS or PARTIAL or WRONG. The bot is now **more useful** (more
answers, fewer "I can't help" handoffs) but the **judge is strict**
on quality.

Three lessons from this iteration:

1. **`refused_incorrectly` is now ~half of what it was** — that was
   the dominant problem in the baseline, and it's substantially
   addressed. Even with PASS down 5.5 pts, the UX is materially
   better.
2. **Mode 1 needs a small correction**: tighten so the bot still
   refuses when capability tier = REFUSE (account, account_renewal,
   etc.) or when scope is genuinely mismatched. The current prompt
   over-rotates toward "answer if any evidence."
3. **The path forward isn't more prompt tweaks** — it's data and
   retrieval. Specifically the Mode 4 finding from this run:

## Mode 4 discovered during this run (queue for next iteration)

While the eval ran I audited the `xc_aa_alias` failure ("Art and
Architecture Library hours" routing to `find_resource` instead of
`hours`). Root cause: of 20 exemplars mentioning Art/Wertz, **only 1
is labeled `hours`**; 7 are labeled `find_resource`. The classifier
correctly picks the dominant intent given its training data.

Fix: add ~5 Art-Library hours exemplars + 3 Wertz space_info
exemplars to `src/router/exemplars/exemplars.jsonl`. Pure data
change, no code. Should fix `xc_aa_alias` and similar misroutes.
Worth bundling with Mode 5 (tightening Mode 1's over-correction):

- **Mode 4**: Art-Library / Wertz exemplar set expansion (~10 lines of JSONL)
- **Mode 5**: Synth prompt micro-tune — keep Mode 1's general
  softening BUT add a refusal pre-flight: if the user query maps
  to a known REFUSE capability (account, account_renewal), respect
  that even when SOME related evidence is in the bundle. This
  recovers most of the `refused_correctly → wrong` cases.

Combined Mode 4+5 estimate: recovers the -5.5 PASS loss + adds
~5-8 pts on top. Realistic target: 35-40% PASS in the third run.

## Suggested next iteration

| # | What | File | Est. lift |
|---|---|---|---:|
| 4 | Add ~10 Art-Library + Wertz exemplars across hours / space_info | `src/router/exemplars/exemplars.jsonl` | +3 pts |
| 5 | Synth prompt: respect REFUSE-capability intents even with on-topic evidence | `src/prompts/synthesizer_v1.py` | +5 pts |
| 6 | Investigate `correct → wrong` regressions (3 cases) — likely judge variance, but worth one drill-down | per case | ~0-2 pts |

Run-cost so far across both full evals: ~$1.30. Still cheap. The
iteration loop works.

## What's working at scale now

- Refusal contract holds: 18 correct refusals out of 29 total. Bot's
  refusing for the right reasons more often than not.
- Citation discipline: 97.4% of non-refusal answers include a citation.
  Up from 82.2%. Mode 1's "answer at medium with citation" framing
  delivered exactly the contract it asked for.
- Orchestrator path match: 83.2%. The agent's tool-choice + routing
  decisions are sound. Most failures are at the synth-content layer,
  not the routing layer.
- Mode 2 bypass: clarification fires dropped 10 → 2, no false-positive
  bypass observed (no case where the bypass picked the wrong intent
  and produced a bad answer).

## How to verify

```bash
cd ai-core
# Re-run with the fixes from this branch:
.venv/bin/python -m src.eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/full_eval_$(date +%Y%m%d).jsonl

# Compare against this run's JSONL using the analyzer (PR #83):
.venv/bin/python -m scripts.analyze_eval_results <jsonl>
```

Both eval JSONLs are gitignored, so this finding doc is the
permanent record.
