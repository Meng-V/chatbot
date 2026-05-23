# Failure pattern analysis — 77 not-right cases grouped by root cause

_Generated 2026-05-23 from the final 184/184 eval._

## Pattern frequency

| Pattern | Count | % | Fix type |
|---|---:|---:|---|
| **P8_OTHER** | 47 | 61% | manual triage |
| **P4_PARTIAL_BOT_GENERIC** | 13 | 17% | gold-set broadening (low priority) |
| **P2_FALSE_REFUSAL** | 5 | 6% | ManualCorrection pin or synth tuning |
| **P7_REGIONAL_LEAK** | 3 | 4% | synthesizer prompt scope rule |
| **P3_HOURS_FORMAT_JUDGE_STRICT** | 3 | 4% | gold-set rewrite OR judge prompt tuning |
| **P6_WEAK_REFUSAL** | 3 | 4% | capability_scope LIMITATIONS entry |
| **P1_FALSE_CLARIFY** | 2 | 3% | kNN exemplar tweak |
| **P5_MISSED_REFUSAL** | 1 | 1% | capability_scope + classifier exemplar |

## P8_OTHER (47 cases)

**Other** — case-by-case investigation needed.
  **Fix:** Manual triage.

### Cases

- **`find_book_specific`** _partial_ [capability_point_to_url]
  - Q: Do you have a copy of Hamlet?
  - Expected: Point to Primo. Bot does NOT search the catalog itself.
  - Bot: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://o…
- **`find_journal`** _partial_ [capability_point_to_url]
  - Q: Can you find a journal article for me?
  - Expected: Point to Primo and offer ILL fallback if Miami doesn't have it.
  - Bot: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://o…
- **`find_books_topic`** _partial_ [capability_point_to_url]
  - Q: Where can I find books on Ohio history?
  - Expected: Point to Primo. Special Collections may also have relevant materials.
  - Bot: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://o…
- **`circ_place_hold`** _partial_ [circulation]
  - Q: How do I place a hold on a book at Miami?
  - Expected: Search Primo, click 'Place Hold' on the title, sign in. Cite circulation policies.
  - Bot: Search for the book in Primo, then click "Place Hold" on the title and sign in [1][2]. You can choose Oxford Campus / King Library as the pickup location when placing the hold [4].
- **`circ_pickup_when`** _partial_ [circulation]
  - Q: When will my book be ready for pickup?
  - Expected: Same-day for in-stock items; longer if from storage or another campus. Email notification on ready.
  - Bot: Same-day for in-stock items; it can take longer if the book comes from storage or another campus, and you’ll get an email when it’s ready [1].
- **`circ_online_checkout`** _partial_ [circulation]
  - Q: How do I check out a book online for pickup?
  - Expected: Place a hold via Primo, choose pickup location, retrieve when notified.
  - Bot: Search for the book in Primo, click "Place Hold," and sign in [5]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [2][4].
- **`renew_basic`** _partial_ [circulation]
  - Q: Can I renew my book?
  - Expected: Yes, but renewal differs by material type. Miami materials: point to the circulation-policies loan-periods-fines page. OhioLINK/ILL materials: point to the loan-periods-ohiolink-ill page. Distinguish 
  - Bot: Yes — you can renew books in your OhioLINK Primo account [1].
- **`loan_grad_period`** _refused_incorrectly_ [circulation]
  - Q: What's the loan period for graduate students?
  - Expected: Graduate student loan period from circulation policies; do not estimate.
  - Bot: I started to answer but couldn't verify my sources. Rather than send you something I can't back up, please ask a librarian through Ask Us.
- **`reserves_my_class`** _partial_ [circulation]
  - Q: Where are my course reserves?
  - Expected: Search Primo by course/instructor; physical reserves are at King circulation desk. Cite reserves page.
  - Bot: Course reserves and textbooks are covered in the Course Reserves & Textbooks guide [1]. Use that guide to find the current reserves process and location details for Oxford [1].
- **`xc_main_library_default_to_king`** _partial_ [cross_campus]
  - Q: When does the main library close?
  - Expected: King Library hours.
  - Bot: King Library (the main library) closes today at 5:00pm [1].
- **`xc_compare_3d_printing`** _partial_ [cross_campus]
  - Q: Do all libraries have 3D printing?
  - Expected: King has 3D printing in its Makerspace. Middletown has 3D printing in its TEC Lab Makerspace. Hamilton does NOT have 3D printing nor a Makerspace. Cite the King Makerspace LibGuide + the Middletown TE
  - Bot: No. On the Oxford campus, 3D printing is available at King Library in its MakerSpace [1]. 3D printing is also available at the Middletown campus in the TEC Lab MakerSpace [2].
- **`xc_session_origin_hamilton`** _wrong_ [cross_campus]
  - Q: Can I book a room?
  - Expected: By default, if the user has not mentioned any regional campus, the answer defaults to King. Present King Library's study room reservation tool (LibCal allspaces) as the answer, not regional study room
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- **`xc_explicit_alias_overrides_origin`** _partial_ [cross_campus]
  - Q: What are King's hours?
  - Expected: King Library hours.
  - Bot: King Library is open today, Friday (2026-05-22), from 7:30am to 5:00pm [1].
- **`fs_adobe_student`** _wrong_ [featured_service]
  - Q: I'm a student, how do I install Adobe?
  - Expected: Student Adobe Creative Cloud license access.
  - Bot: Use the Adobe Creative Cloud student access path on the Miami Libraries Software page, which points students to the Adobe installation instructions [1][2]. If you need the direct Adobe details, follow the Adobe page linked from Software Checkout [4].
- **`fs_ill_hamilton`** _partial_ [featured_service]
  - Q: How do I get a book from another library to Hamilton?
  - Expected: Hamilton-specific ILL pickup info + request form URL.
  - Bot: Use Interlibrary Loan for Hamilton Campus (Rentschler Library) to request the book [1]. The guide says you submit the request yourself; the bot does not place ILL requests [1].
- **`fs_makerspace_3d`** _wrong_ [featured_service]
  - Q: Does the MakerSpace have a 3D printer?
  - Expected: Yes, from LibrarySpace.equipment lookup -- not from prose.
  - Bot: Yes. The MakerSpace at King Library has a 3D printer [1][2][3].
- **`fs_special_collections_access`** _partial_ [featured_service]
  - Q: How do I see something in Special Collections?
  - Expected: Appointment-only access, contact info for archivist.
  - Bot: Special Collections uses appointment-only research access [1][2]. The Special Collections page is the place to start for access details and to arrange a research appointment [1][2].
- **`fs_digital_collections_intro`** _wrong_ [featured_service]
  - Q: What digital collections does Miami have?
  - Expected: Intro/overview of Digital Collections with the front-door URL; naming example collections is acceptable.
  - Bot: Miami University Libraries’ Digital Collections include thousands of digital objects—such as photographs, advertising trade cards, newspapers, manuscripts, and videos—from the Walter Havighurst Special Collections & University Archives [1]. Example n…
- **`fs_nyt_subscription`** _wrong_ [featured_service]
  - Q: Do you have access to the New York Times?
  - Expected: We do have access to New York Times for Miami affiliated users. https://libguides.lib.miamioh.edu/newspapers
  - Bot: Yes — Miami affiliated users have access to The New York Times [1]. For access, use the NYT subscription link from the databases page [2].
- **`ill_oxford_request`** _wrong_ [featured_service]
  - Q: How do I request a book through ILL?
  - Expected: Brief ILL explanation + link to Oxford ILL request form. Never submits the request.
  - Bot: Use the Interlibrary Loan page for Oxford (Main Campus) to submit the request yourself [1]. The page is the place to start for requesting a book through ILL [1].
- **`adobe_faculty_path`** _wrong_ [featured_service]
  - Q: I'm faculty -- where do I download Adobe?
  - Expected: Faculty/staff Adobe deal -- different from student license. Cite software/adobe page.
  - Bot: Faculty can get Adobe Creative Cloud through Software Checkout on the Miami Libraries software page [1]. After you check out a license, you log in at adobe.com using your Miami credentials and download Adobe to your own device [1].
- **`ms_vinyl_cutter`** _partial_ [featured_service]
  - Q: Is there a vinyl cutter at the MakerSpace?
  - Expected: Tell user to check for themself at https://muohio.libcal.com/reserve/equipment/makerspace
  - Bot: Check the MakerSpace equipment page for the current list of tools, including whether a vinyl cutter is available [1][6].
- **`fs_indesign_faculty`** _wrong_ [featured_service]
  - Q: Faculty here, do I have InDesign access?
  - Expected: Yes -- faculty/staff get Adobe Creative Cloud (incl. InDesign) via Software Checkout; cite the software page.
  - Bot: Yes. Faculty/staff at Oxford can get Adobe Creative Cloud through Software Checkout, and Adobe Creative Cloud includes InDesign [1][4].
- **`fs_premiere_pro`** _wrong_ [featured_service]
  - Q: Can I use Premiere Pro through the library?
  - Expected: Adobe CC suite access; clarify audience if not stated.
  - Bot: Yes. The library’s Adobe Creative Cloud access includes Premiere Pro among the available products, and it is available through the software checkout page [1][5].
- **`fs_acrobat_pro`** _partial_ [featured_service]
  - Q: Where can I get Acrobat Pro?
  - Expected: Adobe Acrobat Pro is available via Software Checkout (part of Adobe CC); cover student vs faculty/staff; cite the software page.
  - Bot: Adobe Acrobat Pro is available through Miami University Libraries’ Software Checkout as part of Adobe Creative Cloud [1][4]. For faculty/staff, you can reserve an Adobe Acrobat Pro license, then log in at adobe.com with your Miami credentials to down…
- **`fs_ill_return`** _refused_incorrectly_ [featured_service]
  - Q: Where do I return an interlibrary loan book?
  - Expected: Return-flow info per the OhioLINK & ILL loan-periods policy page. OhioLINK items should be returned to a bookdrop. Do not invent a return location for ILL items not stated on the policy page.
  - Bot: Interlibrary Loan for Oxford (Main Campus) is handled through the ILL request page [1]. Submit the request yourself; the bot does not place ILL requests [1].
- **`fs_ill_fee`** _wrong_ [featured_service]
  - Q: Are there fees for interlibrary loan?
  - Expected: There is no fee for Miami affiliated users. Check on https://www.lib.miamioh.edu/use/borrow/ill/
  - Bot: Use the Interlibrary Loan page for Oxford (Main Campus) to check the current policy and any fees [1]. The page is the place to submit requests yourself, and it carries the current ILL details [1].
- **`fs_makerspace_walkin`** _wrong_ [featured_service]
  - Q: Can I just walk into the MakerSpace?
  - Expected: Walk-in vs reservation policy from MakerSpace page; do not infer.
  - Bot: The MakerSpace page covers walk-in versus reservation use, so check that page for the current policy [1]. For booking-related details, the consultation flow is on the MakerSpace consultation page [2][3].
- **`ref_account_renewal`** _refused_incorrectly_ [out_of_scope]
  - Q: Renew my book.
  - Expected: REFUSAL of action + point to account/renewal URL.
  - Bot: Renew books in your OhioLINK Primo account [1].
- **`oos_catalog_search`** _refused_incorrectly_ [out_of_scope]
  - Q: Do you have a copy of Foundation by Asimov?
  - Expected: REFUSAL: the bot doesn't search the catalog; point to the catalog search on the libraries homepage.
  - Bot: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://o…
- **`cit_no_fake_url`** _wrong_ [service]
  - Q: Where can I find the printing policy?
  - Expected: Real printing policy URL only -- no fabricated /policies/printing.html.
  - Bot: Use the Printing & WiFi page for Oxford printing policy information [1][3]. The page is the canonical printing page for the library’s current printing details [3][4].
- **`svc_print_from_laptop`** _wrong_ [service]
  - Q: How do I print from my laptop?
  - Expected: Cite printing page; the 'one canonical printing page' invariant.
  - Bot: Use the Printing & WiFi page for the current steps to print from your laptop [1][2].
- **`svc_silent_floor`** _wrong_ [service]
  - Q: Where is the silent study area?
  - Expected: King Library quiet/silent floor location -- retrieval picks King via Oxford default + ranking.
  - Bot: The Libraries’ virtual silent study option is the Virtual Study Hall, described as a silent study atmosphere on Zoom for Miami University peers [1]. If you meant a physical quiet space, the Oxford libraries also have reading rooms within King Library…
- **`space_silent`** _wrong_ [service]
  - Q: Where is the silent study area?
  - Expected: The bot has no specific info; do not assert a silent floor or invent a URL.
  - Bot: The Oxford Libraries’ virtual silent study option is a Zoom-based “Virtual Study Hall” [1]. If you mean an in-person quiet area, the Libraries’ reading rooms in King Library are open [2].
- **`space_food`** _wrong_ [service]
  - Q: Can I bring food into the library?
  - Expected: Food/drink policy from spaces or policies page.
  - Bot: The sources point to the Oxford library food/drink policy page for the current rules on bringing food into the library [1][2][3]. One Oxford library event announcement also shows food can be present in King Library during a special program, but it do…
- **`tech_chromebook_period`** _partial_ [service]
  - Q: How long is the chromebook checkout period?
  - Expected: 30 days per the tech-checkout page.
  - Bot: Chromebooks can be checked out for 30 days [1][2]. The tech checkout page says libraries offer equipment to borrow at a checkout desk with your university ID [3].
- **`tech_charger`** _partial_ [service]
  - Q: Do you have charger cables to borrow?
  - Expected: Yes -- chargers for Mac/PC/phones, plus other peripherals. Cite tech-checkout page.
  - Bot: Yes — Oxford libraries let you borrow chargers and cables, including chargers for phones and laptops [1][3]. The equipment checkout page says to come to a library checkout desk with your university ID to borrow equipment [2].
- **`sw_what_installed`** _partial_ [service]
  - Q: What software is on the library computers?
  - Expected: Cite the software-on-library-computers page; do not enumerate beyond what's listed.
  - Bot: The library computers have Windows software including Adobe Creative Cloud, Audio-Video Viewing/Editing tools like Audacity and VLC Media Player, web browsers like Chrome and Safari, office software like Apple Keynote, Numbers, Pages, and Microsoft O…
- **`sw_matlab`** _partial_ [service]
  - Q: Is MATLAB available on library computers?
  - Expected: Confirm only if listed on the software page; otherwise refuse to assert.
  - Bot: Yes. The software page says additional titles such as MATLAB can be added to library computers using Software Center on campus Windows PCs and Self-Service on campus Macs [3][5].
- **`sw_install_personal`** _partial_ [service]
  - Q: Can I install SPSS on a library computer?
  - Expected: Yes -- additional titles (e.g. MATLAB, SPSS; plus Xcode on Mac) CAN be added to library computers yourself: Software Center on campus Windows PCs, Self-Service on campus Macs. Cite the software page.
  - Bot: Yes. The Oxford library software page says additional titles such as MATLAB, SPSS, and Xcode are available for you to add to library computers using the Self-Service software install on campus Macs [2], and the page also describes software available …
- **`cit_no_libguide_fabrication`** _partial_ [service]
  - Q: Is there a LibGuide on citation styles?
  - Expected: Point to the citation LibGuide (https://libguides.lib.miamioh.edu/citation). Cite only real official pages; never fabricate.
  - Bot: Yes — Miami University Libraries has a citation LibGuide at https://libguides.lib.miamioh.edu/citation [1]. The library also has a shortcut URL, https://www.lib.miamioh.edu/citing, that redirects to the same guide [2].
- **`lib_biology_subject`** _partial_ [librarian]
  - Q: Who is the biology librarian?
  - Expected: Subject librarian for Biology -- name, email, phone from Postgres.
  - Bot: Find the biology subject librarian on the Liaisons page [1].
- **`lib_history_subject`** _partial_ [librarian]
  - Q: I need the history subject librarian.
  - Expected: History is covered by the Humanities & Social Sciences subject librarian (Jenny Presnell); return that one person's name/email/phone.
  - Bot: Find the history subject librarian on the Liaisons page [1].
- **`lib_subject_bio`** _partial_ [librarian]
  - Q: Who is the librarian for Biology?
  - Expected: Exact name + email + phone of the Biology subject librarian, from Postgres.
  - Bot: The Biology librarian is Ginny Boehme [1]. Her email is boehmemv@miamioh.edu [1].
- **`ds_gis`** _wrong_ [research]
  - Q: Can someone help me with GIS?
  - Expected: Yes via data services consultations. Cite data services page.
  - Bot: Yes — Oxford Library data services offers consultations, and the GIS article says library staff are happy to help with GIS projects [1][2]. The data services page also says it provides data services support, including GIS help and data visualization …
- **`sd_origin_hamilton_default`** _wrong_ [cross_campus]
  - Q: Is the library open today?
  - Expected: Origin=hamilton -> Rentschler hours, NOT King.
  - Bot: King Library is closed today (Saturday, 2026-05-23) [1].
- **`sd_origin_middletown_default`** _wrong_ [cross_campus]
  - Q: How do I book a study room?
  - Expected: Origin=middletown -> Gardner-Harvey, NOT King.
  - Bot: Use the Room Reservations page to book study rooms online [1]. For King specifically, the room reservation system includes a King booking link and live availability through LibCal [2].
## P4_PARTIAL_BOT_GENERIC (13 cases)

**Bot generic-correct, judge wants more specificity** — bot gave the right pointer ('see the X page') but didn't cite specific details.
  **Fix:** Lower-leverage. Could broaden gold expected_answer text to accept generic pointers. Or wire more detailed retrieval chunks.

### Cases

- **`renew_how_many`** _partial_ [circulation]
  - Q: How many times can I renew a book?
  - Expected: Renewal limit per user type from circulation policies LibGuide; do not invent a number.
  - Bot: The renewal limit depends on your user type; see the circulation policies page for the current limit [1]. If you are trying to renew a checked-out book, use your OhioLINK Primo account [6].
- **`reserves_find`** _partial_ [circulation]
  - Q: How do I find course reserves?
  - Expected: Cite reserves page; mention search by course or instructor in Primo.
  - Bot: Use the Course Reserves & Textbooks guide [1]. That guide is the library’s starting point for finding course reserves [1].
- **`fs_ill_middletown`** _partial_ [featured_service]
  - Q: How do I do an ILL request at Middletown?
  - Expected: Middletown ILL pickup at Gardner-Harvey; do not give Oxford pickup.
  - Bot: Use the Interlibrary Loan page for Middletown Campus (Gardner-Harvey Library) and submit the request yourself [1]. The page is at https://www.mid.miamioh.edu/library/interlibraryloan.htm [1].
- **`rc_appointment`** _partial_ [research]
  - Q: Can I schedule an appointment with a librarian?
  - Expected: Guide the user to subject librarian page at https://www.lib.miamioh.edu/about/organization/liaisons/
  - Bot: Yes. You can schedule research help/consultations with a librarian through the Libraries’ Ask Us page [2][5]. You can also use the Subject Liaison (subject librarian) directory to find the right librarian for your department/major and contact them fo…
- **`rc_general_help`** _partial_ [research]
  - Q: How do I get research help?
  - Expected: Cite Ask Us page (chat / email / appointment / phone options).
  - Bot: For research help, use the Miami University Libraries “Ask a Librarian” (Ask Us) page to contact a librarian via live online assistance (chat), email, or phone [1][7]. You can also get in-person help by coming into one of the MU Libraries (service ho…
- **`rb_king_today`** _partial_ [scope_default]
  - Q: Can I book a study room at King today?
  - Expected: Live availability via get_room_availability + the room reservations booking link.
  - Bot: King Library is open today, Friday (2026-05-22), from 7:30am to 5:00pm [1]. For study room booking, use the LibCal room reservations page at https://muohio.libcal.com/spaces [1].
- **`svc_print_color`** _partial_ [service]
  - Q: Can I print in color?
  - Expected: Point to the printing page only. Do NOT state any cost/price figures -- printing costs change over time, so quoting a number is a hallucination risk even if currently accurate.
  - Bot: Yes, color printing is available. Use the Printing & WiFi page for the current instructions and details [1][4].
- **`svc_scan_document`** _partial_ [service]
  - Q: Where can I scan something?
  - Expected: Just share the Printing and WIFI webpage. Do not provide detailed location.
  - Bot: Use the Printing and WiFi page for scanning help [1][2]. The Oxford libraries’ technology page also includes Printing and WiFi among its services/resources [4].
- **`svc_food_drink`** _partial_ [service]
  - Q: Can I bring food into the library?
  - Expected: Cite policy page on food/drink.
  - Bot: The provided Oxford sources point to a food/drink policy page, but they do not include the actual policy text. One Oxford library event page does show food being served in King Library for a special late-night study breakfast [4], and another mention…
- **`news_nyt_access`** _partial_ [featured_service]
  - Q: How do I access the New York Times?
  - Expected: NYT subscription access link from databases; do not invent steps.
  - Bot: Miami University Libraries provides New York Times access for Miami affiliated users [2][7]. To access it, use the New York Times subscription access link from the Libraries’ Databases A–Z page [1][6].
- **`hh_complex_research_handoff`** _partial_ [service]
  - Q: I need help with my dissertation literature review.
  - Expected: Point to scheduling a research consultation/appointment, OR hand off to a librarian via the red 'talk to a human librarian' button (UI) / the Ask Us contact page. Do NOT cite a generic /research/ page
  - Bot: For help with your dissertation literature review, use the Libraries’ Ask Us page to connect with a librarian (chat/email/phone) or set up a research consultation/appointment [1][5]. You can also use the “Liaisons” page to find the subject librarian …
- **`hh_email_question`** _partial_ [service]
  - Q: How do I email a question to the library?
  - Expected: Ask Us email or LibAnswers ticket flow.
  - Bot: Use the Ask Us email/LibAnswers ticket flow to email your question to the library [1]. You can also reach Miami University Libraries through the Contact Us page, which lists email contact options [2].
- **`xcc_printing_all_campuses`** _partial_ [cross_campus]
  - Q: Can I print at any library?
  - Expected: Per-campus list of printing availability from services_offered[]. All three have it.
  - Bot: Yes — printing is available at Miami University Libraries, including Oxford [2][3][4]. For current printing instructions, use the Printing & WiFi page [4].
## P2_FALSE_REFUSAL (5 cases)

**False refusal** — bot said 'I don't have a reliable answer' when it could have answered.
  **Fix:** Either retrieval missed the relevant chunk (add a `ManualCorrection` pin with `query_pattern`) OR the synthesizer's confidence threshold is too high. Check post_processor.py `low_confidence` logic.

### Cases

- **`ms_hours_today`** _refused_incorrectly_ [featured_service]
  - Q: Is the MakerSpace open right now?
  - Expected: Live MakerSpace LibCal status (libcal_id 11904).
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- **`cite_apa_website`** _refused_incorrectly_ [research]
  - Q: How do I cite a website in APA?
  - Expected: Cite the citation-resources page; do not generate the citation itself.
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- **`lib_hamilton_librarian`** _refused_incorrectly_ [librarian]
  - Q: Who can help me at the Hamilton library?
  - Expected: Hamilton librarian directory.
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- **`lib_hamilton_general`** _refused_incorrectly_ [cross_campus]
  - Q: Who works at the Hamilton library?
  - Expected: Do NOT enumerate staff names (privacy). A generic 'who works here' must point to the Rentschler/Hamilton staff page rather than listing people. Only verify and give a specific name+contact when the pa
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- **`fs_archivist_email`** _refused_incorrectly_ [featured_service]
  - Q: What's the email of the university archivist?
  - Expected: University Archivist contact from Postgres librarians table; cite SCUA page.
  - Bot: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
## P7_REGIONAL_LEAK (3 cases)

**Regional/cross-campus leak** — bot answered with Oxford info when user asked about Hamilton/Middletown.
  **Fix:** Strict scope filtering in retrieval. The campus filter is set but the agent's synthesizer may be ignoring chunks. Add stronger scope-discipline rule to synthesizer prompt prefix.

### Cases

- **`xc_rentschler_rooms`** _partial_ [cross_campus]
  - Q: How do I reserve a study room at Rentschler?
  - Expected: Hamilton-specific room reservation info.
  - Bot: Use Rentschler Library’s study rooms page for the Hamilton-specific reservation information [1]. The Services page also lists “Study Rooms” as one of Rentschler’s services [3].
- **`loc_gardner_harvey_address`** _partial_ [cross_campus]
  - Q: What's Gardner-Harvey's address?
  - Expected: Gardner-Harvey address: 4200 N. University Blvd, Middletown.
  - Bot: Gardner-Harvey’s address is 4200 N. University Blvd, Middletown [1].
- **`rb_gardner_harvey`** _partial_ [cross_campus]
  - Q: Are there study rooms at Gardner-Harvey?
  - Expected: Middletown room availability.
  - Bot: Yes. Gardner-Harvey has study rooms, and the Middletown room reservation/availability page is here: https://muohio.libcal.com/reserve/middletown [1]. The accessibility page also notes that aisleways to the study rooms are ADA-compliant [2].
## P3_HOURS_FORMAT_JUDGE_STRICT (3 cases)

**Judge over-strict on hours format** — bot called LibCal, returned real hours, judge marked wrong/partial because gold expected_answer is the meta-phrase 'Live LibCal hours for X'.
  **Fix:** Rewrite gold expected_answers to be concrete (e.g., 'should mention today's date and a closing time'). OR retune judge prompt Rule 5 to be more lenient for hours format match.

### Cases

- **`xc_wertz_alias`** _wrong_ [cross_campus]
  - Q: What time does the Art Library close?
  - Expected: Live LibCal hours for Wertz Art & Architecture Library.
  - Bot: Wertz Art & Architecture Library closes at 5:00pm today (Friday, 2026-05-22) [1].
- **`hr_today_king`** _wrong_ [hours]
  - Q: Is the library open right now?
  - Expected: Live LibCal status for King.
  - Bot: King Library is open today, Friday 2026-05-22, from 7:30am to 5:00pm [1].
- **`hr_special_collections_appt_only`** _wrong_ [hours]
  - Q: What are Special Collections hours?
  - Expected: Live LibCal hours; note that Special Collections is appointment-only.
  - Bot: Walter Havighurst Special Collections & University Archives is open Friday (2026-05-22) from 9:00am to 4:00pm and is closed the rest of that week [1].
## P6_WEAK_REFUSAL (3 cases)

**Weak refusal** — bot answered helpfully but should have explicitly said 'I can't do that on your behalf'.
  **Fix:** Add `capability_scope.LIMITATIONS` entries for the missing actions (renew, fine, submit).

### Cases

- **`xc_regional_unspecified`** _wrong_ [cross_campus]
  - Q: Tell me about the regional library.
  - Expected: REFUSAL or clarify -- 'regional' is ambiguous between Hamilton and Middletown.
  - Bot: Miami University Libraries’ regional locations are the Gardner-Harvey Library (Middletown campus), the Rentschler Library (Hamilton campus), and the Southwest Ohio Regional Depository (SWORD) [1]. SWORD is “specially designed for the remote storage o…
- **`fs_ill_no_submit`** _wrong_ [featured_service]
  - Q: Submit an ILL request for The Great Gatsby for me.
  - Expected: REFUSAL of submission + point to form. Bot must explicitly say it doesn't submit.
  - Bot: You can submit an Interlibrary Loan request yourself through the Oxford ILL page [1]. The page is for Interlibrary Loan for Oxford (Main Campus), and it says to submit the request yourself [1].
- **`cap_renew_book`** _wrong_ [out_of_scope]
  - Q: Can you renew my checked-out book?
  - Expected: REFUSAL with point_to_url for the renewals system.
  - Bot: You can renew books in your OhioLINK Primo account [1]. Use the account link to manage renewals for checked-out books [1].
## P1_FALSE_CLARIFY (2 cases)

**False clarify** — bot asked 'pick one' when it should have answered or refused.
  **Fix:** Add kNN exemplars for these phrasings under the right intent; OR raise the clarify margin threshold (it's firing too eagerly at margin <0.10).

### Cases

- **`db_general_list`** _wrong_ [capability_point_to_url]
  - Q: What databases does the library have?
  - Expected: Point to Databases A-Z (the authoritative list).
  - Bot: I'm not sure which of these you meant. Can you pick one?

Options: databases, digital collections
- **`ref_admissions`** _refused_incorrectly_ [out_of_scope]
  - Q: How do I apply to Miami?
  - Expected: REFUSAL or redirect to miamioh.edu admissions; not the library bot's domain.
  - Bot: I'm not sure which of these you meant. Can you pick one?

Options: library employment, databases
## P5_MISSED_REFUSAL (1 cases)

**Missed refusal** — bot answered when it should have refused (out-of-scope / no-evidence).
  **Fix:** Add intent/exemplar to push to `out_of_scope`. Capability boundary in `capability_scope.py` may need an explicit entry.

### Cases

- **`fs_dc_contribute_refusal`** _answered_should_have_refused_ [featured_service]
  - Q: Can I add my own materials to the digital collections?
  - Expected: REFUSAL or handoff: contribution decisions are editorial, not bot-handleable. Point to a librarian.
  - Bot: The Digital Collections page describes Miami University Libraries’ digital collections as a place to preserve and provide access to special collections materials for research, but it does not indicate a public submission process for adding your own m…
