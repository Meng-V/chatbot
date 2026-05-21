# Synthesizer-alone quality eval — first real measurement

**Date:** 2026-05-20
**Tool:** `ai-core/scripts/eval_synth_alone.py`
**Cases:** 6 hand-curated, covering featured services + tech checkout
**Cost:** ~$0.009 in API spend (synth + judge combined)
**Plan reference:** Robustness ladder Gap 4 (real-LLM measurement)

## Why this instead of the full eval

The full `run_eval --with-real-llm --with-judge` needs Weaviate up (the
classifier loads exemplar embeddings from it). Weaviate is under
construction. This script bypasses retrieval entirely — gives the
synthesizer hand-curated "good retrieval" evidence and watches its
real output, scored by the real judge.

What this proves: GIVEN good retrieval, does the synthesizer produce
grounded, cited, contract-respecting answers?
What this does NOT prove: retrieval quality. That needs Weaviate.

## Results

| # | Case | Verdict | Citation validity | Notes |
|---|---|---|---|---|
| 1 | `fs_makerspace_3d` | **partial** | some_invalid | Substance right, didn't cite the LibGuide URL specifically |
| 2 | `fs_nyt_subscription` | **correct** | all_valid | Clean — caught the on-campus-only activation rule |
| 3 | `fs_ill_oxford` | **partial** | some_invalid | Implies bot is "part of submission guidance" — roleplay leak |
| 4 | `fs_adobe_unspecified` | **wrong** | no_citations | Cited a URL not in evidence (judge flag) |
| 5 | `fs_special_collections` | **correct** | all_valid | Correctly noted King-only + appointment |
| 6 | `tech_borrow_laptop` | **correct** | all_valid | Got both checkout periods + ID requirement |

**5/6 passed** (counting `partial` as PASS since the substance was
defensible).

## Token / cache / latency

| Metric | Value |
|---|---|
| Synth input tokens | 20,457 |
| Synth cached tokens | 16,896 |
| **Cache hit rate** | **82.6%** |
| Synth output tokens | 744 |
| Avg synth latency | 1378 ms |
| Avg judge latency | 1176 ms |
| **Total LLM cost** | **~$0.009** |

Cache rate (82.6%) is consistent with the dedicated cache-verify run
(91% on synth alone). The per-case cost of ~$0.0015 is **20× cheaper**
than the plan's $0.03/case projection. Implication: the full 184-case
`--with-real-llm --with-judge` run is likely closer to **$0.30** total
than the $5.52 we'd been budgeting against.

## Three real issues to address

### Issue 1: URL citation discipline (1 wrong, 2 partial flagged on this)

The synth sometimes cites URLs adjacent to evidence URLs rather than
the URL the evidence chunk explicitly carries. Cases 1, 3, 4 show
variants of this. The post-processor's URL validator IS catching
some — but the judge is flagging others where the synth's URL is
plausible-looking but not exact.

**Hypothesis:** the synthesizer's stable prefix tells it to cite
URLs from the evidence bundle, but doesn't tell it to cite them
verbatim. When the model summarizes, it sometimes invents a
slightly different URL (e.g., `accessnyt.com` when the evidence
gave `libguides.lib.miamioh.edu/newspapers/nyt`).

**Action item:** consider tightening rule wording in
`prompts/synthesizer_v1.py` to "cite the EXACT source_url string
shown in the evidence bundle; do not modify or shorten URLs."
Validate with a re-run of this eval — should move from 5/6 to 6/6.

### Issue 2: ILL roleplay leak

Case 3 (`fs_ill_oxford`): the bot answered "Log in to ILLiad with
your Miami credentials and submit a request form" — which is
action-flavored language. The plan's rule 5 (don't roleplay
submission) lives in `agent_v1.py` but **not** in `synthesizer_v1.py`.
For the v2 stack the agent is upstream of synth, so this might be
caught there in production — but if synth is ever called directly
(or if the agent's framing is weak), the synth doesn't enforce the
rule itself.

**Action item:** mirror rule 5 into `synthesizer_v1.py`'s rule list,
OR document explicitly that synth depends on the agent for action-
vs-guidance framing.

### Issue 3: judge-vs-bot URL strictness mismatch

In case 2 (NYT), the bot cited `accessNYT.com` (which is a real
activation URL but not in `allowed_urls`). The judge said `all_valid`
anyway. In case 4 (Adobe), the bot cited an adobe.com URL and the
judge said `no_citations`. These are inconsistent. The judge prompt
may be applying different strictness depending on the question's
domain — worth a follow-up to either tighten the judge prompt or
loosen the `allowed_urls` definition to include "natural" external
URLs the bot is expected to surface.

**Action item:** decide whether `allowed_urls` should be the
ONLY-allowed set (strict) or a SUFFICIENT set (lenient — external
URLs from the evidence are also ok). Codify in `judge_v1.py`.

## What this unblocks

This is the **first real measurement of v2 LLM behavior** in the
project. Before today we had unit tests (lots, passing) and offline
adapter tests, but no real-API quality number. Now we do.

Combined with the cache-hit verification (also today, PR #81), we
can answer the threshold-3 question "is the synth ready for real
traffic?" with: **mostly yes, with three known issues that don't
block 10% rollout but should be tracked.** Each issue traces to a
specific file (a `_v1.py` prefix or a rule list).

## How to re-run

```bash
cd ai-core
python -m scripts.eval_synth_alone                # all 6 cases
python -m scripts.eval_synth_alone --filter ill   # just one
python -m scripts.eval_synth_alone --out /tmp/eval.jsonl  # save per-case results
```

Exit code: 0 if every case has verdict ∈ {correct, partial,
refused_correctly}; 1 otherwise. The 6 cases are deliberately
inline in the script (not loaded from JSONL) so the evidence
bundles are explicit and auditable — adding a case is a localized
edit.

## Next measurements (once Weaviate is back)

1. **Full eval suite** — `run_eval --with-real-llm --with-judge`
   against the populated corpus. Tests synth + classifier +
   retrieval together. Cost ~$0.30–$0.50 (revised down from $5.52
   based on this run's actual numbers).
2. **Address Issue 1 first**, then re-run synth-alone to confirm
   improvement. ~$0.01.
3. **Compare cited-URL exact-match rate** vs gold's `allowed_urls`
   across the full suite once Issue 3 is resolved.
