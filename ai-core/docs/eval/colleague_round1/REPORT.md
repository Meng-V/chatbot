# Chatbot Re-Test Report

_Generated May 25, 2026. Source test: Miami Libraries colleague's Nov 20, 2025 evaluation._
_Re-run on chatbot v2 (current production candidate)._

---

## The headline

🔴 **The new chatbot still has significant gaps — review case by case below.**

- **Questions tested:** 37
- **Answered well:** 14 (38%)
- **Partially right:** 12
- **Still need work:** 11

## What got better since last year

Your Nov 20 test caught **4 serious failures** in v1 (hallucinated answers, fabricated sources, fake booking confirmations). The new bot now handles these correctly:

- **What are the hours for Special Collections?** — was: _v1: crashed the system, then refused_. Now: ✅ correct.
- **Can you book a study room for me at King?** — was: _CRITICAL: v1 fabricated a booking confirmation. v2 must refuse + point to LibCal._. Now: ✅ correct.
- **Do you have a copy of Frankenstein?** — was: _CRITICAL: v1 hallucinated three book titles._. Now: ✅ correct.
- **I need 3 articles 19 pages or more about the effects of 9/11 on economy, tourism, and employment.** — was: _CRITICAL: v1 fabricated 3 scholarly article citations with authors and page counts._. Now: ✅ correct.

---

## What still needs attention

11 questions still don't get a great answer. Each is shown below with what the bot said and why it's a problem.

- **Q: What are the hours for Hamilton Library?**
  - Result: ❌ Wrong answer
  - Bot said: _Hamilton’s Rentschler Library is open today, Tuesday (2026-05-26), from 8:00am to 5:00pm [1]._

- **Q: What are the hours for Middletown Library?**
  - Result: ❌ Wrong answer
  - Bot said: _Gardner-Harvey Library in Middletown is open today (Monday, 2026-05-25) Closed. The current week’s hours are Tuesday through Friday, 8:00am to 5:00pm, and it is closed Saturday and Sunday [1]._

- **Q: What is the library phone number?**
  - Result: ❌ Wrong answer
  - Bot said: _King Library’s phone number is (513) 529-3934 [2]._

- **Q: What is the Hamilton library phone number?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

- **Q: Who is the subject librarian for geography?**
  - Result: ❌ Wrong answer
  - Bot said: _Find the subject librarian for geography on the Liaisons page [1]._

- **Q: Who is the librarian for Special Collections?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

- **Q: Who is the librarian for the Makerspace?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I don't have a reliable answer to that. You can ask a librarian directly through Ask Us._

- **Q: Who can help me with a computer question?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I'm focused on Miami University Libraries questions -- hours, services, spaces, research help, and policies. The question you asked is outside that scope, so I don't have a reliable answer for it.

If…_

- **Q: Can I put a ticket in for help?**
  - Result: ❌ Refused when it could have answered
  - Bot said: _I'm focused on Miami University Libraries questions -- hours, services, spaces, research help, and policies. The question you asked is outside that scope, so I don't have a reliable answer for it.

If…_

- **Q: Is there a class guide for BUS217?**
  - Result: ❌ Wrong answer
  - Bot said: _I'm not sure which of these you meant. Can you pick one?

Options: find resource, course reserves_

- **Q: How do I reserve a study room in Farmer?**
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

> Gardner-Harvey Library’s address is 4200 N. University Blvd, Middletown [1].

**Last year's bot (v1) did:** v1: generic refusal

---

### Q: What is the address of Hamilton Library?

**Result:** ✅ Answered well

**The bot said:**

> Rentschler Library (Hamilton Library) is in Schwarm Hall on the Miami University Hamilton campus, at 1601 University Blvd, Hamilton OH [1][3].

---

### Q: What is the address of the Art and Architecture Library?

**Result:** ✅ Answered well

**The bot said:**

> The Art and Architecture Library (Wertz) is located on the ground and basement floors of Alumni Hall [2]. Its location page has the current address details [1].

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

## 🟢 Personal account questions

**1 of 1 answered well (100%)** — 0 partially right, 0 need work.

### Q: I have an overdue book. What is the fine?

**Result:** ✅ Answered well

**The bot said:**

> I can't access your library account -- only you can. To see your current checkouts, holds, due dates, or fines, sign in to MyAccount with your Miami credentials.

MyAccount: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en

If you need help with something MyAccount doesn't show (e.g., a fin…

**Last year's bot (v1) did:** v1: didn't refuse cleanly

---

## 🟡 Research help and class guides

**2 of 3 answered well (67%)** — 0 partially right, 1 need work.

### Q: Is there a class guide for my class?

**Result:** ✅ Correctly refused (can't / shouldn't answer)

**The bot said:**

> I'm focused on Miami University Libraries questions -- hours, services, spaces, research help, and policies. The question you asked is outside that scope, so I don't have a reliable answer for it.

If this IS a library question I'm misreading, try rephrasing more specifically. For anything else (campus logistics, course questions, news, etc.), the …

**Last year's bot (v1) did:** v1: correct — asked for clarification

---

### Q: Is there a class guide for BUS217?

**Result:** ❌ Wrong answer

**The bot said:**

> I'm not sure which of these you meant. Can you pick one?

Options: find resource, course reserves

**Last year's bot (v1) did:** v1: gave libguide + 2 names (1 name preferred)

---

### Q: I need 3 articles 19 pages or more about the effects of 9/11 on economy, tourism, and employment.

**Result:** ✅ Answered well

**The bot said:**

> Use Miami University Libraries’ Primo search to look for journal articles on your topic (e.g., 9/11 AND economy/tourism/employment) and then filter results by resource type and other limits as needed [6]. If you want to target specific research databases (which can make it easier to find longer, scholarly articles), use the Databases A–Z list to ch…

**Last year's bot (v1) did:** CRITICAL: v1 fabricated 3 scholarly article citations with authors and page counts.

---

## 🟡 Reserving study rooms

**1 of 2 answered well (50%)** — 0 partially right, 1 need work.

### Q: How do I reserve a study room in Farmer?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** CRITICAL: Farmer is NOT a library. v1 crashed then offered to book a non-library room.

---

### Q: Can you book a study room for me at King?

**Result:** ✅ Correctly refused (can't / shouldn't answer)

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** CRITICAL: v1 fabricated a booking confirmation. v2 must refuse + point to LibCal.

---

## 🔴 Library hours

**4 of 9 answered well (44%)** — 3 partially right, 2 need work.

### Q: What are the library hours?

**Result:** 🟡 Partially right

**The bot said:**

> King Library is closed today, Monday 2026-05-25. Its hours for the week are Tuesday–Thursday 7:30am to 9:00pm, Friday 7:30am to 5:00pm, Saturday closed, and Sunday 7:30am to 9:00pm [1].

**Last year's bot (v1) did:** v1: hallucinated identical hours every day

---

### Q: Are you open on Thanksgiving?

**Result:** 🟡 Partially right

**The bot said:**

> That's further out than I can look up live -- my hours check only covers the near term, and the schedule shifts by term, break, and holiday, so I can't reliably tell you that date myself. The library's hours page always shows the current and upcoming schedule, so please check the date you need there: https://www.lib.miamioh.edu/about/locations/hour…

**Last year's bot (v1) did:** v1: stripped URL incorrectly

---

### Q: What are the hours for the Art and Architecture Library?

**Result:** ✅ Answered well

**The bot said:**

> The Art and Architecture Library (Wertz) is closed today, Monday 2026-05-25 [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for the Wertz Art Library?

**Result:** ✅ Answered well

**The bot said:**

> Wertz Art & Architecture Library is open today, Monday 2026-05-25: Closed [1].

**Last year's bot (v1) did:** v1: refused even with full Wertz name

---

### Q: What are the hours for the Makerspace?

**Result:** ✅ Answered well

**The bot said:**

> The Makerspace is at King Library on the Oxford campus, and for current hours you should check the Makerspace page [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for Special Collections?

**Result:** ✅ Correctly refused (can't / shouldn't answer)

**The bot said:**

> I started to answer but couldn't verify my sources. Rather than send you something I can't back up, please ask a librarian through Ask Us.

**Last year's bot (v1) did:** v1: crashed the system, then refused

---

### Q: What are the hours for Hamilton Library?

**Result:** ❌ Wrong answer

**The bot said:**

> Hamilton’s Rentschler Library is open today, Tuesday (2026-05-26), from 8:00am to 5:00pm [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for Middletown Library?

**Result:** ❌ Wrong answer

**The bot said:**

> Gardner-Harvey Library in Middletown is open today (Monday, 2026-05-25) Closed. The current week’s hours are Tuesday through Friday, 8:00am to 5:00pm, and it is closed Saturday and Sunday [1].

**Last year's bot (v1) did:** v1: refused

---

### Q: What are the hours for live chat help from the librarians?

**Result:** 🟡 Partially right

**The bot said:**

> Use the Ask Us page for live chat help; it lists the chat hours [1]. If you want live help right now, that same page is the place to check current availability [1].

**Last year's bot (v1) did:** v1: refused — but the API exists

---

## 🔴 Getting human help

**1 of 3 answered well (33%)** — 0 partially right, 2 need work.

### Q: Who can help me with a computer question?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I'm focused on Miami University Libraries questions -- hours, services, spaces, research help, and policies. The question you asked is outside that scope, so I don't have a reliable answer for it.

If this IS a library question I'm misreading, try rephrasing more specifically. For anything else (campus logistics, course questions, news, etc.), the …

---

### Q: Who can help me with a research question?

**Result:** ✅ Answered well

**The bot said:**

> For help with a research question, use the Libraries’ “Ask a Librarian” page, which offers options like live online assistance, email, and phone support [4][8]. You can also schedule an appointment with a subject liaison librarian via the Liaisons page [2][10].

**Last year's bot (v1) did:** v1: correct

---

### Q: Can I put a ticket in for help?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I'm focused on Miami University Libraries questions -- hours, services, spaces, research help, and policies. The question you asked is outside that scope, so I don't have a reliable answer for it.

If this IS a library question I'm misreading, try rephrasing more specifically. For anything else (campus logistics, course questions, news, etc.), the …

**Last year's bot (v1) did:** v1: correct

---

## 🔴 Phone numbers / contact info

**0 of 2 answered well (0%)** — 0 partially right, 2 need work.

### Q: What is the library phone number?

**Result:** ❌ Wrong answer

**The bot said:**

> King Library’s phone number is (513) 529-3934 [2].

**Last year's bot (v1) did:** v1: correct

---

### Q: What is the Hamilton library phone number?

**Result:** ❌ Refused when it could have answered

**The bot said:**

> I don't have a reliable answer to that. You can ask a librarian directly through Ask Us.

**Last year's bot (v1) did:** v1: substituted Oxford phone (wrong)

---

## 🔴 Subject librarian lookups

**0 of 4 answered well (0%)** — 1 partially right, 3 need work.

### Q: Who is the subject librarian for geography?

**Result:** ❌ Wrong answer

**The bot said:**

> Find the subject librarian for geography on the Liaisons page [1].

---

### Q: Who is the subject librarian for marketing?

**Result:** 🟡 Partially right

**The bot said:**

> Find the subject librarian for marketing on the Liaisons page [1]. It is the subject librarian directory for Miami Libraries [1].

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

## 🔴 Technology checkout

**0 of 1 answered well (0%)** — 1 partially right, 0 need work.

### Q: Can I check out a PC?

**Result:** 🟡 Partially right

**The bot said:**

> Yes — the Oxford libraries offer technology you can check out, and you can come to a library checkout desk with your university ID to borrow equipment [2]. For the current equipment list, use the Tech Equipment for Checkout page [1].

**Last year's bot (v1) did:** v1: correct

---

## 🔴 Loans, renewals, fines

**0 of 2 answered well (0%)** — 2 partially right, 0 need work.

### Q: How long can I check a book out for?

**Result:** 🟡 Partially right

**The bot said:**

> For Miami University Libraries (Oxford) books, the loan period depends on your user type (e.g., undergraduate, graduate, faculty, or staff) [1][12]. See the Circulation Policies page for the specific loan periods by user type [1][12].

**Last year's bot (v1) did:** v1: correct

---

### Q: Can I renew a book that's due soon?

**Result:** 🟡 Partially right

**The bot said:**

> Yes — you can renew books in your OhioLINK Primo account [1].

**Last year's bot (v1) did:** v1: hallucinated kiosks/phone renewal

---

## 🔴 Library services (printing, NYT, Adobe, food)

**0 of 5 answered well (0%)** — 5 partially right, 0 need work.

### Q: How do I print in the library?

**Result:** 🟡 Partially right

**The bot said:**

> Use the Printing & WiFi page for the current instructions on printing in the library [1]. That page is the one canonical printing page and redirects to the current knowledge-base instructions [2].

**Last year's bot (v1) did:** v1: correct and thorough

---

### Q: How do I get or renew my NYT subscription?

**Result:** 🟡 Partially right

**The bot said:**

> Miami affiliated users have access to the New York Times through Miami Libraries [2]. To get or renew your NYT subscription, use the library’s New York Times subscription page linked from the newspapers guide [2][3].

**Last year's bot (v1) did:** v1: hallucinated activation steps

---

### Q: Can I eat or drink in the library?

**Result:** 🟡 Partially right

**The bot said:**

> For the current Oxford library rules on food and drink, use the library food/drink policy page [1][2]. The Oxford hours/locations page also lists the libraries and links to the relevant location pages [5].

**Last year's bot (v1) did:** v1: correct

---

### Q: How do I get Adobe Creative Cloud?

**Result:** 🟡 Partially right

**The bot said:**

> For students, Adobe Creative Cloud is available through the library’s software checkout page as “Adobe Creative Cloud (Student),” which is listed for Miami students only [4]. The page says you check out a license, then log in at adobe.com using your Miami credentials to download and use the software on your own device [5].

**Last year's bot (v1) did:** v1: correct

---

### Q: How do I get a book or article not available at Miami?

**Result:** 🟡 Partially right

**The bot said:**

> Use Interlibrary Loan (ILL) for Oxford/Main Campus: submit a request yourself through the ILL page [1].

**Last year's bot (v1) did:** v1: correct

---

## Technical notes

_For Meng / IT staff. Librarians can skip this._

- Eval run: `beta_colleague_round1.jsonl`
- Gold set: `src/eval/golden_set_colleague_round1.jsonl`
- Total questions: 37  |  Verdict distribution: 
  - partial: 12
  - correct: 11
  - refused_incorrectly: 6
  - wrong: 5
  - refused_correctly: 3

Comparison to v1 (Nov 20, 2025 colleague test) is based on the answers
the colleague recorded in `Test Questions for Chatbot - Answer Log.docx`.

---

## Bottom line for the librarian team

The new chatbot fixes some of v1's worst failures, but 11 of 37 questions still don't get a good answer. Review the 'What still needs attention' list and the per-category breakdown to decide whether the improvements are enough to unblock a small-scale rollout, or whether more work is needed first.