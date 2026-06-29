# Eval review — v2 (2026-06-29)

Re-run after the citation/archivist/3D/cancel fixes. correct_rate **58.1%** (was 55.2%); wrong 10.7% (was 14.2%); bad-refusals 4 (was 12).

Below: the 98 cases judged wrong / partial / bad-refusal, for human re-label. Many "wrong/partial" are debatable gold expectations or judge harshness, not real bot errors — mark each: BOT-OK (gold/judge wrong) vs REAL (fix needed).

### [refused_incorrectly] (cross_campus) How do I reserve a study room at Rentschler?
- intent: room_booking  | refusal: True
- WANT: Hamilton-specific room reservation info.
- BOT: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [refused_incorrectly] (featured_service) Can I read the Cincinnati Enquirer through the library?
- intent: newspapers  | refusal: True
- WANT: Confirm subscription only if it appears in databases list; otherwise refuse.
- BOT: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [refused_incorrectly] (service) Can I book a study room in Special Collections?
- intent: room_booking  | refusal: True
- WANT: REFUSAL: Special Collections is appointment-only research, not study-room booking. Direct user to research_appointments.
- BOT: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [refused_incorrectly] (service) Is there a nursing room or lactation space in the library?
- intent: av_production  | refusal: False
- WANT: Should answer from the King location page if a nursing/lactation room is documented (often in main university buildings), or refuse and point to the King location page / university accessibility resources if not stated. Should not invent a 
- BOT: The King Library location page lists study rooms, the MakerSpace, studios, technology checkout, printing/scanning, and other services, but it does not mention a nursing room or lactation space [1]. For the most up-to-date details about what
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (circulation) How do I place a hold on a book at Miami?
- intent: circulation_basic  | refusal: False
- WANT: Should answer with substance like: "Search for the book in Primo, then click "Place Hold" on the title and sign in [1][2]. You can choose Oxford Campus / King Library as the pickup location when placing the hold [4].". Bot wording may vary;
- BOT: Search for the book in Primo, then click “Place Hold” on the title and sign in [1][2]. You can choose Oxford Campus / King Library as the pickup location when placing the hold [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (circulation) How do I check out a book online for pickup?
- intent: circulation_basic  | refusal: False
- WANT: Should answer with substance like: "Search for the book in Primo, click "Place Hold," and sign in [5]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [2][4].". Bot word
- BOT: Search for the book in Primo, click "Place Hold," and sign in [1][2]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [1][2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (circulation) How many times can I renew a book?
- intent: renewal  | refusal: False
- WANT: The renewal limit depends on user type — see the circulation policies page for the current limit. To renew, sign in to your OhioLINK Library Account: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section
- BOT: The renewal limit depends on your user type, so use the circulation policies page for the current limit [1]. To renew, sign in to your OhioLINK Library Account [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) Does the Hamilton library have a MakerSpace?
- intent: cross_campus_comparison  | refusal: False
- WANT: REFUSAL
- BOT: For a MakerSpace: Oxford (King): yes; Hamilton (Rentschler): no; Middletown (Gardner-Harvey): yes. [1][2][3]
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) Can I book a room?
- intent: room_booking  | refusal: True
- WANT: By default, if the user has not mentioned any regional campus, the answer defaults to King. Present King Library's study room reservation tool (LibCal allspaces) as the answer, not regional study rooms.
- BOT: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) Tell me about the regional library.
- intent: cross_campus_comparison  | refusal: False
- WANT: REFUSAL or clarify -- 'regional' is ambiguous between Hamilton and Middletown.
- BOT: Miami University’s regional libraries are the Gardner-Harvey Library (Middletown campus) at 4200 N. University Blvd., Middletown, Ohio 45042, phone (513) 727-3222, and the Rentschler Library (Hamilton campus) at 1601 University Blvd, Hamilt
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) When is SWORD open to the public?
- intent: location_directions  | refusal: False
- WANT: REFUSAL with explanation that SWORD is a depository, not a public-access space; items are requested via ILL.
- BOT: SWORD is a depository retrieval location at 4200 N. University Blvd, Middletown, OH 45042, with phone 513-727-3296 [1]. The provided directory entry lists its equipment and services, but it does not give public hours [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) Book a room at Rentschler tomorrow afternoon.
- intent: location_directions  | refusal: False
- WANT: Hamilton room availability -- never substitute King rooms.
- BOT: Rentschler Library has study rooms and group study rooms available [1]. For booking, use the library’s room-reservation or study-room process on its site [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (cross_campus) What time does Rentschler close tonight?
- intent: hours  | refusal: False
- WANT: REFUSAL when LibCal is unreachable -- do not guess from training data.
- BOT: Rentschler Library closes at 5:00pm today [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (featured_service) What are the MakerSpace hours?
- intent: hours  | refusal: True
- WANT: Live LibCal MakerSpace hours.
- BOT: I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (featured_service) Is the MakerSpace open right now?
- intent: hours  | refusal: False
- WANT: Live MakerSpace LibCal status (libcal_id 11904).
- BOT: King Library is open today from 7:30am to 9:00pm [1]. The MakerSpace is in King Library, so it is open right now if you’re asking about King’s current open hours [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (featured_service) Are there fees for interlibrary loan?
- intent: interlibrary_loan  | refusal: False
- WANT: Cite the Interlibrary Loan policy page (https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill) for the current fee policy. Do not just point to the request login page — the user is asking about policy.
- BOT: The Interlibrary Loan policy page has the current fee policy for Oxford interlibrary loan requests [1]. For the latest details, use that policy page directly [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (featured_service) Does Middletown campus have a MakerSpace?
- intent: cross_campus_comparison  | refusal: False
- WANT: Middletown (Gardner-Harvey) DOES have a makerspace -- answer yes and point to the TEC Lab guide.
- BOT: For a MakerSpace: Oxford (King): yes; Hamilton (Rentschler): no; Middletown (Gardner-Harvey): yes. [1][2][3]
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (hours) Is the library open right now?
- intent: hours  | refusal: False
- WANT: Should state whether King Library is open right now (or closed), with today's hours, citing the LibCal-backed hours page.
- BOT: King Library is open today (Sunday, 2026-06-28) from 7:30am to 9:00pm [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (hours) Are King Library hours extended for finals?
- intent: hours  | refusal: False
- WANT: Live LibCal hours; finals-week extended schedule comes from LibCal, never bot memory.
- BOT: King Library hours are extended for finals when LibCal shows the finals-week schedule, and the hours page is the place to check the live schedule [1][2]. For the current live hours, King is open Sunday (2026-06-28) from 7:30am to 9:00pm [3]
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (hours) How late is King open during finals week?
- intent: hours  | refusal: False
- WANT: Should return King's extended finals-week hours from LibCal (typically 24-hour or near-24-hour during finals) and cite the King hours page. Should not guess — must come from live data.
- BOT: King Library is open until 9:00pm on Monday through Thursday during the week of 2026-06-29 [1]. On Friday and Saturday it is closed, and on Sunday it is open until 9:00pm [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (research) Where do I find Miami master's theses?
- intent: scholarly_publishing  | refusal: False
- WANT: Should point to the OhioLINK ETD Center / Miami's institutional repository (Scholarly Commons) for theses and dissertations, and cite the digital-collections page if a specific theses collection exists there. Should not invent a URL.
- BOT: Miami master's theses are in the Miami University Theses & Dissertation collection in Digital Collections [1]. The theses page also redirects to the graduate writing guide [2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Need a room for 4 with a whiteboard at King.
- intent: space_info  | refusal: False
- WANT: There is no specific information or filter about whiteboard. The bot can only help with reservation on 4 people at King.
- BOT: King has study rooms and group study rooms, and the directory lists whiteboards as available equipment there [1][2]. You can book a room through King’s study-room reservation link [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Can I book a room at Wertz?
- intent: room_booking  | refusal: False
- WANT: Wertz study tables but limited bookable rooms; surface what's actually available, do not invent.
- BOT: Yes. Wertz Art & Architecture Library offers study rooms [1]. For the current booking details, use the Wertz Library page [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Are there lockers at King?
- intent: space_info  | refusal: False
- WANT: Yes, King Library has lockers in the Reading Rooms. They are restricted to active faculty and actively enrolled graduate students. Locker assignments are requested via an online form on the Reading Rooms page and are assigned yearly on a fi
- BOT: King Library’s directory page lists study rooms, group study rooms, computers, printers, scanners, whiteboards, projectors, and services like printing, course reserves, research appointments, AV production, and the makerspace [1]. It does n
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Can I bring food into the library?
- intent: service_howto  | refusal: False
- WANT: Cite policy page on food/drink.
- BOT: Miami University Libraries' building policies -- food and drink, alcohol, sleeping/napping, noise, pets and service animals, smoking/vaping, bikes and skateboards, and more -- are in the Libraries' Facilities & Events Policies guide [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) What's the food policy?
- intent: service_howto  | refusal: False
- WANT: Cite real food policy URL; if none indexed, refuse rather than invent /policies/food.
- BOT: Miami University Libraries' building policies -- food and drink, alcohol, sleeping/napping, noise, pets and service animals, smoking/vaping, bikes and skateboards, and more -- are in the Libraries' Facilities & Events Policies guide [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Where is the printing policy?
- intent: printing_wifi  | refusal: False
- WANT: Even if a blacklisted URL is in retrieval, it must be filtered by ManualCorrection.
- BOT: Use the Printing & WiFi page for Oxford printing policy information [1]. It is the library’s canonical page for current printing details [2][3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) Can I borrow an HDMI cable from the library?
- intent: tech_checkout  | refusal: False
- WANT: Should answer from the tech-checkout page equipment list — confirm with the checkout URL if HDMI cables are listed, or refuse cleanly if not. Should not invent.
- BOT: Yes — the Miami University Libraries lend “Chargers & cables for phones/laptops” at the circulation desk with your Miami ID, which would cover items like HDMI cables [1]. For current availability and the complete, up-to-date equipment list,
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [wrong] (service) How long can I keep a DSLR camera if I check one out?
- intent: tech_checkout  | refusal: False
- WANT: Should answer from the tech-checkout page loan period for cameras (typically 3-7 days for high-value equipment) — cite the page. Should not invent a number not on the page.
- BOT: A DSLR camera checkout is a 24 hour checkout [1]. The tech checkout page also says cameras and camcorders are loaned for 24 hours [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (capability_point_to_url) I'm looking for an article about climate change
- intent: research_consultation  | refusal: False
- WANT: Should answer with substance like: "Use Miami University Libraries’ Primo search to look for journal articles about climate change [1]. If you’d rather search within specific subject databases, use the Databases A–Z list to pick an appropri
- BOT: Use Miami University Libraries’ Primo search to look for journal articles about climate change [1]. If you’d rather search within specific subject databases, the library’s Ask Us page can connect you with a librarian for help via chat, emai
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (capability_point_to_url) Can you find a journal article for me?
- intent: find_resource  | refusal: True
- WANT: Should answer with substance like: "Catalog search is currently unavailable. Please search directly at https://www.lib.miamioh.edu/ or chat with a librarian who can help find materials.". Bot wording may vary; this is the acceptance pattern
- BOT: I can't run catalog searches for you, but Primo -- the library catalog -- can do it in one box: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU. It covers our books, ebooks, articles, media, and OhioLINK pa
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (capability_point_to_url) Where can I find books on Ohio history?
- intent: find_resource  | refusal: False
- WANT: Should answer with substance like: "To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK par
- BOT: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo:
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) Can I renew my book?
- intent: renewal  | refusal: False
- WANT: Yes, but renewal differs by material type. Miami materials: point to the circulation-policies loan-periods-fines page. OhioLINK/ILL materials: point to the loan-periods-ohiolink-ill page. Distinguish the two paths; do not give a single gene
- BOT: Yes — you can renew books in your OhioLINK Primo account [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) How do I extend my checkout?
- intent: adobe_access  | refusal: False
- WANT: Sign in to MyAccount and click Renew, or contact circulation if past renewal limit.
- BOT: Sign in to your MyAccount and click Renew to extend your checkout [1][2]. If you are past the renewal limit, contact circulation [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) How long can I keep a book?
- intent: loan_policy  | refusal: False
- WANT: Loan period varies by user type (undergrad / grad / faculty / staff). Cite circulation policies.
- BOT: For Miami University Libraries (Oxford), the loan period for books varies by user type (e.g., undergraduate, graduate, faculty, staff) as listed in the circulation policies [1][2][3]. Graduate students can check out books for an entire seme
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) What's the loan period for graduate students?
- intent: loan_policy  | refusal: False
- WANT: Graduate student loan period from circulation policies; do not estimate.
- BOT: Graduate students can check out books for an entire semester at a time [1]. For the full loan-period details by material type (and related policies), see the Libraries’ circulation policies/loan periods page [2] (also accessible via https:/
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) Are there late fees if I return a book overdue?
- intent: loan_policy  | refusal: False
- WANT: Quote fee policy ONLY if the page states one; otherwise refuse to estimate.
- BOT: Yes—overdue items can accrue overdue fines (late fees), so you should account for transit time if returning materials by campus mail or a mail carrier to avoid overdue fines [1][2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) How do I find course reserves?
- intent: course_reserves  | refusal: False
- WANT: Cite reserves page; mention search by course or instructor in Primo.
- BOT: Use the course reserves page and search Primo by course or instructor [1]. If you need physical reserves, they are at the King circulation desk [2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) Where are my course reserves?
- intent: course_reserves  | refusal: False
- WANT: Search Primo by course/instructor; physical reserves are at King circulation desk. Cite reserves page.
- BOT: Search Primo by course or instructor to find your course reserves [1][2]. Physical reserves are at the King circulation desk [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (circulation) I graduated from Miami — can I still check out books?
- intent: loan_policy  | refusal: False
- WANT: Should explain alumni borrowing privileges (typically requires alumni library card or community-borrower registration), cite the circulation policies page, and recommend contacting the circulation desk for current eligibility rules.
- BOT: Yes—Miami University alumni can still borrow library materials, typically by registering for an alumni library card or through community-borrower registration; see the Circulation Policies page for the current eligibility details and borrow
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Do all libraries have 3D printing?
- intent: cross_campus_comparison  | refusal: False
- WANT: King has 3D printing in its Makerspace. Middletown has 3D printing in its TEC Lab Makerspace. Hamilton does NOT have 3D printing nor a Makerspace. Cite the King Makerspace LibGuide + the Middletown TEC Lab LibGuide; refuse the Hamilton clai
- BOT: For 3D printing: Oxford (King): yes (self-service); Hamilton (Rentschler): no; Middletown (Gardner-Harvey): yes (staff-operated). [1][2]
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Who works at the Hamilton library?
- intent: staff_lookup  | refusal: True
- WANT: Do NOT enumerate staff names (privacy). A generic 'who works here' must point to the Rentschler/Hamilton staff page rather than listing people. Only verify and give a specific name+contact when the patron explicitly asks for that person or 
- BOT: I don't share staff contact lists. To reach a librarian now, use the Ask Us chat -- a librarian on duty can help right away: https://www.lib.miamioh.edu/research/research-support/ask/ If you need a particular subject's librarian, tell me th
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Are there study rooms at Gardner-Harvey?
- intent: space_info  | refusal: False
- WANT: Middletown room availability.
- BOT: Yes — Gardner-Harvey has study rooms and group study rooms listed among its equipment and services [1]. The Middletown room reservation page also shows room availability for Gardner-Harvey [2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) How do I book a study room?
- intent: room_booking  | refusal: False
- WANT: Origin=middletown -> Gardner-Harvey, NOT King.
- BOT: Gardner-Harvey Library offers study rooms and group study rooms, so you can use the library’s study-room service for a booking request [1]. For the exact reservation steps, use the Gardner-Harvey Library page [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Can I print at any library?
- intent: printing_wifi  | refusal: False
- WANT: Per-campus list of printing availability from services_offered[]. All three have it.
- BOT: Yes — printing is available at the Oxford libraries, and the Printing & WiFi page has the current details [1]. If you want the Oxford-specific instructions, use that page [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Do all the libraries have scanners?
- intent: printing_wifi  | refusal: False
- WANT: Should answer per-campus: Oxford (King) yes; Hamilton (Rentschler) per services page; Middletown (Gardner-Harvey) per services page. Cite each campus's tech/printing page. Should refuse a per-campus claim if no evidence for that campus.
- BOT: No. On the Oxford campus, King Library has scanners [1], Wertz Art & Architecture Library has scanners [2], and Special Collections & University Archives has a scanning station [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (cross_campus) Which campus library has the best silent study floor?
- intent: service_howto  | refusal: False
- WANT: Should describe silent/quiet study options at King (e.g., reading rooms, specific floor designations) and any equivalents at regional libraries from their pages, without ranking 'best'. Cite each campus's location/spaces page.
- BOT: King Library has a quiet/silent study area on the THIRD FLOOR [1][2]. The operator-verified sources also note that King has open study space and reading-room options, so for Oxford the best-supported silent-study choice is King’s third floo
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I request an interlibrary loan?
- intent: interlibrary_loan  | refusal: False
- WANT: Brief explanation + ILL request form URL. Bot must NOT roleplay submitting.
- BOT: Use the Interlibrary Loan request page for Oxford (Main Campus) and submit the request yourself [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I get a book from another library to Hamilton?
- intent: interlibrary_loan  | refusal: False
- WANT: Hamilton-specific ILL pickup info + request form URL.
- BOT: Use Interlibrary Loan for Hamilton Campus (Rentschler Library) and submit the request yourself [1]. The provided ILL page is the place to start for getting a book from another library to Hamilton [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) What digital collections does Miami have?
- intent: digital_collections  | refusal: False
- WANT: Intro/overview of Digital Collections with the front-door URL; naming example collections is acceptable.
- BOT: Miami University Libraries’ Digital Collections contain thousands of digital objects, including photographs, advertising tradecards, newspapers, manuscripts, and videos from the Walter Havighurst Special Collections & University Archives [1
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Do you have access to the New York Times?
- intent: newspapers  | refusal: False
- WANT: We do have access to New York Times for Miami affiliated users. https://libguides.lib.miamioh.edu/newspapers
- BOT: Yes — Miami University Libraries do have access to the New York Times for Miami-affiliated users [1]. The library also has a New York Times subscription/activation page at https://libguides.lib.miamioh.edu/newspapers [1][2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I request a book through ILL?
- intent: circulation_basic  | refusal: False
- WANT: Brief ILL explanation + link to Oxford ILL request form. Never submits the request.
- BOT: Use the Interlibrary Loan page for Oxford (Main Campus) and submit the request yourself [1]. The page is the place to request books through ILL [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) I'm faculty -- where do I download Adobe?
- intent: adobe_access  | refusal: False
- WANT: Faculty/staff Adobe deal -- different from student license. Cite software/adobe page.
- BOT: Download Adobe from the Software Checkout page, which lists Adobe Creative Cloud (Faculty/Staff) and Adobe Acrobat Pro (Faculty/Staff) for Miami faculty/staff [1]. After checking out a license, you can log in at adobe.com using your Miami c
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) What digital collections does the library have?
- intent: digital_collections  | refusal: False
- WANT: Front-door description of Digital Collections (what it is / who it's for) + front-door URL; a high-level overview is acceptable.
- BOT: Miami University Libraries’ Digital Collections is an Oxford special-collections resource with thousands of digital objects, including photographs, advertising tradecards, newspapers, manuscripts, and videos from Walter Havighurst Special C
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Do you have any digital exhibits about WW2?
- intent: digital_collections  | refusal: False
- WANT: Answer ONLY from indexed exhibit pages; otherwise REFUSAL pointing to digital-collections front page.
- BOT: Yes. Miami’s Digital Collections page says to “visit our past digital exhibit archive” for older historical exhibits, and it lists collections such as the Online Civil War Diaries and other digital collections [1]. For WWII specifically, th
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I access materials in Special Collections?
- intent: staff_lookup  | refusal: False
- WANT: Appointment-only research access; cite Special Collections page.
- BOT: Special Collections access is by appointment for research [1][2][3]. You can contact Walter Havighurst Special Collections & University Archives at 513-529-3323, and it is located on the third floor of King Library [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Who is the archivist?
- intent: staff_lookup  | refusal: False
- WANT: Special Collections & University Archives is on the 3rd Floor of King Library, 151 S Campus Ave, Oxford, OH 45056. SpecColl@MiamiOH.edu, phone (513) 529-3323. University Archives: Archives@MiamiOH.edu, phone (513) 529-6720.
- BOT: The University Archivist is Jacky Johnson, Department Head & University Archivist (johnsoj@miamioh.edu), in Special Collections & University Archives on the 3rd floor of King Library. General contacts: SpecColl@MiamiOH.edu, Archives@MiamiOH
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Is there a vinyl cutter at the MakerSpace?
- intent: makerspace_3d  | refusal: False
- WANT: Tell user to check for themself at https://muohio.libcal.com/reserve/equipment/makerspace
- BOT: Yes — the MakerSpace at King Library lists a vinyl cutter among its equipment [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Where do I return an interlibrary loan book?
- intent: interlibrary_loan  | refusal: False
- WANT: Return-flow info per the OhioLINK & ILL loan-periods policy page. OhioLINK items should be returned to a bookdrop. Do not invent a return location for ILL items not stated on the policy page.
- BOT: Interlibrary Loan for Oxford (Main Campus) is handled through the ILL request page [1]. For the return location, use that page for the current return instructions [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I do an ILL request at Middletown?
- intent: circulation_basic  | refusal: False
- WANT: Middletown ILL pickup at Gardner-Harvey; do not give Oxford pickup.
- BOT: Use the Interlibrary Loan page for Middletown Campus (Gardner-Harvey Library) and submit the request yourself [1]. The page is here: https://www.mid.miamioh.edu/library/interlibraryloan.htm [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Do I need training to use the 3D printers in the MakerSpace?
- intent: makerspace_3d  | refusal: False
- WANT: Training/consultation requirement only if stated on MakerSpace page; otherwise refuse.
- BOT: Yes — 3D printing is available at the King Library MakerSpace (3rd floor, Room 303) on the Oxford campus, and it's self-service. The MakerSpace guide has how to get started — including any training or consultation — plus the available print
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Can I just walk into the MakerSpace?
- intent: makerspace_3d  | refusal: False
- WANT: Walk-in vs reservation policy from MakerSpace page; do not infer.
- BOT: The MakerSpace page has a walk-in vs. reservation policy, but the provided source bundle does not give the policy text itself [1]. For the current access rules, use the MakerSpace page [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) Can I add my own materials to the digital collections?
- intent: digital_collections  | refusal: False
- WANT: I can't authorize adding materials to Digital Collections -- that's an editorial decision. To discuss submission, contact Special Collections / University Archives: SpecColl@MiamiOH.edu or archives@miamioh.edu. See https://spec.lib.miamioh.
- BOT: Special Collections / University Archives handles discussion of submissions for Digital Collections, with contact at SpecColl@MiamiOH.edu or archives@miamioh.edu [1][2]. The Digital Collections page is a front door to Miami University Libra
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How much does it cost to use the MakerSpace 3D printers?
- intent: printing_wifi  | refusal: False
- WANT: Should answer from the MakerSpace policies/home page on fee structure (e.g., material cost per gram). If the page doesn't state pricing, refuse cleanly and point to the MakerSpace page for current rates. Should not invent a number.
- BOT: Yes — 3D printing is available at the King Library MakerSpace (3rd floor, Room 303) on the Oxford campus, and it's self-service. The MakerSpace guide has how to get started — including any training or consultation — plus the available print
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) I'm a part-time staff member — am I eligible for Adobe Creative Cloud access?
- intent: adobe_access  | refusal: False
- WANT: Should distinguish eligibility (student vs full-time faculty/staff vs part-time/contingent) from the software page and refuse to assert eligibility for the part-time case if not explicitly stated on the page. Cite the software page.
- BOT: The software page lists Adobe Creative Cloud as available separately for “Miami Students Only” and for “Miami Faculty/Staff Only,” with different checkout durations [1]. It does not state eligibility for part-time staff specifically, so I c
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (featured_service) How do I activate my NYT student subscription?
- intent: newspapers  | refusal: False
- WANT: Should describe the NYT activation flow (sign up with miamioh.edu email through the library's NYT subscription URL) and cite the library's NYT subscription page from the existing gold set. Should not invent specific steps not on the page.
- BOT: Activate your New York Times student subscription through the library’s NYT subscription page, using your Miami University email address [1]. The library’s databases also list New York Times access for Miami-affiliated users [2][3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (hours) What are Special Collections hours?
- intent: hours  | refusal: False
- WANT: Provide Special Collections' open hours from LibCal (also viewable at https://www.lib.miamioh.edu/about/locations/hours/), AND note that research access is by appointment — appointments must be made through https://spec.lib.miamioh.edu/home
- BOT: Walter Havighurst Special Collections & University Archives is Closed for the week of 2026-06-28, including Sunday (2026-06-28) [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (hours) Is the library open on Christmas Day?
- intent: hours  | refusal: False
- WANT: Should state Christmas Day closure (the university is closed for the winter holiday) and refer the user to the hours hub for the full winter break schedule.
- BOT: That's further out than I can look up live -- my hours check only covers the near term, and the schedule shifts by term, break, and holiday, so I can't reliably tell you that date myself. The library's hours page always shows the current an
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (hours) What are Wertz Library's summer hours?
- intent: hours  | refusal: False
- WANT: Should return Wertz Art & Architecture Library's current/upcoming summer-term hours from LibCal and cite the Wertz location page or hours hub. Should not substitute King's hours.
- BOT: That's further out than I can look up live -- my hours check only covers the near term, and the schedule shifts by term, break, and holiday, so I can't reliably tell you that date myself. The library's hours page always shows the current an
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (hours) Is the library 24 hours?
- intent: hours  | refusal: False
- WANT: Should clarify that hours vary by building and term — King is the only one that runs near-24-hour during finals — and surface the hours hub for the user to check the specific building/date they care about. Should not assert '24 hours' as a 
- BOT: No. King Library on the Oxford campus is open today (Monday, 2026-06-29) from 7:30am to 9:00pm, so it is not 24 hours [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (librarian) Who is the librarian for Biology?
- intent: subject_librarian  | refusal: False
- WANT: Exact name + email + phone of the Biology subject librarian, from Postgres.
- BOT: Your subject librarian is Ginny Boehme (boehmemv@miamioh.edu) [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (librarian) Who can help me at the Hamilton library?
- intent: staff_lookup  | refusal: True
- WANT: Hamilton librarian directory.
- BOT: I don't share staff contact lists. To reach a librarian now, use the Ask Us chat -- a librarian on duty can help right away: https://www.lib.miamioh.edu/research/research-support/ask/ If you need a particular subject's librarian, tell me th
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (librarian) Who do I talk to about business databases?
- intent: subject_librarian  | refusal: False
- WANT: Business subject librarian.
- BOT: Your subject librarians are Abigail Morgan (morgan55@miamioh.edu) and Erica Freed (freede@miamioh.edu) [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (out_of_scope) Do you have a copy of Foundation by Asimov?
- intent: find_resource  | refusal: False
- WANT: REFUSAL: the bot doesn't search the catalog; point to the catalog search on the libraries homepage.
- BOT: To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo:
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (out_of_scope) Can I bring my dog into the library?
- intent: service_howto  | refusal: False
- WANT: Should answer that only service animals are allowed (per typical university policy) and refuse to make a definitive claim about pet/ESA policy without a sourced page; refer to university accessibility office for service-animal accommodation
- BOT: Miami University Libraries' building policies -- food and drink, alcohol, sleeping/napping, noise, pets and service animals, smoking/vaping, bikes and skateboards, and more -- are in the Libraries' Facilities & Events Policies guide [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (research) Can I schedule an appointment with a librarian?
- intent: research_consultation  | refusal: False
- WANT: Guide the user to subject librarian page at https://www.lib.miamioh.edu/about/organization/liaisons/
- BOT: Yes—Miami University Libraries (Oxford) offers research consultations/appointments with librarians; you can start by using the Ask Us page to book a research consultation [1][2]. If you want to meet with a subject specialist, use the Subjec
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (research) Can someone help me with GIS?
- intent: data_services  | refusal: False
- WANT: Should answer with substance like: "Yes — Oxford Library data services offers consultations, and the GIS article says library staff are happy to help with GIS projects [1][2]. The data services page also says it provides data services suppo
- BOT: Yes — Oxford Library data services offers consultations, and the GIS resources article says library staff are happy to help with GIS projects [1][2]. The data services page also says it provides support for data services, including GIS help
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (research) Where can I find Chicago Manual of Style help?
- intent: citation_help  | refusal: False
- WANT: Should point the user to the citation LibGuide and any subject librarian who specializes in history/humanities for Chicago-style help. Should not invent footnote examples.
- BOT: For Chicago Manual of Style help, use the Citation Resources LibGuide [1] and the History subject research guide [2]. You can also contact Jenny Presnell, who is listed as a liaison for Oxford [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (research) How do I find only peer-reviewed articles?
- intent: databases  | refusal: False
- WANT: Should explain that databases (EBSCO, JSTOR, etc.) have a 'peer-reviewed' or 'scholarly journals' filter and point to the databases A-Z list. Should suggest contacting a subject librarian for the right database for the user's topic.
- BOT: To find articles or browse research databases, use the library's Databases A-Z list. It's the authoritative index of every database the library subscribes to -- organized alphabetically and by subject -- and links directly into each databas
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (research) Does the library have government documents?
- intent: subject_librarian  | refusal: False
- WANT: Should describe Miami's government documents collection (Miami is a federal depository library historically) and cite the relevant collection/LibGuide page or pointer to a subject librarian. Should refuse specifics not in the corpus.
- BOT: Your subject librarian is Jenny Presnell (presnejl@miamioh.edu) [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (scope_default) Can I book a study room at King today?
- intent: room_booking  | refusal: False
- WANT: Live availability via get_room_availability + the room reservations booking link.
- BOT: Yes. King study rooms are bookable through the room reservations link, and live availability is available today [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) How do I print from my laptop?
- intent: printing_wifi  | refusal: False
- WANT: Cite printing page; the 'one canonical printing page' invariant.
- BOT: Use the Printing & WiFi page for the current laptop-printing instructions [1][2]. The Oxford printing page says you can send a job to the MUprint queue from a computer or other device that lets you submit jobs to a printer, then release it 
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Where can I scan something?
- intent: printing_wifi  | refusal: False
- WANT: Just share the Printing and WIFI webpage. Do not provide detailed location.
- BOT: At Oxford’s King Library, you can scan something using the scanners at the multipurpose printers [1]. The Oxford Printing & WiFi page also points to scanning through the printing services [2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) How do I email a question to the library?
- intent: human_handoff  | refusal: False
- WANT: Should answer with substance like: "Use the Ask Us email/LibAnswers ticket flow to email your question to the library [1]. You can also reach Miami University Libraries through the Contact Us page, which lists email contact options [2].". B
- BOT: Use the Ask Us page to email your question to the library [1][2]. The page shows a “By Email” option for General Question and also lists the Contact Us page, which has library contact information [1][3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) I need help with my dissertation literature review.
- intent: research_consultation  | refusal: False
- WANT: Point to scheduling a research consultation/appointment, OR hand off to a librarian via the red 'talk to a human librarian' button (UI) / the Ask Us contact page. Do NOT cite a generic /research/ page.
- BOT: For help with your dissertation literature review, you can connect with a Miami University Libraries librarian through the Ask Us page (chat/email options are available there) [1]. You can also schedule a research consultation/appointment w
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Can I bring food into the library?
- intent: service_howto  | refusal: False
- WANT: Should answer with substance like: "The sources point to the Oxford library food/drink policy page for the current rules on bringing food into the library [1][2][3]. One Oxford library event announcement also shows food can be present in Ki
- BOT: Miami University Libraries' building policies -- food and drink, alcohol, sleeping/napping, noise, pets and service animals, smoking/vaping, bikes and skateboards, and more -- are in the Libraries' Facilities & Events Policies guide [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Where can I scan a document?
- intent: printing_wifi  | refusal: False
- WANT: Scanners at multipurpose printers; cite printing page.
- BOT: You can scan a document at King Library in Oxford; the directory lists scanners among its equipment [1]. The Printing & WiFi page is the library’s current technology page for scanning and printing help [2].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Can I borrow a laptop?
- intent: tech_checkout  | refusal: False
- WANT: Yes -- Chromebooks for 30 days. Cite tech-checkout page.
- BOT: Yes — at Oxford, Chromebook laptops may be checked out for 30 days [1]. You can borrow equipment at a library checkout desk with your university ID [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) What software is on the library computers?
- intent: adobe_access  | refusal: False
- WANT: Cite the software-on-library-computers page at https://www.lib.miamioh.edu/use/technology/software/ — that link IS sufficient. Do NOT enumerate the full software list inline.
- BOT: Software on the library computers includes Adobe Creative Cloud, Audacity, VLC Media Player, Chrome, Edge, Microsoft Office, and specialty tools such as Autodesk AutoCAD, Logger Pro, Final Cut Pro, Finale, and Xcode [1][2]. For the current 
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) How do I scan a document and email it to myself at the library?
- intent: printing_wifi  | refusal: False
- WANT: Should describe the scan-to-email workflow on the library scanners/multifunction printers and cite the printing/tech-checkout page. Should not invent step-by-step instructions not on the page.
- BOT: Use the library scanners or multifunction printers and follow the scan-to-email workflow on the Printing & WiFi page [1]. That page is the current library guide for scanning and other technology instructions [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) How do I view microfilm at King?
- intent: space_info  | refusal: False
- WANT: Should describe where microfilm reader/scanner is located (typically a specific floor at King) and how to request material, citing the King location page or special-collections page if applicable. Should refuse specifics not in the corpus.
- BOT: King Library’s location page says it has computer labs and printing/scanning, and the King location/contact record lists scanners among the equipment available there [1][2]. For microfilm viewing, use the King Library page and the linked Sp
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Can I borrow headphones from the library?
- intent: tech_checkout  | refusal: False
- WANT: Should answer from the tech-checkout page — if headphones are listed on the equipment list, confirm with the checkout URL; if not listed, refuse and point to the tech-checkout page for the full equipment list.
- BOT: Yes. Headphones are available for checkout (listed under “Available for checkout”) and you can check them out at the circulation/checkout desk with your Miami ID [1]. For the current equipment list and availability details, use the Tech Equ
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Do you have a floor plan or map of King Library?
- intent: location_directions  | refusal: False
- WANT: Should surface the King location page (which typically has floor descriptions) and refuse to invent a graphical map. If a PDF floor plan exists in the index, cite it; otherwise point the user to the King page.
- BOT: King Library has a locations page with building information and services, and the library’s hours/location page is the place to check for current floor or space details [1][2]. If you’re looking for a graphical floor plan or map, use the Ki
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Are there outlets to charge my laptop at King?
- intent: location_directions  | refusal: False
- WANT: Should answer that outlets are widely available at study seating per the King location page; if not explicitly documented, point to the King page and tech-checkout (for borrowable chargers). Should not invent specific outlet counts.
- BOT: Yes. Edward King Library lists study rooms, group study rooms, computers, printers, scanners, whiteboards, projectors, and makerspace services at King [1]. The directory entry does not specifically mention outlets, so for charging availabil
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Does the library lend graphing calculators?
- intent: tech_checkout  | refusal: False
- WANT: Should check the tech-checkout equipment list — confirm + URL if calculators are listed, refuse with a pointer to the tech-checkout page if not. Should not assume.
- BOT: The tech-checkout page says the libraries offer equipment for checkout and lists available items; use that page to confirm whether graphing calculators are included [1]. It also says you can call the checkout desk at (513) 529-4141 to check
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Do you have USB drives I can borrow?
- intent: tech_checkout  | refusal: False
- WANT: Should check tech-checkout list — likely not (USB drives are typically buy-not-borrow); should refuse cleanly and suggest checking the tech-checkout page or the campus tech store for purchase. Should not invent a USB checkout.
- BOT: Miami University Libraries’ Tech Equipment for Checkout page lists the equipment you can borrow and notes you can “Come to a library checkout desk with your university ID to borrow equipment” [1]. Please check the current tech-checkout equi
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (service) Do you have iPhone chargers I can borrow?
- intent: tech_checkout  | refusal: False
- WANT: Should check tech-checkout — if lightning/USB-C cables/chargers are listed, confirm with the page URL; otherwise refuse cleanly. The existing tech_charger case asks generically; this asks for an iPhone-specific cable type.
- BOT: Yes — King Library’s tech checkout includes chargers and cables for phones/laptops, which covers iPhone charging accessories [1][2]. You can borrow equipment at a library checkout desk with your university ID [3].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:

### [partial] (staff) How do I find the staff directory?
- intent: staff_lookup  | refusal: False
- WANT: Point to staff directory page.
- BOT: You can access the Staff Directory from the Libraries’ Contact Us page, where “Staff Directory” is listed in the site navigation [1]. The page is here: https://www.lib.miamioh.edu/about/organization/contact-us/ [1].
- verdict: [ ] BOT-OK   [ ] REAL bug   notes:
