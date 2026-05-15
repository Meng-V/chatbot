# Canonical truth: Makerspaces across Miami University Libraries

**Date captured**: 2026-05-14
**Sources** (verbatim verified):
  - <https://libguides.lib.miamioh.edu/create/makerspace/home> (King)
  - <https://libguides.lib.miamioh.edu/middletown_tec_lab/home> (Middletown)
  - <https://www.ham.miamioh.edu/library/> (Hamilton — confirmed absent)

**Why this doc exists**: an earlier draft of the gold eval set and
the plan's §7 featured-services section both assumed there is only
ONE makerspace at Miami (King Library, Oxford), and that "Middletown
does not have a MakerSpace." **This is wrong.** Middletown has its
own makerspace under a different name — the TEC Lab ("Tinker, Envision,
Create"), founded Fall 2014, located inside Gardner-Harvey Library.

A user asking "is there a makerspace at Middletown?" should receive
"yes — the TEC Lab" with the LibGuide URL, NOT a refusal that points
them to Oxford.

---

## TL;DR

| Campus / Library | Makerspace? | Name | URL |
|---|---|---|---|
| **Oxford / King Library** | **Yes** | The Makerspace | <https://libguides.lib.miamioh.edu/create/makerspace/home> |
| **Middletown / Gardner-Harvey Library** | **Yes** | TEC Lab Makerspace (Tinker, Envision, Create) | <https://libguides.lib.miamioh.edu/middletown_tec_lab/home> |
| **Hamilton / Rentschler Library** | No | — | — |
| **Oxford / Wertz Art & Architecture** | No (but is the Art library, not a fabrication space) | — | — |
| **Oxford / Special Collections** | No (archival; not a creation space) | — | — |
| **Middletown / SWORD** | No (depository) | — | — |

---

## King Makerspace (Oxford)

URL: <https://libguides.lib.miamioh.edu/create/makerspace/home>

- **Location**: King Library, **3rd floor, room 303**.
- **Equipment** (per the official "What's Available" list referenced
  on the page):
  - 3D printers
  - Laser cutter/engravers
  - Sewing/embroidery machines
  - Digital cutters
  - Additional maker equipment (full list lives on the LibGuide)
- **Hours** (verbatim):
  - **Regular semester**: Mon-Fri 9am-5pm; Wed-Thu until 7pm; Sun noon-4pm
  - **Finals week**: Mon-Fri 9am-5pm
  - **Summer**: Mon-Fri 9am-4pm
- **Who can use it** (verbatim): "Everyone at Miami can use the
  Makerspace" — students, faculty, staff. Public access not addressed.
- **Access requirements** (verbatim, two-step):
  1. "Fill out and sign the Makerspace Liability Waiver"
  2. "Make an appointment to use a machine" via the reservation system
- **Cost**: no fees mentioned for equipment use.
- **Contact**:
  - Email: `create@miamioh.edu`
  - Phone: (513) 529-2871
  - Faculty inquiries: Sarah Nagle (Creation and Innovation Services Librarian)
- **Out-of-stock note** (verbatim, captured 2026-05-14, may rotate):
  "Currently out of button supplies of all sizes; restocking begins
  Fall Semester."

---

## Middletown TEC Lab Makerspace

URL: <https://libguides.lib.miamioh.edu/middletown_tec_lab/home>

- **Name decoded**: "TEC" stands for **Tinker, Envision, Create**.
  Described verbatim as: "The TEC Lab Makerspace was founded as a
  place for you to Tinker, Envision, and Create!"
- **Founded**: Fall 2014. Currently celebrating its 10th anniversary
  per the page.
- **Location**: Inside **Gardner-Harvey Library**, 4200 N. University
  Blvd., Middletown, OH 45042. Two rooms across two levels:
  - **TEC Lab** — Room **125**, **upper level**
  - **TEC SPACE** — Room **014**, **lower level**
- **Equipment in the TEC Lab (upper level)** (verbatim list):
  - Laser engraver/cutter
  - Glowforge laser
  - 3D printers (**staff use only**)
  - Button maker
  - Wood burning pens
  - Craft supplies
  - 3D pens
- **Equipment in the TEC SPACE (lower level)** (verbatim list):
  - Heat press
  - Sublimation printing
  - Perler beads
  - Sewing machine
  - Vinyl cutter — Silhouette
- **Hours**: not directly listed; defers to "the library's open hours"
  (i.e. Gardner-Harvey's hours).
- **Who can use it**: page does not restrict by user category. Anyone
  who signs the user agreement gets access.
- **Access paths** (four, verbatim):
  - Independent use: "Sign our user agreement" to work independently
    "during the library's open hours"
  - Reservations: "Use our online reservation system to book the TEC
    Lab or TEC SPACE for up to 2 hours"
  - Workshops: "Attend one of our workshops"
  - Tours: "Ask us for a tour"
- **Cost** (verbatim): "Equipment in the TEC Lab and TEC SPACE is
  free to use. There may be costs associated with materials used
  with the equipment." Specific material costs are documented on a
  "TEC Lab Charges" subpage.
- **Contact**:
  - Jennifer Hicks — `hicksjl2@miamioh.edu`
  - John Burke — `burkejj@miamioh.edu`
  - Phone: 513-727-3222
  - Chat: AskGHL (Ask Gardner-Harvey Library)
  - Text: 513-273-5360
  - Training: online form to "Schedule a time to learn how to use
    equipment"
- **Mission statement**: <https://www.mid.miamioh.edu/library/TECmission.htm>

### TEC Lab subpages worth indexing

The LibGuide has dedicated pages for each major equipment / service:
Workshops • 3D Printing • 3D Pens • Button Maker • Heat
Press/Sublimation/Vinyl • Glowforge & Full Spectrum Laser
Cutter/Engravers • Graphic Design Software • Poster Printing •
Silhouette Cameo Cutter • TEC Lab Charges.

When the ETL re-runs against a broader URL set including
`libguides.lib.miamioh.edu/middletown_tec_lab/*`, each of these
becomes its own chunk and the bot can answer equipment-specific
questions ("can I sublimate at Middletown?") directly.

---

## Hamilton (Rentschler Library) — explicitly NO makerspace

Confirmed from <https://www.ham.miamioh.edu/library/>. The Rentschler
Library page lists "Audiovisual Resources" as a service but no maker,
fabrication, TEC Lab, design studio, or equivalent creation space.

**The bot's `service_not_at_building` refusal for "MakerSpace at
Hamilton" remains correct.** Just point the user to either King
(Oxford) or Middletown (TEC Lab) as alternatives, depending on
which campus is closer to where they're already standing.

---

## What the bot is allowed to say about makerspaces

Synthesizer prompt should treat the following as facts:

1. **Two makerspaces exist** in the Miami library system, with
   **different names and inventories**:
   - King's "Makerspace" (Oxford, room 303)
   - Middletown's "TEC Lab" (Gardner-Harvey, rooms 125 + 014)
2. **Both are free to use** with appropriate sign-up / agreement.
   Material costs may apply at both.
3. **Hamilton (Rentschler) has neither.** Refer Hamilton users to
   the closer of the two (depending on travel preference).
4. **Equipment is different at each location** — the canonical doc
   above is the truth table. The bot should not claim King-specific
   equipment exists at Middletown or vice versa.
5. **King has a 3D printer for student use; Middletown's 3D printers
   are staff-use only.** This is the most common easily-conflated
   detail.
6. Both have **online reservation systems** and **liability
   waivers / user agreements**.

What the bot must **refuse** to claim without checking:

- Specific real-time equipment availability ("is the Glowforge free
  right now?" — requires live calendar query)
- Current workshop schedule ("what workshops are running next week?"
  — depends on the LibGuide subpages, refresh frequency)
- Specific material costs ("how much for a sheet of acrylic?" —
  links to TEC Lab Charges or King-equivalent page)

---

## URL canonicalization note

The URL `https://www.lib.miamioh.edu/use/spaces/makerspace/` is a
**redirect**, not a content page. It forwards to the LibGuide
canonical: `https://libguides.lib.miamioh.edu/create/makerspace/home`.

The post-processor's URL validator should treat both as valid when
appearing in citations, since clicking either lands the user on the
same canonical content. The gold set currently lists the redirect URL
in some `allowed_urls` fields; bot answers citing the LibGuide URL
are functionally equivalent.

Either:
- (a) treat the two URLs as aliases in the URL validator's allowlist
  (read both into `UrlSeen.url` rows with the same `canonical_url`
  via the ETL's redirect-following), OR
- (b) update the gold set's `allowed_urls` to include both forms

Recommended: (a). The ETL's `fetch()` step already captures the
canonical post-redirect URL; we just need `UrlSeen` to store both
the requested URL and the canonical, and the validator to accept
either.

## Gold-set corrections to file

When updating `ai-core/src/eval/golden_set.jsonl` against this truth:

| Gold case | Current state | Bug + correction |
|---|---|---|
| `xc_makerspace_hamilton_refusal` | Expects refusal | **Correct.** Hamilton has no makerspace. But refusal *copy* should mention BOTH King and TEC Lab as alternatives (not just King). |
| `xc_makerspace_middletown_refusal` | Expects REFUSAL on "Is there a 3D printer at the Middletown library?" | **Wrong.** Middletown DOES have 3D printers (TEC Lab, staff-use only). Change `expected_outcome` to `answer`; bot should point to TEC Lab + note 3D printers are staff-use; update `allowed_urls` to include `https://libguides.lib.miamioh.edu/middletown_tec_lab/home`. |
| `fs_makerspace_hours` | `allowed_urls` is `lib.miamioh.edu/use/spaces/makerspace/` (redirect) | Add `libguides.lib.miamioh.edu/create/makerspace/home` to `allowed_urls`. Both forms reach the same content. |
| Any other case asserting "Middletown does not have a MakerSpace" | Wrong | Bot should answer YES (TEC Lab) with the LibGuide URL |
| Any `cross_campus_comparison` case listing makerspace as "Oxford-only" | Wrong | Correct list: Oxford (King) + Middletown (TEC Lab). Hamilton lacks one. |
| Cases referencing "MakerSpace at every Miami library" | Still wrong, just not as wrong | Two of three campuses; Hamilton doesn't |
| The plan §7 statement "If asked about a MakerSpace at Hamilton or Middletown, refuse" | **Wrong for Middletown** | Refuse only for Hamilton + Wertz + Special Collections + SWORD. Answer with TEC Lab for Middletown. |

---

## Refusal-trigger impact

In `src/synthesis/refusal_templates.py`, the `service_not_at_building`
refusal template currently reads (verbatim):

```
There isn't a {service_name} at the {campus_display} campus
library. {service_name} is at {service_available_at}. For help
at {campus_display}, ask the library staff through Ask Us.
```

The `service_available_at` field for "makerspace" is now:
**"King Library on the Oxford campus OR the TEC Lab at Gardner-Harvey
Library on the Middletown campus."**

When the user resolves to Hamilton scope and asks about MakerSpace,
both alternatives should be offered. Implementation note: this is a
single-string field in `RefusalContext`; we can either:
- (a) write the disjunction into the string at refusal-render time
- (b) extend `RefusalContext` to support multiple alternatives — overkill

(a) is fine for now.

---

## `LibrarySpace.services_offered` impact

When the librarian provides the truth table for the
`services_offered` column (currently empty — blocker for the
cross-campus refusal guard to fire correctly), the makerspace
column must include:

- **king** (Oxford): `makerspace` ✓
- **gardner_harvey** (Middletown): `makerspace` ✓
- **rentschler** (Hamilton): NOT `makerspace`
- **wertz** (Oxford, art & arch): NOT `makerspace`
- **special** (Oxford, archives): NOT `makerspace`
- **sword** (Middletown, depository): NOT `makerspace`

---

## ETL coverage gap

`libguides.lib.miamioh.edu/*` URLs are **not currently in the ETL
sitemap** (per the 396-URL discover snapshot from 2026-05-14). That
means neither makerspace page is indexed in Weaviate today, even
though they're the canonical truth for these questions.

Action: discover.py needs to add `libguides.lib.miamioh.edu` (or at
minimum the two makerspace pages plus their subpages) as a separate
discoverable sitemap or seed list. This is a separate small PR; track
as a follow-up.

Until that lands, the bot would have to either (a) get the chunks via
a manual upsert, (b) refuse with "I can't find that in my index — try
[URL]," or (c) hard-code these two URLs as featured-service pinned
chunks. Option (c) via `ManualCorrection` (action: `pin`) is the
cheapest immediate workaround.
