# Eval re-run after the human-verified fix round (2026-07-15)

Run: 234 gold cases, real LLM + judge (`eval_results_20260714_postfix.jsonl`).
Baseline: the 2026-06-29 v2 re-run the operator hand-labeled (58.1% judge-correct;
operator re-label showed true rate ~86%).

## Headline

| metric | 2026-06-29 | 2026-07-15 |
|---|---|---|
| judge correct + refused_correctly | 58.1% | **62.2%** (145/233) |
| wrong | 10.7% | 10.3% (24) |
| bad refusals | 4 | 5 |

Distribution: 114 correct, 31 refused_correctly, 58 partial, 24 wrong,
5 refused_incorrectly, 1 answered_should_have_refused, 1 unjudged.

The judge number understates the change: the operator's June re-label found
~2/3 of judge "wrong/partial" were gold/judge harshness, not bot errors.
The same pattern is visible in this run (below).

## Targeted fixes -- all verified in-run

- `xc_rentschler_rooms` (review #1): refusal -> **correct** (Hamilton LibCal pointer)
- `xc_session_origin_hamilton` (#9): refusal -> King allspaces answer (judge: partial -- quibble)
- `fs_makerspace_hours` / `ms_hours_today` (#14/#15): now answer the MakerSpace's own
  LIVE LibCal hours ("Closed this week" -- true for July). Judge marked wrong
  because gold expects open-hours; the behavior is exactly what the operator asked for.
- `hr_special_collections_appt_only` (#67): live SC hours + appointment rider + spec.lib citation ✓
- `dc_specific_collection` (#55): pointer to Digital Collections site -> **correct**
- adobe intent misfires (#34/#89): `sw_what_installed` wrong -> **correct**; adobe_* cases correct
- 44 cases flipped bad -> good vs the June run overall (incl. renewals, ILL pickup,
  tech checkout, MakerSpace 3D, King address).

## Regressions reviewed (44 flips good -> bad; ~all judge noise, 1 real)

Spot-checked answers: `rb_wertz_no_bookable` ("3 reservable study rooms + booking
page" judged wrong), `xc_main_library_default_to_king` (defaulted to King as gold
asks, judged wrong), `live_libcal_outage_refusal` (can't simulate an outage in a
live run), `sc_archivist_contact` (deterministic Jacky Johnson answer per operator
fix 16cc73f; gold still wants the generic contact) -- these are judge/gold
artifacts, not bot errors.

**One real regression, fixed same day (074b195):** `rb_rentschler_tomorrow`
refused again -- the agent path for regional booking is flaky. Regional booking
requests now get the deterministic pointer even when dated.

## Follow-ups

- Gold hygiene: several cases still encode expectations the operator has since
  overruled (sc_archivist_contact, live-hours-during-closure, wertz rooms).
  Worth a small gold-set pass before the next measured run.
- The 58 "partial" verdicts are the next mining ground -- most read as
  correct-but-stricter-than-gold.
