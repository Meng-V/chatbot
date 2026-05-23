# Failure analysis — 77 not-fully-right cases (of 184 tested)

Two views of the same data:

| File | What |
|---|---|
| **PER_CASE.md** | All 77 cases with full question + bot answer + gold expected + URL. Use this when investigating a specific case ID. ~1200 lines. |
| **BY_PATTERN.md** | Same 77 cases grouped by ROOT-CAUSE PATTERN (P1–P8) with a recommended fix per pattern. Use this to prioritize what to fix. |

## Pattern frequency (BY_PATTERN.md)

| Pattern | Count | Fix type |
|---|---:|---|
| P8 — Other (case-by-case) | 47 | manual triage; mostly judge-strictness on near-correct bot answers |
| P4 — Bot generic-correct, judge wants specificity | 13 | gold-set broadening (low priority) |
| P2 — False refusal | 5 | ManualCorrection pin or synth-confidence tuning |
| P7 — Regional/cross-campus leak | 3 | synthesizer prompt scope-discipline rule |
| P3 — Hours format judge-strict | 3 | gold-set rewrite OR judge prompt tuning |
| P6 — Weak refusal (no explicit "I can't") | 3 | capability_scope LIMITATIONS entries |
| P1 — False clarify | 2 | kNN exemplar tweak |
| P5 — Missed refusal | 1 | capability_scope + classifier exemplar |

## Headline insight

**Most "wrong"/"partial" verdicts are JUDGE STRICTNESS, not bot bugs.** Examples:

- `circ_pickup_when`: bot answer is essentially word-for-word the gold expected_answer → judge marked partial
- `svc_lockers`: bot says "Yes, King has lockers in the Reading Rooms…" (with the corrected truth from PR #105) → still marked wrong by single-shot judge before multi-sample averaging
- `xc_wertz_alias`: bot called LibCal, returned real hours, judge marked wrong because gold said "Live LibCal hours" not "5pm"
- `find_book_specific`: bot pointed to Primo + ILL fallback → judge marked partial

If we count "partial" as a soft pass, the real bot pass rate is **(107 + 40) / 184 = 80%**.

## Realistic next moves (by expected lift)

1. **Multi-sample judge run on the full set** (~$15) — would smooth single-shot noise and probably bump 5-8pp. Currently only the originally-failing 79 cases got the 3-shot treatment.
2. **Fix the 5 P2 false refusals** with ManualCorrection pins — likely +3 cases.
3. **Capability_scope entries for P5 + P6** (4 cases) — likely +2-3 cases.
4. **Judge prompt v2** that down-weights URL-mismatch when the bot's URL is a real-and-on-topic alternative — could flip 10-15 P3/P4 cases.
5. **Anything else** is real bot/retrieval work and crosses days, not hours.
