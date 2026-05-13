# Miami University Libraries Chatbot Intent Labeling Guide — 38 Labels

Pick exactly one label per row. Classify by the user's actual library service need, not by user role, website section, or keyword alone.

## Valid labels

hours
location_directions
staff_lookup
subject_librarian
circulation_basic
renewal
loan_policy
account
interlibrary_loan
course_reserves
find_resource
room_booking
space_info
makerspace_3d
printing_wifi
tech_checkout
software_access
adobe_access
databases
citation_help
research_consultation
data_services
digital_collections
special_collections
newspapers
events_news
instruction_request
service_howto
cross_campus_comparison
human_handoff
out_of_scope
remote_access
accessibility_services
copyright_permissions
scholarly_publishing
av_production
website_feedback
library_employment

## Priority rules

1. If clearly not a Miami University Libraries service question, use `out_of_scope`.
2. If the user explicitly asks for a real person, call, email, chat, or contact now, use `human_handoff`, unless a more specific label applies, such as `research_consultation`, `instruction_request`, `staff_lookup`, or `subject_librarian`.
3. Personal circulation/account questions take priority over general policy: `account`, `renewal`, `circulation_basic`.
4. Specific service areas override generic `service_howto`.
5. Use `service_howto` only as fallback when no more specific label fits.

## Label definitions and boundaries

`hours`: library hours, service desk hours, chat hours, holiday hours, whether a library is open today. Not directions.

`location_directions`: address, parking, floor location, directions, where a room/service/library is located. Not hours.

`staff_lookup`: find a staff member, librarian by name, dean, department contact, role, email, phone, staff directory. Not subject liaison lookup.

`subject_librarian`: liaison librarian for a subject, major, department, or course area. Not research appointment.

`circulation_basic`: Miami-owned item holds, requests, pickup, curbside pickup, department/dorm delivery, home delivery, or whether a Miami request worked. Not OhioLINK/ILL.

`renewal`: renew checkout, extend due date, item renewal.

`loan_policy`: loan periods, due dates in general, late fees, overdue rules, lost/damaged fees, borrowing policy. Not personal account status.

`account`: My Library Account, personal checkouts, personal fines, personal holds, login to account, account status.

`interlibrary_loan`: ILL, ILLiad, OhioLINK, WorldCat, storage requests, borrowing from another library.

`course_reserves`: course reserves, textbooks on reserve, instructor placed item on reserve, searching course reserve material. Not room reservation.

`find_resource`: “Do you have this book/article/journal/movie?”, catalog search, availability, call number, item lookup, finding a known resource.

`room_booking`: reserving a study room, collaboration room, creation space, LibCal room, group study room, room availability.

`space_info`: quiet floors, study areas, lockers, cafe/vending, food rules, computer availability, building occupancy, general space features.

`makerspace_3d`: MakerSpace, 3D printing, 3D scanning, maker tools, fabrication, filament, making physical objects.

`printing_wifi`: printing, scanning, copying, wireless printing, WiFi connection, printer instructions, WiFi troubleshooting.

`tech_checkout`: borrowing laptops, tablets, chargers, cameras, microphones, recorders, projectors, calculators, cables, or physical technology equipment.

`software_access`: software on library computers, general software availability, Microsoft Office, MATLAB, SPSS, Xcode, Final Cut, GarageBand, Audacity, software checkout excluding Adobe-specific questions.

`adobe_access`: Adobe Creative Cloud, Photoshop, Illustrator, InDesign, Premiere Pro, Acrobat Pro, After Effects, Dreamweaver, Adobe license checkout, Adobe availability.

`av_production`: audio-video production, podcast studio, video studio, recording, media creation workflow, filming/editing support, A/V production spaces/services.

`databases`: JSTOR, EBSCO, PubMed, FactSet, database recommendations, Databases A-Z, which database to use.

`citation_help`: APA, MLA, Chicago, citation format, bibliography, annotated bibliography, Zotero, EndNote, quoting, paraphrasing, works cited.

`research_consultation`: research appointment, meet with a librarian, source strategy, topic narrowing, literature search strategy, research process support.

`data_services`: GIS, data analysis, data visualization, R/Python for data, research data, spatial data, data-management support.

`digital_collections`: online digital collections, digitized photos, manuscripts, newspapers, videos, digital exhibits, CONTENTdm, Miami digital objects.

`special_collections`: archives, rare books, manuscripts, University Archives, SCUA, finding aids, appointments with Special Collections, archival research.

`newspapers`: New York Times, Wall Street Journal, Cincinnati Enquirer, newspaper subscriptions, newspaper access.

`remote_access`: off-campus access, proxy links, database login from home, access denied, 401/403, EZproxy, CAS/access problems for e-resources.

`copyright_permissions`: copyright, fair use, permission to reuse materials, public domain, TEACH Act, reproduction rights, publication permission.

`scholarly_publishing`: open access, Scholarly Commons, institutional repository, author rights, publishing support, article deposit, thesis/dissertation deposit, scholarly communication.

`events_news`: library events, exhibits, workshops, news, announcements, construction updates, what is happening at the library.

`instruction_request`: faculty/instructor requests a library session, class visit, course-integrated instruction, information literacy session, librarian-led instruction for students.

`accessibility_services`: accessibility resources, ADA accommodation, accessible content, accessible library services, alternative access, disability-related library support.

`website_feedback`: broken links, website errors, incorrect web content, form problems, chatbot feedback, library website feedback.

`library_employment`: student jobs, staff jobs, faculty librarian jobs, employment at the Libraries, job postings, Workday library positions.

`cross_campus_comparison`: comparing services across Oxford, Hamilton, Middletown, Art & Architecture, King, or regional libraries; “Do all campuses have this?”

`human_handoff`: talk to a real person, call someone, email someone, chat with a librarian, contact the library, “I need a person.”

`service_howto`: generic “How do I use the library?” or “How do I do X?” when no more specific label fits. Fallback only.

`out_of_scope`: weather, sports, general homework answers, non-library life questions, campus services not connected to the Libraries, unrelated public information.

## Critical tie-breaks

“Reserve” is ambiguous: room reservation = `room_booking`; course/textbook reserve = `course_reserves`.

“Library account” is strong evidence for `account`.

Adobe overrides general software: any Adobe product = `adobe_access`.

OhioLINK, WorldCat, ILL, and “another library” override normal borrowing = `interlibrary_loan`.

Subject librarian and research consultation are different: “Who is the biology librarian?” = `subject_librarian`; “Can I meet with someone to help with my biology paper?” = `research_consultation`.

Databases and known-item search are different: “Which database has psychology articles?” = `databases`; “Do you have this article?” = `find_resource`.

Copyright and citation are different: “How do I cite this image?” = `citation_help`; “Am I allowed to use this image?” = `copyright_permissions`.

Remote access and databases are different: “How do I get into JSTOR from home?” = `remote_access`; “Do you have JSTOR?” = `databases`.

Audio-video production and equipment checkout are different: “Can I borrow a microphone?” = `tech_checkout`; “Can I use a podcast studio / record a video / get help producing media?” = `av_production`.
