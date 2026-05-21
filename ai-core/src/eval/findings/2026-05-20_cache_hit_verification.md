# Cache-hit verification on the four stable prefixes

**Date:** 2026-05-20
**Tool:** `ai-core/scripts/verify_prompt_cache.py`
**Plan reference:** Verification §7 (cache-hit gate: `cached_input_tokens
/ input_tokens >= 0.6`)

## TL;DR

All four production prefixes hit cache well above the 60% gate on
their target models. The byte-stability discipline shipped in PR #74
is working. Total spend to verify: ~$0.02.

| Prefix | Production model | Input tokens | Cache hit (calls 2+) | Pass? |
|---|---|---|---:|---|
| `synthesizer_v1` | gpt-5.4-mini | 3094 | **91.0%** | ✅ |
| `agent_v1` | gpt-5.4-mini | 1453 | **88.1%** | ✅ |
| `judge_v1` | gpt-5.4-nano | 2620 | **68.4%** | ✅ |
| `clarifier_v1` | gpt-5.4-mini | 1537 | **83.3%** | ✅ |

First call always misses (cold cache). Calls 2+ hit cached_input as
shown. Side benefit: cached calls are roughly 2-3× faster
(synth: 2225ms cold → 696ms warm).

## One bonus finding worth knowing

The nano model has a **higher practical cache floor than mini** at our
prefix sizes. Specifically:

| Prefix | On nano | On mini |
|---|---|---|
| `synthesizer_v1` (3094 tok) | 91.0% | 91.0% |
| `agent_v1` (1453 tok) | **0.0%** | 88.1% |

A 1453-token prefix is above OpenAI's documented 1024-token cache
minimum but doesn't actually cache on nano — observed empirically.
This doesn't affect production because the agent runs on mini per
`LLM_MODEL_BASIC` (PR #74). It WOULD affect anyone considering
routing the agent through nano to save model-cost — the cache savings
would vanish and the per-token-cost win would be offset by ~2× more
billable input tokens.

Practical implication: nano is fine for the judge (its prefix is 2620
tokens, well above whatever nano's true floor is) and for any future
nano call site as long as the stable prefix is >= ~2000 tokens. Keep
that in mind when adding new call sites.

## How to re-verify

```bash
cd ai-core
python -m scripts.verify_prompt_cache --prefix synthesizer_v1
python -m scripts.verify_prompt_cache --prefix agent_v1 --model gpt-5.4-mini
python -m scripts.verify_prompt_cache --prefix judge_v1 --model gpt-5.4-nano
python -m scripts.verify_prompt_cache --prefix clarifier_v1 --model gpt-5.4-mini
```

Each exits 0 if >= 60% cache hit, 1 otherwise. Cost per run: ~$0.005.

Re-run when:
- Editing any `_v1` prefix file (catches accidental byte drift).
- Switching `LLM_MODEL_*` to a new model family (different cache rules).
- The cost dashboard shows `cached_input_tokens / input_tokens < 0.6`
  for a 1-hour rolling window (Op 3 alert).

## What this unblocks

The cost gate from plan Verification §7 is met. Combined with PR #77
(cost rollup landing yesterday), we now have:

1. **Cache investment proven** (this doc)
2. **Cache measured per-call** (`cached_input_tokens` column on
   `ModelTokenUsage` — PR #74)
3. **Daily rollup of token cost** (`scripts/cost_rollup.py` — PR #77)

That's the full cost-observability stack. Cost surprises after this
point will surface in `DailyCost` within 24h instead of "noticed
during the monthly billing review."
