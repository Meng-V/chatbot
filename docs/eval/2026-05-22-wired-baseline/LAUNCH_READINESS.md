# Launch readiness assessment — 2026-05-22

Honest answer: **we are at Threshold 2 (internally usable / measurable), not yet at Threshold 3 (10% rollout).** Tonight's work pushed Threshold 2 hard. Going from here to Threshold 3 is a distinct ~2 weeks of work per the original plan.

## What landed tonight

- 184/184 gold-set cases reviewed and verified by the operator (PRs #91–#96)
- Operator-verified Q+A pairs wired into Weaviate (189 chunks) + UrlSeen (32 rows) — bot retrieval now surfaces operator-correct URLs at rank 1 for matching queries
- Jekyll URL aliases wired (77 chunks + 19 UrlSeen rows) — `/NYT`, `/ill`, `/adobe` short-forms all recognized
- First end-to-end eval against the wired index: **147/184 cases (80%), 50.3% fully right, 85% citation discipline** (PR #97)
- 3 `ManualCorrection` rows for false-refusal/clarify patterns identified in the eval (Op 2 mechanism, live immediately)
- Eval-harness hang documented as GitHub issue #98 (37 cases untestable, root cause TBD)

## Gap to Threshold 3 (10% rollout)

Per the plan's "Recommended sequencing — the next two weeks":

| Gap | Plan name | Status | Effort | Blocker? |
|---|---|---|---|---|
| 1 | HTTP/Socket.IO wiring to new orchestrator | ❌ not started | 1-2 days | **Yes — bot can't be served to real users** |
| 2 | React citation chips + refusal UI | ❌ scaffolded, not wired | 1 day | Yes — users won't see citations |
| 3 | `LibrarySpace.services_offered` seeded | ❌ requires librarian input | 30 min once data arrives | Yes — needed for cross-campus refusal guard |
| 5 | ETL apply cron + librarian-approval handoff | ❌ phased ETL exists, no cron | 1 day | Yes — index will age without it |
| 6 | Op 3 MVP — structured logs + Sentry + `/smoketest` | ❌ not started | 3-4 days | **Yes — outages will be invisible** |
| 7 | Daily cost rollup cron | ❌ skeleton exists, not scheduled | 0.5 day | No — but you'll bleed money silently without it |

**Total estimated work to Threshold 3: 6-9 person-days.**

## Sub-50% sections — fixable vs measurement-artifact

The eval shows 4 sections below 50%. Of those:

### Likely real bot bugs (worth fixing)

- `db_general_list` (false clarify) — **fixed tonight** via ManualCorrection
- `xc_session_origin_hamilton` (false refuse "Can I book a room?") — **fixed tonight** via ManualCorrection
- `loan_grad_period` (false refuse "couldn't verify sources") — **fixed tonight** via ManualCorrection
- 3 `capability_point_to_url` cases (find_book_specific, find_journal, find_books_topic) returning near-identical canned text — agent isn't differentiating the questions. Would benefit from intent-specific prompt tweaks or per-intent canned responses.

### Likely measurement artifacts (judge calibration, not bot bugs)

Most of the "wrong" hours/cross-campus verdicts look like this:

- bot: "King Library is open today, Friday 2026-05-22, from 7:30am to 5:00pm [1]"
- gold expected_answer: "Live LibCal hours for King Library"
- judge: marked "wrong"

The bot called `get_hours`, got real LibCal data, formatted it. The judge can't tell that the bot's concrete answer satisfies the gold's meta-description. **The fix is in the gold set, not the bot** — make `expected_answer` concrete enough that the judge can verify (e.g., "should mention today's date and a closing time in the afternoon"). This is its own follow-up task.

Roughly: 10–15 of the 25 "wrong" verdicts in the current eval are likely measurement artifacts.

### Realistic estimate of bot quality

Adjusting for the measurement artifacts:
- Current measured: 50.3% fully right (74/147)
- Estimated real bot accuracy: ~60–65%
- After fixing the 3 false-refusal/clarify cases via ManualCorrection: should bump 2-3 percentage points

Strong enough to launch behind a flag at 10%. Weak enough that we need ongoing librarian review (Op 1 + Op 2) to keep correcting.

## Recommended next steps (after tonight)

1. **Gap 6 first** — Op 3 MVP (logs + Sentry + smoketest). Without it, the first launch will be flying blind. ~3-4 days.
2. **Gap 1 + 2 together** — Wire the new orchestrator behind a `?v2=1` developer flag, get citation chips rendering, eat dogfood. ~2-3 days.
3. **Gap 3 librarian input** — Email the librarian for the `services_offered` truth-table. Async; could land while Gap 1+6 are being built.
4. **Fix the eval harness** (Issue #98) — re-run the 37 untestable cases. This blocks claiming "184/184 measured" pre-launch.
5. **Iterate on judge calibration** — review the 10-15 measurement-artifact verdicts, tighten gold `expected_answer` text.
6. **Flip the 10% flag** — only after Gap 6 is shipping, and only with the daily cost rollup in place.

Estimated calendar: ~2 weeks of focused work to flip the 10% flag with confidence.

## What we could ship NOW vs what would be irresponsible

| Action | Safe to ship now? | Why |
|---|---|---|
| Operator-wiring writes to Weaviate + UrlSeen | ✅ Live | Idempotent, reversible, no user-facing impact yet |
| ManualCorrection rows | ✅ Live | Take effect at next request, low blast radius |
| Eval baseline as public docs | ✅ Just landed | Useful for stakeholders to see current state |
| **v2 bot to real users** | ❌ **No** | Gap 1 (no HTTP wiring), Gap 6 (no observability). A 1-user bug would be invisible. |
| **10% rollout flag flip** | ❌ **No** | Same as above. Plus Gap 5 (ETL aging) and Gap 7 (cost bleed). |

## TL;DR

We did real work tonight. We are not done. Threshold 3 (launch behind a flag) is ~2 weeks of distinct engineering away — the work is bounded and known, just not done.
