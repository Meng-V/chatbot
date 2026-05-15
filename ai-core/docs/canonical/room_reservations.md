# Canonical truth: Room reservations across Miami University Libraries

**Date captured**: 2026-05-14
**Source**: <https://www.lib.miamioh.edu/use/spaces/room-reservations/> + each per-building LibCal page linked from there.
**Why this doc exists**: an earlier draft of the gold eval set
(`ai-core/src/eval/golden_set.jsonl`) carried incorrect "expected answers"
about room booking that didn't match what the Miami library website
actually says. This document is the source-of-truth captured directly
from `lib.miamioh.edu` so future evals, prompts, `LibrarySpace.services_offered`
seeds, and synthetic evidence can be grounded on real facts.

When the bot's eventual LibCal API integration lands, this doc gets
*verified* against the live API but stays as a human-readable summary.

---

## TL;DR

| Building | Campus | Bookable rooms? | LibCal URL |
|---|---|---|---|
| **King Library** | Oxford | Yes — most extensive inventory | <https://muohio.libcal.com/reserve/king> |
| **Wertz Art & Architecture Library** | Oxford | Yes — smaller inventory | <https://muohio.libcal.com/reserve/ArtArch> |
| **Armstrong Student Center** | Oxford | Yes — via libraries' LibCal | <https://muohio.libcal.com/spaces?lid=4757&gid=8174> |
| **Rentschler Library (Hamilton)** | Hamilton | Yes — small inventory (≤8 capacity) | <https://muohio.libcal.com/reserve/hamilton> |
| **Gardner-Harvey Library (Middletown)** | Middletown | Yes — full capacity range | <https://muohio.libcal.com/reserve/middletown> |
| **Special Collections & University Archives (King)** | Oxford | No — appointment-only access for archival research | not via room reservation system |
| **SWORD (Middletown depository)** | Middletown | No — not a study space | n/a |

**Universal rules across every bookable location** (per the
`/use/spaces/room-reservations/` page):

- **Max 2 hours per day per user**.
- **May reserve up to 2 weeks in advance**.
- Reservations require a Miami login through LibCal.
- Walk-ins are allowed if a room is currently free, but no walk-in
  guarantee of any specific room.

---

## Per-building detail

### King Library (Oxford)

LibCal URL: <https://muohio.libcal.com/reserve/king>

Room categories visible on the booking page:

| Category | Notes |
|---|---|
| **King Study Rooms (Key Access Only)** | Pick up key at service desk |
| **King Study Rooms (Swipe Accessible)** | Card swipe entry, no desk pickup |
| **Sensory-Friendly Study Rooms (Key Access Only)** | Rooms **022 + 023** (lower level, rear of Instructional Media Center) and **242 + 243** (second floor, behind main staircase) |
| **Large Group Study Rooms** | 9-12 and 13+ capacity tiers |
| **Makerspace Study Room** | Located adjacent to / in the King MakerSpace |

Zoom-equipped rooms (named):
- **112A, 112B, 112C** — equipped with Zoom Room capabilities. Operator
  instruction (verbatim from the page): "Set the TV to HDMI1 and use
  the iPad in the room to control your zoom meeting."

Capacity buckets supported (LibCal filter):
- 1-4 people
- 5-8 people
- 9-12 people
- 13+ people

### Wertz Art & Architecture Library (Oxford)

LibCal URL: <https://muohio.libcal.com/reserve/ArtArch>

Category visible: "Art & Architecture Study Rooms".

Capacity buckets advertised on the booking page: **at least 9-12**
(this filter appears explicitly). Other capacity tiers likely exist
but the static page doesn't enumerate them; the LibCal calendar UI
shows the actual inventory at request time.

**Gold-set correction**: an earlier draft (`rb_wertz_no_bookable`)
asserted Wertz has "no bookable rooms." That is **incorrect**.
Wertz has at least one bookable room in the 9-12 capacity tier and
likely additional smaller rooms.

### Armstrong Student Center (Oxford — NOT a library building)

LibCal URL: <https://muohio.libcal.com/spaces?lid=4757&gid=8174>

Listed on the libraries' room-reservation page because the libraries
manage some Armstrong study space reservations through the same
LibCal instance. Building is NOT operated by the libraries — note
the `lid=4757` (different location id from library buildings).

When users ask about "study rooms on campus" generally, Armstrong is
a valid answer; when they ask about "study rooms at the library,"
it is NOT.

### Rentschler Library (Hamilton campus)

LibCal URL: <https://muohio.libcal.com/reserve/hamilton>

Marked on the page as a **private category** (`Rentschler Study
Rooms is a private category and can only be viewed at this URL`).

Capacity buckets advertised: 1-4 and 5-8 people. **No 9-12 or 13+
tiers visible** — Rentschler does not have large-group rooms.

**Gold-set correction**: any case implying Hamilton has the same
inventory as King is wrong. Hamilton has the smallest bookable
inventory.

### Gardner-Harvey Library (Middletown campus)

LibCal URL: <https://muohio.libcal.com/reserve/middletown>

Category visible: "Gardner-Harvey Study Rooms".

Capacity buckets advertised: 1-4, 5-8, 9-12, 13+ — the **full range**,
unlike Hamilton's restricted set. Gardner-Harvey appears to have a
fuller bookable inventory than Hamilton.

### Special Collections & University Archives (Oxford, in King)

**Not in the room-reservation system.** Access is by **appointment
with the Special Collections staff**, not by self-service booking.
Confirms the `LibrarySpace.services_offered` truth-table for the
`special` building: does NOT include `study_rooms` as a self-service
offering.

### SWORD (Southwest Ohio Regional Depository, Middletown)

**Not a study space.** SWORD is a closed-stack depository for
shared OhioLINK storage. Not in the room reservation system. Should
never appear in a "where can I study?" answer.

---

## What the bot is allowed to say about room booking

Synthesizer prompt should treat the following as facts:

1. **There are 5 building locations** with bookable rooms (King,
   Wertz, Armstrong, Rentschler, Gardner-Harvey). Special Collections
   and SWORD are NOT bookable spaces.
2. **All booking goes through LibCal** — Miami login required.
   `https://muohio.libcal.com/reserve/{building}` is the canonical
   per-building URL.
3. **Universal rules**: 2 hours/day, 2 weeks ahead.
4. **Inventory varies by building**: King has the most; Hamilton has
   the smallest (only ≤8 capacity); Wertz is small; Middletown is
   medium; Armstrong is non-library.
5. **Specific room numbers** (King 022/023/242/243 sensory-friendly,
   King 112A/B/C Zoom rooms) are real and citable.

What the bot must **refuse** to claim without live LibCal data:

- "Room X is available right now" — requires live API call
- "There's a room with capacity exactly N free at time T" — same
- "This room has whiteboard / monitor / Mac / PC" — equipment details
  are not surfaced on the static room-reservation page; only via
  the LibCal calendar UI per-room. Until the API integration lands,
  the bot can say "many King study rooms have whiteboards and screens"
  in general but cannot promise specific equipment in a specific room.

---

## Gold-set corrections to file

When updating `ai-core/src/eval/golden_set.jsonl` against this truth:

| Gold case ID | Current state | Correction |
|---|---|---|
| `rb_king_4_people_whiteboard` | `allowed_urls` includes `/use/spaces/study-rooms/` (404) | Replace with `https://www.lib.miamioh.edu/use/spaces/room-reservations/` AND `https://muohio.libcal.com/reserve/king` |
| `rb_wertz_no_bookable` | `expected_answer` says Wertz has "limited bookable rooms" | True but expand: Wertz HAS bookable rooms; cite `https://muohio.libcal.com/reserve/ArtArch` |
| `rb_rentschler_tomorrow` | (verify URL field) | Should cite `https://muohio.libcal.com/reserve/hamilton` + the universal 2-hour / 2-week rules |
| `rb_gardner_harvey` | (verify URL field) | Should cite `https://muohio.libcal.com/reserve/middletown` |
| Any case claiming "no rooms at X" | Verify | Special Collections + SWORD are correct refusals; **all other library buildings have rooms** |

---

## What's still unknown (parked for LibCal API integration)

When the user provides write access to LibCal, this section becomes
the integration checklist:

1. **Per-room metadata** — current equipment lists per room, capacity
   per room (not per filter bucket), accessibility notes.
2. **Live availability** — "is room X free now?" requires LibCal's
   availability endpoint.
3. **Reservation submission** — letting the bot book on the user's
   behalf is an Op-2 / capability-scope decision the librarians have
   to sign off on. Plan §7 notes the action-vs-guidance distinction:
   the bot should POINT users to LibCal, not submit reservations.

Until then, the bot should answer at the granularity captured above
and let users complete the actual booking on LibCal.
