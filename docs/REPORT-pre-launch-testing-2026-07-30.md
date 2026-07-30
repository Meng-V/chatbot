# Libraries Smart Chatbot — pre-launch testing report

**Date:** July 30, 2026
**Prepared by:** Meng Qu (qum@miamioh.edu)
**Subject:** Results of a simulated student acceptance test, and what it changed

---

## Summary

Before running the acceptance test with real students, we ran it against ten
**simulated** students — each one asking the same ten questions in their own
words, the way people actually type, plus three questions of their own
invention. 130 questions per round, graded against our published rubric with no
partial credit.

The first round scored **75 out of 100**, below our 80% threshold.

We identified the causes, fixed them, and re-measured. The final round scored
**99 out of 100**.

Two things to hold in mind when reading that number, both covered in detail
below: it measures **answer correctness against our rubric**, which is not the
same thing as student satisfaction, and it was produced by simulated students,
who cannot be surprised or disappointed the way real ones can.

---

## What we tested

Our acceptance test (published July 27) asks testers to put ten questions to
the chatbot **word for word**. In practice they will read a question, look up,
and type it their own way. That gap is where failures hide, so the simulation
deliberately closed it: ten students, ten distinct ways of typing.

| Student | How they type |
|---|---|
| 1 | Careful, near-verbatim, full sentences |
| 2 | Short, lowercase, drops words — *"makerspace open saturday?"* |
| 3 | Fast, with typos — *"is the makerspce open this saturday"* |
| 4 | Explains their whole situation before asking |
| 5 | Abbreviations and jargon — *"Hamilton student — ILL pickup location?"* |
| 6 | Very polite — *"Could you tell me whether…"* |
| 7 | Keywords only, like a search box — *"hamilton ill pickup"* |
| 8 | Non-native phrasing — *"This Saturday, the MakerSpace will open or not?"* |
| 9 | Leads with their situation, question second |
| 10 | Blunt and compressed — *"Subject librarian — who's mine?"* |

Each also asked three questions of their own, per the "optional second pass"
in our test plan. Every question opened a fresh conversation, and the
two-turn question was run as two turns, exactly as the plan specifies.

Grading followed our own rubric row by row, with the rubric's rule that
**partial credit is not given** — a hesitant answer counts as wrong.

---

## Results

| Round | Score |
|---|---|
| Before any changes | **75 / 100** |
| After the first four fixes | 92 / 100 |
| After all fixes | **99 / 100** |

Eight of the ten questions ended at **10 out of 10 across all ten students** —
eighty consecutive correct answers spanning typos, abbreviations, and
non-native phrasing.

### The most important finding is not the score

Three of the ten questions are deliberate traps, designed to catch the failure
mode that matters most for a library: a chatbot that invents an answer rather
than admitting it does not know.

- **A library that closed in 2023.** Asked what time the Amos Music Library
  closes today, the bot said it has permanently closed — for all ten
  phrasings. It never invented an opening time.
- **A service that differs by campus.** Asked whether 3D printing is available
  at the Middletown campus, it gave the correct per-campus answer — Oxford yes,
  Hamilton no, Middletown yes — every time.
- **A catalogue lookup it genuinely cannot do.** Asked whether we hold a
  specific book, it directed the reader to the catalogue rather than claiming
  the book is or isn't on the shelf.

**These traps produced no fabricated answers in any round, including the
round that scored 75%.** The failures we found were the bot being unhelpful,
never the bot being wrong about a fact.

---

## What was wrong, and what we fixed

Every failure was a phrasing the system had not been shown before. Nothing
was broken in a new way. Four were significant:

**1. The bot asked a question and then rejected the answer.**
Asked "who's my subject librarian?", it correctly replied "tell me your
subject" — and then told the student their answer ("marketing") was outside
what it covers. This was the worst failure found: it makes the bot look
broken in a way a student will remember. Fixed, and the fix no longer depends
on the exact wording the bot happens to use when it asks.

**2. Half of a two-part question went unanswered.**
Asked "how long can I keep a book, and can I renew it if I'm a grad student?",
the bot explained renewal but never said how long, and never mentioned that
the loan period depends on who you are — even though the student had said they
were a graduate student. It now gives the policy's own figures.

**3. Asking whether we have a book was treated as off-topic.**
Typed in full, this worked. Typed informally — *"do u have braiding
sweetgrass"* — the bot replied that the question was outside a library
chatbot's scope. Fixed.

**4. Naming the equipment you came for lost the opening hours.**
"I'm free Saturday and wanted to use the 3D printer — is the MakerSpace
open?" got an answer about 3D printing and no hours. Our own test plan had
recorded this as a known issue and had *worded its question to avoid it*.
The simulated students walked straight back into it, because naming the
machine you came for is how people ask. Now fixed.

That last point is worth stating plainly: **wording a test question around a
known defect measures the defect away.** It was the only question in our
plan carrying such a note, and it was the only trap-adjacent question that
lost points.

We also found and corrected two errors introduced by our own fixes before
they could reach anyone — one that would have quoted the six-week book loan
period for reserve textbooks and laptops, and one that would have directed a
student asking about parking to search the library catalogue. Both were caught
by checking the fixes against our full evaluation set rather than only against
the automated tests, which passed throughout.

The full technical record, including every phrasing that exposed a defect, is
in `docs/STUDENT-SIM-2026-07-30.md`. All changes are covered by automated
regression tests (864 passing).

---

## Limits of this exercise

Stated plainly, because the number above is easy to over-read.

**Simulated students are not students.** Ten scripted voices cover more
phrasing variety than one person testing carefully, but they cannot be
surprised, they do not follow up when an answer is unsatisfying, and they
never ask the question behind the question. Real testers will find things
this could not.

**We graded correctness, not satisfaction.** The rubric asks whether the
answer is right. A student may mark down an answer that is technically correct
but reads badly — and we know of one such case: a "this might be a research
question" notice currently appears on some answers where it makes no sense.
It costs nothing on the rubric and may cost something with a real person. It
is logged for fixing.

**One known gap remains.** Typing only a book title, with no question around
it, still gets an out-of-scope reply. Two lowercase words with no verb are
genuinely ambiguous, and guessing would create worse errors elsewhere. It
affected one student in ten, which our plan defines as a phrasing fluke rather
than a defect.

**The knowledge base is dated May 14, 2026.** Live information — opening
hours, room availability, the librarian directory — is queried in real time and
is current. The crawled website content is not. A refresh is prepared and
blocked on a separate issue.

---

## Recommended before and during the live session

1. **Ask the bot one question before the first student arrives.** The first
   request after a restart takes about 35 seconds; every one after that is
   fast (median 7 seconds). Warming it up avoids a bad first impression.

2. **Record what happens on paper.** Conversation logging stopped writing in
   February 2026, so today's questions and answers are not being saved
   anywhere. Anything not written down in the room is lost, and the session's
   value is in exactly those details. Restoring conversation logging — with a
   decision on what may be retained about student questions — is the single
   highest-value item after this session.

3. **Treat the free-form questions as the real findings.** 28 of the 30 that
   the simulation invented were answered well; the two that were not are both
   cases of an in-scope question being classified as out of scope. That is the
   failure pattern to watch for, and real students will find more of it.
