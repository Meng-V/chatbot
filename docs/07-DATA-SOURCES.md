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
- **Stale corpus pages** — COVID-era `/libraryhealthy/*`, the closed Amos
  Music Library's location page, the dated news archive
  (`/YYYY-MM-DD-slug`, 398 chunks) and the 2021–2024 annual goal
  documents. All tombstoned (reversible with
  `scripts/tombstone_by_url_prefix.py --undelete`).

## What is *intentionally* still in code

Six people are named directly in `new_orchestrator.py` — Sarah Nagle
(MakerSpace), Carla Myers (scholarly communication), Jacky Johnson
(University Archivist), Barry Zaslow (music), plus two liaison examples.
These are **functional specialists the operator verified by hand**, not
subject-liaison data; they answer questions the lookup path gets wrong.
They need a deploy to change — that's the accepted trade for
reliability. Don't grow this list: if it's subject-liaison data, it
belongs in `LibrarianSubject`.

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
5. `MYGUIDE_API_URL` points at **myguidedev** — only the ingest script
   reads it, but the next import would pull from a dev host.

The operator's review snapshot backing items 1–4 is archived at
[reference/2026-07-28-subject-librarians-review.xlsx](./reference/2026-07-28-subject-librarians-review.xlsx).
It is a **point-in-time export, read by no code** — don't treat it as a
source.
