# Where each fact lives — one source per kind

**Last Updated:** July 28, 2026

The bot's people-and-subject data had grown into six overlapping copies
that disagreed with each other, and two of them caused the bot to hand
patrons the **wrong person's contact details** in a single day. This page
is the rule that prevents that: **each kind of fact has exactly one
source, and everything else is derived or deleted.**

## The rule

| Fact | Single source | How it's updated |
|---|---|---|
| Who works here (name, email, phone, title, campus) | **Postgres `Librarian`**, reconciled from the operator's **staff CSV** | `scripts/reconcile_staff_from_csv.py` |
| What subjects exist (+ course / dept / major codes) | **Postgres `Subject`** + its code tables | same ingest |
| Which librarian covers which subject | **Postgres `LibrarianSubject`**, with the **live LibGuides API** as fallback | ingest / LibGuides |
| Live hours, room availability | **LibCal API** — never cached, never crawled | n/a (live) |
| Page content, policies, guides | **Weaviate corpus** (ETL'd website) | `scripts/etl/` |
| Answers the operator has hand-fixed | **Postgres `ManualCorrection`** | `/admin/corrections/view` |

## Two rules about people (2026-07-28)

**1. Middle names never appear — anywhere.** Not in what we say, not in
what we match on. `src/utils/person_names.py` is the only place names are
compared, and every caller goes through it: the DB lookup, the
contact-by-name short-circuit, the wrong-person guard, the departed-staff
check, and the synthesizer prompt. It ignores middle names *and* middle
initials on **both** sides of a comparison, folds accents, and drops
punctuation (`O'Brien` → `obrien`, `Jones-Scott` → `jonesscott`) so a
hyphenated or apostrophised surname stays one word instead of matching by
halves.

This matters because one human appears in three spellings across our
sources, and matching used to be a `contains` on the whole string:

| Roster | LibGuides API | Patron types |
|---|---|---|
| `Roger A Justus` | `Roger Justus` | `roger justus` |
| `Patricia Kay Russell` | `Patricia Russell` | `patricia russell` |
| `Rob O'Brien Withers` | `Rob Withers` | `rob withers` |

All 14 spelling variants of those names now resolve to the right person,
and the bot says `Roger Justus` regardless of which one was typed.
`Anthony Jones-Scott` keeps his full surname — a hyphen is not a middle
name.

**2. Every personnel answer states its source.** When the bot gives a
person's name, email, phone, or title, it ends with one of:

- `Source: Libraries staff directory database.` — Postgres `Librarian`
- `Source: LibGuides API (live).` — the Springshare API
- `Source: Libraries staff pages, verified by library staff.` — the
  hand-verified specialist answers below

The reason is operational: these systems are edited by **different people
in different places**. A librarian who spots a wrong phone number can now
tell from the answer alone whether to fix it in LibGuides or ask the
operator to correct the database. Rows carry a `source` field from the
lookup all the way into the evidence text, so the synthesizer repeats the
label instead of inventing one.

## What was removed (2026-07-28) and why

- **`LIBRARIAN_SUBJECTS`** (hand-maintained person→subjects map in
  `src/tools/subject_aliases.py`) — **deleted.** A third copy of a fact
  Postgres and LibGuides already owned. It went stale silently (a
  departed colleague stayed in it for weeks) and its substring matching
  made "How do I contact Krista McDonald?" answer with Roger Justus's
  email, because the middle initial in `"roger a justus"` matched almost
  any name.
- **Name→subject inference** in `real_backends._resolve_subject_terms` —
  **removed.** Turning a person's name into their subject list and then
  querying by subject is what let a departed colleague's name resolve to
  whoever covers her old subjects, presented as the person asked for.
  A name now goes straight to the Postgres name lookup.
- **Ten unused functions in `enhanced_subject_search.py`** (455 → 99
  lines) — a whole second implementation of subject search with **its
  own** copy of the librarian mapping and the same matching flaw. Zero
  callers outside the file. Only `extract_course_codes` and
  `extract_keywords` are live.
- **`scripts/sync_liaisons_from_website.py`** — **deleted 2026-07-28.**
  A fourth hand-typed copy of the subject↔librarian relationship (82
  lines of `{subject: [emails]}`), and a script that WRITES to
  `LibrarianSubject` — the table this page names as the single source.
  Of its 15 distinct emails, **9 do not exist in the roster at all**
  (`adamskk@` vs the real `adamsk3@`, `morgana3@` vs `morgan55@`,
  `hilless@` vs `hillessa@`, `gibsonkr@` vs `gibsonke@`, `revellam@` vs
  `revellaa@`, `dahlqumw@` vs `dahlqumj@`, plus `birkenla@`, `obrier@`
  and departed `spraetjr@`), and a 10th pointed at Erica Freed's
  **inactive** duplicate row. Running it would have overwritten correct
  liaison data with wrong addresses. It was never referenced by anything
  and had never been run — the 70 live `LibrarianSubject` rows contain
  none of its bad emails. Someone had already tried to hide it by adding
  it to `.gitignore`, which does nothing to an already-tracked file.
  Recoverable from git history if the *subject list* is ever wanted; the
  emails are not.
- **Stale corpus pages** — COVID-era `/libraryhealthy/*`, the closed Amos
  Music Library's location page, the dated news archive
  (`/YYYY-MM-DD-slug`, 398 chunks) and the 2021–2024 annual goal
  documents. All tombstoned (reversible with
  `scripts/tombstone_by_url_prefix.py --undelete`).

## What is *intentionally* still in code

**Eight people are named in hardcoded answers**, all in
`new_orchestrator.py`. Six of those answers state an email; two name the
person and send the patron to a page for contact details. These are
**functional specialists**, not subject-liaison data — they answer
questions the lookup path gets wrong. Changing one needs a deploy; that's
the accepted trade for reliability.

Every row below was checked against the `Librarian` roster on
**2026-07-28**:

| Named in | Person | Email in code | Roster check |
|---|---|---|---|
| MakerSpace answer | Sarah Nagle | `pricesb@` | ✅ active, email matches |
| MakerSpace answer | Lori Chapin | `pheanila@` | ✅ active, email matches |
| MakerSpace answer | Lindsey Masters | `masterlr@` | ✅ active, email matches |
| MakerSpace answer | John Williams | `williajc@` | ✅ active, email matches |
| MakerSpace answer | Nathan Hall | `hallnj3@` | ✅ active, email matches |
| Archivist answer | Jacky Johnson | `johnsoj@` | ✅ active, email matches — but roster spells her **Jacqueline** (see below) |
| Scholarly-comm answer | Carla Myers | — | ✅ active (`myersc2@`) |
| Gov-docs answer | Jenny Presnell | — | ✅ active (`presnejl@`) |

**Barry Zaslow was never hardcoded.** An earlier version of this page
said he was; that was wrong. His name appeared only in a code *comment*
explaining why denylisting the closed Amos Music Library's page doesn't
break music questions. The comment no longer names him — whoever holds
the role is resolved through the normal liaison lookup, so a staffing
change needs no code edit. ("Who is the music librarian?" still answers
correctly, from the LibGuides API.)

Don't grow this list: if it's subject-liaison data, it belongs in
`LibrarianSubject`.

### Nicknames — solved with a data column, not code

`Librarian.name` is **what the bot says**. `Librarian.alternateName` is a
second spelling of the same person that the bot **accepts when matching
and never speaks**. Nicknames are not middle names — no normalization
gets from "Jacky" to "Jacqueline" — so this column is the only place they
can live.

It works in **both directions**, which is the whole point:

| Asked | Bot says | Why |
|---|---|---|
| Jacky Johnson | **Jacqueline Johnson** | formal in `name`, nickname in `alternateName` |
| Andy Revelle | **Andrew Revelle** | same |
| Eric Yarnetsky | **Jerry Yarnetsky** | reversed — his formal first name is Eric, but everyone including him uses Jerry, and the operator's rule is that the bot must **not** display "Eric", so `name` is Jerry and the formal spelling is the alternate |

Set with `ai-core/scripts/set_alternate_names.py` (idempotent, has
`--dry-run`). Add a colleague there rather than in code.

**Hazard to know about:** three scripts write `Librarian.name` —
`sync_librarians_from_csv.py`, `sync_staff_directory.py`, and
`populate_librarian_subject_mapping.py`. None of them know about
`alternateName`, so they will not erase it, but one **could** overwrite
`name` itself from an upstream source. If Jerry ever starts showing up as
"Eric", that is what happened: re-run the script above. (Those three are
themselves overlapping copies of the same job and should be reduced to
one — not yet done.)

## Subject matching: words, not character distance (2026-07-28)

The LibGuides lookup accepted the closest subject name by
Damerau-Levenshtein distance at a **0.45** threshold — 45% of characters
aligning. On the live liaison list that silently swapped the subject and
then answered with **that** subject's librarian, reporting success:

| Patron asked | Matched | Bot answered with |
|---|---|---|
| Botany | **Accountancy** | the Business Librarian's email |
| Chinese | **Business** | the Business Librarians |
| Data Science | **Political Science** | the Humanities Librarian |
| Paper Science and Engineering | **Computer Science and Software Eng.** | wrong liaison |

**No threshold can fix this.** The tightest genuine typo we must keep,
`biolgy` → `Biology`, scores **0.857**. The worst wrong match we must
reject, `paper science and engineering` → `computer science and software
engineering`, scores **0.844** — higher than several real typos, purely on
a shared tail.

So admission is now a **word-level** decision
([subject_match.py](../ai-core/src/tools/subject_match.py)), the same
discipline as person names: no character-soup matching across different
words. A match is real if the names share the same words, one is a
whole-word subset of the other, they share a **distinctive** word, the
whole string is a genuine typo (≥0.85), or the head words share a 6-char
stem (`Accounting` ~ `Accountancy`).

"Distinctive" is **derived from the candidate list**, not hand-written: a
word appearing in 3+ subject names can't prove two subjects are the same.
On the current list that yields `{and, american, business, engineering,
science, studies}` — which is exactly why *Data Science* / *Political
Science* is rejected.

This also **admits** matches the old threshold wrongly rejected —
`Kinesiology` scores only 0.32 against `Kinesiology, Nutrition, and
Health` but is a whole-word subset of it — and fixed two answers outright:
*Paper Science and Engineering* now resolves to `Chemical, Paper, and
Biomedical Engineering`, and *Art and Architecture History* to the Art
librarian instead of the Humanities one. A rejection now produces "no
liaison listed for that, here is the directory" instead of a confident
wrong name.

## The same bug, three times: substring matching (2026-07-28/29)

Three separate wrong-person defects turned out to be one root cause —
**matching fragments of text instead of whole words.** Recording it here
because it will be tempting again:

| Where | What it did |
|---|---|
| Person names | `"roger a justus"` contains `"a"`, so **Krista McDonald** matched **Roger Justus** and the bot gave out his email |
| Subject names | `"botany"` scored 0.45 against `"Accountancy"`, so Botany answered with the **Business Librarian** |
| Subject aliases | `"digital collections"` contains `"ita"`, so it resolved to **Italian** and answered with the Humanities Librarian |

The alias case was the worst, because the table holds 56 course-code
abbreviations (`cs`, `ee`, `the`, `ita`, `art`) and a bare substring test
put every one of them inside ordinary English:

```
"the reserve desk"    -> 'the' -> Theater
"meeting rooms"       -> 'ee'  -> Electrical and Computer Engineering
"quarterly reports"   -> 'art' -> Art
"start a paper"       -> 'sta' -> Statistics
"relevant databases"  -> 'rel' -> Religion
```

Each then had a real librarian's name and email attached. Which one you
got depended on **dict insertion order**, so an unrelated edit could
change the answer.

The fix is the same discipline in all three places: **compare words, not
character runs.** For aliases specifically, word boundaries alone are not
enough — `"the"` *is* a word in `"the reserve desk"` — so a match inside a
phrase must also be **≥5 characters**; anything shorter is a code that only
names a subject when it is the entire query. Longest alias wins, which also
removes the dict-order dependency. `find_subject_by_course_code` had the
same flaw (it read the first 2–4 letters of *any* string) and now requires
the whole argument to look like a course code.

## Regional campuses: label, don't hide (option C, 2026-07-28)

**Operator decision:** when a subject has liaisons on more than one
campus, name them **all**, each labelled with their campus, the student's
own campus first.

The old rule dropped any liaison outside the asked campus. That looked
safe and wasn't: a **Middletown** student asking about Nursing got
**nothing**, because the only regional nursing liaison is based at
Hamilton and the Oxford specialist was filtered out for the same reason.
The genuinely unsafe outcome — naming an off-campus person as "your
librarian" — is avoided by **stating the campus**, not by hiding the
person.

```
Hamilton student, Nursing:
  Your subject librarians are Krista McDonald at Hamilton
  (mcdonak@miamioh.edu); Ginny Boehme at Oxford (boehmemv@miamioh.edu).
  Any of them can help; the one on your campus is usually easiest to
  meet in person.

Middletown student, Nursing:
  There isn't a librarian based at Middletown listed for this subject.
  The subject librarians are Krista McDonald at Hamilton and Ginny
  Boehme at Oxford, who support students on every campus.
```

**The regional data already existed** — in LibGuides, not in our DB.
`LibrarianSubject` has zero regional rows, but the LibGuides accounts API
shows regional liaisons with real subject assignments under the
**regional programme names**:

| Librarian | Campus | Subjects in LibGuides |
|---|---|---|
| Krista McDonald | Hamilton | Civic and Regional Development, Community Arts, **Engineering Technology**, Liberal Studies, **Nursing**, Psychological Science |
| Jennifer Hicks | Middletown | Applied Biology, **Criminal Justice**, Health Communication, Liberal Studies, Psychological Science |
| John Burke | Middletown | Commerce, Community Arts, Information Technology |
| Mark Shores | Hamilton | Appalachian Studies, Applied Social Research, Commerce, Communication Studies, Criminal Justice, … |

Three things had to be fixed before that data could reach a student:

1. **Aliases were overriding exact matches.** "Engineering Technology" is
   Krista McDonald's subject verbatim, but the alias map rewrote it to
   "Electrical and Computer Engineering" and answered with an Oxford
   librarian. Same for "Psychological Science" and "Criminal Justice" —
   *precisely the regional programme names*, so the alias layer was
   defeating regional coverage exactly where it was scarcest. The user's
   own wording is now queried **first**; aliases remain the fallback for
   wording the API can't match ("chem", "BIO 203"). Safe only because
   admission is now word-level.
2. **Campus enrichment matched on email alone.** Miami issues two
   addresses per person — a `firstname.lastname@` alias and a
   `lastname+initials@` primary — and LibGuides and the roster don't
   always pick the same one. Mark Shores is `mark.shores@` in LibGuides
   and `shoresml@` in the roster, so he came back with no campus and the
   answer named him with no location at all. Now falls back to the name.
3. **"I study X, who is my librarian?" ignored the X.** The guard matched
   "studying" but not "study", so the student got the generic "tell me
   your subject" reply after already saying it. Anchored to a pronoun —
   a bare `study\s+\w` would swallow "I need a study room".

## The staff CSV is the roster's source (2026-07-29)

The operator's HR export (`staff-members.csv`, **not** in git — it holds
personal data) is authoritative for who works here. Run
`scripts/reconcile_staff_from_csv.py` after every refresh; it is
idempotent and has `--dry-run`.

It settled four things the other sources couldn't:

1. **Who is on the roster.** A row with a past `last-date` is off it. A
   future `start-date` is **included** — an incoming colleague should be
   findable before their first day. The table was carrying **26 rows the
   CSV doesn't have**: 21 people absent from it entirely, 1 with a recorded
   departure date, 3 duplicate rows, and 1 more. All **deleted**, not
   deactivated (see below). The table is now **74 rows, all current,
   exactly matching the CSV**, with no history left behind.
2. **The two-address problem.** Miami issues two addresses per person: a
   `firstname.lastname@` alias and a `uniqueid@` primary
   (`aaron.shrimplin@` / `shrimpak@`). Both deliver, different systems
   picked different ones, and the roster grew a second row per person —
   always the one with no title. The CSV's `email` column decides. Active
   duplicates: **4 → 0.**
3. **Titles.** Rows with no title: **19 → 0.**
4. **Liaison duties.** The `liaison` column is the operator's own subject
   assignment, and 71 of its 77 entries matched `Subject` exactly. The 6
   that didn't are now created (one real subject the table was missing,
   plus five new service areas).

**The name we display is `first-name`, not `legal-first-name`.** Fifteen
colleagues go by something other than their legal first name, and for at
least one the difference reflects a name change — printing the legal name
would out them. `legal-first-name` is deliberately **not** copied into
`alternateName` either: that column exists so a *patron's* wording finds
the right person, and patrons don't type colleagues' legal names.

### The bot never says someone has left

**Operator instruction 2026-07-29.** Rows absent from the CSV are
**deleted outright**, and the answer for an unknown name says only:

> I don't have a listing for *X* in the Libraries staff directory. You can
> search the directory yourself, or ask a librarian through Ask Us and
> they can point you to the right person.

An earlier version kept departed rows with `isActive=False` so the bot
could say *"that person may no longer be with Miami University
Libraries"*. That was wrong on two counts: the bot has **no standing** to
characterise anyone's employment, and it **cannot actually know** — a gap
in the roster is not a resignation, and the person may be on leave, newly
hired, or not library staff at all. The hardcoded `_DEPARTED_STAFF` list
is gone too; nobody's departure is recorded in source any more.

What still matters is that this answer is **deterministic**. Without it the
turn falls through to the synthesizer, which composes from crawled staff
pages and would happily reconstruct contact details for someone the roster
no longer carries. Tests assert both halves: the name is stated, and the
words "no longer", "left", "departed", "former", "resigned" and "used to"
appear nowhere in the answer.

## Known gaps (need operator decisions, not code)

1. **`LibrarianSubject` covers 67 of 734 subjects (9%)**, and **zero**
   of the 108 regional (`- HC` / `- MC`) variants. Most subject answers
   therefore come from the live LibGuides API, which the operator can't
   edit and which can't be campus-scoped. Filling this table is the
   single highest-value data task.
2. **`Subject` last changed 2026-01-06** for the bulk of its rows.
3. **Subjects can be left without a liaison when someone leaves.** The
   reconciler drops a departing colleague's `LibrarianSubject` links along
   with their row, which is correct — a stale link is how a former
   colleague keeps being named as a subject's contact — but it does not
   reassign the subject. After any departure, check which subjects lost
   their only liaison and set the replacement in the CSV's `liaison`
   column. (Names deliberately not listed here: this page is shared, and
   who has left is not the bot's business to publish.)
4. **12 subjects where MyGuide and Primo name different librarians** with
   no overlap — several are Oxford-vs-regional and resolve by labelling
   the campus; the rest need a human call.
5. `MYGUIDE_API_URL` points at **myguidedev** — only the ingest script
   reads it, but the next import would pull from a dev host.

The operator's review snapshot backing items 1–4 is archived at
[reference/2026-07-28-subject-librarians-review.xlsx](./reference/2026-07-28-subject-librarians-review.xlsx).
It is a **point-in-time export, read by no code** — don't treat it as a
source.
