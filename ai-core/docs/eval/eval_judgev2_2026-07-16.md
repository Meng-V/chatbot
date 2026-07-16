# Judge v2 measured run (2026-07-16, evening)

Full 234-case run, real LLM, judge_v2 (`eval_results_20260716_judgev2.jsonl`,
archived next to this file).

## Trend

| run | judge-good | wrong | bad refusals |
|---|---|---|---|
| 2026-06-29 (v1 judge) | 58.1% | 25 | 4 |
| 2026-07-15 (v1) | 62.2% | 24 | 5 |
| 2026-07-16 morning (v1, cleaned gold) | 67.5% | 15 | 3 |
| **2026-07-16 evening (judge_v2)** | **74.4%** (174/234) | 16 | 3 |

Distribution: 142 correct, 32 refused_correctly, 41 partial, 16 wrong,
3 refused_incorrectly.

## What judge_v2 changed

- The gold `notes` field (operator review verdicts) now reaches the judge
  as an OPERATOR NOTES section (rule 7).
- E1 no longer counts the bot's own in-chat capability offers as uncited
  claims; pointer golds are satisfied by pointer answers (rule 8); extras
  the gold marks optional never downgrade (rule 9).
- Targeted validation: 12 operator-confirmed noise cases from the morning
  triage -- 10 flipped to correct under v2 (0 under v1).

## Judge noise, quantified

Across the two same-day runs, 115 cases produced byte-identical bot
answers. The 3-vote nano judge still flipped 21/115 (18%) of those
verdicts run-to-run (14 toward good under v2, 7 away). Actions taken:

- default judge samples bumped 3 -> 5 (majority vote over 5);
- two more gold `allowed_urls` gaps found this way and fixed
  (`xc_rentschler_rooms`, `rb_rentschler_tomorrow`: the operator-provided
  /reserve/hamilton URL was missing, so the operator-verified pointer's
  citation scored invalid).

If the residual flip rate still bothers the next run, the remaining lever
is the judge model tier (nano -> mini, ~3.7x judge cost).

## Reading the 60 remaining flags

Roughly three buckets (not re-triaged case-by-case here):

1. The known small REAL bugs from the morning triage, still unfixed
   (#4-9: gov-docs bare-name answer, digital-collections download rights,
   unknown-subject librarian phrasing, thin renewal answer, local-paper
   hard refusal, Jennifer Hicks data verification).
2. Residual nano-judge noise (see flip rate above) -- e.g. the two
   Rentschler pointer cases judged "wrong" this run on byte-identical,
   operator-approved answers.
3. A long tail of "partial" verdicts on subject-librarian and
   service-pointer answers worth one more mining pass after the next run.

## Next measured run checklist

- judge samples=5 and the Rentschler URL fixes are in -- both land
  automatically next run.
- Fix the #4-9 small bugs first so the run measures them.
- Expect the judge-good number to settle in the low-80s; the operator
  re-label estimate of true rate remains ~93%.
