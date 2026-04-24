"""
Seed the v2 LibrarySpace table with the six canonical buildings + the
spaces inside them, matching the plan's Data preparation playbook §8
truth table.

Why a separate v2 seed (rather than extending `seed_library_locations.py`):
  - The plan adds NEW columns (`building_role`, `services_offered`,
    `equipment`, `hours_source`, `source_url`) that the legacy LibrarySpace
    table doesn't have. The legacy table also has a different shape (it's
    nested under Library->Campus, while the plan's LibrarySpace is flat).
  - The legacy seed is still in use by the v1 booking path during the
    rebuild's 8-week rollout. Don't touch it.
  - The v2 table is what the new agent's `lookup_space` tool reads. It's
    the load-bearing truth source for "does the MakerSpace exist at
    Hamilton?" -> NO (and the bot must refuse, not assume).

Run:
    python -m scripts.seed_library_spaces_v2          # idempotent upsert
    python -m scripts.seed_library_spaces_v2 --print  # dump JSON, don't write

This module's `SPACES` constant is the authoritative source. It's
intentionally a pure Python list (not YAML) so a code review of changes
shows up in PRs and a librarian-facing change goes through the normal
deploy path. Adding a new building or service is a one-edit append plus
re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger("seed_library_spaces_v2")


# ---------------------------------------------------------------------------
# Canonical data
# ---------------------------------------------------------------------------
#
# Each row corresponds to one row in the v2 LibrarySpace table. Field
# semantics:
#
#   library         canonical id matching plan §8 (king/wertz/special/
#                   rentschler/gardner_harvey/sword)
#   campus          oxford / hamilton / middletown
#   name            display name librarians use ("King 110", "MakerSpace")
#   building_role   "main_building" - the campus's primary library
#                   "sub_building"  - co-located library on same campus
#                                     (e.g. Wertz on Oxford)
#                   "department"    - a unit inside another building
#                                     (e.g. Special Collections inside King)
#                   "depository"    - storage facility, limited services
#                                     (SWORD)
#   address         street address, used for "where is X" answers
#   phone           main contact line for the building
#   libcal_id       LibCal location id for live hours (string -- LibCal
#                   uses string ids). Null when LibCal doesn't track it.
#   capacity        Total seating capacity if known (rough; for "how big
#                   is X"). Null when unknown / not applicable.
#   equipment       Tags matching MakerSpace equipment list and study-
#                   room equipment lists. ETL chunks may surface these.
#   services_offered  THE TRUTH TABLE for "does this building have X".
#                     If a service isn't here, the bot must refuse rather
#                     than assume parity with Oxford.
#   hours_source    URL to fetch live hours from (LibCal page or library
#                   subpage). Belt-and-suspenders for when the LibCal
#                   API is down.
#   source_url      Canonical lib page describing this building -- the
#                   citation chip target when the bot answers "what is X".


@dataclass(frozen=True)
class LibrarySpaceRow:
    """One row in the v2 LibrarySpace table.

    Immutable so a typo here -> caught at module-load time, not at first
    upsert. Each field maps 1:1 to the Postgres column of the same name.
    """
    library: str
    campus: str
    name: str
    building_role: str
    address: Optional[str]
    phone: Optional[str]
    libcal_id: Optional[str]
    capacity: Optional[int]
    equipment: list[str] = field(default_factory=list)
    services_offered: list[str] = field(default_factory=list)
    hours_source: Optional[str] = None
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# The six buildings (plus Special Collections as an Oxford department)
# ---------------------------------------------------------------------------
#
# Cross-reference with plan §8 "The buildings" table. If you add a row,
# bump the alias table at src/scope/aliases.py too -- otherwise the
# scope resolver won't find it.

SPACES: list[LibrarySpaceRow] = [
    # ------------- Oxford ------------------------------------------------
    LibrarySpaceRow(
        library="king",
        campus="oxford",
        name="Edward King Library",
        building_role="main_building",
        address="151 S. Campus Ave, Oxford, OH 45056",
        phone="513-529-4141",
        libcal_id="8113",
        capacity=1200,
        equipment=[
            "study_rooms", "group_study_rooms",
            "computers", "printers", "scanners",
            "whiteboards", "projectors",
        ],
        # Truth table: King is the flagship -- has nearly everything.
        services_offered=[
            "printing", "ill_pickup", "study_rooms",
            "course_reserves", "research_appointments",
            "av_production", "makerspace",
        ],
        hours_source="https://www.lib.miamioh.edu/about/hours/",
        source_url="https://www.lib.miamioh.edu/about/locations/king-library/",
    ),

    LibrarySpaceRow(
        library="wertz",
        campus="oxford",
        name="Wertz Art & Architecture Library",
        building_role="sub_building",
        address="Alumni Hall, 100 Bishop Cir, Oxford, OH 45056",
        phone="513-529-6638",
        libcal_id="8116",
        capacity=80,
        equipment=[
            "study_tables", "computers", "printers", "scanners",
            "art_books", "architecture_drawings",
        ],
        # Wertz is ART/ARCHITECTURE-focused. No makerspace, no AV
        # production. Course reserves limited to art/arch courses.
        services_offered=[
            "printing", "ill_pickup", "study_rooms",
            "course_reserves", "research_appointments",
        ],
        hours_source="https://www.lib.miamioh.edu/about/hours/",
        source_url="https://www.lib.miamioh.edu/about/locations/art-arch/",
    ),

    LibrarySpaceRow(
        library="special",
        campus="oxford",
        # Officially "Special Collections and University Archives".
        # Common short forms in §8: "Special Collections", "SCUA",
        # "the archives".
        name="Walter Havighurst Special Collections & University Archives",
        building_role="department",  # housed inside King, third floor
        address="King Library, Third Floor, 151 S. Campus Ave, Oxford, OH 45056",
        phone="513-529-3323",
        libcal_id="8424",
        capacity=20,  # reading room only -- by appointment
        equipment=[
            "rare_books_reading_room", "white_gloves",
            "scanning_station", "microfilm_reader",
        ],
        # Special Collections is appointment-only, archival research.
        # No printing, no group study, no AV.
        services_offered=[
            "rare_books_access", "archival_research",
            "research_appointments",
        ],
        hours_source="https://spec.lib.miamioh.edu/home/visit/",
        source_url="https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
    ),

    # ------------- Hamilton ----------------------------------------------
    LibrarySpaceRow(
        library="rentschler",
        campus="hamilton",
        name="Rentschler Library",
        building_role="main_building",
        address="1601 University Blvd, Hamilton, OH 45011",
        phone="513-785-3235",
        libcal_id="9226",
        capacity=180,
        equipment=[
            "study_rooms", "group_study_rooms",
            "computers", "printers", "scanners", "whiteboards",
        ],
        # Rentschler is the Hamilton main library. NO makerspace, NO AV
        # production -- those are Oxford-only. Bot must refuse Hamilton
        # makerspace queries with the campus-specific refusal template.
        services_offered=[
            "printing", "ill_pickup", "study_rooms",
            "course_reserves", "research_appointments",
        ],
        hours_source="https://www.ham.miamioh.edu/library/about/hours/",
        source_url="https://www.ham.miamioh.edu/library/",
    ),

    # ------------- Middletown --------------------------------------------
    LibrarySpaceRow(
        library="gardner_harvey",
        campus="middletown",
        name="Gardner-Harvey Library",
        building_role="main_building",
        address="4200 N. University Blvd, Middletown, OH 45042",
        phone="513-727-3222",
        libcal_id="9227",
        capacity=120,
        equipment=[
            "study_rooms", "group_study_rooms",
            "computers", "printers", "scanners", "whiteboards",
        ],
        # Same shape as Rentschler. NO makerspace.
        services_offered=[
            "printing", "ill_pickup", "study_rooms",
            "course_reserves", "research_appointments",
        ],
        hours_source="https://www.mid.miamioh.edu/library/about/hours/",
        source_url="https://www.mid.miamioh.edu/library/",
    ),

    LibrarySpaceRow(
        library="sword",
        campus="middletown",
        name="Southwest Ohio Regional Depository (SWORD)",
        building_role="depository",
        address="4200 N. University Blvd, Middletown, OH 45042",
        phone="513-727-3296",
        libcal_id=None,  # depository not on LibCal -- request via ILL
        capacity=None,   # storage facility, no public seating
        equipment=[
            "high_density_shelving", "climate_controlled_storage",
        ],
        # Depository has only retrieval-via-request. Items are pulled
        # and routed to the requesting library for pickup.
        services_offered=[
            "depository_retrieval",
        ],
        hours_source=None,  # not a public-access space
        source_url="https://www.lib.miamioh.edu/about/locations/sword/",
    ),
]


# ---------------------------------------------------------------------------
# Self-checks (run at module import to catch typos at the earliest moment)
# ---------------------------------------------------------------------------


_VALID_CAMPUSES = {"oxford", "hamilton", "middletown"}
_VALID_LIBRARIES = {"king", "wertz", "special", "rentschler",
                    "gardner_harvey", "sword"}
_VALID_ROLES = {"main_building", "sub_building", "department", "depository"}


def _self_check(rows: list[LibrarySpaceRow]) -> None:
    """Catch silently-broken rows before they hit Postgres.

    Failures here mean someone added a row with an invalid campus /
    library / role, or duplicated a (campus, library) pair. Both are
    bugs the next caller would hit but with worse error messages.
    """
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if r.campus not in _VALID_CAMPUSES:
            raise ValueError(f"Invalid campus {r.campus!r} on {r.name!r}")
        if r.library not in _VALID_LIBRARIES:
            raise ValueError(f"Invalid library {r.library!r} on {r.name!r}")
        if r.building_role not in _VALID_ROLES:
            raise ValueError(
                f"Invalid building_role {r.building_role!r} on {r.name!r}"
            )
        # (library, campus) must be unique. A library can't be on two
        # campuses.
        key = (r.library, r.campus)
        if key in seen:
            raise ValueError(f"Duplicate (library, campus) = {key}")
        seen.add(key)


_self_check(SPACES)


# ---------------------------------------------------------------------------
# Upsert (idempotent)
# ---------------------------------------------------------------------------


async def seed(*, dry_run: bool = False) -> int:
    """Upsert all SPACES into Postgres v2 LibrarySpace.

    Idempotent: re-running produces no schema-level changes (Prisma
    upsert by (campus, library) primary-key analog). Returns the count
    of rows touched.

    Gated on Prisma being importable. In sandbox / CI without the
    generated client, raises NotImplementedError so the failure is
    obvious rather than silently doing nothing.
    """
    if dry_run:
        logger.info("dry-run: %d spaces would be upserted", len(SPACES))
        return len(SPACES)

    try:
        from prisma import Prisma  # type: ignore
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated. Run `npx prisma generate` "
            "after migrating the v2 LibrarySpace schema, then retry."
        ) from e

    db = Prisma()
    await db.connect()
    try:
        for row in SPACES:
            data = asdict(row)
            # Use (campus, library) as the unique upsert key. Schema
            # should declare @@unique([campus, library]) on the v2 table
            # so this works without a separate id lookup.
            await db.libraryspace_v2.upsert(
                where={"campus_library": {
                    "campus": row.campus,
                    "library": row.library,
                }},
                data={
                    "create": data,
                    "update": data,
                },
            )
            logger.info("upserted %s/%s -- %s",
                        row.campus, row.library, row.name)
    finally:
        await db.disconnect()
    return len(SPACES)


def _print_json() -> None:
    """Dump SPACES as JSON. Useful for review before running migrations
    and for cross-checking the alias table at src/scope/aliases.py."""
    print(json.dumps(
        [asdict(r) for r in SPACES],
        indent=2,
        default=str,
    ))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed v2 LibrarySpace table.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate SPACES + count rows; do not write to Postgres.",
    )
    parser.add_argument(
        "--print",
        dest="print_json",
        action="store_true",
        help="Dump SPACES as JSON to stdout and exit.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.print_json:
        _print_json()
        return 0

    try:
        n = asyncio.run(seed(dry_run=args.dry_run))
        logger.info("done -- %d spaces processed", n)
        return 0
    except NotImplementedError as e:
        logger.error("cannot seed: %s", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LibrarySpaceRow",
    "SPACES",
    "seed",
]
