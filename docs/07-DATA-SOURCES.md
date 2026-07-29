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
| Page content, policies, guides | **Weaviate corpus** (ETL'd website) | `scripts/etl_watch.py` weekly → librarian signs → `run_etl --phase apply` |
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

## Keeping the corpus fresh (2026-07-29)

The corpus had been frozen at **2026-05-14** for two and a half months. Not
because the ETL was broken — because it is a **two-phase gated** pipeline
(`prepare` → a librarian signs → `apply`) and **nobody was running
`prepare`**. No diff, no signature, no refresh. The bot answered from a May
snapshot of the website.

Two things were needed, and neither was "run the ETL":

**1. The diff had to say something.** `prepare` skipped the upsert step
wholesale, so every diff reported `new: 0, changed: 0, tombstoned: 0`
however far the site had moved. **The gate was asking for a signature on an
invisible change.** The dry run now previews against the *live* collection —
one bulk read of `{uuid: content_hash}` plus in-memory comparison, ~9
seconds, no API spend, no writes. Today's real numbers:

```
Chunks crawled                     20,068
New or rewritten                      693
Unchanged                           19,375
No longer produced by the crawl        852
```

> **Reading it.** `chunk_id` is `hash(url, position, content_hash)`, so
> **edited text never shows as "changed"** — it appears as a new chunk and
> orphans the old one. `changed` is structurally always 0. Read *new* and
> *no longer produced* together: they are the size of one rewrite, not two
> events. The diff report now says this in prose, because "0 changed" reads
> as "nothing changed", which is the opposite of the truth.

**2. Someone had to be told.** `scripts/etl_watch.py` runs `prepare` weekly
(Mondays 06:10) and emails the operator **only when something changed** — so
a message in the inbox always means there is something to look at. It never
applies anything; the signature gate is untouched.

A full prepare is ~410 fetches of our own public pages, ~25 seconds, **$0.00**.

### Cleaned up 2026-07-29

- **Three orphaned Weaviate collections** from abandoned May runs —
  `Chunk_vv20260517_1629` (4,596), `Chunk_vv20260517_1702` (20,335) and
  `Chunk_vv20260518_0124` (2,799), **27,730 chunks** — deleted. The
  20,335-chunk one was *larger* than what serves, so a run had finished and
  was never promoted. Weaviate's volume went 2.13 GB → 919 MB.
- **`LibGuideSubject`** — dropped. It modelled the same subject↔guide
  relationship as `SubjectLibGuide`, with a proper foreign key instead of a
  guide-name string — arguably the better design, but never adopted: **0
  rows, read by nothing**, and written only by `sync_libguides.py`, which
  read the *live* table and wrote the dead one. `SubjectLibGuide` (587 rows)
  is what `real_backends` serves from and `ingest_myguide.py` owns.
- **`data/raw`** (163 MB fetch cache) — cleared. It regenerates, and now
  expires, so it is safe to delete any time.

The classifier embedding cache (`data/eval/classifier_embeddings.json`,
339 MB) was **kept** on the operator's instruction: it is a cache, but
rebuilding it costs embedding spend.

Also: **Hamilton publishes no sitemap** (`www.ham.miamioh.edu/sitemap.xml`
→ 404), so that campus is crawled from a short hand-curated seed list in
`scripts/etl/config.py`. Middletown's sitemap is a 2,487-entry *regional*
sitemap with zero library URLs, which the host filter correctly discards.
Only Oxford is genuinely sitemap-driven (395 URLs).

## The box is the constraint (2026-07-29)

Worth recording because it looked like "AWS jitter" and wasn't. During an
eval run everything slowed to a crawl; one judge call took **200 seconds**.
Measured rather than assumed:

| Checked | Result |
|---|---|
| CPU steal time | **0** — no hypervisor contention, so not AWS |
| Network to OpenAI | TLS 16–23 ms, first byte 0.4–1.0 s — healthy |
| OpenAI responses | **7× 429**, 3× 504, 2× 503, 2× 502, 2× timeout — upstream |
| Memory | **OOM killer fired twice** |

This is a **t4g.medium: 2 vCPU, 4 GB**. With the service (~1 GB), an eval
(~750 MB), Weaviate (~400 MB) and tooling resident, it ran out.

**The dangerous part was not the slowness.** At that moment `uvicorn` had
the **highest `oom_score` on the machine (779)** — first in line to be
killed — and the unit had `OOMPolicy=stop`, so systemd would have left it
**down**. A silent outage, discoverable only by someone noticing the bot
was gone.

Fixed in `/etc/systemd/system/chatbot.service` (copy kept at
`ai-core/docs/chatbot.service.reference`):

```
OOMScoreAdjust=-500   # the kernel picks a different victim first
OOMPolicy=continue    # an OOM-killed child does not stop the unit
Restart=always        # and if the main process dies, it comes back
```

Verified: `oom_score` 779 → **442** (now the lowest of the large
processes), and `kill -9` on the main pid brought a new one up
automatically.

Use `scripts/run_eval_safely.sh` for eval runs — it caps the eval at
1.5 GB via `systemd-run`, so **the eval dies before the machine does**.

**For the launch-readiness monitoring work:** liveness checks are not
enough. Watch **memory and OOM events** — the failure mode here was the
service being killed and staying dead, which a "is the port open" probe
only catches after the fact.

## Regional liaisons now survive an outage (2026-07-29)

The operator filled the CSV's `liaison` column for the four regional
librarians, so their duties finally live in Postgres as well as LibGuides:
**`LibrarianSubject` 70 → 98 rows, regional 0 → 19.**

| Librarian | Campus | Subjects |
|---|---|---|
| Krista McDonald | Hamilton | Civic and Regional Development, Community Arts, Engineering Technology, Liberal Studies, Nursing, Psychological Science |
| Mark Shores | Hamilton | Appalachian Studies, Applied Social Research, Commerce, Communication Studies, Criminal Justice |
| Jennifer Hicks | Middletown | Applied Biology, Criminal Justice, Health Communication, Liberal Studies, Psychological Science |
| John Burke | Middletown | Commerce, Community Arts, Information Technology |

**Loading the data revealed that the fallback it was meant to feed did not
work.** Three defects, each found by testing the outage rather than assuming:

1. **An API failure aborted the whole lookup.**
   `_lookup_by_subject_via_libguides` raised `ToolError` on any exception,
   which returned before the Postgres path ran. A Springshare outage took
   out *every* subject question — including the ones our own table could
   answer. It now logs and degrades.
2. **The DB path dropped the user's own wording.**
   `terms0 = resolved if resolved else [subject]` discarded the raw term
   whenever an alias existed, so "Criminal Justice" was rewritten to
   "Criminology" and the DB never looked for the subject Jennifer Hicks is
   linked to. Same defect already fixed on the API path; raw wording is now
   queried first here too.
3. **The `- HC` / `- MC` campus variants were never queried at all.**
   The suffix map was keyed lower-case (`"middletown"`) while `campus` at
   that point is title-cased (`"Middletown"`), so `campus in _SUFFIX` was
   **always False**. All 108 campus-variant `Subject` rows the operator had
   created were unreachable by construction.

Verified by stubbing the LibGuides tool to raise: **7 of 7** regional and
Oxford subject lookups now answer from Postgres during a total outage, and
the healthy path is unchanged.

**Honesty is preserved in both directions.** If the API is unreachable *and*
the subject is not in the local table, the lookup raises rather than
returning empty — "Miami has no librarian for that" is a claim we cannot
support during an outage. A genuine miss with a *healthy* API still returns
an empty list, because that one is a fact.

## How you know the data is still good (2026-07-29)

The operator's real worry was not any single table — it was **not knowing
whether something had quietly gone wrong**. Reading 740 rows by hand does
not fix that; it moves the worry. `scripts/data_health.py` runs daily
(06:40) and **emails only when something needs action**, so a quiet inbox
means every check passed.

| Check | Catches |
|---|---|
| roster vs CSV | someone joined or left and nobody ran the reconciler |
| duplicate people | the two-address problem growing back |
| stale liaison links | a departed colleague still named as a subject contact |
| **refused real questions** | actual patrons who asked and got nothing — shows the QUESTION, not the bot's refusal text |
| corpus freshness | the weekly ETL diff is produced but never signed |
| dependencies | LibGuides / LibCal / OpenAI / Weaviate / Postgres |
| **memory + OOM kills** | today's near-miss, where the service was first in line to be killed |

### The measurement that replaced a bad one

"**664 of 740 subjects have no liaison (9% coverage)**" was reported as the
top data gap. **That framing was wrong and it generated anxiety instead of
information.** Most of those rows are registrar program codes and
administrative units — `Provost`, `Degree Audit Reporting System`,
`Assist VP Student Leadership` — which are not supposed to have a librarian.

The honest measurement is against **real traffic**. Of the 35 subjects
patrons actually asked a librarian question about across 4,432 messages, the
bot answers **32**. The three misses are a typo (`makerspce`), a test
placeholder (`underwater basket weaving`), and a pronoun (`my major`, from
"who is the librarian for my major"). **There is no subject-data gap.**

A 150-line "subject gaps for review" file was produced from my own guess at
which registrar strings looked academic; checked against real questions, 95%
of it was noise, so it was deleted. The health check now reports what real
users were refused instead — a list that is short, current, and always
worth reading.

## Why the ETL apply still has not run (2026-07-29)

Three attempts, three distinct bugs, each one hidden behind the previous:

**Attempt 1 — OOM-killed at a 1.2 GB cap.** `embeddings = pipeline.embed(all_chunks)`
embedded the *entire* corpus before upserting anything. 20,068 chunks × 3072
boxed Python floats ≈ **1.5 GB**. Fixed by slicing: embed 500 → upsert 500 →
discard, so peak is one slice (~37 MB). Verified by re-running under an
**800 MB** cap — tighter than the one that had just failed — and it held.

**Attempt 2 — died 2,664 chunks in, and NOT from memory.** I assumed memory
again and was wrong: Weaviate was never OOM-killed (`OOMKilled=false`,
`Restarts=0`, no kernel OOM at that time). The real cause was a retry-strategy
bug in `etl_adapter.upsert_chunk`:

```
connection drops mid-insert  ->  code treats ANY error as "wrong verb"
                             ->  switches to `replace`
                             ->  500 "no object with id" (the insert never landed)
                             ->  whole run dies
```

Two failure kinds need two responses, and they were conflated:

| Failure | Outcome | Correct response |
|---|---|---|
| transport (disconnect, timeout, 502/503/504) | **unknown** | retry the **same** verb, with backoff |
| semantic (already exists / no such object) | known: wrong verb | **switch** verbs |

Note the trap in classifying them: the semantic error's message *contains
"500"*, so a naive "50x means transient" rule would retry it forever instead
of switching. The classifier tests that string explicitly.

**Still outstanding:** the apply has not completed a full run. What is fixed
is the memory ceiling and the retry logic; whether the corpus writes cleanly
end to end is unproven, and the diff signed at 16:18 is still valid and
unapplied.

### The cost problem this did NOT fix

A real apply embeds **all 20,068** chunks even though only **693** are new —
about **$1.30** and 200 API batches weekly, 96% of it discarded at the dedupe
step. The preview already computes the new/changed set read-only in 9 seconds.

Fixing it properly means either copying the unchanged vectors from the live
collection (needs a vector-read the adapter does not expose) or indexing
incrementally into the serving collection instead of building a fresh
versioned one. **The second changes the promotion model** — versioned
collections exist so eval can run against a new index before the alias swap —
so it is an architecture decision, not a bug fix, and is left for the
operator.

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
