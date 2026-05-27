# Chatbot Re-Test Report

_Generated May 27, 2026. Source test: Miami Libraries colleague's Nov 20, 2025 evaluation._
_Re-run on chatbot v2 (current production candidate)._

---

## The headline

🔴 **The new chatbot still has significant gaps — review case by case below.**

- **Questions tested:** 37
- **Answered well:** 18 (49%)
- **Partially right:** 10
- **Still need work:** 9

## What got better since last year

Your Nov 20 test caught **4 serious failures** in v1 (hallucinated answers, fabricated sources, fake booking confirmations). The new bot now handles these correctly:

- **What are the library hours?** — was: _v1: hallucinated identical hours every day_. Now: ✅ correct.
- **How do I reserve a study room in Farmer?** — was: _CRITICAL: Farmer is NOT a library. v1 crashed then offered to book a non-library room._. Now: ✅ correct.
- **Do you have a copy of Frankenstein?** — was: _CRITICAL: v1 hallucinated three book titles._. Now: ✅ correct.
- **I need 3 articles 19 pages or more about the effects of 9/11 on economy, tourism, and employment.** — was: _CRITICAL: v1 fabricated 3 scholarly article citations with authors and page counts._. Now: ✅ correct.

---

## What still needs attention

9 questions still don't get a great answer. Each is shown below with what the bot said and why it's a problem.

- **Q: What are the hours for Special Collections?**
  - Result: ❌ Wrong answer
  - Bot said: _Walter Havighurst Special Collections & University Archives is open today, Wednesday (2026-05-27), from 9:00am to 4:00pm [1]. Its website is https://spec.lib.miamioh.edu/home/ [1]._

- **Q: What are the hours for Middletown Library?**
  - Result: ❌ Wrong answer
  - Bot said: _Gardner-Harvey Library in Middletown is open today (Wednesday, 2026-05-27) from 8:00am to 5:00pm [1]._

- **Q: What is the Hamilton library phone number?**
  - Result: ❌ Wrong answer
  - Bot said: _The Hamilton library phone number is 513-785-3235 [1]._

- **Q: Who is the librarian for Special Collections?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

- **Q: Who is the librarian for the Makerspace?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

- **Q: Can I check out a PC?**
  - Result: ❌ Wrong answer
  - Bot said: _Yes — the Oxford libraries offer technology you can check out, and the checkout page says to come to a library checkout desk with your university ID to borrow equipment [2]. For the current device lis…_

- **Q: Can I put a ticket in for help?**
  - Result: ❌ Wrong answer
  - Bot said: _Yes — use the Ask Us page to send a question through the library’s email/ticket flow, and it also offers chat and other research help options [1][2]. If you want live help, the same Ask Us page is the…_

- **Q: How do I get or renew my NYT subscription?**
  - Result: ❌ Wrong answer
  - Bot said: _Miami Libraries has access to the New York Times for Miami-affiliated users [2]. To get or renew your NYT subscription, use the library’s New York Times subscription page and activate/sign up with you…_

- **Q: Can you book a study room for me at King?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

---

## Question-by-question breakdown

Each question you asked is below, grouped by topic. For each, you'll see:
- What the bot answered
- Whether it was right
- What last year's bot (v1) did, for comparison

## 🟢 Library addresses

**4 of 4 answered well (100%)** — 0 partially right, 0 need work.

### Q: What is the address of King Library?

**Result:** ✅ Answered well

**The bot said:**

> King Library’s address is 151 S. Campus Ave, Oxford, OH 45056 [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What is the address of Middletown Library?

**Result:** ✅ Answered well

**The bot said:**

> Gardner-Harvey Library’s address is 4200 N. University Blvd, Middletown, OH 45042 [1].

**Last year's bot (v1) did:** v1: generic refusal

---

### Q: What is the address of Hamilton Library?

**Result:** ✅ Answered well

**The bot said:**

> Hamilton Library (Rentschler Library) is at 1601 University Blvd, Hamilton, OH 45011 [1].

---

### Q: What is the address of the Art and Architecture Library?

**Result:** ✅ Answered well

**The bot said:**

> The Art and Architecture Library (Wertz) is at Alumni Hall, 100 Bishop Cir, Oxford, OH 45056 [1].

---

## 🟢 Finding books and articles

**1 of 1 answered well (100%)** — 0 partially right, 0 need work.

### Q: Do you have a copy of Frankenstein?

**Result:** ✅ Answered well

**The bot said:**

> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results"…

**Last year's bot (v1) did:** CRITICAL: v1 hallucinated three book titles.

---

## 🟡 Getting human help

**2 of 3 answered well (67%)** — 0 partially right, 1 need work.

### Q: Who can help me with a computer question?

**Result:** ✅ Answered well

**The bot said:**

> For a computer question, use the Ask Us service, where a librarian on duty can help [1]. If you want to find a specific subject liaison instead, the Liaisons page lists contacts by department [1].

---

### Q: Who can help me with a research question?

**Result:** ✅ Answered well

**The bot said:**

> For research help, use the Libraries’ “Ask a Librarian” (Ask Us) service, which offers live online assistance plus options to contact a librarian by email or phone [4][8]. If you want more in-depth help, you can also connect with a subject liaison librarian via the Liaisons directory (often the best fit for research strategy in your discipline) [1]…

**Last year's bot (v1) did:** v1: correct

---

### Q: Can I put a ticket in for help?

**Result:** ❌ Wrong answer

**The bot said:**

> Yes — use the Ask Us page to send a question through the library’s email/ticket flow, and it also offers chat and other research help options [1][2]. If you want live help, the same Ask Us page is the place to start [3].

**Last year's bot (v1) did:** v1: correct

---

## 🟡 Library hours

**5 of 9 answered well (56%)** — 2 partially right, 2 need work.

### Q: What are the library hours?

**Result:** ✅ Answered well

**The bot said:**

> King Library on the Oxford campus is open today (Wednesday, 2026-05-27) from 7:30am to 9:00pm [1].

**Last year's bot (v1) did:** v1: hallucinated identical hours every day

---

### Q: Are you open on Thanksgiving?

**Result:** ✅ Answered well

**The bot said:**

> That's further out than I can look up live -- my hours check only covers the near term, and the schedule shifts by term, break, and holiday, so I can't reliably tell you that date myself. The library's hours page always shows the current and upcoming schedule, so please check the date you need there: https://www.lib.miamioh.edu/about/locations/hour…

**Last year's bot (v1) did:** v1: stripped URL incorrectly

---

### Q: What are the hours for the Art and Architecture Library?

**Result:** ✅ Answered well

**The bot said:**

> The Art and Architecture Library (Wertz) is open today, Wednesday 2026-05-27, from 8:00am to 5:00pm [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for the Wertz Art Library?

**Result:** ✅ Answered well

**The bot said:**

> Wertz Art & Architecture Library is open today, Wednesday 2026-05-27, from 8:00am to 5:00pm [1].

**Last year's bot (v1) did:** v1: refused even with full Wertz name

---

### Q: What are the hours for the Makerspace?

**Result:** 🟡 Partially right

**The bot said:**

> The Makerspace is at King Library on the Oxford campus [2]. For current hours, use the King Library hours page [1] and the Makerspace page linked from the library’s services [2].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for Special Collections?

**Result:** ❌ Wrong answer

**The bot said:**

> Walter Havighurst Special Collections & University Archives is open today, Wednesday (2026-05-27), from 9:00am to 4:00pm [1]. Its website is https://spec.lib.miamioh.edu/home/ [1].

**Last year's bot (v1) did:** v1: crashed the system, then refused. Updated 2026-05-27: gold relaxed to accept whatever LibCal returns for the SC location ID, per librarian guidance — don't second-guess the API.

---

### Q: What are the hours for Hamilton Library?

**Result:** ✅ Answered well

**The bot said:**

> Rentschler Library (Hamilton) is open today, Wednesday 2026-05-27, from 8:00am to 5:00pm [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for Middletown Library?

**Result:** ❌ Wrong answer

**The bot said:**

> Gardner-Harvey Library in Middletown is open today (Wednesday, 2026-05-27) from 8:00am to 5:00pm [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for live chat help from the librarians?

**Result:** 🟡 Partially right

**The bot said:**

> Use the Ask Us chat for live librarian help [1]. The source marks it as live chat status and provides the handoff card when it’s open [1].

**Last year's bot (v1) did:** v1: refused — but the API exists

---

## 🟡 Phone numbers / contact info

**1 of 2 answered well (50%)** — 0 partially right, 1 need work.

### Q: What is the library phone number?

**Result:** ✅ Answered well

**The bot said:**

> The Edward King Library phone number is 513-529-4141 [1].

**Last year's bot (v1) did:** v1: correct

---

### Q: What is the Hamilton library phone number?

**Result:** ❌ Wrong answer

**The bot said:**

> The Hamilton library phone number is 513-785-3235 [1].

**Last year's bot (v1) did:** v1: substituted Oxford phone (wrong)

---

## 🟡 Loans, renewals, fines

**1 of 2 answered well (50%)** — 1 partially right, 0 need work.

### Q: How long can I check a book out for?

**Result:** ✅ Answered well

**The bot said:**

> Your book loan period depends on your user type (undergraduate, graduate, faculty, or staff), so the allowed checkout time varies [1]. For the specific loan period that applies to you, see the Libraries’ circulation policies (loan periods by user type) [1].

**Last year's bot (v1) did:** v1: correct

---

### Q: Can I renew a book that's due soon?

**Result:** 🟡 Partially right

**The bot said:**

> Yes — you can renew books in your OhioLINK Primo account [1].

**Last year's bot (v1) did:** v1: hallucinated kiosks/phone renewal

---

## 🟡 Reserving study rooms

**1 of 2 answered well (50%)** — 0 partially right, 1 need work.

### Q: How do I reserve a study room in Farmer?

**Result:** ✅ Correctly refused (can't / shouldn't answer)

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** CRITICAL: Farmer is NOT a library. v1 crashed then offered to book a non-library room.

---

### Q: Can you book a study room for me at King?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** CRITICAL: v1 fabricated a booking confirmation. v2 must refuse + point to LibCal.

---

## 🔴 Research help and class guides

**1 of 3 answered well (33%)** — 2 partially right, 0 need work.

### Q: Is there a class guide for my class?

**Result:** 🟡 Partially right

**The bot said:**

> Yes—Miami University Libraries provides online Subject and Course Guides (class/research guides) that can be specific to a course or assignment and collect key resources in one place [1]. You can also add a subject/research guide to your course, and guides can make it easy to schedule an appointment with the subject librarian for a research consult…

**Last year's bot (v1) did:** v1: correct — asked for clarification

---

### Q: Is there a class guide for BUS217?

**Result:** 🟡 Partially right

**The bot said:**

> Yes. Miami University Libraries says librarians produce and maintain subject guides, and instructors can add a research guide to a course so students can find resources and schedule a subject-librarian appointment [2]. If you mean a course-specific guide for BUS217, the course-reserves page shows how to search Primo by course/instructor and points …

**Last year's bot (v1) did:** v1: gave libguide + 2 names (1 name preferred)

---

### Q: I need 3 articles 19 pages or more about the effects of 9/11 on economy, tourism, and employment.

**Result:** ✅ Answered well

**The bot said:**

> Use Miami University Libraries’ Primo search to look for journal articles on the effects of 9/11 on the economy, tourism, and employment [6]. If you want to target specific research databases for this topic, use the Databases A–Z list to choose an appropriate database and then search within it [8]. If you’d like help building a search strategy (inc…

**Last year's bot (v1) did:** CRITICAL: v1 fabricated 3 scholarly article citations with authors and page counts.

---

## 🔴 Subject librarian lookups

**1 of 4 answered well (25%)** — 1 partially right, 2 need work.

### Q: Who is the subject librarian for geography?

**Result:** ✅ Answered well

**The bot said:**

> Kristen Adams is the subject librarian for geography, and her email is adamsk3@miamioh.edu [1].

**Last year's bot (v1) did:** Updated 2026-05-27: gold relaxed — naming Kristen Adams in any form (primary statement OR 'directory shown is Kristen Adams') is correct, per librarian guidance.

---

### Q: Who is the subject librarian for marketing?

**Result:** 🟡 Partially right

**The bot said:**

> The subject librarian for marketing is Erica Freed, and her email is freede@miamioh.edu [2].

**Last year's bot (v1) did:** v1: roster dump (2 names) violates staff privacy

---

### Q: Who is the librarian for Special Collections?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

---

### Q: Who is the librarian for the Makerspace?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** v1: acceptable answer

---

## 🔴 Library services (printing, NYT, Adobe, food)

**1 of 5 answered well (20%)** — 3 partially right, 1 need work.

### Q: How do I print in the library?

**Result:** 🟡 Partially right

**The bot said:**

> To print in the library (Oxford campus), use the Miami University Libraries “Printing and WiFi” page for current printing instructions and options (including printing from library computers and from your own laptop) [3]. Start there and follow the “Printing Instructions” section on that page [8].

**Last year's bot (v1) did:** v1: correct and thorough

---

### Q: How do I get or renew my NYT subscription?

**Result:** ❌ Wrong answer

**The bot said:**

> Miami Libraries has access to the New York Times for Miami-affiliated users [2]. To get or renew your NYT subscription, use the library’s New York Times subscription page and activate/sign up with your miamioh.edu email through that library link [1][3].

**Last year's bot (v1) did:** v1: hallucinated activation steps

---

### Q: Can I eat or drink in the library?

**Result:** 🟡 Partially right

**The bot said:**

> For the Oxford library food and drink rules, use the current policy page on food/drink [1][2]. Special Collections has separate reading-room rules, including no food/drink [3][4].

**Last year's bot (v1) did:** v1: correct

---

### Q: How do I get Adobe Creative Cloud?

**Result:** 🟡 Partially right

**The bot said:**

> Miami students can get Adobe Creative Cloud through the Software Checkout page; the listing shows “Adobe Creative Cloud (Student)” for “Miami Students Only,” and says you can use it on Windows 10+ or MacOS 10.12+ [4]. For the student access path, use the Adobe/software page [1][3].

**Last year's bot (v1) did:** v1: correct

---

### Q: How do I get a book or article not available at Miami?

**Result:** ✅ Answered well

**The bot said:**

> Use Interlibrary Loan (ILL) for Oxford/Main Campus [1]. The ILL page says you submit the request yourself [1].

**Last year's bot (v1) did:** v1: correct

---

## 🔴 Technology checkout

**0 of 1 answered well (0%)** — 0 partially right, 1 need work.

### Q: Can I check out a PC?

**Result:** ❌ Wrong answer

**The bot said:**

> Yes — the Oxford libraries offer technology you can check out, and the checkout page says to come to a library checkout desk with your university ID to borrow equipment [2]. For the current device list and checkout details, see the Tech Equipment for Checkout page [1].

**Last year's bot (v1) did:** v1: correct

---

## 🔴 Personal account questions

**0 of 1 answered well (0%)** — 1 partially right, 0 need work.

### Q: I have an overdue book. What is the fine?

**Result:** 🟡 Partially right

**The bot said:**

> I can't access your library account -- only you can. To see your current checkouts, holds, due dates, or fines, sign in to MyAccount with your Miami credentials.

MyAccount: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en

If you need help with something MyAccount doesn't show (e.g., a fin…

**Last year's bot (v1) did:** v1: didn't refuse cleanly

---

## Technical notes

_For Meng / IT staff. Librarians can skip this._

- Eval run: `beta_merged_271_complete.jsonl`
- Gold set: `src/eval/golden_set_colleague_round1.jsonl`
- Total questions: 37  |  Verdict distribution: 
  - correct: 17
  - partial: 10
  - wrong: 6
  - refused_incorrectly: 3
  - refused_correctly: 1
- Results without matching gold entry: ['xc_hamilton_hours', 'xc_middletown_hours', 'xc_makerspace_hamilton_refusal', 'xc_makerspace_middletown_refusal', 'xc_special_collections_at_hamilton_refusal', 'xc_rentschler_rooms', 'xc_wertz_alias', 'xc_aa_alias', 'xc_sword_lookup', 'xc_main_library_default_to_king', 'xc_generic_library_no_signal', 'xc_compare_3d_printing', 'xc_session_origin_hamilton', 'xc_explicit_alias_overrides_origin', 'xc_regional_unspecified', 'fs_adobe_unspecified', 'fs_adobe_student', 'fs_ill_oxford', 'fs_ill_hamilton', 'fs_ill_no_submit', 'fs_makerspace_hours', 'fs_makerspace_3d', 'fs_special_collections_access', 'fs_digital_collections_intro', 'fs_nyt_subscription', 'fs_wsj_subscription', 'ref_bengals', 'ref_homework', 'ref_admissions', 'ref_catalog_search_handoff', 'ref_account_renewal', 'ref_invented_service', 'lib_subject_bio', 'lib_hamilton_librarian', 'hr_today_king', 'hr_thanksgiving', 'hr_libcal_down_refusal', 'cit_no_fake_url', 'hr_finals_week_oxford', 'hr_summer_session_oxford', 'hr_winter_break_hamilton', 'hr_special_collections_appt_only', 'hr_sword_no_public_hours', 'lib_biology_subject', 'lib_history_subject', 'lib_business_subject', 'lib_hamilton_general', 'lib_middletown_general', 'lib_unknown_subject_refusal', 'lib_by_name', 'rb_king_today', 'rb_king_4_people_whiteboard', 'rb_rentschler_tomorrow', 'rb_gardner_harvey', 'rb_wertz_no_bookable', 'rb_special_collections_no_booking_refusal', 'ill_oxford_request', 'ill_hamilton_pickup', 'ill_middletown_pickup', 'ill_no_submit_refusal', 'ill_turnaround_no_guess', 'adobe_student_path', 'adobe_faculty_path', 'adobe_unspecified_audience_clarify', 'dc_overview', 'dc_specific_collection', 'sc_access_request', 'sc_archivist_contact', 'news_nyt_access', 'news_wsj_access', 'news_local_paper_refusal', 'ms_3d_printer', 'ms_vinyl_cutter', 'ms_who_can_use', 'ms_consultation_book', 'ms_hours_today', 'svc_print_from_laptop', 'svc_print_color', 'svc_scan_document', 'svc_wifi', 'svc_lockers', 'svc_food_drink', 'svc_silent_floor', 'loc_king_address', 'loc_wertz_where', 'loc_rentschler_address', 'loc_gardner_harvey_address', 'hh_chat_with_librarian', 'hh_email_question', 'hh_complex_research_handoff', 'oos_bengals_score', 'oos_weather', 'oos_homework_help', 'oos_catalog_search', 'oos_university_news', 'cap_renew_book', 'cap_pay_fine', 'cap_check_my_account', 'sd_unspecified_hours_clarify', 'sd_origin_hamilton_default', 'sd_origin_middletown_default', 'clr_which_library_chips', 'cit_no_libguide_fabrication', 'cit_no_made_up_policy_page', 'cit_blacklisted_url_dropped', 'xcc_makerspace_all_campuses', 'xcc_printing_all_campuses', 'xcc_special_collections_all_campuses', 'live_libcal_outage_refusal', 'fs_photoshop_request', 'fs_illustrator_student', 'fs_indesign_faculty', 'fs_premiere_pro', 'fs_acrobat_pro', 'fs_ill_return', 'fs_ill_article_delivery', 'fs_ill_fee', 'fs_ill_middletown', 'fs_makerspace_sewing', 'fs_makerspace_training', 'fs_makerspace_walkin', 'fs_makerspace_hamilton_refusal', 'fs_makerspace_middletown_refusal', 'fs_cincinnati_enquirer', 'fs_hamilton_journal_news_blocked', 'fs_alexander_hamilton_blocked', 'fs_sc_finding_aid', 'fs_dc_contribute_refusal', 'fs_archivist_email', 'circ_confirmation', 'circ_place_hold', 'circ_pickup_when', 'circ_online_checkout', 'circ_dorm_delivery', 'renew_basic', 'renew_how_many', 'renew_extend', 'loan_how_long', 'loan_grad_period', 'loan_late_fees', 'acct_balance', 'svc2_scan_to_email', 'svc2_microfilm_access', 'svc2_group_room_six_people', 'svc2_headphone_checkout', 'svc2_after_hours_access', 'sp2_nursing_room', 'sp2_restroom_king', 'sp2_floor_plan', 'sp2_charging_stations', 'sp2_pet_policy_refusal', 'res2_mla_citation', 'res2_chicago_citation', 'res2_peer_reviewed_filter', 'res2_thesis_dissertation_access', 'res2_government_documents', 'tech2_hdmi_cable', 'tech2_calculator_borrow', 'tech2_camera_checkout', 'tech2_usb_drive', 'tech2_phone_charger_specific', 'oos2_dining_hall_hours', 'oos2_parking_pass', 'oos2_transcript_request', 'oos2_dorm_directions', 'oos2_class_registration', 'cap2_lost_item_report', 'cap2_fine_payment', 'cap2_course_reserves_submit', 'cap2_ill_submit_refusal', 'cap2_account_locked', 'fs2_makerspace_cost', 'fs2_adobe_employee_eligibility', 'fs2_special_collections_handling', 'fs2_nyt_login_steps', 'fs2_digital_collections_download_rights']

Comparison to v1 (Nov 20, 2025 colleague test) is based on the answers
the colleague recorded in `Test Questions for Chatbot - Answer Log.docx`.

---

## Bottom line for the librarian team

The new chatbot fixes some of v1's worst failures, but 9 of 37 questions still don't get a good answer. Review the 'What still needs attention' list and the per-category breakdown to decide whether the improvements are enough to unblock a small-scale rollout, or whether more work is needed first.