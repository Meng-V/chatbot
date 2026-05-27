# 06 — Evaluation & Quality

> How to measure bot quality, how to interpret the numbers, and how to avoid the Goodhart's Law trap.

## What we're measuring

For each question in the gold set, the bot:
1. Produces an answer (or refusal)
2. An LLM judge evaluates the answer against the gold's `expected_answer`
3. Returns one of 7 verdicts:

| Verdict | Meaning |
|---|---|
| `correct` | Bot answered well, judge approves |
| `partial` | Bot answered but missed some detail (still useful — typically gave URL pointer) |
| `wrong` | Bot answered with bad/incorrect content |
| `refused_correctly` | Gold expected a refusal, bot refused (good) |
| `refused_incorrectly` | Gold expected an answer, bot refused (bad) |
| `answered_should_have_refused` | Gold expected refusal, bot answered |

The headline metric we report:
**Fully right = correct + refused_correctly**

But this isn't the whole story — see "Why verdict ≠ truth" below.

---

## Gold sets

Three jsonl files in `ai-core/src/eval/`:

| File | Cases | Purpose |
|---|---|---|
| `golden_set.jsonl` | 234 | The main test suite. Built up over months by the project team. |
| `golden_set_colleague_round1.jsonl` | 37 | The colleague's Nov 20, 2025 test (the one that originally blocked v1 deployment). |
| `golden_set_merged_271.jsonl` | 271 | The two above combined for one-shot full-coverage runs. |

The eval reads `golden_set.jsonl` by default. To run a different gold file, temporarily swap:

```bash
cp src/eval/golden_set.jsonl src/eval/golden_set.jsonl.bak
cp src/eval/golden_set_merged_271.jsonl src/eval/golden_set.jsonl
# ... run eval ...
mv src/eval/golden_set.jsonl.bak src/eval/golden_set.jsonl
```

### Gold case schema

```json
{
  "id": "hr_today_king",
  "question": "What time does King Library close tonight?",
  "intent": "hours",
  "scope_campus": "oxford",
  "scope_library": "king",
  "expected_answer": "Should call get_hours for King and return today's close time from live LibCal, citing the King hours page.",
  "expected_outcome": "answer",
  "allowed_urls": [
    "https://www.lib.miamioh.edu/about/locations/king-library/"
  ],
  "category": "hours",
  "notes": "Updated 2026-05-23: ..."
}
```

| Field | Notes |
|---|---|
| `id` | Stable identifier. Conventions: short prefix (hr_, circ_, lib_, etc.) + descriptor. Colleague cases prefixed `r1_`. |
| `intent` | What the kNN classifier SHOULD classify this as |
| `scope_campus` / `scope_library` | What the scope resolver SHOULD produce. `null` means "any" |
| `expected_answer` | Prose description of what a correct answer looks like. The judge reads this. |
| `expected_outcome` | `answer` / `refusal` / `clarify` |
| `allowed_urls` | URLs the bot may cite. Used for operator-gold chunk wiring. |
| `category` | Bucketing for per-category breakdown. Use intent-aligned prefixes (`hours`, `circulation`, `librarian`, etc.) |

---

## Running the eval

### Quick smoke test (free, ~10 sec)

```bash
cd ai-core
.venv/bin/python -m src.eval.run_eval --scope-only
```

Tests scope resolver only. No LLM. Gates: scope_match ≥ 90%.

### Stub-mode eval (free, ~30 sec)

```bash
.venv/bin/python -m src.eval.run_eval
```

Real classifier (1 embedding/turn, cents) + canned synth/agent stubs. Tests routing accuracy.

### Real-LLM eval (~$5, ~50-60 min for full 271)

```bash
.venv/bin/python -m src.eval.run_eval \
  --with-real-llm --with-judge \
  --results-out beta_run_$(date +%Y%m%d_%H%M%S).jsonl
```

This is the "real" measurement. Real OpenAI calls for agent + synth + judge.

### Run one category only

```bash
.venv/bin/python -m src.eval.run_eval \
  --with-real-llm --with-judge \
  --filter hours \
  --results-out hours_only.jsonl
```

Categories available: see `gold.category` values (`hours`, `circulation`, `cross_campus`, `featured_service`, `service`, `out_of_scope`, etc.).

### Resume a dropped run

```bash
# If your tunnel died mid-run and the eval aborted at case ~141:
.venv/bin/python -m src.eval.run_eval \
  --with-real-llm --with-judge \
  --skip-ids-in beta_run_partial.jsonl \
  --results-out beta_run_part2.jsonl

# Then merge:
cat beta_run_partial.jsonl beta_run_part2.jsonl > beta_run_complete.jsonl
```

---

## Reading the results

### Stdout summary

After the run, you'll see:
```
Eval results: 271 total questions ...
Scope-resolver matches: 268/268 (100.0%)
Intent classification:  187/271 (69.0%)
Orchestrator path:      230/271 (84.9%)

Refusals: 56/271 turns (20.7%)
  correct refusals:    34
  false positives:     22  (refused when gold expected an answer)
  missed refusals:     0   (answered when gold expected a refusal)

Citations: 188/215 non-refusal answers cited at least one source (87.4%)

LLM-as-judge verdicts:
  correct_rate (correct + refused_correctly): 60.5%
  by verdict:
    correct                  130
    partial                   45
    refused_correctly         34
    wrong                     35
    refused_incorrectly       22
    answered_should_have_refused 5
```

### Per-case rows

The `--results-out` file is jsonl, one row per case:

```json
{
  "question_id": "hr_today_king",
  "category": "hours",
  "scope_match": true,
  "actual_scope_campus": "oxford",
  "actual_scope_library": "king",
  "intent_match": true,
  "actual_intent": "hours",
  "expected_path_set": "['point_to_url', 'agent_then_answer']",
  "actual_path": "agent_then_answer",
  "path_match": true,
  "bot_was_refusal": false,
  "bot_refusal_trigger": null,
  "bot_citations_count": 1,
  "judge_verdict": "correct",
  "latency_ms": 2150,
  "input_tokens": 1450,
  "cached_input_tokens": 1200,
  "output_tokens": 35,
  "clf_score": 0.91,
  "clf_margin": 0.18,
  "clf_needs_clarification": false,
  "clf_candidates": "[['hours', 0.91], ['hours_clarification', 0.73]]",
  "bot_answer": "King Library closes at 9:00pm tonight [1]."
}
```

### Generate librarian-friendly report

For non-developer audiences:

```bash
.venv/bin/python scripts/generate_librarian_report.py \
  --results beta_run.jsonl \
  --gold src/eval/golden_set_colleague_round1.jsonl \
  --output docs/eval/colleague_round1/REPORT.md
```

Output: a markdown report with plain-English verdicts, "what got better since v1", and per-category breakdown. Suitable for sharing with librarians.

### Run the failure analyzer

```bash
.venv/bin/python scripts/analyze_eval.py
# Reads eval_results.jsonl (symlink it to your run file)
# Prints scope/intent/path failures, refusal triggers, per-category ranking
```

---

## Why verdict ≠ truth

**Critical caveat: the LLM-as-judge is biased and noisy.**

Empirically, hand-review of `wrong` verdicts shows roughly:
- 30-40% are real bot errors (factually wrong, hallucinated, missing required info)
- 30-40% are judge over-strictness (bot's answer is correct but doesn't match gold's prose closely enough)
- 20-30% are pure judge non-determinism (same answer judged differently on re-run)

**Implication:** a 50% verdict is closer to 65-70% real-user quality. A 60% verdict is closer to 75-80% real-user quality.

The verdict is useful for:
- Trend tracking ("did this commit help or hurt?")
- Catching big regressions (5+ pp swings are meaningful)
- Identifying which categories are weakest

The verdict is misleading for:
- Absolute quality claims ("the bot is 60% accurate")
- Comparing against other bots (different judges = different biases)
- Tuning prompts to chase higher numbers (Goodhart trap)

---

## The Goodhart trap (must read)

**Goodhart's Law:** when a measure becomes a target, it ceases to be a good measure.

If you change bot behavior specifically to make the judge happier — but the change makes the bot worse for real users — you've Goodharted yourself. This is the dominant failure mode of LLM-eval-driven development.

### Examples we hit in May 2026

1. **"Synth MUST name librarian" rule** — judge marked `Find on Liaisons page` as wrong when Kristen Adams was in evidence. So we added a rule forcing the synth to name people. But this **reduced privacy protection** — bot started over-sharing specific staff names. Rolled back.

2. **Verbatim test-case kNN exemplars** — judge marked some intent classifications as wrong because exemplar coverage was thin. So we added the exact test questions as exemplars. But that's **test-set leakage** — kNN now memorizes specific questions but doesn't generalize. Rolled back; kept only paraphrased exemplars.

3. **`MUST/NEVER` agent rules** — judge marked some questions as wrong because the agent used search_kb when we wanted lookup_space. So we wrote "MUST call lookup_space FIRST, NEVER use search_kb for X". But that **removed fallback** when lookup_space returned empty, causing more refusals overall. Softened to "PREFER ... falls back to search_kb if empty".

### How to avoid Goodharting

1. **Verdict is a smoke test, not a gate.** A drop of 1-2pp is noise. Only investigate drops ≥5pp.

2. **Hand-review failures.** For any case the judge marks `wrong`, read the bot's actual answer. Is it really wrong? Or did it just not match the gold's specific prose?

3. **Maintain a non-regression list.** A small set of cases that MUST not regress (e.g., the 6 v1-hallucination cases the colleague found). Any commit that breaks one of these is reverted, regardless of verdict on other cases.

4. **Real-user signal > synth eval signal.** Beta-flag rollout + `ManualCorrection` filings from librarians is more honest than re-running the judge 10 times.

5. **Read the rationale before changing the prompt.** If the bot's behavior is conservative, it's conservative for a reason. Don't override that reason just because the judge prefers verbosity.

---

## How the eval pipeline is wired (for hacking on it)

### Top-level entry

`ai-core/src/eval/run_eval.py::main()` (CLI) → `run_eval()` (logic).

### Key files

| File | Role |
|---|---|
| `run_eval.py::_build_real_deps` | Builds OrchestratorDeps with real backends. **This is where tools get hidden via `registry.tools.pop()` — a common source of bugs.** |
| `real_backends.py` | Implementations of each tool backend (validate_url, lookup_librarian, lookup_space, get_hours, etc.). Mirror what prod uses, with eval-specific connection patterns. |
| `judge.py` | LLM-as-judge: prompt + scoring + multi-shot majority voting |
| `golden_set.py` | Gold-set loader (Pydantic-typed) |
| `inspect_turn.py` | Run a single question end-to-end with verbose tracing (for debugging) |
| `smoke_e2e.py` | Smoke tests with canned fixtures (the kind you run in CI) |

### Adding a new tool to the eval surface

1. Implement the backend in `real_backends.py::_make_yourtool()`
2. Wire it in `build_eval_backends()` — add it to the `ToolBackends(...)` constructor
3. Make sure it's NOT in the pop list in `_build_real_deps`
4. Add gold cases for that tool's use case
5. Run eval

### Adding a new intent to the kNN classifier

1. Add the intent to `_INTENT_REGISTRY` in `intent_knn.py`
2. Add 10-30 paraphrased exemplars to `src/router/exemplars/exemplars*.jsonl`
   - DO NOT just add the verbatim test questions — that's test-set leakage
3. Optionally add the intent to `intent_capabilities.py` if it should short-circuit
4. Re-run eval to confirm classification works on held-out gold cases

### Adding a new judge prompt version

1. Create `src/prompts/judge_v2.py` (don't mutate v1 — would break cache continuity)
2. Update `judge.py` to use v2 by default
3. Re-run eval against the SAME gold set with both prompt versions; compare verdicts

---

## Cost reference

| Action | Cost (approx) |
|---|---|
| Single embedding call | $0.00001 |
| Single agent turn (gpt-5.4-mini, ~1.5k cached + 0.5k uncached + 100 output) | $0.005 |
| Single synth turn | $0.005 |
| Single judge call (3-shot majority) | $0.02 |
| Full 271-case eval with `--with-real-llm --with-judge` | ~$5 |
| Full 271-case eval with stubs (`--with-real-llm` off) | ~$0.05 (just embeddings) |
| `wire_gold_to_weaviate.py` (276 chunks × embedding) | <$0.01 |

---

## Cache-hit optimization

The bot's per-turn cost is dominated by the input tokens to the agent + synth. OpenAI's automatic prompt caching gives 50% discount on cached tokens, but only when:
- The prefix is ≥1,024 tokens
- The prefix is byte-identical across calls (recent prior call)

Our prompts are designed for this — see `ai-core/src/prompts/*.py`. The `register_prefix(...)` calls assert byte-stability across runs.

If you change a prompt, the cache invalidates for ~5 minutes (until the new prefix is established). During an eval run, you'll see lower cache-hit rate at the start.

Healthy steady-state cache hit rate: **≥60%** (gate from the plan). If much lower, the prefix is drifting somehow.

Check current cache rate:
```bash
# From eval results
.venv/bin/python -c "
import json
rows = [json.loads(l) for l in open('your_eval.jsonl') if l.strip()]
total_in = sum(r.get('input_tokens',0) or 0 for r in rows)
cached = sum(r.get('cached_input_tokens',0) or 0 for r in rows)
print(f'cache hit rate: {cached/total_in*100:.1f}%')
"
```

---

## What "good enough to ship" looks like

There is no magic verdict number. The decision to ship a new version is based on:

1. **No new regressions on critical cases** (the v1-hallucination cases, the privacy-sensitive cases, the cross-campus refusal cases) — gate via hand-review, not verdict.
2. **Citation rate ≥ 95%** — every answered turn has at least one cited source.
3. **Scope match ≥ 90%** — kNN + resolver are doing their job.
4. **Cache hit rate ≥ 60%** — economically viable at scale.
5. **No crashes** — `crash:*` paths in results should be 0.
6. **Trend is up or flat** — recent commits didn't decrease the verdict count meaningfully.

If 1-6 hold, ship to a beta flag (10% traffic), monitor for 1 week. If `ManualCorrection` filings stay <10/week and Sentry stays clean, ramp to 100%.
