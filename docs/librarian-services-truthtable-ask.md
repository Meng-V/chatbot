# Librarian ask: confirm services-offered per building

This is a 30-minute task. The output unblocks a load-bearing safety
check in the rebuilt chatbot: it stops the bot from telling a
Hamilton or Middletown user that there's a MakerSpace at their
building when there isn't.

**Send to**: TBD (subject lead per building, or program lead who can
delegate). Cc: TBD.
**From**: Meng Qu / qum@miamioh.edu
**Subject**: Quick chatbot accuracy ask — confirm 6 rows of "which
services exist at which library"

---

## What we need

For each of the 6 library buildings, confirm or correct the
services-offered list below. The chatbot uses this as a strict
truth-table: if a service isn't on the list for a building, the bot
**refuses** to answer "does X library have <service>?" rather than
guessing — and points the user to the building that does have it.

This is what prevents the failure we've seen in testing: a Hamilton
user asking "do you have a MakerSpace?" and the bot answering as if
they were in Oxford.

You don't have to fix the list from scratch — just confirm or strike
through. Reply by email or annotate the table inline.

## The 6 rows to confirm

### 1. Edward King Library (Oxford)

- printing
- ill_pickup
- study_rooms
- course_reserves
- research_appointments
- av_production
- makerspace

→ Right? Anything missing? Anything that shouldn't be on the list?

### 2. Wertz Art & Architecture Library (Oxford)

- printing
- ill_pickup
- study_rooms
- course_reserves
- research_appointments

→ Right? (Notably **no** av_production, **no** makerspace — correct?)

### 3. Walter Havighurst Special Collections & University Archives (Oxford)

- rare_books_access
- archival_research
- research_appointments

→ Right? Should ill_pickup / printing be on this list too, or are
those genuinely not offered at this location?

### 4. Rentschler Library (Hamilton)

- printing
- ill_pickup
- study_rooms
- course_reserves
- research_appointments

→ Right? Anything Hamilton-specific we're missing (e.g. tutoring
services, a maker-style space if one exists there)?

### 5. Gardner-Harvey Library (Middletown)

- printing
- ill_pickup
- study_rooms
- course_reserves
- research_appointments

→ Right? Anything Middletown-specific?

### 6. Southwest Ohio Regional Depository — SWORD (Middletown)

- depository_retrieval

→ Right? (SWORD is the storage facility, so this short list is
intentional — but if it offers anything user-facing beyond retrieval,
say so.)

## Service vocabulary (so we're all using the same words)

If you want to add a service that isn't already in the lists above,
pick from this controlled vocabulary so the bot's matching logic
keeps working. If something belongs but isn't in the list, tell me
and I'll add it (it's one line of code).

| ID | What it means |
|---|---|
| `printing` | Self-service printing / pickup at the building |
| `ill_pickup` | Interlibrary Loan pickup point |
| `study_rooms` | Bookable study spaces |
| `course_reserves` | Physical course reserves held here |
| `research_appointments` | One-on-one librarian consultations |
| `av_production` | AV / media production equipment users can check out or use on site |
| `makerspace` | 3D printers, vinyl cutter, sewing, etc. |
| `rare_books_access` | Rare materials available for reading-room use |
| `archival_research` | University archives available for research |
| `depository_retrieval` | Off-site materials retrieved on request |

## What happens after you reply

I update one Python file (`ai-core/scripts/seed_library_spaces_v2.py`),
re-seed the database (idempotent, takes ~5 seconds), and the bot
picks up the new truth-table on the next request. No restart needed.
I'll send a one-line confirmation when it's live.

## Why this is the blocking ask

It's the only Gap-3 item on the rebuild's "10% rollout" checklist
that can't be done by the engineering side alone. Code-wise the safety
check (cross-campus refusal guard) is shipped and tested; what it
needs is for the truth-table behind it to be confirmed by someone who
actually knows the buildings.

Thanks for the 30 minutes.

— Meng
