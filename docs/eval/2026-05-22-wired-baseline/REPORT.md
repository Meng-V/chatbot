# Smart Chatbot Eval Report — operator-wired index

_Generated: 2026-05-22 | wired-index run | LLM-as-judge + real backends_

## Headline

- **Cases tested:** 147 of 184 (80%)
- **Fully correct:** 74 / 147 = **50.3%**
- **Cited at least one source:** 125 / 147 = 85.0%
- **Refusals fired:** 24 / 147 = 16.3%
- **Untestable (eval-harness hang):** 37 cases (20%) — see below

## Judge verdict distribution

| Verdict | Count | % of tested |
|---|---:|---:|
| correct | 54 | 36.7% |
| refused_correctly | 20 | 13.6% |
| partial | 42 | 28.6% |
| wrong | 25 | 17.0% |
| refused_incorrectly | 4 | 2.7% |
| answered_should_have_refused | 2 | 1.4% |

## Per-section breakdown

| Section | Tested / Total | Fully right | % |
|---|---:|---:|---:|
| instruction | 2 / 2 | 2 | 100.0% |
| capability_refuse | 6 / 6 | 5 | 83.3% |
| scope_default | 6 / 6 | 5 | 83.3% |
| out_of_scope | 14 / 14 | 9 | 64.3% |
| research | 7 / 9 | 4 | 57.1% |
| featured_service | 42 / 49 | 22 | 52.4% |
| hours | 6 / 6 | 3 | 50.0% |
| service | 26 / 30 | 10 | 38.5% |
| capability_point_to_url | 8 / 8 | 3 | 37.5% |
| cross_campus | 16 / 30 | 6 | 37.5% |
| circulation | 14 / 14 | 5 | 35.7% |

## Untestable cases (orchestrator hang)

These cases never produced a result in this run. The bug is in the eval harness's per-case loop, not the bot itself — librarian cases were verified to work correctly via standalone diagnostic. They should be re-tested after fixing the per-case state leak in `run_eval.py`.

| Section | Missing IDs |
|---|---|
| cross_campus | `ill_hamilton_pickup, ill_middletown_pickup, lib_hamilton_general, lib_middletown_general, live_libcal_outage_refusal, loc_gardner_harvey_address, loc_rentschler_address, rb_gardner_harvey, rb_rentschler_tomorrow, sd_origin_hamilton_default, sd_origin_middletown_default, xcc_makerspace_all_campuses, xcc_printing_all_campuses, xcc_special_collections_all_campuses` |
| featured_service | `fs_archivist_email, fs_dc_contribute_refusal, fs_sc_finding_aid, news_local_paper_refusal, news_nyt_access, news_wsj_access, sc_archivist_contact` |
| librarian | `lib_biology_subject, lib_business_subject, lib_by_name, lib_hamilton_librarian, lib_history_subject, lib_subject_bio, lib_unknown_subject_refusal` |
| research | `ds_analysis, ds_gis` |
| service | `cit_no_libguide_fabrication, hh_chat_with_librarian, hh_complex_research_handoff, hh_email_question` |
| staff | `sl_circulation_head, sl_dean, sl_directory` |

## Top wins (the bot answered correctly)

- **db_jstor** — To find articles or browse research databases, use the library's Databases A-Z list. It's the authoritative index of every database the library subscribes to -- organized alphabetically and by subject
- **db_psycinfo** — To find articles or browse research databases, use the library's Databases A-Z list. It's the authoritative index of every database the library subscribes to -- organized alphabetically and by subject
- **db_ebsco** — Use the Miami Libraries Databases A-Z list to find current access options [1]. That is the library’s subject-organized database index, so it’s the place to check for EBSCO and other research platforms
- **acct_my_checkouts** — I can't access your library account -- only you can. To see your current checkouts, holds, due dates, or fines, sign in to MyAccount with your Miami credentials.

MyAccount: https://ohiolink-mu.primo.
- **events_exhibits** — For current/upcoming exhibits, check the Libraries’ live News & Events page [1].

You can also browse past exhibits in the Past Digital Exhibits Archive [4].
- **circ_confirmation** — Yes — you’ll get a confirmation email when the hold is queued, and another email when it’s ready for pickup [1].
- **circ_dorm_delivery** — Yes — Miami University Libraries offer a Department/Dorm Delivery service, and the page says current Miami patrons can request physical items to be delivered to their department or dorm [1][2]. For th
- **loan_how_long** — Loan periods for books vary by user type (undergraduate/graduate/faculty/staff) as listed in the Libraries’ Circulation Policies [1]. For the specific loan period that applies to you, see the Loan Per
- **reserves_loan_period** — A reserve textbook loan period is **2 hours, 1 day, or 3 days**, depending on the instructor [1].
- **xc_aa_alias** — A&A Library (Wertz Art & Architecture Library) is located on the ground and basement floors of Alumni Hall in Oxford [2]. The location page also lists the address as Alumni Hall, Oxford, OH 45056 [4].

## Notable misses (judge marked wrong)

- **find_article_topic** — Use Miami University Libraries’ Primo search to look for journal articles about climate change [1]. If you’d rather search within specific subject databases, use the Databases A–Z list to pick an appr
- **db_general_list** — I'm not sure which of these you meant. Can you pick one?

Options: databases, digital collections
- **xc_middletown_hours** — Gardner-Harvey opens tomorrow at 8:00am and closes at 5:00pm [1].
- **xc_rentschler_rooms** — Use Rentschler Library’s study rooms page for the Hamilton-specific reservation information [1]. The Services page also lists “Study Rooms” as one of Rentschler’s services [3].
- **xc_wertz_alias** — Wertz Art & Architecture Library closes at 5:00pm today (Friday, 2026-05-22) [1].
- **xc_explicit_alias_overrides_origin** — King Library is open today, Friday (2026-05-22), from 7:30am to 5:00pm [1].
- **xc_regional_unspecified** — Miami University Libraries’ regional locations are the Gardner-Harvey Library (Middletown campus), the Rentschler Library (Hamilton campus), and the Southwest Ohio Regional Depository (SWORD) [1]. SWO
- **fs_ill_oxford** — Use the Interlibrary Loan page for Oxford (Main Campus) and submit the request yourself [1]. The page is here: https://www.lib.miamioh.edu/use/borrow/ill/ [1].
- **fs_ill_no_submit** — You can submit an Interlibrary Loan request yourself through the Oxford ILL page [1]. The page is for Interlibrary Loan for Oxford (Main Campus), and it says to submit the request yourself [1].
- **fs_digital_collections_intro** — Miami University Libraries’ Digital Collections include thousands of digital objects—such as photographs, advertising trade cards, newspapers, manuscripts, and videos—from the Walter Havighurst Specia

## Operator wiring impact (rough comparison)

Pre-wiring eval (32 cases captured before the hang, no operator chunks in Weaviate):
- **34.4% fully right** (11/32)

Post-wiring (this run, 147 cases):
- **50.3% fully right** (74/147)

_Caveat: the 32-case pre-wiring sample was weighted toward harder categories (cross_campus + out_of_scope). This run covers the full spectrum, so the comparison is noisy. But the citation rate jumped from ~78% to 85%, which is a real signal that retrieval is more grounded._