#!/usr/bin/env python3
"""
find_chunks.py -- librarian helper for the ManualCorrection workflow.

When the bot cites something wrong, you need the chunk_id to file a
`suppress` or `replace` correction in /admin/corrections/view. The
citation popup shows the snippet and source URL but not the chunk_id;
this script bridges that gap.

Usage (from ai-core/, venv active):
  # Every chunk indexed from a page (use the URL from the citation popup):
  python scripts/find_chunks.py --url https://www.lib.miamioh.edu/about/locations/art-arch/

  # Or search by words you saw in the wrong answer:
  python scripts/find_chunks.py --contains "100 Bishop"

  # Show full chunk text instead of a preview:
  python scripts/find_chunks.py --url <url> --full

Output per chunk: chunk_id (copy this into the corrections form),
campus/library/topic tags, and the text.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="source_url to list chunks for (exact match)")
    ap.add_argument("--contains", help="substring to search chunk text for")
    ap.add_argument("--collection",
                    default=os.getenv("WEAVIATE_CHUNK_COLLECTION", "Chunk_current"),
                    help="defaults to WEAVIATE_CHUNK_COLLECTION from .env "
                         "(the same collection the bot serves from)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--full", action="store_true", help="print full chunk text")
    args = ap.parse_args()

    if not args.url and not args.contains:
        ap.error("need --url or --contains")

    from src.utils.weaviate_client import get_weaviate_client
    client = get_weaviate_client()
    if client is None:
        print("ERROR: cannot connect to Weaviate (check WEAVIATE_* in .env / tunnel up?)")
        return 1

    try:
        from weaviate.classes.query import Filter
        coll = client.collections.get(args.collection)

        filters = None
        if args.url:
            filters = Filter.by_property("source_url").equal(args.url)
        if args.contains:
            f = Filter.by_property("text").like(f"*{args.contains}*")
            filters = f if filters is None else (filters & f)

        res = coll.query.fetch_objects(filters=filters, limit=args.limit)
        objs = res.objects
        if not objs:
            print("No chunks matched. Tips: the URL must match the citation popup "
                  "exactly (trailing slash matters); --contains is case-sensitive.")
            return 0

        print(f"{len(objs)} chunk(s) in collection {args.collection!r}:\n")
        for o in objs:
            p = o.properties or {}
            chunk_id = p.get("chunk_id") or str(o.uuid)
            text = (p.get("text") or "").strip()
            preview = text if args.full else (text[:300] + ("…" if len(text) > 300 else ""))
            print("=" * 78)
            print(f"chunk_id : {chunk_id}")
            print(f"source   : {p.get('source_url', '')}")
            print(f"tags     : campus={p.get('campus', '?')} "
                  f"library={p.get('library', '?')} topic={p.get('topic', '?')}")
            if p.get("deleted"):
                print("NOTE     : tombstoned (deleted=true) -- not served to users")
            print(f"text     : {preview}")
        print("=" * 78)
        print("\nTo fix a wrong chunk: open /admin/corrections/view?key=YOUR_TOKEN,")
        print("action=replace (scope=chunk, target=<chunk_id>, replacement=<correct text>)")
        print("or action=suppress (scope=chunk, target=<chunk_id>) to just hide it.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
