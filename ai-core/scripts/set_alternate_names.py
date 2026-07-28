"""
Set `Librarian.alternateName` -- the second spelling of a person's name.

WHY THIS EXISTS
    `name` is what the bot SAYS. `alternateName` is another spelling of
    the same human that the bot ACCEPTS when someone asks by name, and
    never speaks. Nicknames are not middle names, so
    src/utils/person_names.py cannot derive them; this column is the only
    place they live.

    It works in both directions, which is the point:

      * `name` formal, alternate is the nickname
            Jacqueline Johnson  <- said       Jacky Johnson  <- accepted
      * `name` is what they go by, alternate is the formal name
            Jerry Yarnetsky     <- said       Eric Yarnetsky <- accepted

IDEMPOTENT. Matches on email (the roster's unique key), reports what it
changed, and touches nothing else. Safe to re-run.

    Run:  .venv/bin/python scripts/set_alternate_names.py [--dry-run]

NOTE FOR WHOEVER ADDS THE NEXT ONE: three scripts write Librarian.name
(sync_librarians_from_csv, sync_staff_directory,
populate_librarian_subject_mapping). None of them know about
alternateName, so they will not erase it -- but one of them COULD
overwrite `name` itself from an upstream source. If Jerry ever starts
displaying as "Eric", that is what happened; re-run this script and see
docs/07-DATA-SOURCES.md.
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from prisma import Prisma

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

# email -> (name we DISPLAY, alternate spelling we ACCEPT)
# Operator-confirmed 2026-07-28.
ALTERNATES: dict[str, tuple[str, str]] = {
    # Goes by Jacky; the bot says her formal name.
    "johnsoj@miamioh.edu": ("Jacqueline Johnson", "Jacky Johnson"),
    # Goes by Andy; the bot says his formal name.
    "revellaa@miamioh.edu": ("Andrew Revelle", "Andy Revelle"),
    # The reverse: his formal first name is Eric, but everyone -- himself
    # included -- calls him Jerry, and the operator's instruction is that
    # the bot must NOT display "Eric". So `name` stays Jerry and the
    # formal spelling becomes the accepted alternate.
    "yarnete@miamioh.edu": ("Jerry Yarnetsky", "Eric Yarnetsky"),
}


async def main(dry_run: bool) -> int:
    db = Prisma()
    await db.connect()
    changed = failed = 0
    try:
        for email, (display, alternate) in ALTERNATES.items():
            row = await db.librarian.find_unique(where={"email": email})
            if row is None:
                print(f"  MISSING  {email} -- not in the roster, skipped")
                failed += 1
                continue

            todo: dict = {}
            if row.name != display:
                todo["name"] = display
            if row.alternateName != alternate:
                todo["alternateName"] = alternate

            if not todo:
                print(f"  ok       {email:26} {row.name}  (alt: {alternate})")
                continue

            was = f"name={row.name!r} alt={row.alternateName!r}"
            if dry_run:
                print(f"  WOULD    {email:26} {was} -> {todo}")
            else:
                await db.librarian.update(where={"email": email}, data=todo)
                print(f"  updated  {email:26} {was} -> {todo}")
            changed += 1
    finally:
        await db.disconnect()

    verb = "would change" if dry_run else "changed"
    print(f"\n{verb} {changed} row(s); {failed} missing.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--dry-run" in sys.argv)))
