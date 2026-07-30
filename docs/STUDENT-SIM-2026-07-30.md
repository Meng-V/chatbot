# Ten simulated students against the acceptance sheet

**Run:** overnight 2026-07-30, before the live session
**Sheet:** [STUDENT-TEST-2026-07.md](STUDENT-TEST-2026-07.md) · **Target:** ≥80%

## Why simulate at all

The sheet tells testers to ask its ten questions **verbatim**. They won't.
They'll read the question, look up, and type it their own way. So this run
used ten students who each rephrased all ten questions in a consistent
personal voice, then asked three questions of their own — the sheet's own
recommended second pass.

| Student | Voice |
|---|---|
| S01 | reads carefully, near-verbatim, full sentences |
| S02 | short, lowercase, drops words ("makerspace open saturday?") |
| S03 | types fast, typos, no punctuation ("makerspce", "libary") |
| S04 | explains the whole situation before asking |
| S05 | abbreviations and jargon ("ILL pickup location?", "3DP") |
| S06 | very polite, asks permission first |
| S07 | keywords only, like a search box |
| S08 | non-native phrasing, grammatical but unidiomatic |
| S09 | leads with their identity, question second |
| S10 | merges clauses, blunt |

130 turns per run: 10 students × (10 scripted + 3 of their own). Q6 is two
turns, as the sheet specifies. Every turn opened a fresh conversation.

Graded by the sheet's rubric with **no partial credit** — a hesitation is
Wrong, as the sheet requires. The grader is mechanical per rubric row, and
anything a regex could not honestly settle was flagged for a human read
rather than quietly passed.

## Result

| Run | Code | Scripted score |
|---|---|---|
| 1 | as of 2026-07-30 evening | **75 / 100** |
| 2 | + the four fixes below | **92 / 100** |
| 3 | + typo tolerance and two self-caught regressions | **95 / 100** |
| — | + the last three fixes, Q9/Q10 re-run for all ten students | **99 / 100** |

Run 3 measured Q1–Q8 at **10/10 each** — eighty consecutive passes across ten
voices, typos and all. Its five failures were one Q9 and four Q10, and the
last three commits landed after it started, so Q9 and Q10 were re-asked by all
ten students against the finished code: **Q9 10/10, Q10 9/10**.

The single remaining failure is S07's bare `braiding sweetgrass` — a title
typed with no question around it. See "Known limit" below.

75% would have lost the bet. Not because anything was broken in a new way —
every failure was a phrasing the code had never been shown.

### Run 2, per question

| Q | Passed | What was left |
|---|---|---|
| 1 | 9/10 | one typo refusal ("makerspce") |
| 2 | 10/10 | — |
| 3 | 10/10 | — |
| 4 | 10/10 | — |
| 5 | 9/10 + 1 flagged | — |
| 6 | 7/10 | a *third* synthesizer wording, an em dash, and a self-inflicted guard |
| 7 | 10/10 | — |
| 8 | 10/10 | fixed from 2/9 |
| 9 | 9/10 | the polite phrasing still loses the research notice |
| 10 | 8/10 | a bare lowercase title, and one clarification prompt |

### Per question, before

| Q | Passed | What went wrong |
|---|---|---|
| 1 | 7/10 | hours lost when the student named the machine they came for; one typo refusal |
| 2 | 10/10 | — |
| 3 | 10/10 | — |
| 4 | 10/10 | the closed-library trap held for every phrasing |
| 5 | 10/10 | — |
| 6 | 2/9 | **asked "which subject?" then called the answer out of scope** |
| 7 | 9/9 | — |
| 8 | 2/9 | answered renewal but never the loan period, and never by user type |
| 9 | 8/9 | one polite phrasing lost the required research notice |
| 10 | 2/9 | "do u have <title>" classified as outside a library's scope |

Q2, Q3, Q4, Q5 and Q7 held across all ten voices, typos included. The traps
— the closed Amos Music Library, the per-campus 3D printing difference —
never once produced an invention. That is the part of the sheet that was
designed to catch hallucination, and it caught none.

## The four defects, and why they only showed up here

**Q6 — the bot asked a question and then rejected the answer.** Two bugs in
series. `who\s+(is|'s)` required a space before the apostrophe, so "who's my
subject librarian" missed the deterministic reply that "who is my subject
librarian" hit — 3 of 10 phrasings reached it. Then the continuation keyed off
a byte-stable substring of that one reply, so when the synthesizer asked the
question in its own words instead ("Which subject or department are you asking
about?"), a bare "marketing" the next turn came back OUT OF SCOPE. Now the
continuation matches the *question*, whoever composed it.

**Q8 — half the question went unanswered.** "How long can I keep a book, and
can I renew it if I'm a grad student?" got a renewal answer split by item
source (Miami vs OhioLINK/ILL) that never mentioned the borrower. The rubric
requires "depends on user type", and the student had said which type they
were. It now states the policy page's own figures — undergraduate 6 weeks,
graduate 1 semester, faculty 1 year, other patrons 6 weeks — with the page
cited. Several phrasings also carried no renewal verb the old trigger could
see ("Loan period + grad renewal policy?"), so it has its own trigger now.

**Q10 — a book request was called off-topic.** The full sentence routed to
`find_resource` and got the right Primo + Interlibrary Loan handoff. "do u
have braiding sweetgrass" classified as `out_of_scope`: a bare title carries
no library vocabulary for a stateless classifier. Only the routing is
rescued — the existing answer is better than a second one written for the
occasion.

**Q1 — the sheet already knew about this one.** Its "known rough edge" note
says that mentioning 3D printing and hours together loses the hours, and that
Q1 was *worded to avoid it*. The students walked straight back in, because
naming the machine you came for is how people ask: "I'm free Saturday and
wanted to use the 3D printer — is the MakerSpace open?" An explicit hours
question now wins over both the equipment and the 3D short-circuit.

Worth noting what this says about the sheet: wording a question around a known
defect measures the defect away. Q1 was the only question with such a note,
and it was the only trap-adjacent question that lost points.

## Two regressions I put in and took back out

Both were found by checking my own work against things the unit suite does not
cover. Recording them because they are the failure mode of this kind of fixing:
a widened trigger reaches further than you meant.

**The 6-week figure nearly answered for reserves.** The loan-period trigger was
broad enough to capture four gold cases whose right answers are nothing like a
book loan period — reserve textbooks (2 hours / 1 day / 3 days), Chromebooks
(30 days), DSLR cameras, and the hold-shelf window. All four would have been
told "6 weeks to undergraduates". **The unit suite stayed green**, because
those are eval cases, not unit tests. Reading the golden set by hand is what
caught it; the seven exclusions are now pinned in a test.

**"Search Primo for parking."** The rescue that stops a book request being
called out-of-scope keyed on the question shape alone, so "do you have
parking?", "do you have a gym?", "do you have tutoring?" and four more would
have been sent to the library catalogue. That is a worse answer than the scope
deflection they get today. The rescue now needs an item signal too — a noun
like *book* or *copy*, a borrow/read verb, or a Capitalised Title. Seven of
the ten Q10 phrasings carry one; the two that don't are all-lowercase with no
noun, and they stay unrescued deliberately, because there is no honest way to
separate "do u have braiding sweetgrass" from "do u have parking" without
knowing the title.

## Free-form questions (30)

28 of 30 were answered well. Two were not, both "in scope but classified out":

- *"were is the bathroom in king libary"* — hard refusal. Typos plus a basic
  building question. **Not fixed:** I have no verified restroom-location data
  and will not invent it. A floor-plan or service-desk pointer is the right
  answer and needs a librarian to confirm the source.
- *"Athletic training resources — what do you have?"* — out of scope. A
  subject-resources question. Incidentally rescued by the Q10 routing fix
  (it now reaches the catalogue handoff), though a research-guide answer
  would be better still.

## Known limit, left in on purpose

`braiding sweetgrass` — a title typed with no question around it — still gets
the out-of-scope deflection. Two lowercase words with no verb are genuinely
ambiguous: a title, a research topic, or a fragment. The rescue that catches
"do u have braiding sweetgrass" needs a have-question shape to fire, and
inventing a "bare noun phrase → catalogue" rule would be a guess that also
catches every off-topic fragment a student types.

It failed for 1 of 10 students, which is the sheet's own definition of a
phrasing fluke rather than a defect. Worth revisiting with real session data.

## What changed overnight

Nine commits, all from this simulation. Each carries the phrasing that
exposed it, so a future reader can tell a real defect from a guess:

| Commit | What |
|---|---|
| `216906b` | fines question hard-refused because the gold rubric said "refuse" |
| `6a626ec` | the four Q6/Q8/Q10/Q1 routing defects |
| `9691a30` | typo tolerance for `librarian` and `makerspace` |
| `e55c38a` | stop the 6-week book figure answering for reserves and Chromebooks |
| `120ff12` | require an item signal before rescuing a turn into the catalogue |
| `f594e7d` | all ten "who's my librarian" phrasings land |
| `8c2fb09` | being polite should not cost you the answer |
| `77c93e9` | name the facilities instead of demanding an item noun |
| `33aa46e` | don't ask a student to pick between two intent names |

`216906b` is already on origin; the rest are local and need a push:

```bash
cd /opt/chatbot && git push origin main
```

The running service already has all of them — it was restarted to measure
each round — so a push is for the remote's benefit, not the box's.

## Two things to do before the session

1. **Warm it up.** The first request after a restart took 35 seconds; every
   later one was fast. Ask it one question yourself before the first student
   sits down. Median 7s, p90 13s, p95 14s across 130 turns.
2. **Nothing the students say will be recorded.** Conversation persistence
   stopped writing in February 2026 and the logs hold no question or answer
   text. Whatever the session finds has to be written down by hand in the
   room, or it is lost.

## What this run does not tell you

- **It is not ten humans.** Ten *simulated* voices cover more phrasing
  variety than one person testing carefully, but they cannot be surprised,
  they don't follow up when an answer is unsatisfying, and they don't ask the
  question behind the question.
- **The grader is mine.** It applies the sheet's rubric row by row, but a
  human tester may be stricter about a technically-correct answer that reads
  badly — the research-question notice now prefixes several answers where it
  makes no sense, and a student may well count that against the bot even
  though the rubric doesn't.
- **Same corpus, same day.** Live LibCal hours and the librarian API were
  real; the crawled corpus is from 2026-05-14 and unchanged by any of this.
