"""
Reconcile Postgres `Librarian` / `LibrarianSubject` against the operator's
staff CSV -- the authoritative HR roster.

    Run:  .venv/bin/python scripts/reconcile_staff_from_csv.py [--dry-run]
          [--csv /opt/chatbot/staff-members.csv]

WHY A SCRIPT AND NOT A ONE-OFF
    The CSV is refreshed by the Libraries' own process, so this needs to be
    re-runnable. It is IDEMPOTENT: it computes the difference each time and
    reports what it changed. Run it after every CSV refresh.

WHAT THE CSV IS AUTHORITATIVE FOR
    * who is on the roster       -- a row with a past `last-date` is off it.
                                    A future `start-date` is INCLUDED
                                    (operator instruction 2026-07-29): an
                                    incoming colleague should be findable
                                    before their first day, not after.
    * the name we DISPLAY        -- `first-name` is what they go by, which
                                    is NOT always the legal name. This
                                    matters for dignity, not just style:
                                    at least one colleague's legal first
                                    name differs because of a name change,
                                    and printing it would out them.
    * title, phone               -- `title`, `phone`
    * subject liaison duties     -- `liaison`, a "; "-separated list

WHAT IT IS *NOT* USED FOR
    `legal-first-name` is deliberately NOT copied into `alternateName`.
    That column exists so a PATRON's wording finds the right person, and
    patrons do not type colleagues' legal names. Storing former names
    without being asked is the wrong default. Nicknames that patrons DO
    use (Jacky for Jacqueline) are set by set_alternate_names.py instead.

THE TWO-ADDRESS PROBLEM
    Miami issues two addresses per person: a `firstname.lastname@` alias
    and a `uniqueid@` primary (`aaron.shrimplin@` / `shrimpak@`). Both
    deliver. Different systems picked different ones, so the roster grew a
    second row per person, and the second row had no title. This script
    keeps the row matching the CSV's `email` column and REMOVES the other
    -- one row per human.

REMOVED, NOT DEACTIVATED
    Operator instruction 2026-07-29: rows absent from the CSV are deleted
    outright. An earlier version kept them with `isActive=False` so the bot
    could say "that person may no longer be with the Libraries" -- but that
    is the bot editorialising about someone's employment, which it has no
    standing to do and cannot actually know (a gap in the CSV is not a
    resignation). With the row gone, the bot says only what is true: it has
    no listing for that name. Verified before the first deletion that no
    LibrarianSubject or LibrarianReview rows depended on them.
"""

import argparse
import asyncio
import csv
import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv
from prisma import Prisma

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

from src.utils.person_names import names_match  # noqa: E402

# CSV `library` -> the campus the bot scopes answers by.
_CAMPUS = {
    "king": "Oxford",
    "king library": "Oxford",
    "artarch": "Oxford",
    "hamilton": "Hamilton",
    "middletown": "Middletown",
    # The Southwest Ohio Regional Depository is a shared off-site store,
    # not a campus library. Left unmapped so it never answers a
    # campus-scoped question; the roster row keeps whatever it has.
    "sword": "",
}


def _disp(row: dict) -> str:
    """The name to DISPLAY: what the person goes by, not the legal name."""
    return f"{(row.get('first-name') or '').strip()} " \
           f"{(row.get('last-name') or '').strip()}".strip()


def load_csv(path: str, today: datetime.date):
    """-> (on_roster, off_roster, starting_soon). Second entries dropped:
    one human, one row, even when they serve two campuses.

    `starting_soon` is a subset of `on_roster`, reported separately so the
    run log shows who is new -- they ARE listed, per the operator."""
    on, off, soon = [], [], []
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if (row.get("second-entry-for-person") or "").strip().upper() == "TRUE":
            continue
        if not (row.get("email") or "").strip():
            continue
        last = (row.get("last-date") or "").strip()
        start = (row.get("start-date") or "").strip()
        if last and last <= today.isoformat():
            off.append(row)
            continue
        on.append(row)
        if start and start > today.isoformat():
            soon.append(row)
    return on, off, soon


async def main(dry: bool, csv_path: str) -> int:
    today = datetime.date.today()
    current, departed, future = load_csv(csv_path, today)  # future ⊆ current
    keep_emails = {(r["email"] or "").strip().lower() for r in current}
    # Reason lookup for the run log. "Their last day has passed" and "they
    # are not in this file at all" are different facts and the operator
    # needs to tell them apart -- the first is a recorded departure, the
    # second could just as easily be a gap in the export.
    off_dates = {(r["email"] or "").strip().lower(): (r.get("last-date") or "")
                 for r in departed}

    db = Prisma()
    await db.connect()
    changes = {k: 0 for k in
               ("removed", "added", "titles", "phones", "subjects_made",
                "links_added", "links_removed")}
    try:
        rows = await db.librarian.find_many()

        # --- 1. anyone absent from the CSV comes off the roster ----------
        # Deliberately NOT limited to isActive rows: the point is that the
        # table matches the CSV exactly, so previously-deactivated rows go
        # too. Leaving them behind is what made the bot able to speculate
        # about people's employment.
        for r in rows:
            email = (r.email or "").lower()
            if email in keep_emails:
                continue
            # A second address for someone who IS current still counts as
            # a duplicate row, not a departure -- but either way this row
            # should stop being served.
            twin = next((c for c in current if names_match(r.name, _disp(c))), None)
            if email in off_dates:
                why = f"CSV records a last day of {off_dates[email]}"
            elif twin:
                why = f"duplicate row -- CSV uses {twin['email']}"
            else:
                why = "not in the CSV"
            print(f"  {'would ' if dry else ''}remove      {r.email:32} "
                  f"{r.name:24} ({why})")
            if not dry:
                await db.librarian.delete(where={"email": r.email})
            changes["removed"] += 1

        # --- 2. CSV rows we are missing, plus title/phone drift ----------
        by_email = {(r.email or "").lower(): r for r in rows}
        for c in current:
            email = (c["email"] or "").strip().lower()
            # The CSV itself contains a non-breaking space in at least one
            # title ("Social Science\xa0Librarian"); normalise so the
            # stored value is comparable and never renders oddly.
            title = (c.get("title") or "").replace("\xa0", " ").strip()
            phone = (c.get("phone") or "").strip()
            campus = _CAMPUS.get((c.get("library") or "").strip().lower(), "")
            existing = by_email.get(email)
            if existing is None:
                print(f"  {'would ' if dry else ''}ADD         {email:32} "
                      f"{_disp(c):24} {title!r}")
                if not dry:
                    await db.librarian.create(data={
                        "name": _disp(c), "email": email,
                        "title": title or None,
                        "phone": phone or None, "campus": campus or "Oxford",
                        "isRegional": campus in ("Hamilton", "Middletown"),
                        "isActive": True,
                    })
                changes["added"] += 1
                continue
            patch = {}
            if not existing.isActive:
                patch["isActive"] = True
            if _disp(c) and existing.name != _disp(c):
                patch["name"] = _disp(c)
            if title and (existing.title or "").replace("\xa0", " ").strip() != title:
                patch["title"] = title
                changes["titles"] += 1
            if phone and not (existing.phone or "").strip():
                patch["phone"] = phone
                changes["phones"] += 1
            if patch:
                print(f"  {'would ' if dry else ''}update      {email:32} "
                      f"{_disp(c):24} {patch}")
                if not dry:
                    await db.librarian.update(where={"email": email}, data=patch)

        # --- 3. liaison duties -> LibrarianSubject ----------------------
        subjects = await db.subject.find_many()
        by_subject = {s.name.strip().lower(): s for s in subjects}
        wanted: set = set()          # (email, subjectId)
        for c in current:
            names = [x.strip() for x in (c.get("liaison") or "").split(";")
                     if x.strip()]
            for name in names:
                s = by_subject.get(name.lower())
                if s is None:
                    print(f"  {'would ' if dry else ''}new subject {name!r}")
                    if not dry:
                        s = await db.subject.create(data={"name": name})
                        by_subject[name.lower()] = s
                    changes["subjects_made"] += 1
                    if dry:
                        continue
                wanted.add(((c["email"] or "").strip().lower(), s.id))

        live = await db.librarian.find_many(where={"isActive": True})
        lib_by_email = {(l.email or "").lower(): l for l in live}
        have = {(l.librarianId, l.subjectId)
                for l in await db.librariansubject.find_many()}
        want_ids = {(lib_by_email[e].id, sid) for e, sid in wanted
                    if e in lib_by_email}

        for lid, sid in sorted(want_ids - have):
            changes["links_added"] += 1
            if not dry:
                await db.librariansubject.create(
                    data={"librarianId": lid, "subjectId": sid})
        # Links for people who are no longer active, or duties the CSV
        # dropped, must go -- a stale link is how a departed colleague
        # keeps being named as a subject's liaison.
        active_ids = {l.id for l in live}
        for lid, sid in sorted(have):
            if lid not in active_ids or (lid, sid) not in want_ids:
                if lid in {i for i, _ in want_ids} or lid not in active_ids:
                    changes["links_removed"] += 1
                    if not dry:
                        rec = await db.librariansubject.find_first(
                            where={"librarianId": lid, "subjectId": sid})
                        if rec:
                            await db.librariansubject.delete(where={"id": rec.id})
    finally:
        await db.disconnect()

    print(f"\nCSV: {len(current)} on the roster "
          f"(incl. {len(future)} starting soon), "
          f"{len(departed)} with a past last-date")
    for r in future:
        print(f"   starting soon, listed: {_disp(r)} on {r['start-date']}")
    verb = "would change" if dry else "changed"
    print(f"{verb}: " + ", ".join(f"{k}={v}" for k, v in changes.items() if v))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", default="/opt/chatbot/staff-members.csv")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.dry_run, a.csv)))
