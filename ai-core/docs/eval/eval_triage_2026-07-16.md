# Eval triage — post-gold-hygiene run (2026-07-16)

Run: 234 gold cases, real LLM + judge, on the cleaned gold set (fed46f2).
Results: `eval_results/eval_results_20260716_postclean.jsonl`.

## Headline

| metric | 2026-06-29 | 2026-07-15 | **2026-07-16** |
|---|---|---|---|
| judge correct + refused_correctly | 58.1% | 62.2% | **67.5%** (158/234) |
| wrong | 10.7% | 10.3% | 6.4% (15) |
| bad refusals | 4 | 5 | 3 |

Distribution: 125 correct, 33 refused_correctly, 58 partial, 15 wrong,
3 refused_incorrectly.

This is the follow-up #2 pass from the 2026-07-15 report: all 76 non-good
verdicts were triaged (the 2026-07-14 raw results file no longer exists on this
box, so the triage ran on this fresh post-hygiene run instead).

## Triage method

1. **46 of 76** match questions the operator already hand-labeled **BOT-OK**
   in the 2026-06-29 review — carried over as judge noise, not re-litigated
   (loan-policy phrasing, tech-checkout pointers, find-resource Primo answers,
   food/pet policy pointers, etc.).
2. The remaining 30 (14 previously-REAL + 16 new) were read individually
   against their bot answers. Verdict recommendations below await operator
   confirmation.

## Confirmed judge noise among the re-read 30 (recommend BOT-OK)

- `ms_hours_today` [wrong]: bot said "No. The Makerspace is closed today" —
  exactly what the freshly cleaned gold accepts. The judge still scored it
  wrong. Pure judge noise; worth a judge-prompt tweak (see follow-ups).
- `hr_special_collections_appt_only` [partial]: full live SC hours + the
  appointment rider + spec.lib link — textbook gold match.
- `lib_by_name` [wrong]: bot correctly said no "Erica Wolfe" exists and
  suggested Erica Freed with contact — exactly the gold's anti-fabrication ask.
- `xc_rentschler_rooms`, `xc_session_origin_hamilton`, `reserves_find`,
  `reserves_my_class`, `fs2_makerspace_cost`, `circ2_alumni_borrowing`,
  `xc2_scanning_all_campuses`, `res2_chicago_citation`, `hr_summer_session_oxford`,
  `fs_makerspace_sewing`, `fs_special_collections_access`,
  `xc_makerspace_middletown_refusal`, `xc_generic_library_no_signal`,
  `news_nyt_access`, `news_wsj_access`, `svc_print_color`,
  `circ2_hold_pickup_window`, `svc2_after_hours_access`: answers match the
  operator-approved behavior; judge quibbles.

Two of these exposed stale gold and were fixed in this pass:
`circ2_alumni_borrowing` (gold still described a nonexistent alumni library
card — operator called this out as critical in June #40) and
`fs_makerspace_sewing` (aligned with the June #58 vinyl-cutter verdict:
equipment questions get the live equipment-page pointer).

## REAL problems (recommend fixing, ranked)

1. **`sd_origin_middletown_default` [wrong] — session-origin ignored.**
   A "How do I book a study room?" with session_origin=middletown got the
   King reservation answer. Operator rule (June #44): default King ONLY when
   no other signal; a regional-widget session is a signal. Likely the same
   flakiness family as the fixed `rb_rentschler_tomorrow` (074b195).
2. **`cap2_course_reserves_submit` [partial] — faculty flow missing.**
   A professor asking to put their book on reserve got the student-facing
   "search reserves in Primo" answer. Should refuse to act, surface the
   faculty submission process, and point to reserves staff.
3. **`rb_king_today` [partial] — live availability path flaky.**
   "Can I book a study room at King today?" answered with a generic King-page
   pointer — no live availability, no booking link. Regression risk vs the
   be5ae17 fix; same agent-path flakiness family as item 1.
4. **`res2_government_documents` [partial] — bare-name answer.**
   "Does the library have government documents?" answered with only the
   subject librarian's name. Should describe the collection (federal
   depository) + guide pointer. (June note also asks to verify Jenny Presnell
   is the right liaison.)
5. **`fs2_digital_collections_download_rights` [partial] — wrong template.**
   A download/use-rights question got the generic digital-exhibits deflection.
   Should say rights vary per collection/item and route to the archives
   contact.
6. **`lib_unknown_subject_refusal` [wrong] — minor.** For a nonexistent
   subject the bot silently pointed to the directory; gold wants an explicit
   "no librarian for that subject" before the pointer.
7. **`renew_extend` [partial] — minor thin answer.** Missing the
   "contact circulation if past the renewal limit" half.
8. **`news_local_paper_refusal` [refused_incorrectly] — minor.** Hamilton
   Journal-News question got a hard refusal; per the newspaper-routing policy
   (9de65f3) it should point to the newspapers guide.
9. **`lib_middletown_general` [wrong] — data verification.** Bot names
   Jennifer Hicks (hicksjl@miamioh.edu, 513-727-3221) as the Gardner-Harvey
   librarian. Verify against the live staff page before treating as correct.

## Follow-ups

- Judge harshness is now the dominant error source: ~60 of the 76 flagged
  cases are noise. Two structural fixes worth considering before chasing more
  bot fixes: (a) have the judge treat "pointer to the operator-designated
  page" as satisfying gold when gold asks for a pointer; (b) feed the judge
  the gold `notes` field, which now carries the operator's intent.
- Estimated true correct rate from this triage: (158 + ~60) / 234 ≈ **93%**.
- The `live_libcal_outage_refusal` fault-injection gap from the hygiene pass
  still stands.
