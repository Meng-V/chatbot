# Gold hygiene pass (2026-07-16)

Follow-up #1 from [eval_rerun_2026-07-15.md](eval_rerun_2026-07-15.md): several gold
cases still encoded expectations the operator has since overruled, so the judge
was penalizing behavior the operator explicitly asked for. This pass rewrites
those expectations in `src/eval/golden_set.jsonl`. All case ids are kept stable
for cross-run comparison. The set still loads: 234 cases.

Sources of truth: the operator's hand-labeled review
([eval_review_2026-06-29.md](eval_review_2026-06-29.md)) and the rerun report's
regression triage. Cases from the June review already cleaned on 2026-07-14
(`xc_makerspace_hamilton_refusal`, `hr_finals_week_oxford`, `hr2_late_night_finals`)
were left untouched.

## Cases updated (7)

| id | what changed | why |
|---|---|---|
| `sc_archivist_contact` | Expected answer is now the deterministic named-archivist answer (Jacky Johnson + general contacts), not generic contacts only | Operator fix 16cc73f made this deterministic; gold still asked for the generic contact, so the rerun judged the fixed answer wrong |
| `fs_makerspace_hours` | Live LibCal status is correct **including a closed status** ("Closed this week" in summer); never King's building hours | Rerun judged the true live answer wrong because gold implied open-hours (review #14) |
| `ms_hours_today` | Same as `fs_makerspace_hours` | Review #15 |
| `rb_wertz_no_bookable` | "3 reservable study rooms + booking page" is the correct answer; gold no longer suggests a "no bookable rooms" claim | Rerun judged the correct answer wrong; operator confirmed BOT-OK (review #23) |
| `hr_sword_no_public_hours` | `refusal` → `answer`: depository explanation (no public hours, items via ILL) **plus** contact info (phone 513-727-3474) | Operator verdict on review #11: "combine both the WANT and the BOT"; bot fixed in 3007117/b0bede2 |
| `live_libcal_outage_refusal` | `refusal` → `answer` for live runs: Rentschler's live closing time is correct; the outage-refusal invariant needs a fault-injection test, not a live gold case | Operator marked the live answer BOT-OK (review #13); rerun: "can't simulate an outage in a live run" |
| `xc_main_library_default_to_king` | Expected answer now states explicitly that defaulting to King is correct, not an error | Rerun judged the correct King-default answer wrong (judge artifact) |

## Checked, deliberately not changed

- `sl_directory` (review #98): the gold and its allowed URL
  (`/about/organization/staff/`) are already correct — the wrong URL was a bot
  error, not gold.
- `hr_special_collections_appt_only` (review #67): fixed on the bot side and
  verified in the rerun; gold already matches.
- Review cases marked REAL bug (e.g. #42/#72 Hamilton staff pointer, #33
  renewal paths, #40 alumni borrowing, #64 MakerSpace pricing): these stay as-is —
  they are bot work, tracked separately, not gold noise.

## Follow-up

- The `live_libcal_outage_refusal` invariant (refuse when LibCal is unreachable)
  now has no measured coverage; add a fault-injection test in the eval harness
  if that guarantee matters.
- Next: mine the 58 "partial" verdicts from the 2026-07-15 run (follow-up #2),
  then a fresh measured run on the cleaned gold set.
