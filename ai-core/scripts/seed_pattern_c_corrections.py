"""
Seed the first Op 2 ManualCorrection row: blacklist the stale 2018
WSJ news announcement page.

Why this exists -- the 2026-05-20 third+fourth full evals identified a
recurring Pattern C failure: the bot confidently asserts "Miami
University Libraries offer complimentary electronic memberships to
The Wall Street Journal" when asked about WSJ. A Weaviate BM25 query
traced the source to chunks from this URL:

    https://www.lib.miamioh.edu/2018-09-07-libraries-offer-free-access-to-the-wall-street-journal

That URL is a 2018 NEWS ANNOUNCEMENT page (~7 years old) with the
original launch announcement. The plan's ETL design excludes
`/about/news-events/*` for exactly this reason -- but this page lives
at a /YYYY-MM-DD-... slug outside that prefix and slipped through.

The correct authoritative answer per `ai-core/docs/canonical/newspapers.md`
(captured 2026-05-15, verified) is that WSJ and NYT each have their
OWN distinct activation URL with distinct rules. The 2018 page's
prose is now misleading.

The Op 2 fix is a `blacklist_url` ManualCorrection row: retrieval
drops chunks from that URL, and the URL validator rejects it from
synthesizer output. Bot will fall back to other newspaper content (or
refuse cleanly per rule 4) on WSJ questions.

A more durable fix (re-indexing without this URL, or updating the
LibGuide newspaper page) is out of scope today; this surgical
correction unblocks the failing eval cases NOW.

Usage:
    .venv/bin/python -m scripts.seed_pattern_c_corrections
    .venv/bin/python -m scripts.seed_pattern_c_corrections --dry-run

Idempotent: if the row already exists (matched by created_by + target
+ action) it's a no-op + reports the existing row's UUID.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path
from typing import Optional


# Load env so Prisma resolves DATABASE_URL.
def _load_env() -> None:
    from dotenv import load_dotenv
    here = Path(__file__).resolve().parent
    load_dotenv(here.parent.parent / ".env")


STALE_WSJ_URL = (
    "https://www.lib.miamioh.edu/2018-09-07-libraries-offer-free-access-to-the-wall-street-journal"
)

CORRECTION_REASON = (
    "Stale 2018 news-announcement page being retrieved as if authoritative "
    "for WSJ-subscription questions. Per ai-core/docs/canonical/newspapers.md "
    "(captured 2026-05-15), WSJ has its own activation URL with distinct "
    "rules; the 2018 launch-day prose ('complimentary electronic memberships') "
    "is misleading. Blacklist the URL until the page is removed or the "
    "newspaper LibGuide is re-indexed. Tracks the failing eval cases "
    "fs_wsj_subscription and news_wsj_access (3rd + 4th full evals, 2026-05-20)."
)
CREATED_BY = "qum@miamioh.edu"  # Operator-recorded; librarians use their own email.


async def _aseed(dry_run: bool) -> int:
    from prisma import Prisma

    client = Prisma()
    await client.connect()
    try:
        # Idempotency: look for an existing active row with the same
        # (target, action, created_by) tuple before inserting.
        existing = await client.manualcorrection.find_first(
            where={
                "target": STALE_WSJ_URL,
                "action": "blacklist_url",
                "createdBy": CREATED_BY,
                "active": True,
            }
        )
        if existing is not None:
            print(f"already exists: id={existing.id}  expires={existing.expiresAt}")
            return 0

        # 6-month expiry per the plan's correction-review policy.
        expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=180)
        if dry_run:
            print(f"DRY RUN -- would insert ManualCorrection:")
            print(f"  target={STALE_WSJ_URL}")
            print(f"  action=blacklist_url")
            print(f"  scope=url")
            print(f"  created_by={CREATED_BY}")
            print(f"  expires_at={expires_at.isoformat()}")
            print(f"  reason={CORRECTION_REASON[:80]}...")
            return 0

        row = await client.manualcorrection.create(
            data={
                "scope": "url",
                "target": STALE_WSJ_URL,
                "action": "blacklist_url",
                "replacement": None,
                "queryPattern": None,
                "reason": CORRECTION_REASON,
                "createdBy": CREATED_BY,
                "expiresAt": expires_at,
                "active": True,
            }
        )
        print(f"created: id={row.id}")
        print(f"  expires_at={row.expiresAt}")
        return 0
    finally:
        await client.disconnect()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Pattern C ManualCorrection rows.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be inserted, don't actually write.",
    )
    args = parser.parse_args(argv)

    _load_env()
    try:
        return asyncio.run(_aseed(args.dry_run))
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
