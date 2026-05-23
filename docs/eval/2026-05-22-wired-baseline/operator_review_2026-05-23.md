# Gold-Set Review — 2026-05-23 (focused, post-fix-session)

_Eval state at time of generation: **131/184 = 71.2%** fully right._

Two buckets to review. Total: **21 real-error + 7 C-list = 28 cases**.

## How to use

For each case, you'll see:
- The user's **Question**
- The **Gold expected_answer** (what we tell the bot is right)
- The **Gold allowed_urls** (URLs the bot is permitted to cite)
- The **Bot's actual answer** + verdict
- A 2-checkbox decision: ✅ ACCEPT (bot's answer is fine — broaden gold to accept it) or ❌ REJECT (bot is wrong — needs real fix)

Where I see how to fix gold-side, I've drafted a **suggested rewrite** below the checkboxes.

---

## Bucket 1 — Real bot errors (21 cases)

These are `wrong` / `refused_incorrectly` / `answered_should_have_refused`. Check whether the bot is actually wrong (real bug → ❌ REJECT) or whether the gold is too narrow / outdated (broaden → ✅ ACCEPT).

### 1. `circ_online_checkout` [circulation/`wrong`]

**Q:** How do I check out a book online for pickup?

**Gold expects:** Place a hold via Primo, choose pickup location, retrieve when notified.

**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (6337ms):**
> Search for the book in Primo, click "Place Hold," and sign in [5]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [2][4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 2. `loan_grad_period` [circulation/`refused_incorrectly`]

**Q:** What's the loan period for graduate students?

**Gold expects:** Graduate student loan period from circulation policies; do not estimate.

**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (8009ms):**
> I started to answer but couldn't verify my sources. Rather than send you something I can't back up, please ask a librarian through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 3. `renew_how_many` [circulation/`wrong`]

**Q:** How many times can I renew a book?

**Gold expects:** Renewal limit per user type from circulation policies LibGuide; do not invent a number.

**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies`

**Bot answered (6974ms):**
> The renewal limit depends on your user type; see the circulation policies page for the current limit [1]. If you are trying to renew a checked-out book, use your OhioLINK Primo account [6].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 4. `lib_hamilton_general` [cross_campus/`refused_incorrectly`]

**Q:** Who works at the Hamilton library?

**Gold expects:** Do NOT enumerate staff names (privacy). A generic 'who works here' must point to the Rentschler/Hamilton staff page rather than listing people. Only verify and give a specific name+contact when the patron explicitly asks for that person or a subject librarian.

**Gold URLs:** `https://www.ham.miamioh.edu/library/about/rentschler-library-staff/`

**Bot answered (4505ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 5. `xc_session_origin_hamilton` [cross_campus/`refused_incorrectly`]

**Q:** Can I book a room?

**Gold expects:** By default, if the user has not mentioned any regional campus, the answer defaults to King. Present King Library's study room reservation tool (LibCal allspaces) as the answer, not regional study rooms.

**Gold URLs:** `https://muohio.libcal.com/allspaces`

**Bot answered (2837ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 6. `fs_archivist_email` [featured_service/`refused_incorrectly`]

**Q:** What's the email of the university archivist?

**Gold expects:** The University Archives email is Archives@MiamiOH.edu (phone (513) 529-6720). Special Collections & University Archives is on the 3rd Floor of King Library, 151 S Campus Ave, Oxford, OH 45056. The general Special Collections inbox is SpecColl@MiamiOH.edu, phone (513) 529-3323.

**Gold URLs:** `https://spec.lib.miamioh.edu/home/`, `https://spec.lib.miamioh.edu/home/staff/`

**Bot answered (4654ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 7. `fs_ill_fee` [featured_service/`wrong`]

**Q:** Are there fees for interlibrary loan?

**Gold expects:** There is no fee for Miami affiliated users. Check on https://www.lib.miamioh.edu/use/borrow/ill/

**Gold URLs:** `https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill`

**Bot answered (3424ms):**
> Use the Interlibrary Loan page for Oxford (Main Campus) to check the current policy and any fees [1]. The page is the place to submit requests yourself, and it carries the current ILL details [1].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 8. `fs_premiere_pro` [featured_service/`wrong`]

**Q:** Can I use Premiere Pro through the library?

**Gold expects:** Adobe CC suite access; clarify audience if not stated.

**Gold URLs:** `https://www.lib.miamioh.edu/software/`

**Bot answered (4589ms):**
> Yes. The library’s Adobe Creative Cloud access includes Premiere Pro among the available products, and it is available through the software checkout page [1][5].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 9. `ms_hours_today` [featured_service/`answered_should_have_refused`]

**Q:** Is the MakerSpace open right now?

**Gold expects:** Live MakerSpace LibCal status (libcal_id 11904).

**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (3244ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 10. `sc_archivist_contact` [featured_service/`refused_incorrectly`]

**Q:** Who is the archivist?

**Gold expects:** Special Collections & University Archives is on the 3rd Floor of King Library, 151 S Campus Ave, Oxford, OH 45056. SpecColl@MiamiOH.edu, phone (513) 529-3323. University Archives: Archives@MiamiOH.edu, phone (513) 529-6720.

**Gold URLs:** `https://spec.lib.miamioh.edu/home/`, `https://spec.lib.miamioh.edu/home/staff/`

**Bot answered (3146ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 11. `hr_special_collections_appt_only` [hours/`answered_should_have_refused`]

**Q:** What are Special Collections hours?

**Gold expects:** Provide Special Collections' open hours from LibCal (also viewable at https://www.lib.miamioh.edu/about/locations/hours/), AND note that research access is by appointment — appointments must be made through https://spec.lib.miamioh.edu/home/.

**Gold URLs:** `https://www.lib.miamioh.edu/about/locations/hours/`, `https://spec.lib.miamioh.edu/home/`

**Bot answered (4452ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 12. `lib_hamilton_librarian` [librarian/`refused_incorrectly`]

**Q:** Who can help me at the Hamilton library?

**Gold expects:** Hamilton librarian directory.

**Gold URLs:** `https://www.ham.miamioh.edu/library/about/rentschler-library-staff/`

**Bot answered (4072ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 13. `ref_admissions` [out_of_scope/`answered_should_have_refused`]

**Q:** How do I apply to Miami?

**Gold expects:** REFUSAL or redirect to miamioh.edu admissions; not the library bot's domain.

**Gold URLs:** _(none — refusal/free-text case)_

**Bot answered (673ms):**
> I'm not sure which of these you meant. Can you pick one?

Options: library employment, databases

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 14. `cite_apa_website` [research/`refused_incorrectly`]

**Q:** How do I cite a website in APA?

**Gold expects:** Cite the citation-resources page; do not generate the citation itself.

**Gold URLs:** `https://libguides.lib.miamioh.edu/citation/apa`

**Bot answered (2629ms):**
> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 15. `ds_gis` [research/`wrong`]

**Q:** Can someone help me with GIS?

**Gold expects:** Yes via data services consultations. Cite data services page.

**Gold URLs:** `https://www.lib.miamioh.edu/research/creation/data-services/`

**Bot answered (6859ms):**
> Yes — Oxford Library data services offers consultations, and the GIS article says library staff are happy to help with GIS projects [1][2]. The data services page also says it provides data services support, including GIS help and data visualization support [4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 16. `cit_no_fake_url` [service/`wrong`]

**Q:** Where can I find the printing policy?

**Gold expects:** Real printing policy URL only -- no fabricated /policies/printing.html.

**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/printing/`

**Bot answered (4777ms):**
> Use the Printing & WiFi page for Oxford printing policy information [1][3]. The page is the canonical printing page for the library’s current printing details [3][4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 17. `hh_email_question` [service/`wrong`]

**Q:** How do I email a question to the library?

**Gold expects:** Ask Us email or LibAnswers ticket flow.

**Gold URLs:** `https://www.lib.miamioh.edu/research/research-support/ask/`

**Bot answered (5993ms):**
> Use the Ask Us email/LibAnswers ticket flow to email your question to the library [1]. You can also reach Miami University Libraries through the Contact Us page, which lists email contact options [2].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 18. `space_food` [service/`wrong`]

**Q:** Can I bring food into the library?

**Gold expects:** Food/drink policy from spaces or policies page.

**Gold URLs:** `https://docs.google.com/document/d/1ZQdegDmo_8V7_aM8EMzpr57lQ5-kOj_jgtCqsbJ8_d4/edit#bookmark=id.7hxtip1fvnqu`

**Bot answered (6644ms):**
> The sources point to the Oxford library food/drink policy page for the current rules on bringing food into the library [1][2][3]. One Oxford library event announcement also shows food can be present in King Library during a special program, but it does not state the general policy [4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 19. `sw_matlab` [service/`wrong`]

**Q:** Is MATLAB available on library computers?

**Gold expects:** Confirm only if listed on the software page; otherwise refuse to assert.

**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/software/`

**Bot answered (6050ms):**
> Yes. The software page says additional titles such as MATLAB can be added to library computers using Software Center on campus Windows PCs and Self-Service on campus Macs [3][5].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 20. `sw_what_installed` [service/`wrong`]

**Q:** What software is on the library computers?

**Gold expects:** Cite the software-on-library-computers page; do not enumerate beyond what's listed.

**Gold URLs:** `https://www.lib.miamioh.edu/use/technology/software/`

**Bot answered (5453ms):**
> The library computers have Windows software including Adobe Creative Cloud, Audio-Video Viewing/Editing tools like Audacity and VLC Media Player, web browsers like Chrome and Safari, office software like Apple Keynote, Numbers, Pages, and Microsoft Office (Excel, PowerPoint, and Word), plus specialty software and utilities such as Logger Pro and Xcode [1][3]. The page also notes that additional titles such as MATLAB and SPSS may be available on campus Macs through self-service software install […

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

### 21. `sl_circulation_head` [staff/`wrong`]

**Q:** Who is the head of circulation?

**Gold expects:** Look up in staff directory; do not invent a name.

**Gold URLs:** `https://www.lib.miamioh.edu/about/organization/staff/`

**Bot answered (7736ms):**
> Alea Henle was named the new head of the Access & Borrow department, which encompasses circulation [2]. The staff directory page is the place to look up the current head of circulation [1].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is fine; broaden gold to accept it
- [ ] ❌ REJECT — bot is actually wrong; needs real bot fix
- [ ] 📝 NEW EXPECTED → write below:

  ```
  (operator: paste a better expected_answer here if needed)
  ```

---

## Bucket 2 — Partial verdicts to opt-in/opt-out (7 cases)

These are cases where the bot gave the right idea but the judge wanted slightly different phrasing. If you ACCEPT, I'll broaden the gold to mark them correct.

### 1. `circ_online_checkout` [circulation/`wrong`]

**Q:** How do I check out a book online for pickup?

**Gold expects:** Place a hold via Primo, choose pickup location, retrieve when notified.

**Bot answered:**
> Search for the book in Primo, click "Place Hold," and sign in [5]. Choose Oxford Campus / King Library as the pickup location, then wait for the notification that it is ready for pickup [2][4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 2. `circ_pickup_when` [circulation/`correct`]

**Q:** When will my book be ready for pickup?

**Gold expects:** Same-day for in-stock items; longer if from storage or another campus. Email notification on ready.

**Bot answered:**
> Same-day for in-stock items; it can take longer if the book comes from storage or another campus, and you’ll get an email when it’s ready [1].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 3. `circ_place_hold` [circulation/`partial`]

**Q:** How do I place a hold on a book at Miami?

**Gold expects:** Search Primo, click 'Place Hold' on the title, sign in. Cite circulation policies.

**Bot answered:**
> Search for the book in Primo, then click "Place Hold" on the title and sign in [1][2]. You can choose Oxford Campus / King Library as the pickup location when placing the hold [4].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 4. `find_article_topic` [capability_point_to_url/`correct`]

**Q:** I'm looking for an article about climate change

**Gold expects:** Point to Primo (or specific subject databases via A-Z).

**Bot answered:**
> Use Miami University Libraries’ Primo search to look for journal articles about climate change [1]. If you’d rather search within specific subject databases, use the Databases A–Z list to pick an appropriate database for your topic [6]. If you get stuck, contact a librarian through the Ask Us page for chat/email/appointment help [9].

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 5. `find_book_specific` [capability_point_to_url/`partial`]

**Q:** Do you have a copy of Hamlet?

**Gold expects:** Should point the user to Primo (search.lib.miamioh.edu / OhioLINK Primo) to find books — do NOT search the catalog itself. Mentioning ILL fallback is acceptable but not required.

**Bot answered:**
> Catalog search is currently unavailable. Please search directly at https://www.lib.miamioh.edu/ or chat with a librarian who can help find materials.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 6. `find_books_topic` [capability_point_to_url/`partial`]

**Q:** Where can I find books on Ohio history?

**Gold expects:** Point to Primo. Special Collections may also have relevant materials.

**Bot answered:**
> To find a specific book, article, journal, or DVD at Miami University Libraries, search Primo -- the library catalog. It searches across our physical collection, ebooks, journal articles, and OhioLINK partner libraries in one place.

Primo: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU

If Primo says "no results" and you think the library should have it, you can request it through Interlibrary Loan: https://www.lib.miamioh.edu/use/borrow/ill/

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---

### 7. `find_journal` [capability_point_to_url/`partial`]

**Q:** Can you find a journal article for me?

**Gold expects:** Should point to Primo to find journal articles — do NOT search the catalog itself. Mentioning ILL fallback for items Miami doesn't have is acceptable.

**Bot answered:**
> Catalog search is currently unavailable. Please search directly at https://www.lib.miamioh.edu/ or chat with a librarian who can help find materials.

**Decision:**
- [ ] ✅ ACCEPT — bot's answer is good enough; broaden gold
- [ ] ❌ REJECT — bot missed something important; keep as partial

---
