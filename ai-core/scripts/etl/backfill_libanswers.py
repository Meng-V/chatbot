"""Add the LibAnswers FAQs to the collection that is already serving.

WHEN TO USE THIS INSTEAD OF run_etl.py
    run_etl rebuilds the corpus: it re-crawls every page and writes a
    NEW collection, which is then promoted after eval. That is the right
    shape for "the website changed". It is the wrong shape for "we have
    a new source and nothing else moved" -- it would put a full corpus
    rebuild, and the score change that comes with it, in the path of
    adding 128 chunks.

    This script only ADDS. It writes into the live collection named by
    WEAVIATE_CHUNK_COLLECTION, never deletes, never tombstones, and
    never touches a chunk it did not create. upsert is idempotent on
    (chunk_id, content_hash), so running it twice is a no-op.

    Everything about how a FAQ becomes a chunk lives in
    scripts/etl/libanswers.py and is shared with the ETL proper, so a
    later full run produces the same chunks this one did.

TO UNDO
    Delete the chunks whose source_url starts with
    https://libanswers.lib.miamioh.edu/ from the collection. Nothing
    else was modified.

Run:
    python ai-core/scripts/etl/backfill_libanswers.py            # dry run
    python ai-core/scripts/etl/backfill_libanswers.py --write
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

# Same inline .env loader run_etl uses -- no python-dotenv dependency,
# and real exported vars win.
_ENV_PATH = _AI_CORE.parent / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        if _k and _k not in os.environ:
            os.environ[_k] = _v.strip().strip('"').strip("'")

from scripts.etl import chunker, libanswers, upsert  # noqa: E402

logger = logging.getLogger("backfill.libanswers")

COLLECTION_PREFIX = "Chunk"


def collection_and_version() -> tuple[str, str]:
    """The live collection, and the version suffix upsert needs.

    make_upsert_step composes `f"{prefix}_v{version}"`, so the version
    is whatever follows "Chunk_v" in the configured name -- for
    Chunk_vv20260804_1110 that is "v20260804_1110". Derived rather than
    hardcoded so this cannot silently write to last month's collection.
    """
    name = (os.getenv("WEAVIATE_CHUNK_COLLECTION") or "").strip()
    if not name:
        raise SystemExit("WEAVIATE_CHUNK_COLLECTION is not set")
    head = f"{COLLECTION_PREFIX}_v"
    if not name.startswith(head):
        raise SystemExit(f"collection {name!r} does not start with {head!r}")
    return name, name[len(head):]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="actually write; without it nothing is sent")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    collection, version = collection_and_version()

    faqs = libanswers.fetch_faqs()
    pairs = libanswers.to_classified(faqs)
    chunks: list[chunker.Chunk] = []
    for doc, meta in pairs:
        chunks.extend(chunker.chunk_document(doc, meta))

    urls = {c.source_url for c in chunks}
    print(f"  source      : {len(faqs)} FAQs -> {len(pairs)} documents")
    print(f"  chunks      : {len(chunks)} across {len(urls)} URLs")
    print(f"  destination : {collection}")

    if not args.write:
        print("\n  DRY RUN -- nothing written. Re-run with --write.")
        for c in chunks[:3]:
            print(f"\n  {c.source_url}\n    {c.text[:150]}...")
        return 0

    from openai import OpenAI  # type: ignore

    from src.config.models import EMBEDDING_MODEL  # type: ignore
    from src.database.urlseen_adapter import PrismaUrlSeenStore  # type: ignore
    from src.weaviate_adapters.etl_adapter import WeaviateETLAdapter  # type: ignore

    vectors = upsert.embed_chunks(
        chunks, OpenAI().embeddings, model=EMBEDDING_MODEL)
    result = upsert.make_upsert_step(
        WeaviateETLAdapter(), collection_prefix=COLLECTION_PREFIX
    )(chunks, vectors, version)

    # The answer validator drops any citation whose URL is not in
    # UrlSeen, so without this the FAQs would be retrieved and then
    # quoted with their source stripped off.
    allowlisted = upsert.make_allowlist_step(PrismaUrlSeenStore())(
        [(u, 200, "seed", "text/html") for u in sorted(urls)])

    print(f"\n  new         : {len(result.new_chunk_ids)}")
    print(f"  changed     : {len(result.changed_chunk_ids)}")
    print(f"  already there: {len(result.deduped_chunk_ids)}")
    print(f"  URLs newly allowlisted: {allowlisted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
