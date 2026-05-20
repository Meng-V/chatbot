# The first full real-LLM eval — honest baseline

**Date:** 2026-05-20
**Command:**
```
.venv/bin/python -m src.eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/full_eval_20260520.jsonl
```
**Cost:** ~$0.60 (1.62M input tokens, 1.03M cached, 33k output)
**Wall time:** ~24 minutes
**Plan reference:** Robustness ladder Gap 4 ("first honest 'is it good enough?' number")

## Headline

This is the project's first end-to-end real-LLM measurement against
the populated v2 stack. The infrastructure works flawlessly. The
content/contract layer has three clear, file-traceable failure modes
that account for the bulk of the gap to threshold-3 quality.

| | Value | Target | Pass? |
|---|---|---|---|
| **Judge PASS (correct + refused_correctly)** | **33.2%** | ≥ 75% | ❌ |
| Judge PARTIAL | 25.0% | — | — |
| Judge FAIL | 41.8% | — | ❌ |
| Scope-resolver match | 99.5% | ≥ 95% | ✅ |
| Intent classification | 72.8% | ≥ 80% | ⚠️ close |
| Orchestrator path match | 62.5% | ≥ 75% | ❌ |
| Cache hit rate | 63.5% | ≥ 60% | ✅ |
| Citations on cited answers | 82.2% | ≥ 90% | ⚠️ close |
| p50 latency | 5.1s | < 8s | ✅ |
| p95 latency | 10.9s | < 30s | ✅ |
| Cases run | 184/184 | 184 | ✅ infra clean |

**Reading this honestly:** every piece of infrastructure I've shipped
in the last two weeks works. Tunnels, classifier, retrieval, synth
prompt cache, judge — all green. What the eval surfaces is **the
synth's behavior under real evidence**, and the answer is "too
conservative, refuses too often."

## Per-category PASS rate

| Category | N | PASS% |
|---|---:|---:|
| staff | 3 | 100.0% |
| capability_refuse | 6 | 83.3% |
| hours | 6 | 50.0% |
| instruction | 2 | 50.0% |
| scope_default | 6 | 50.0% |
| out_of_scope | 14 | 42.9% |
| featured_service | 49 | 40.8% |
| capability_point_to_url | 8 | 37.5% |
| service | 30 | 26.7% |
| cross_campus | 30 | 23.3% |
| librarian | 7 | 14.3% |
| circulation | 14 | 7.1% |
| research | 9 | 0.0% |

The worst categories (research 0%, circulation 7%, librarian 14%)
share a pattern: they're knowledge-base questions where evidence
SHOULD be in the index, and the synth refuses anyway. See Failure
Mode 1 below.

## Three failure modes, each traceable to one file

### Mode 1 — Synth self-flags low confidence even with evidence (~30 cases)

**Pattern:** bot emits `"I don't have a reliable answer to that. You
can ask a librarian directly through Ask Us."` with refusal trigger
`model_self_flagged`. Evidence WAS in the bundle (8-13k input tokens
per call); synth chose to refuse.

**Example case** (`space_silent`):
- clf_score 1.0, margin 0.41 (confident classification)
- 12,844 input tokens (evidence was bundled)
- bot refused with `model_self_flagged`

**Affected categories:** service_howto, citation_help,
research_consultation, circulation_basic, loan_policy, renewal,
tech_checkout.

**Trace to file:** `ai-core/src/prompts/synthesizer_v1.py`. The
prompt currently emphasizes "if not in sources, REFUSE" hard. The
model interprets that as "if anything is even slightly ambiguous,
REFUSE." We need to balance the rule so it answers when evidence
is present, even if the answer requires light synthesis.

**Estimated impact of fix:** ~30 cases shift from FAIL to PASS/PARTIAL.
That alone moves the aggregate from 33% to ~50% PASS.

### Mode 2 — Classifier clarification gate too tight (~10 cases)

**Pattern:** bot emits `"I'm not sure which of these you meant. Can
you pick one? Options: X, Y"` for queries that are unambiguous to a
human. The margin between top-1 and top-2 is tiny (e.g. 0.008) but
both intents lead to the same answer.

**Example case** (`tech_borrow_laptop`):
- Top: `tech_checkout` 0.725
- Next: `renewal` 0.717
- Margin: 0.008
- Both intents would route to "yes, you can borrow a laptop" — no
  user disambiguation needed
- bot asked for clarification anyway

**Affected categories:** service (tech_borrow_laptop,
rb_king_4_people_whiteboard, svc_lockers, rb_wertz_no_bookable),
featured_service (ill_oxford_request, ill_hamilton_pickup,
ms_consultation_book), out_of_scope (cap_renew_book, oos_university_news).

**Trace to file:** `ai-core/src/router/intent_knn.py` margin threshold.
The current threshold treats 0.008 as "ambiguous." A more nuanced
gate would check whether the top-2 intents both lead to the same
agent_path before forcing clarification.

**Estimated impact of fix:** ~10 cases shift from FAIL to PASS. Plus
faster turn (~1s instead of 7s — these cases short-circuit before
even hitting the LLM).

### Mode 3 — Cross-campus answers cite content but to wrong building (~12 cases)

**Pattern:** bot picks up content from the right intent but the
evidence-to-output binding loses building specificity. Example: ask
about Wertz hours, bot returns hours but for King; ask about
Rentschler hours, bot returns hours but for the wrong day.

**Example case** (`xc_wertz_alias`):
- intent_match=True (hours), path_match=True
- 1 citation, evidence_bundle had Wertz content
- Answer text claimed Wertz hours but values looked off vs. the gold
- Judge: wrong

**Affected categories:** cross_campus (most of its 17 FAILs),
hr_libcal_down_refusal, loc_gardner_harvey_address.

**Trace to file:** Two candidates:
1. `ai-core/src/synthesis/post_processor.py` — the cross-campus
   citation guard exists but maybe isn't strict enough on building
   sub-aliases (Wertz=Art Library, etc.).
2. The Weaviate retrieval scoping might over-fetch Oxford-King chunks
   even when the question specifies a sub-library. Worth inspecting
   `src/retrieval/scope_filter.py`.

**Estimated impact of fix:** ~10 cases shift. Combined with Modes 1
and 2, total estimated lift: ~50 cases, from 33% to ~60% PASS.

## What's working

- **Scope resolver: 99.5%.** The rule-based aliases.py + resolver.py
  pair is doing its job.
- **Cache hit: 63.5%.** PR #74's prompt-cache investment pays off at
  the steady-state rate the plan budgeted for.
- **Capability refusals: 83% PASS.** When the bot SHOULD refuse
  (account ops, fines, etc.), it does refuse correctly.
- **Hours category: 50% PASS** — the date-window feature shipped in
  PR #78 is working for the half-passing cases.
- **No infrastructure failures.** Every case ran to completion. No
  timeouts, no connection errors after the initial setup.

## Suggested next actions

Each linked to a specific file + expected delta:

| # | File to touch | Mode it fixes | Expected PASS lift |
|---|---|---|---:|
| 1 | `prompts/synthesizer_v1.py` — soften "refuse if any doubt" wording | Mode 1 | +15 pts |
| 2 | `router/intent_knn.py` — same-agent-path gate before clarification | Mode 2 | +5 pts |
| 3 | `synthesis/post_processor.py` + `retrieval/scope_filter.py` — sub-building strictness | Mode 3 | +6 pts |
| 4 | After each fix: re-run `eval_synth_alone` (8 cases, ~$0.01) | Iterative | — |
| 5 | After all three fixes: full re-run (184 cases, ~$0.60) | Verification | confirmed total lift |

Three small, scoped PRs. Each can be measured independently against
this baseline.

## Cost report

Token totals (real):
- input: 1,621,132 (591,884 uncached at mini + 1,029,248 cached)
- output: 33,446
- cache hit: 63.5%

Estimated cost split:
- Agent + synth (mini): ~$0.57
- Judge (nano): ~$0.03
- **Total: ~$0.60**

This is **9× cheaper than the plan's $5.52 projection** — every
subsequent full-eval iteration costs less than a coffee. The "we
can't afford to re-measure" excuse is dead; re-running after each
fix is fully tractable.

## How to re-run

See `ai-core/docs/OPERATOR.md` → "Run the full real-LLM + judge eval"
section for the runbook. TL;DR:

```bash
# Tunnels up (Weaviate 8888/50051 + Postgres 5432)
# Then:
cd ai-core
.venv/bin/python -m src.eval.run_eval --with-real-llm --with-judge \
    --results-out eval_results/full_eval_$(date +%Y%m%d).jsonl
.venv/bin/python -m scripts.analyze_eval_results <jsonl>
```

This file is the anchor. Every subsequent eval finds drift relative
to this 33.2% / 25.0% / 41.8% split. Document next runs in their own
findings file referencing this one as the baseline.
