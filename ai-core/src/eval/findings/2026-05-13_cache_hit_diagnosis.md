# Cache-hit regression diagnosis — synthesizer prefix below the empirical threshold

**Date:** 2026-05-13
**Triggered by:** real-LLM smoke run on the `hours` category showed
**cache hit 45.6%**, below the plan §week-4 gate of ≥60%.

## TL;DR

The synthesizer prefix (`synthesizer_v1`) was at 4,247 chars
(~1,062 tokens estimated) — nominally above OpenAI's 1,024-token
cache threshold but empirically failing to engage cache on 100% of
calls. Padded it to 9,118 chars (~2,280 tokens) with additional
stable reference content; cache hit jumps to 77% per call. Smoke
re-run after padding: **68.7% overall cache hit**, above the gate.

Also tightened the proactive lock-in test
(`test_all_shipped_prefixes_clear_cache_threshold`) from
`CACHE_THRESHOLD_TOKENS = 1024` to `1300` so we catch the next
case before it ships.

## Symptom

Smoke run of `--filter hours --with-real-llm --with-judge`
(6 cases) reported:

```
Tokens:  input p50=4589 p95=6546 sum=31,419
  cached input sum=14,336 (cache hit 45.6% -- plan §week-4 gate >=60%)
```

The plan's gate ("cached_input_tokens / input_tokens >= 0.6 after
week 4") was not met.

## Investigation

Step 1 — **probe each prefix's length**:

| prefix_id | chars | ~tokens | passes 1024? |
|---|---|---|---|
| agent_v1 | 6,259 | ~1,565 | YES |
| clarifier_v1 | 6,008 | ~1,502 | YES |
| judge_v1 | 7,074 | ~1,768 | YES |
| synthesizer_v1 | **4,247** | **~1,062** | YES (just) |

All four nominally clear the 1,024 mark.

Step 2 — **back-to-back identical calls to isolate which prefix
fails to cache**:

```
agent_v1 identical-call probe (4 calls):
  call    input  cached  output
  1        1463       0      40
  2        1463    1280      67   <- cache hit
  3        1463    1280      39
  4        1463    1280      40

synthesizer_v1 identical-call probe (4 calls):
  #     input  cached hit%
  1      1142       0    0%
  2      1142       0    0%
  3      1142       0    0%
  4      1142       0    0%
```

The agent prefix caches normally (cold start at 0%, then 87.5% on
every subsequent call). The synth **never** caches across 4
identical back-to-back calls. Cache stays cold even when the call
pattern is ideal.

Step 3 — **hypothesis**: the synth prefix is right at the 1,024
threshold, and OpenAI's actual cache-eligibility requires somewhat
more than nominal 1,024. Likely contributors:

- Tokenizer density. The synth prompt is JSON-heavy (curly braces,
  URLs, schema examples) which tokenizes denser than prose; the
  `chars/4` approximation overcounts.
- Responses API system overhead. The `instructions=` field gets
  wrapped into a system message; a few tokens of wrapper eat into
  the cacheable prefix.
- The cache may be eligibility-by-1024-block, so a 1,062-token
  prefix that's just barely over the line doesn't fill a block
  and gets no cache benefit.

## Fix

**Pad the synthesizer prefix past 1,300 tokens of stable content.**

Added to `src/prompts/synthesizer_v1.py`:

- 3 additional refusal/answer exemplars (EXAMPLE 5, 6, 7) covering
  databases / subject-librarian / room-booking question shapes.
- A "Common library URLs" reference table — 16 canonical URLs
  with their purpose. Cache-padding only; the rules section
  forbids citing from this block, so it's stable load-bearing
  content not used in answers.
- An extended confidence-rating discipline section anchoring the
  cache prefix with explicit guidance.

Prefix grows: 4,247 chars (~1,062 tokens) → 9,118 chars
(~2,280 tokens). Comfortably clears the empirical threshold.

## Verification

Identical-call probe after padding:

```
synthesizer_v1 NOW: 9118 chars  ~2280 tokens estimated
#     input  cached hit%
1      2337       0    0%
2      2337    1792   77%
3      2337    1792   77%
4      2337    1792   77%
```

Cold start at 0% (expected), then 77% per call. Working.

Re-ran the same smoke (`--filter hours --with-real-llm --with-judge`):

```
Tokens:  input p50=5782 p95=7313 sum=36,889
  cached input sum=25,344 (cache hit 68.7% -- plan §week-4 gate >=60%)
```

**Cache hit 45.6% → 68.7%**, above the gate.

Latency benefited too: `p50 6982ms → 5076ms` (-27%, the cache
savings translate to faster responses).

## Prevention — tightened lock-in test

`src/prompts/test_builder.py` had `CACHE_THRESHOLD_TOKENS = 1024`,
which let the unpadded synth ship. Empirically that threshold is
too generous. Bumped to **1,300** (~25% safety margin) with a
comment explaining the empirical reason. All four shipped prefixes
clear the new gate.

`src/prompts/builder.py`'s
`assert_prefix_clears_cache_threshold` docstring now explicitly
warns callers to pass a threshold >1024 — the nominal value is the
lower bound, not a guaranteed hit.

## Open question

Why exactly OpenAI's cache requires >1024 in practice is unclear:
the docs say 1024 is the threshold. Could be:
- A documented-elsewhere rule about block sizes
- An undocumented wrinkle around `instructions=` token accounting
- Variation between gpt-5.4-mini and other models

I haven't dug further. The empirical fix (pad to 1,300+) works
across all current call sites, and the lock-in test prevents a
regression. If we want to verify against real tokenization, adding
`tiktoken` as a dev dependency would let us swap the chars/4
estimate for a precise count.

## Reproducing

```sh
# From ai-core/
python3 -m src.eval.run_eval --filter hours --with-real-llm --with-judge
```

Look at the `Tokens:` block — `cache hit` percentage should be
>=60% after the cold-start call.

## Side findings (out of scope but worth noting)

The same smoke run surfaced a second issue: synthesizer's
`model_self_flagged` refusal triggered on 4 of 6 hours questions
despite valid single-chunk evidence. The model is being
over-conservative with `confidence: low` when only one source is
available. Separate follow-up; the cache fix doesn't address it.
