# Failure analysis — 77 not-fully-right cases (of 184 total)

_Generated 2026-05-23 from the final eval (post-PR #109 LibGuides fix)._


## capability_point_to_url — partial (3)

### `find_book_specific`

**Q:** Do you have a copy of Hamlet?

**Gold expected:** Point to Primo. Bot does NOT search the catalog itself.
**Gold URLs:** `https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU`

**Bot answered (722ms):**
> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results" and you think the library should have it, you can request it through Interlibrary Loan: https://www.lib.miamioh.edu/use/borrow/ill/

**Verdict:** `partial`

---

### `find_journal`

**Q:** Can you find a journal article for me?

**Gold expected:** Point to Primo and offer ILL fallback if Miami doesn't have it.
**Gold URLs:** `https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU`

**Bot answered (670ms):**
> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results" and you think the library should have it, you can request it through Interlibrary Loan: https://www.lib.miamioh.edu/use/borrow/ill/

**Verdict:** `partial`

---

### `find_books_topic`

**Q:** Where can I find books on Ohio history?

**Gold expected:** Point to Primo. Special Collections may also have relevant materials.
**Gold URLs:** `https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU`

**Bot answered (675ms):**
> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results" and you think the library should have it, you can request it through Interlibrary Loan: https://www.lib.miamioh.edu/use/borrow/ill/

**Verdict:** `partial`

---


## capability_point_to_url — wrong (1)

### `db_general_list`

**Q:** What databases does the library have?

**Gold expected:** Point to Databases A-Z (the authoritative list).
**Gold URLs:** `https://libguides.lib.miamioh.edu/az/databases`

**Bot answered (678ms):**
> I'm not sure which of these you meant. Can you pick one?

Options: databases, digital collections

**Verdict:** `wrong`

---


## circulation — partial (7)

### `circ_place_hold`

**Q:** How do I place a hold on a book at Miami?

**Gold expected:** Search Primo, click 'Place Hold' on the title, sign in. Cite circulation policies.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`, `https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU`

**Bot answered (5291ms):**
> Search for the book in Primo, then click "Place Hold" on the title and sign in [1][2]. You can choose Oxford Campus / King Library as the pickup location when placing the hold [4].

**Verdict:** `partial`

---

### `circ_pickup_when`

**Q:** When will my book be ready for pickup?

**Gold expected:** Same-day for in-stock items; longer if from storage or another campus. Email notification on ready.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (4664ms):**
> Same-day for in-stock items; it can take longer if the book comes from storage or another campus, and you’ll get an email when it’s ready [1].

**Verdict:** `partial`

---

### `circ_online_checkout`

**Q:** How do I check out a book online for pickup?

**Gold expected:** Place a hold via Primo, choose pickup location, retrieve when notified.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (6337ms):**
> Search for the book in Primo, click "Place Hold," and sign in [5]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [2][4].

**Verdict:** `partial`

---

### `renew_basic`

**Q:** Can I renew my book?

**Gold expected:** Yes, but renewal differs by material type. Miami materials: point to the circulation-policies loan-periods-fines page. OhioLINK/ILL materials: point to the loan-periods-ohiolink-ill page. Distinguish the two paths; do not give a single generic answer.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-fines`, `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill`

**Bot answered (6219ms):**
> Yes — you can renew books in your OhioLINK Primo account [1].

**Verdict:** `partial`

---

### `renew_how_many`

**Q:** How many times can I renew a book?

**Gold expected:** Renewal limit per user type from circulation policies LibGuide; do not invent a number.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (6974ms):**
> The renewal limit depends on your user type; see the circulation policies page for the current limit [1]. If you are trying to renew a checked-out book, use your OhioLINK Primo account [6].

**Verdict:** `partial`

---

### `reserves_find`

**Q:** How do I find course reserves?

**Gold expected:** Cite reserves page; mention search by course or instructor in Primo.
**Gold URLs:** `https://www.lib.miamioh.edu/use/borrow/reserves/`

**Bot answered (4352ms):**
> Use the Course Reserves & Textbooks guide [1]. That guide is the library’s starting point for finding course reserves [1].

**Verdict:** `partial`

---

### `reserves_my_class`

**Q:** Where are my course reserves?

**Gold expected:** Search Primo by course/instructor; physical reserves are at King circulation desk. Cite reserves page.
**Gold URLs:** `https://www.lib.miamioh.edu/use/borrow/reserves/`

**Bot answered (6707ms):**
> Course reserves and textbooks are covered in the Course Reserves & Textbooks guide [1]. Use that guide to find the current reserves process and location details for Oxford [1].

**Verdict:** `partial`

---


## circulation — refused_incorrectly (1)

### `loan_grad_period`

**Q:** What's the loan period for graduate students?

**Gold expected:** Graduate student loan period from circulation policies; do not estimate.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (8009ms):**
> I started to answer but couldn't verify my sources. Rather than send you something I can't back up, please ask a librarian through Ask Us.

**Verdict:** `refused_incorrectly`

---


## cross_campus — partial (7)

### `xc_rentschler_rooms`

**Q:** How do I reserve a study room at Rentschler?

**Gold expected:** Hamilton-specific room reservation info.
**Gold URLs:** `https://www.ham.miamioh.edu/library/study-rooms/`

**Bot answered (4899ms):**
> Use Rentschler Library’s study rooms page for the Hamilton-specific reservation information [1]. The Services page also lists “Study Rooms” as one of Rentschler’s services [3].

**Verdict:** `partial`

---

### `xc_main_library_default_to_king`

**Q:** When does the main library close?

**Gold expected:** King Library hours.
**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/king-library/`, `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (4856ms):**
> King Library (the main library) closes today at 5:00pm [1].

**Verdict:** `partial`

---

### `xc_compare_3d_printing`

**Q:** Do all libraries have 3D printing?

**Gold expected:** King has 3D printing in its Makerspace. Middletown has 3D printing in its TEC Lab Makerspace. Hamilton does NOT have 3D printing nor a Makerspace. Cite the King Makerspace LibGuide + the Middletown TEC Lab LibGuide; refuse the Hamilton claim.
**Gold URLs:** `https://libguides.lib.miamioh.edu/create/makerspace/home`, `https://libguides.lib.miamioh.edu/middletown_tec_lab/home`

**Bot answered (9172ms):**
> No. On the Oxford campus, 3D printing is available at King Library in its MakerSpace [1]. 3D printing is also available at the Middletown campus in the TEC Lab MakerSpace [2].

**Verdict:** `partial`

---

### `xc_explicit_alias_overrides_origin`

**Q:** What are King's hours?

**Gold expected:** King Library hours.
**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/king-library/`, `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (3576ms):**
> King Library is open today, Friday (2026-05-22), from 7:30am to 5:00pm [1].

**Verdict:** `partial`

---

### `loc_gardner_harvey_address`

**Q:** What's Gardner-Harvey's address?

**Gold expected:** Gardner-Harvey address: 4200 N. University Blvd, Middletown.
**Gold URLs:** `https://www.mid.miamioh.edu/library/`

**Bot answered (21707ms):**
> Gardner-Harvey’s address is 4200 N. University Blvd, Middletown [1].

**Verdict:** `partial`

---

### `rb_gardner_harvey`

**Q:** Are there study rooms at Gardner-Harvey?

**Gold expected:** Middletown room availability.
**Gold URLs:** `https://muohio.libcal.com/reserve/middletown`

**Bot answered (6167ms):**
> Yes. Gardner-Harvey has study rooms, and the Middletown room reservation/availability page is here: https://muohio.libcal.com/reserve/middletown [1]. The accessibility page also notes that aisleways to the study rooms are ADA-compliant [2].

**Verdict:** `partial`

---

### `xcc_printing_all_campuses`

**Q:** Can I print at any library?

**Gold expected:** Per-campus list of printing availability from services_offered[]. All three have it.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`, `https://www.lib.miamioh.edu/about/locations/art-arch/`, `https://www.ham.miamioh.edu/library/services/computers-printing-and-copying/`, `https://www.mid.miamioh.edu/library/printing.htm`

**Bot answered (5529ms):**
> Yes — printing is available at Miami University Libraries, including Oxford [2][3][4]. For current printing instructions, use the Printing & WiFi page [4].

**Verdict:** `partial`

---


## cross_campus — refused_incorrectly (1)

### `lib_hamilton_general`

**Q:** Who works at the Hamilton library?

**Gold expected:** Do NOT enumerate staff names (privacy). A generic 'who works here' must point to the Rentschler/Hamilton staff page rather than listing people. Only verify and give a specific name+contact when the patron explicitly asks for that person or a subject librarian.
**Gold URLs:** `https://www.ham.miamioh.edu/library/about/rentschler-library-staff/`

**Bot answered (4505ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `refused_incorrectly`

---


## cross_campus — wrong (5)

### `xc_wertz_alias`

**Q:** What time does the Art Library close?

**Gold expected:** Live LibCal hours for Wertz Art & Architecture Library.
**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/art-arch/`, `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (3633ms):**
> Wertz Art & Architecture Library closes at 5:00pm today (Friday, 2026-05-22) [1].

**Verdict:** `wrong`

---

### `xc_session_origin_hamilton`

**Q:** Can I book a room?

**Gold expected:** By default, if the user has not mentioned any regional campus, the answer defaults to King. Present King Library's study room reservation tool (LibCal allspaces) as the answer, not regional study rooms.
**Gold URLs:** `https://muohio.libcal.com/allspaces`

**Bot answered (2837ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `wrong`

---

### `xc_regional_unspecified`

**Q:** Tell me about the regional library.

**Gold expected:** REFUSAL or clarify -- 'regional' is ambiguous between Hamilton and Middletown.
**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/regional/`

**Bot answered (11249ms):**
> Miami University Libraries’ regional locations are the Gardner-Harvey Library (Middletown campus), the Rentschler Library (Hamilton campus), and the Southwest Ohio Regional Depository (SWORD) [1]. SWORD is “specially designed for the remote storage of permanently held, little used library materials” from multiple universities’ library collections and is located on Miami University’s Middletown Campus [7]. The Libraries’ regional locations page lists addresses and phone numbers for Gardner-Harvey and Rentschler, and links to each location for more details [1].

**Verdict:** `wrong`

---

### `sd_origin_hamilton_default`

**Q:** Is the library open today?

**Gold expected:** Origin=hamilton -> Rentschler hours, NOT King.
**Gold URLs:** `https://www.ham.miamioh.edu/library/about/hours/`, `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (5939ms):**
> King Library is closed today (Saturday, 2026-05-23) [1].

**Verdict:** `wrong`

---

### `sd_origin_middletown_default`

**Q:** How do I book a study room?

**Gold expected:** Origin=middletown -> Gardner-Harvey, NOT King.
**Gold URLs:** `https://muohio.libcal.com/reserve/middletown`

**Bot answered (7477ms):**
> Use the Room Reservations page to book study rooms online [1]. For King specifically, the room reservation system includes a King booking link and live availability through LibCal [2].

**Verdict:** `wrong`

---


## featured_service — answered_should_have_refused (1)

### `fs_dc_contribute_refusal`

**Q:** Can I add my own materials to the digital collections?

**Gold expected:** REFUSAL or handoff: contribution decisions are editorial, not bot-handleable. Point to a librarian.
**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (9874ms):**
> The Digital Collections page describes Miami University Libraries’ digital collections as a place to preserve and provide access to special collections materials for research, but it does not indicate a public submission process for adding your own materials [1]. Use the front door at https://www.lib.miamioh.edu/digital-collections/ to explore the collections and related information [1][2][3].

**Verdict:** `answered_should_have_refused`

---


## featured_service — partial (6)

### `fs_ill_hamilton`

**Q:** How do I get a book from another library to Hamilton?

**Gold expected:** Hamilton-specific ILL pickup info + request form URL.
**Gold URLs:** `http://ill.lib.miamioh.edu/illiad/logon.html`

**Bot answered (3823ms):**
> Use Interlibrary Loan for Hamilton Campus (Rentschler Library) to request the book [1]. The guide says you submit the request yourself; the bot does not place ILL requests [1].

**Verdict:** `partial`

---

### `fs_special_collections_access`

**Q:** How do I see something in Special Collections?

**Gold expected:** Appointment-only access, contact info for archivist.
**Gold URLs:** `https://spec.lib.miamioh.edu/home/`

**Bot answered (6274ms):**
> Special Collections uses appointment-only research access [1][2]. The Special Collections page is the place to start for access details and to arrange a research appointment [1][2].

**Verdict:** `partial`

---

### `ms_vinyl_cutter`

**Q:** Is there a vinyl cutter at the MakerSpace?

**Gold expected:** Tell user to check for themself at https://muohio.libcal.com/reserve/equipment/makerspace
**Gold URLs:** `https://muohio.libcal.com/reserve/equipment/makerspace`

**Bot answered (5554ms):**
> Check the MakerSpace equipment page for the current list of tools, including whether a vinyl cutter is available [1][6].

**Verdict:** `partial`

---

### `fs_acrobat_pro`

**Q:** Where can I get Acrobat Pro?

**Gold expected:** Adobe Acrobat Pro is available via Software Checkout (part of Adobe CC); cover student vs faculty/staff; cite the software page.
**Gold URLs:** `https://www.lib.miamioh.edu/software/`

**Bot answered (6833ms):**
> Adobe Acrobat Pro is available through Miami University Libraries’ Software Checkout as part of Adobe Creative Cloud [1][4]. For faculty/staff, you can reserve an Adobe Acrobat Pro license, then log in at adobe.com with your Miami credentials to download and use Acrobat Pro on your own device [4]. Students can access Adobe Creative Cloud (which includes Acrobat Pro) through the same Software Checkout program [5].

**Verdict:** `partial`

---

### `fs_ill_middletown`

**Q:** How do I do an ILL request at Middletown?

**Gold expected:** Middletown ILL pickup at Gardner-Harvey; do not give Oxford pickup.
**Gold URLs:** `https://www.lib.miamioh.edu/use/borrow/ill/`

**Bot answered (3862ms):**
> Use the Interlibrary Loan page for Middletown Campus (Gardner-Harvey Library) and submit the request yourself [1]. The page is at https://www.mid.miamioh.edu/library/interlibraryloan.htm [1].

**Verdict:** `partial`

---

### `news_nyt_access`

**Q:** How do I access the New York Times?

**Gold expected:** NYT subscription access link from databases; do not invent steps.
**Gold URLs:** `https://libguides.lib.miamioh.edu/az/databases`

**Bot answered (7993ms):**
> Miami University Libraries provides New York Times access for Miami affiliated users [2][7]. To access it, use the New York Times subscription access link from the Libraries’ Databases A–Z page [1][6].

**Verdict:** `partial`

---


## featured_service — refused_incorrectly (3)

### `ms_hours_today`

**Q:** Is the MakerSpace open right now?

**Gold expected:** Live MakerSpace LibCal status (libcal_id 11904).
**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (3244ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `refused_incorrectly`

---

### `fs_ill_return`

**Q:** Where do I return an interlibrary loan book?

**Gold expected:** Return-flow info per the OhioLINK & ILL loan-periods policy page. OhioLINK items should be returned to a bookdrop. Do not invent a return location for ILL items not stated on the policy page.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill`, `https://www.lib.miamioh.edu/use/borrow/ill/`

**Bot answered (3868ms):**
> Interlibrary Loan for Oxford (Main Campus) is handled through the ILL request page [1]. Submit the request yourself; the bot does not place ILL requests [1].

**Verdict:** `refused_incorrectly`

---

### `fs_archivist_email`

**Q:** What's the email of the university archivist?

**Gold expected:** University Archivist contact from Postgres librarians table; cite SCUA page.
**Gold URLs:** `https://spec.lib.miamioh.edu/home/`

**Bot answered (5339ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `refused_incorrectly`

---


## featured_service — wrong (11)

### `fs_adobe_student`

**Q:** I'm a student, how do I install Adobe?

**Gold expected:** Student Adobe Creative Cloud license access.
**Gold URLs:** `https://www.lib.miamioh.edu/software/`

**Bot answered (4666ms):**
> Use the Adobe Creative Cloud student access path on the Miami Libraries Software page, which points students to the Adobe installation instructions [1][2]. If you need the direct Adobe details, follow the Adobe page linked from Software Checkout [4].

**Verdict:** `wrong`

---

### `fs_ill_no_submit`

**Q:** Submit an ILL request for The Great Gatsby for me.

**Gold expected:** REFUSAL of submission + point to form. Bot must explicitly say it doesn't submit.
**Gold URLs:** `https://www.lib.miamioh.edu/use/borrow/ill/`

**Bot answered (4269ms):**
> You can submit an Interlibrary Loan request yourself through the Oxford ILL page [1]. The page is for Interlibrary Loan for Oxford (Main Campus), and it says to submit the request yourself [1].

**Verdict:** `wrong`

---

### `fs_makerspace_3d`

**Q:** Does the MakerSpace have a 3D printer?

**Gold expected:** Yes, from LibrarySpace.equipment lookup -- not from prose.
**Gold URLs:** `https://www.lib.miamioh.edu/use/spaces/makerspace/`

**Bot answered (4117ms):**
> Yes. The MakerSpace at King Library has a 3D printer [1][2][3].

**Verdict:** `wrong`

---

### `fs_digital_collections_intro`

**Q:** What digital collections does Miami have?

**Gold expected:** Intro/overview of Digital Collections with the front-door URL; naming example collections is acceptable.
**Gold URLs:** `https://www.lib.miamioh.edu/digital-collections/`

**Bot answered (6740ms):**
> Miami University Libraries’ Digital Collections include thousands of digital objects—such as photographs, advertising trade cards, newspapers, manuscripts, and videos—from the Walter Havighurst Special Collections & University Archives [1]. Example named collections include the Postcard Collection, Civil War Diaries, Cradle of Coaches, the KAOS Student Newspaper, and the Freedom Summer Digital Archive [2]. You can browse the full set of collections at https://www.lib.miamioh.edu/digital-collections/ (also accessible via https://www.lib.miamioh.edu/digital) [1][4].

**Verdict:** `wrong`

---

### `fs_nyt_subscription`

**Q:** Do you have access to the New York Times?

**Gold expected:** We do have access to New York Times for Miami affiliated users. https://libguides.lib.miamioh.edu/newspapers
**Gold URLs:** `https://libguides.lib.miamioh.edu/az/databases`

**Bot answered (3822ms):**
> Yes — Miami affiliated users have access to The New York Times [1]. For access, use the NYT subscription link from the databases page [2].

**Verdict:** `wrong`

---

### `ill_oxford_request`

**Q:** How do I request a book through ILL?

**Gold expected:** Brief ILL explanation + link to Oxford ILL request form. Never submits the request.
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill`, `https://www.lib.miamioh.edu/use/borrow/ill/`

**Bot answered (3644ms):**
> Use the Interlibrary Loan page for Oxford (Main Campus) to submit the request yourself [1]. The page is the place to start for requesting a book through ILL [1].

**Verdict:** `wrong`

---

### `adobe_faculty_path`

**Q:** I'm faculty -- where do I download Adobe?

**Gold expected:** Faculty/staff Adobe deal -- different from student license. Cite software/adobe page.
**Gold URLs:** `https://www.lib.miamioh.edu/software/`, `https://muohio.libcal.com/equipment/item/82764`, `https://muohio.libcal.com/equipment/item/172159`

**Bot answered (4576ms):**
> Faculty can get Adobe Creative Cloud through Software Checkout on the Miami Libraries software page [1]. After you check out a license, you log in at adobe.com using your Miami credentials and download Adobe to your own device [1].

**Verdict:** `wrong`

---

### `fs_indesign_faculty`

**Q:** Faculty here, do I have InDesign access?

**Gold expected:** Yes -- faculty/staff get Adobe Creative Cloud (incl. InDesign) via Software Checkout; cite the software page.
**Gold URLs:** `https://www.lib.miamioh.edu/software/`

**Bot answered (8234ms):**
> Yes. Faculty/staff at Oxford can get Adobe Creative Cloud through Software Checkout, and Adobe Creative Cloud includes InDesign [1][4].

**Verdict:** `wrong`

---

### `fs_premiere_pro`

**Q:** Can I use Premiere Pro through the library?

**Gold expected:** Adobe CC suite access; clarify audience if not stated.
**Gold URLs:** `https://www.lib.miamioh.edu/software/`

**Bot answered (4589ms):**
> Yes. The library’s Adobe Creative Cloud access includes Premiere Pro among the available products, and it is available through the software checkout page [1][5].

**Verdict:** `wrong`

---

### `fs_ill_fee`

**Q:** Are there fees for interlibrary loan?

**Gold expected:** There is no fee for Miami affiliated users. Check on https://www.lib.miamioh.edu/use/borrow/ill/
**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill`

**Bot answered (3424ms):**
> Use the Interlibrary Loan page for Oxford (Main Campus) to check the current policy and any fees [1]. The page is the place to submit requests yourself, and it carries the current ILL details [1].

**Verdict:** `wrong`

---

### `fs_makerspace_walkin`

**Q:** Can I just walk into the MakerSpace?

**Gold expected:** Walk-in vs reservation policy from MakerSpace page; do not infer.
**Gold URLs:** `https://www.lib.miamioh.edu/use/spaces/makerspace/`

**Bot answered (4708ms):**
> The MakerSpace page covers walk-in versus reservation use, so check that page for the current policy [1]. For booking-related details, the consultation flow is on the MakerSpace consultation page [2][3].

**Verdict:** `wrong`

---


## hours — wrong (2)

### `hr_today_king`

**Q:** Is the library open right now?

**Gold expected:** Live LibCal status for King.
**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (5348ms):**
> King Library is open today, Friday 2026-05-22, from 7:30am to 5:00pm [1].

**Verdict:** `wrong`

---

### `hr_special_collections_appt_only`

**Q:** What are Special Collections hours?

**Gold expected:** Live LibCal hours; note that Special Collections is appointment-only.
**Gold URLs:** `https://spec.lib.miamioh.edu/`, `https://www.lib.miamioh.edu/about/locations/hours/`

**Bot answered (4195ms):**
> Walter Havighurst Special Collections & University Archives is open Friday (2026-05-22) from 9:00am to 4:00pm and is closed the rest of that week [1].

**Verdict:** `wrong`

---


## librarian — partial (3)

### `lib_biology_subject`

**Q:** Who is the biology librarian?

**Gold expected:** Subject librarian for Biology -- name, email, phone from Postgres.
**Gold URLs:** `https://www.lib.miamioh.edu/about/organization/liaisons/`

**Bot answered (10196ms):**
> Find the biology subject librarian on the Liaisons page [1].

**Verdict:** `partial`

---

### `lib_history_subject`

**Q:** I need the history subject librarian.

**Gold expected:** History is covered by the Humanities & Social Sciences subject librarian (Jenny Presnell); return that one person's name/email/phone.
**Gold URLs:** `https://www.lib.miamioh.edu/about/organization/liaisons/`

**Bot answered (6320ms):**
> Find the history subject librarian on the Liaisons page [1].

**Verdict:** `partial`

---

### `lib_subject_bio`

**Q:** Who is the librarian for Biology?

**Gold expected:** Exact name + email + phone of the Biology subject librarian, from Postgres.
**Gold URLs:** `https://www.lib.miamioh.edu/about/organization/liaisons/`

**Bot answered (4770ms):**
> The Biology librarian is Ginny Boehme [1]. Her email is boehmemv@miamioh.edu [1].

**Verdict:** `partial`

---


## librarian — refused_incorrectly (1)

### `lib_hamilton_librarian`

**Q:** Who can help me at the Hamilton library?

**Gold expected:** Hamilton librarian directory.
**Gold URLs:** `https://www.ham.miamioh.edu/library/about/rentschler-library-staff/`

**Bot answered (4072ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `refused_incorrectly`

---


## out_of_scope — refused_incorrectly (3)

### `ref_admissions`

**Q:** How do I apply to Miami?

**Gold expected:** REFUSAL or redirect to miamioh.edu admissions; not the library bot's domain.
**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (673ms):**
> I'm not sure which of these you meant. Can you pick one?

Options: library employment, databases

**Verdict:** `refused_incorrectly`

---

### `ref_account_renewal`

**Q:** Renew my book.

**Gold expected:** REFUSAL of action + point to account/renewal URL.
**Gold URLs:** `https://ohiolink-mu.primo.exlibrisgroup.com/nde/login?vid=01OHIOLINK_MU:MU_NDE26&lang=en`

**Bot answered (3609ms):**
> Renew books in your OhioLINK Primo account [1].

**Verdict:** `refused_incorrectly`

---

### `oos_catalog_search`

**Q:** Do you have a copy of Foundation by Asimov?

**Gold expected:** REFUSAL: the bot doesn't search the catalog; point to the catalog search on the libraries homepage.
**Gold URLs:** `https://www.lib.miamioh.edu/`

**Bot answered (673ms):**
> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results" and you think the library should have it, you can request it through Interlibrary Loan: https://www.lib.miamioh.edu/use/borrow/ill/

**Verdict:** `refused_incorrectly`

---


## out_of_scope — wrong (1)

### `cap_renew_book`

**Q:** Can you renew my checked-out book?

**Gold expected:** REFUSAL with point_to_url for the renewals system.
**Gold URLs:** `https://ohiolink-mu.primo.exlibrisgroup.com/nde/login?vid=01OHIOLINK_MU:MU_NDE26&lang=en`

**Bot answered (3714ms):**
> You can renew books in your OhioLINK Primo account [1]. Use the account link to manage renewals for checked-out books [1].

**Verdict:** `wrong`

---


## research — partial (2)

### `rc_appointment`

**Q:** Can I schedule an appointment with a librarian?

**Gold expected:** Guide the user to subject librarian page at https://www.lib.miamioh.edu/about/organization/liaisons/
**Gold URLs:** `https://www.lib.miamioh.edu/about/organization/liaisons/`

**Bot answered (10289ms):**
> Yes. You can schedule research help/consultations with a librarian through the Libraries’ Ask Us page [2][5]. You can also use the Subject Liaison (subject librarian) directory to find the right librarian for your department/major and contact them for an appointment [1][4].

**Verdict:** `partial`

---

### `rc_general_help`

**Q:** How do I get research help?

**Gold expected:** Cite Ask Us page (chat / email / appointment / phone options).
**Gold URLs:** `https://www.lib.miamioh.edu/research/research-support/ask/`

**Bot answered (11042ms):**
> For research help, use the Miami University Libraries “Ask a Librarian” (Ask Us) page to contact a librarian via live online assistance (chat), email, or phone [1][7]. You can also get in-person help by coming into one of the MU Libraries (service hours vary throughout the year) [7]. If you want more in-depth help (e.g., research strategy), you can schedule a research consultation/appointment and/or connect with a subject librarian through the Libraries’ liaisons page [2][3][5].

**Verdict:** `partial`

---


## research — refused_incorrectly (1)

### `cite_apa_website`

**Q:** How do I cite a website in APA?

**Gold expected:** Cite the citation-resources page; do not generate the citation itself.
**Gold URLs:** `https://libguides.lib.miamioh.edu/citation/apa`

**Bot answered (2629ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Verdict:** `refused_incorrectly`

---


## research — wrong (1)

### `ds_gis`

**Q:** Can someone help me with GIS?

**Gold expected:** Yes via data services consultations. Cite data services page.
**Gold URLs:** `https://www.lib.miamioh.edu/research/creation/data-services/`

**Bot answered (6859ms):**
> Yes — Oxford Library data services offers consultations, and the GIS article says library staff are happy to help with GIS projects [1][2]. The data services page also says it provides data services support, including GIS help and data visualization support [4].

**Verdict:** `wrong`

---


## scope_default — partial (1)

### `rb_king_today`

**Q:** Can I book a study room at King today?

**Gold expected:** Live availability via get_room_availability + the room reservations booking link.
**Gold URLs:** `https://muohio.libcal.com/reserve/king`

**Bot answered (6262ms):**
> King Library is open today, Friday (2026-05-22), from 7:30am to 5:00pm [1]. For study room booking, use the LibCal room reservations page at https://muohio.libcal.com/spaces [1].

**Verdict:** `partial`

---


## service — partial (11)

### `svc_print_color`

**Q:** Can I print in color?

**Gold expected:** Point to the printing page only. Do NOT state any cost/price figures -- printing costs change over time, so quoting a number is a hallucination risk even if currently accurate.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`

**Bot answered (4491ms):**
> Yes, color printing is available. Use the Printing & WiFi page for the current instructions and details [1][4].

**Verdict:** `partial`

---

### `svc_scan_document`

**Q:** Where can I scan something?

**Gold expected:** Just share the Printing and WIFI webpage. Do not provide detailed location.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`

**Bot answered (4612ms):**
> Use the Printing and WiFi page for scanning help [1][2]. The Oxford libraries’ technology page also includes Printing and WiFi among its services/resources [4].

**Verdict:** `partial`

---

### `svc_food_drink`

**Q:** Can I bring food into the library?

**Gold expected:** Cite policy page on food/drink.
**Gold URLs:** `https://docs.google.com/document/d/1ZQdegDmo_8V7_aM8EMzpr57lQ5-kOj_jgtCqsbJ8_d4/edit#bookmark=id.7hxtip1fvnqu`

**Bot answered (5508ms):**
> The provided Oxford sources point to a food/drink policy page, but they do not include the actual policy text. One Oxford library event page does show food being served in King Library for a special late-night study breakfast [4], and another mentions free food at a game night in Wertz [5]. For the current rule on bringing food into the library, please use the library’s food/drink policy page referenced by the sources [1][2][3].

**Verdict:** `partial`

---

### `tech_chromebook_period`

**Q:** How long is the chromebook checkout period?

**Gold expected:** 30 days per the tech-checkout page.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/tech-checkout/`

**Bot answered (4918ms):**
> Chromebooks can be checked out for 30 days [1][2]. The tech checkout page says libraries offer equipment to borrow at a checkout desk with your university ID [3].

**Verdict:** `partial`

---

### `tech_charger`

**Q:** Do you have charger cables to borrow?

**Gold expected:** Yes -- chargers for Mac/PC/phones, plus other peripherals. Cite tech-checkout page.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/tech-checkout/`

**Bot answered (6297ms):**
> Yes — Oxford libraries let you borrow chargers and cables, including chargers for phones and laptops [1][3]. The equipment checkout page says to come to a library checkout desk with your university ID to borrow equipment [2].

**Verdict:** `partial`

---

### `sw_what_installed`

**Q:** What software is on the library computers?

**Gold expected:** Cite the software-on-library-computers page; do not enumerate beyond what's listed.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/software/`

**Bot answered (5453ms):**
> The library computers have Windows software including Adobe Creative Cloud, Audio-Video Viewing/Editing tools like Audacity and VLC Media Player, web browsers like Chrome and Safari, office software like Apple Keynote, Numbers, Pages, and Microsoft Office (Excel, PowerPoint, and Word), plus specialty software and utilities such as Logger Pro and Xcode [1][3]. The page also notes that additional titles such as MATLAB and SPSS may be available on campus Macs through self-service software install [3].

**Verdict:** `partial`

---

### `sw_matlab`

**Q:** Is MATLAB available on library computers?

**Gold expected:** Confirm only if listed on the software page; otherwise refuse to assert.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/software/`

**Bot answered (6050ms):**
> Yes. The software page says additional titles such as MATLAB can be added to library computers using Software Center on campus Windows PCs and Self-Service on campus Macs [3][5].

**Verdict:** `partial`

---

### `sw_install_personal`

**Q:** Can I install SPSS on a library computer?

**Gold expected:** Yes -- additional titles (e.g. MATLAB, SPSS; plus Xcode on Mac) CAN be added to library computers yourself: Software Center on campus Windows PCs, Self-Service on campus Macs. Cite the software page.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/software/`

**Bot answered (5567ms):**
> Yes. The Oxford library software page says additional titles such as MATLAB, SPSS, and Xcode are available for you to add to library computers using the Self-Service software install on campus Macs [2], and the page also describes software available on library computers [3].

**Verdict:** `partial`

---

### `cit_no_libguide_fabrication`

**Q:** Is there a LibGuide on citation styles?

**Gold expected:** Point to the citation LibGuide (https://libguides.lib.miamioh.edu/citation). Cite only real official pages; never fabricate.
**Gold URLs:** `https://libguides.lib.miamioh.edu/citation`

**Bot answered (7405ms):**
> Yes — Miami University Libraries has a citation LibGuide at https://libguides.lib.miamioh.edu/citation [1]. The library also has a shortcut URL, https://www.lib.miamioh.edu/citing, that redirects to the same guide [2].

**Verdict:** `partial`

---

### `hh_complex_research_handoff`

**Q:** I need help with my dissertation literature review.

**Gold expected:** Point to scheduling a research consultation/appointment, OR hand off to a librarian via the red 'talk to a human librarian' button (UI) / the Ask Us contact page. Do NOT cite a generic /research/ page.
**Gold URLs:** `https://www.lib.miamioh.edu/research/research-support/ask/`

**Bot answered (11392ms):**
> For help with your dissertation literature review, use the Libraries’ Ask Us page to connect with a librarian (chat/email/phone) or set up a research consultation/appointment [1][5]. You can also use the “Liaisons” page to find the subject librarian for your department/area and schedule an in-depth research consultation with them [3][4].

**Verdict:** `partial`

---

### `hh_email_question`

**Q:** How do I email a question to the library?

**Gold expected:** Ask Us email or LibAnswers ticket flow.
**Gold URLs:** `https://www.lib.miamioh.edu/research/research-support/ask/`

**Bot answered (5993ms):**
> Use the Ask Us email/LibAnswers ticket flow to email your question to the library [1]. You can also reach Miami University Libraries through the Contact Us page, which lists email contact options [2].

**Verdict:** `partial`

---


## service — wrong (5)

### `cit_no_fake_url`

**Q:** Where can I find the printing policy?

**Gold expected:** Real printing policy URL only -- no fabricated /policies/printing.html.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`

**Bot answered (4777ms):**
> Use the Printing & WiFi page for Oxford printing policy information [1][3]. The page is the canonical printing page for the library’s current printing details [3][4].

**Verdict:** `wrong`

---

### `svc_print_from_laptop`

**Q:** How do I print from my laptop?

**Gold expected:** Cite printing page; the 'one canonical printing page' invariant.
**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`

**Bot answered (11000ms):**
> Use the Printing & WiFi page for the current steps to print from your laptop [1][2].

**Verdict:** `wrong`

---

### `svc_silent_floor`

**Q:** Where is the silent study area?

**Gold expected:** King Library quiet/silent floor location -- retrieval picks King via Oxford default + ranking.
**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (5022ms):**
> The Libraries’ virtual silent study option is the Virtual Study Hall, described as a silent study atmosphere on Zoom for Miami University peers [1]. If you meant a physical quiet space, the Oxford libraries also have reading rooms within King Library, and the room-reservations page lets you reserve study spaces online [2][3].

**Verdict:** `wrong`

---

### `space_silent`

**Q:** Where is the silent study area?

**Gold expected:** The bot has no specific info; do not assert a silent floor or invent a URL.
**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (4529ms):**
> The Oxford Libraries’ virtual silent study option is a Zoom-based “Virtual Study Hall” [1]. If you mean an in-person quiet area, the Libraries’ reading rooms in King Library are open [2].

**Verdict:** `wrong`

---

### `space_food`

**Q:** Can I bring food into the library?

**Gold expected:** Food/drink policy from spaces or policies page.
**Gold URLs:** `https://docs.google.com/document/d/1ZQdegDmo_8V7_aM8EMzpr57lQ5-kOj_jgtCqsbJ8_d4/edit#bookmark=id.7hxtip1fvnqu`

**Bot answered (6644ms):**
> The sources point to the Oxford library food/drink policy page for the current rules on bringing food into the library [1][2][3]. One Oxford library event announcement also shows food can be present in King Library during a special program, but it does not state the general policy [4].

**Verdict:** `wrong`

---

