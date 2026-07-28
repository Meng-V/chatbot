# Student acceptance test — 10 questions

**Prepared:** July 27, 2026 · **Target:** ≥80% correct to pass
**Every question below was piloted against production before release.**

## How to run it

Each tester opens the chatbot fresh (new browser session) and asks all
10 questions **in order**, one conversation per question — except Q6,
which is deliberately two turns. Record the bot's answer and grade it
with the rubric on the right.

Two things testers must be told up front, or the score will be wrong:

1. **"I can't answer that" is sometimes the correct answer.** Q4 and
   Q10 are designed to see whether the bot refuses to invent. Grade
   them by the rubric, not by whether you got an answer.
2. **Don't rephrase.** Ask the question as written. (If you want to
   *also* test robustness, do a second pass where testers rephrase
   freely — see "Optional second pass" below.)

---

## The questions

| # | Question | What it's really testing |
|---|---|---|
| 1 | *Will the MakerSpace be open this Saturday?* | Live LibCal hours **for a space inside a building** — the MakerSpace keeps its own hours, not King's |
| 2 | *I take classes at the Hamilton campus. Where do I pick up a book I requested through interlibrary loan?* | Campus discipline — never substituting Oxford's answer for a regional campus |
| 3 | *I'm writing a paper for BIO 203 and I'm stuck. Who at the library can help me?* | Course code → the right human, by name and email |
| 4 | *What time does the Amos Music Library close today?* | **Trap.** That library closed in 2023. Does the bot invent hours? |
| 5 | *Can I 3D print something at the Middletown campus library?* | Per-campus service truth — the three campuses genuinely differ |
| 6 | *Who is my subject librarian?* → then reply with **your own major** | Asks a clarifying question instead of guessing, then resolves it |
| 7 | *Is there a study room for four people free at King tomorrow afternoon?* | Live room availability + it can actually book one in chat |
| 8 | *How long can I keep a book, and can I renew it if I'm a grad student?* | Policy that varies by user type and item source |
| 9 | *I need to find peer-reviewed articles about social media and teen mental health. Where do I start?* | Real research help **plus** the librarian-referral notice |
| 10 | *Do you have a copy of Braiding Sweetgrass?* | **Boundary.** The bot is not a catalog. Does it admit that? |

---

## Grading rubric

Mark each **Correct** / **Wrong**. Partial credit is not used — if a
tester hesitates, it's Wrong (that keeps the 80% honest).

| # | ✅ Correct if… | ❌ Wrong if… |
|---|---|---|
| 1 | States the MakerSpace's own Saturday status (open hours **or** "closed"), with a source link | Gives King Library's building hours instead, or only describes where the MakerSpace is |
| 2 | Says pick up at **Rentschler / Hamilton** | Says King or Oxford; or gives generic ILL info with no campus |
| 3 | Names a specific librarian **with an email address** | Only links the directory; names someone with no contact; refuses |
| 4 | Says the Amos Music Library is **permanently closed** | Gives any opening/closing time; says it's open; invents a location |
| 5 | Says **yes for Middletown** (may add: King yes, Hamilton no) | Says no for Middletown; says all campuses have it; refuses |
| 6 | Turn 1 **asks which subject**; turn 2 returns a librarian + email for that subject | Turn 1 names a person without asking; turn 2 fails to resolve your major |
| 7 | Gives live availability **or** offers to check a specific time window / gives the booking link | Says it can't help with rooms; invents specific room numbers with no source |
| 8 | Says the loan period **depends on user type** and points to circulation policies; mentions renewing via the account | Quotes one flat number for everyone with no source |
| 9 | Opens with the "This might be a research question…" notice **and** still gives a usable starting point (databases / peer-reviewed filter) | Missing the notice; or the notice with no actual help |
| 10 | Directs you to **Primo / the catalog** and doesn't claim to know whether it's on the shelf | Claims the library does or doesn't own it; invents a call number or location |

**Score = correct answers ÷ 100.** Also log, per question, how many of
the 10 testers got it right — a question that fails for 7 of 10 people
is a real defect; one that fails for 1 of 10 is usually a phrasing
fluke worth reading but not panicking over.

---

## Why these ten

They're picked so that a passing score actually means something:

- **Four of them can only be answered by live systems** (1, 3, 6, 7) —
  hours, the librarian database, room availability. A bot that just
  paraphrases the website fails these.
- **Three are traps** (4, 5, 10) — a closed library, a service that
  differs by campus, and a catalog lookup the bot genuinely can't do.
  These are where a chatbot normally hallucinates, and they're the most
  valuable rows in the whole table.
- **Two test conversation, not lookup** (6, 9) — asking a clarifying
  question, and knowing when to point at a human.
- **One tests nuance** (8) — the answer is legitimately "it depends,"
  and saying so with a source beats a confident wrong number.

None of them is answerable by pasting a single web page, and none needs
insider knowledge to grade.

## Optional second pass (recommended)

After the scripted run, have each tester ask **three questions of their
own** — whatever they'd actually ask the library. Those won't have a
rubric, but they're where genuinely new failures show up, and each one
can be turned into a ticket. The scripted 10 measure whether we hold up;
the free-form 3 measure what we haven't thought of yet.

## Known rough edge (don't let it skew the test)

If a tester mentions 3D printing *and* hours in the same breath
("I want to 3D print this weekend — is the MakerSpace open?"), the bot
answers about 3D printing and skips the hours. Q1 is worded to avoid
this. It's a known routing quirk, logged for a future fix.
