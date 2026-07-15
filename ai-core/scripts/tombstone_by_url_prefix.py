#!/usr/bin/env python3
"""
Tombstone (soft-delete) Weaviate chunks whose source_url starts with a
given prefix.

Why this exists (2026-07-14): the COVID-era "Library Healthy" pages are
still live on the website and got crawled into the index, so retrieval
kept surfacing them (e.g. citing /libraryhealthy/virtual/ for an Adobe
question). Serving now denylists them (new_orchestrator
_EVIDENCE_URL_DENYLIST), but the chunks still burn retrieval slots --
this script removes them from retrieval at the source.

Soft-delete only: sets deleted=true + tombstoned_at, the same tombstone
contract as etl_adapter.soft_delete_by_url. Retrieval filters
deleted=false (search_adapter), and gc_tombstones hard-deletes later.
Reversible: re-run with --undelete to flip them back.

Usage (through the prod tunnel, same env as run_eval):
    python3 scripts/tombstone_by_url_prefix.py --prefix https://www.lib.miamioh.edu/libraryhealthy            # dry-run
    python3 scripts/tombstone_by_url_prefix.py --prefix https://www.lib.miamioh.edu/libraryhealthy --execute
    python3 scripts/tombstone_by_url_prefix.py --prefix ... --undelete --execute   # roll back
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Root .env (repo root), then ai-core/.env as fallback -- same order the
# serving stack uses.
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / "ai-core" / ".env")

from src.utils.weaviate_client import get_weaviate_client  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", required=True,
                    help="source_url prefix to tombstone (startswith match)")
    ap.add_argument("--collection",
                    default=os.getenv("WEAVIATE_CHUNK_COLLECTION", ""),
                    help="collection name (default: $WEAVIATE_CHUNK_COLLECTION)")
    ap.add_argument("--execute", action="store_true",
                    help="actually write; default is a dry-run count")
    ap.add_argument("--undelete", action="store_true",
                    help="flip deleted=false instead (roll a prune back)")
    args = ap.parse_args()

    if not args.collection:
        print("no collection: set WEAVIATE_CHUNK_COLLECTION or --collection")
        return 1

    client = get_weaviate_client()
    if client is None:
        print("could not connect to Weaviate (tunnel up? env set?)")
        return 1
    try:
        coll = client.collections.get(args.collection)
        target_deleted_state = bool(args.undelete)  # undelete targets deleted=true rows
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        matched = 0
        changed = 0
        by_url: dict[str, int] = {}
        for obj in coll.iterator(return_properties=["source_url", "deleted"]):
            url = str(obj.properties.get("source_url") or "")
            if not url.startswith(args.prefix):
                continue
            matched += 1
            by_url[url] = by_url.get(url, 0) + 1
            already = bool(obj.properties.get("deleted"))
            if already != target_deleted_state:
                continue  # nothing to flip for this row
            if args.execute:
                props = {"deleted": not target_deleted_state}
                if not target_deleted_state:
                    props["tombstoned_at"] = now_iso
                coll.data.update(uuid=obj.uuid, properties=props)
            changed += 1

        verb = "un-tombstoned" if args.undelete else "tombstoned"
        mode = "" if args.execute else " (DRY-RUN, nothing written)"
        print(f"matched {matched} chunks under {args.prefix!r} "
              f"in {args.collection!r}:")
        for url, n in sorted(by_url.items()):
            print(f"  {n:4d}  {url}")
        print(f"{verb} {changed} chunk(s){mode}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
