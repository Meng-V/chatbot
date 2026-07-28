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
| Who works here (name, email, phone, title, campus) | **Postgres `Librarian`** | `scripts/ingest_myguide.py` |
| What subjects exist (+ course / dept / major codes) | **Postgres `Subject`** + its code tables | same ingest |
| Which librarian covers which subject | **Postgres `LibrarianSubject`**, with the **live LibGuides API** as fallback | ingest / LibGuides |
| Live hours, room availability | **LibCal API** — never cached, never crawled | n/a (live) |
| Page content, policies, guides | **Weaviate corpus** (ETL'd website) | `scripts/etl/` |
| Answers the operator has hand-fixed | **Postgres `ManualCorrection`** | `/admin/corrections/view` |
| Staff who have LEFT | `_DEPARTED_STAFF` in `new_orchestrator.py` | edit + deploy |

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

## Known gaps (need operator decisions, not code)

1. **`LibrarianSubject` covers 67 of 734 subjects (9%)**, and **zero**
   of the 108 regional (`- HC` / `- MC`) variants. Most subject answers
   therefore come from the live LibGuides API, which the operator can't
   edit and which can't be campus-scoped. Filling this table is the
   single highest-value data task.
2. **`Subject` last changed 2026-01-06** (~7 months).
3. **60 subjects lost their only librarian** to the July departures
   (Jaclyn Spraetz, Nate Floyd) and more will follow Alia Wegner's.
4. **12 subjects where MyGuide and Primo name different librarians** with
   no overlap — several are Oxford-vs-regional and resolve by labelling
   the campus; the rest need a human call.
5. **Duplicate roster row:** Erica Freed has two `Librarian` rows —
   `freede@` (active) and `freedea@` (inactive). Lookups filter on
   `isActive`, so answers are correct today, but the stale row is what
   a hand-written script had wired up (see below).
6. `MYGUIDE_API_URL` points at **myguidedev** — only the ingest script
   reads it, but the next import would pull from a dev host.

The operator's review snapshot backing items 1–4 is archived at
[reference/2026-07-28-subject-librarians-review.xlsx](./reference/2026-07-28-subject-librarians-review.xlsx).
It is a **point-in-time export, read by no code** — don't treat it as a
source.
