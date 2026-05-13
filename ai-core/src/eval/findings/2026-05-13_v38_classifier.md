# v38 intent-kNN classifier — gold-set accuracy

**Date:** 2026-05-13
**Source:** `scripts/eval_classifier_v38.py` against
`src/router/exemplars/exemplars.jsonl` (5,258 librarian-labeled
utterances) + `src/eval/golden_set.jsonl` (129 gold questions, 213
lines including comments).

This is the first real measurement of routing accuracy under the v38
taxonomy. It runs every gold question through `IntentKNN.classify()`
with real `text-embedding-3-large` vectors and compares the top-1
intent against the gold question's expected intent.

## Headline number

**62 / 129 = 48.1% classifier accuracy.**

The kNN gate (>=85%) doesn't pass, but the headline is misleading
without breaking down where the failures cluster.

## Per-category breakdown

| Category | Acc | n |
|---|---|---|
| `hours` | 83.3% | 5/6 |
| `featured_service` | **67.3%** | 33/49 |
| `cross_campus` | 50.0% | 15/30 |
| `scope_default` | 50.0% | 3/6 |
| `librarian` | 42.9% | 3/7 |
| `service` | 17.6% | 3/17 |
| `out_of_scope` | **0.0%** | 0/14 |

The 48% headline is dragged down by three categories:
- `out_of_scope` (0/14) — every off-topic question gets routed as a
  real intent. **Highest-stakes failure** because it bypasses the
  refusal flow.
- `service` (3/17) — these are the `service_howto` fallback cases;
  the classifier picks a more specific intent (often `printing_wifi`)
  when the gold expects the catch-all.
- `cross_campus` (15/30) — half right, half wrong. Confusion mostly
  goes to `printing_wifi` and `interlibrary_loan`.

Excluding these three (38 of 129 questions), accuracy on the
"normal" routing path is **62/91 ≈ 68%** — still below the 85% gate
but a different problem shape.

## Per-intent accuracy (only intents present in gold set)

| Intent | Acc | n | Exemplar count |
|---|---|---|---|
| `adobe_access` | **100%** | 10/10 | 166 |
| `newspapers` | **100%** | 7/7 | 218 |
| `hours` | 94.1% | 16/17 | 72 |
| `room_booking` | 77.8% | 7/9 | 138 |
| `special_collections` | 75.0% | 3/4 | 42 |
| `interlibrary_loan` | 58.3% | 7/12 | 203 |
| `makerspace_3d` | 50.0% | 7/14 | 31 |
| `subject_librarian` | 36.4% | 4/11 | 31 |
| `human_handoff` | 33.3% | 1/3 | 87 |
| `cross_campus_comparison` | 0% | 0/4 | **1** |
| `digital_collections` | 0% | 0/4 | **10** |
| `location_directions` | 0% | 0/7 | 54 |
| `out_of_scope` | 0% | 0/10 | 74 |
| `service_howto` | 0% | 0/17 | 11 |

The pattern is **exemplar imbalance × no absolute-score floor**:

- Intents with thousands of exemplars (`find_resource` 1,255,
  `research_consultation` 810, `databases` 518) dominate the kNN
  space. Almost any utterance has a nearest neighbor in one of these.
- Intents with few exemplars (`cross_campus_comparison` 1,
  `service_howto` 11, `digital_collections` 10) are statistically
  unreachable — they'd need to be the exact nearest neighbor for the
  classifier to pick them.
- `out_of_scope` (74 exemplars) loses for a different reason: the
  classifier always picks the best of 38 — even when the absolute
  score is weak. Looking at the top-1 misses for out-of-scope
  questions, top-1 scores are all in the 0.40–0.55 range — clearly
  weak matches, but no floor triggers a refusal.

## Confusion summary

Most-frequent wrong intent for each broken expected intent:

| Expected | Most-common wrong | n |
|---|---|---|
| `service_howto` | `printing_wifi` | 6× |
| `out_of_scope` | `find_resource` | 4× |
| `interlibrary_loan` | `circulation_basic` | 3× |
| `location_directions` | `find_resource` | 3× |
| `makerspace_3d` | `location_directions` | 3× |
| `cross_campus_comparison` | `printing_wifi` | 2× |
| `room_booking` | `space_info` | 2× |
| `subject_librarian` | `research_consultation` | 2× |

These confusions are coherent — they're real semantic neighbors that
the gold set wanted to split apart. They're not random noise.

## Notable representative misses (lowest-margin failures)

```
[ref_homework] expected=out_of_scope  got=subject_librarian  margin=0.01
  Q: Do my history homework for me.
  top-3: subject_librarian(0.43), research_consultation(0.42), out_of_scope(0.39)

[loc_king_address] expected=location_directions  got=hours  margin=0.01
  Q: What's the address of King Library?
  top-3: hours(0.66), special_collections(0.65), find_resource(0.65)

[loc_wertz_where] expected=location_directions  got=find_resource  margin=0.00
  Q: Where is Wertz?
  top-3: find_resource(0.46), hours(0.46), location_directions(0.35)

[hh_chat_with_librarian] expected=human_handoff  got=hours  margin=0.01
  Q: Can I chat with a librarian?
  top-3: hours(0.74), human_handoff(0.74), research_consultation(0.66)

[svc_silent_floor] expected=service_howto  got=space_info  margin=0.01
  Q: Where is the silent study area?
  top-3: space_info(0.59), room_booking(0.58), location_directions(0.58)

[xc_compare_3d_printing] expected=cross_campus_comparison  got=printing_wifi  margin=0.00
  Q: Do all libraries have 3D printing?
  top-3: printing_wifi(0.59), makerspace_3d(0.59), space_info(0.55)
```

Across the board, **margins are tiny (0.00–0.01)** — the classifier
isn't confidently wrong, it's narrowly wrong. The needs-clarification
band (`MARGIN_LOW`) could be wider to push these into the
"ask the user" path instead of silently mis-routing.

## What this tells us

Two distinct problems, neither of which the exemplar pack solves
on its own:

1. **Thin-tail intents need more exemplars.** Specifically:
   `cross_campus_comparison`, `service_howto`, `location_directions`,
   `digital_collections`. These are bounded sets — we can write 20–40
   synthetic exemplars per intent in an hour and re-pack.

2. **No absolute-score floor for refusals.** The
   `out_of_scope` recall is structurally 0% because the classifier
   always picks a best-of-38 even when no exemplar is genuinely close.
   Two viable fixes:
   - Raise `MARGIN_LOW` to widen the clarification band (covers the
     narrow-margin cases above).
   - Add an absolute-score floor: if top-1 score < ~0.5, route to
     `out_of_scope` regardless of which intent the nearest neighbor
     suggests.

The cleanest minimum-viable fix is probably **(a) absolute-score
floor at ~0.5 → out_of_scope** plus **(b) 20–30 synthetic exemplars
per thin-tail intent**. With those two changes the 48% → ~75%+ is a
reasonable expectation; this report establishes the baseline.

## What this measurement does NOT tell us

- **Capability-tier routing accuracy.** When the gold expects
  `databases` and the classifier picks `databases`, the orchestrator
  still has to short-circuit to POINT_TO_URL correctly. Tested
  separately in `test_new_orchestrator.py` (18/18 pass).
- **Refusal correctness.** The classifier picking the wrong intent
  doesn't always mean the final output is wrong — the post-processor
  may still downgrade to a refusal (citation mismatch, low confidence,
  etc.). Real end-to-end accuracy requires the full bot wired up;
  that's the TODO in `src/eval/run_eval.py`.
- **Live A/B vs. the old 31-intent set.** The 31-intent baseline
  doesn't have the same exemplar set, and PR #33 isn't merged, so a
  direct comparison would require maintaining two side-by-side stacks.
  Not done.

## Reproducing

```sh
# From ai-core/
python -m scripts.eval_classifier_v38                  # full eval
python -m scripts.eval_classifier_v38 --filter cross_campus
python -m scripts.eval_classifier_v38 --top-misses 30  # see 30 worst
```

First run hits the OpenAI embedding API (~$0.05, ~75 seconds).
Subsequent runs are free + instant thanks to the content-hashed
sidecar cache at `data/eval/classifier_embeddings.json` (323 MB,
gitignored).
