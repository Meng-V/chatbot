"""
ETL orchestrator: discover -> fetch -> extract -> classify -> chunk ->
embed -> upsert -> tombstone -> URL allowlist -> diff report.

Run: `python ai-core/scripts/etl/run_etl.py [--dry-run] [--campus X] [--limit N]`

Replaces the ad-hoc ingestion scripts in ai-core/scripts/ with a single
orchestrated pipeline. See plan: Data preparation playbook §4.

The orchestrator's I/O surface is injectable (`Pipeline` dataclass below)
so the same code path runs against:
  - Prod: real `requests`, real OpenAI embeddings, real Weaviate, real
    Postgres `UrlSeen` (configured by `_build_prod_pipeline()`).
  - Sandbox / tests: in-memory stubs (see `tests/etl_smoke.py`).

This decouples "which steps to run in what order" from "where the bytes
come from" -- the skeleton always ran end-to-end; only the concrete
backends switch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

# Allow running as a script: ensure ai-core/ is importable.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl import (  # noqa: E402  (sys.path mutation above)
    chunker,
    classify,
    config,
    diff_report,
    discover,
    extract,
    upsert,
)

logger = logging.getLogger("etl")


# --- Injectable I/O seams ----------------------------------------------------
#
# The pipeline is a sequence of pure-ish transformations bracketed by I/O.
# Make every I/O step an injectable callable so the orchestrator stays
# testable. Prod wires the real implementations in `_build_prod_pipeline`;
# tests pass stubs.


# (html, last_modified, canonical_url, error)
FetchResult = tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
FetchFn = Callable[[str], FetchResult]
EmbedFn = Callable[[list[chunker.Chunk]], list[list[float]]]
UpsertFn = Callable[
    [list[chunker.Chunk], list[list[float]], str], upsert.UpsertResult
]
TombstoneFn = Callable[[set[str], str], upsert.UpsertResult]
AllowlistFn = Callable[
    [list[tuple[str, int, str, Optional[str]]]], int
]


@dataclass
class Pipeline:
    """The injectable surface of the ETL pipeline.

    Each field is the I/O step the orchestrator calls -- swap any of them
    out in tests without touching the orchestrator.

    The defaults are deliberately lazy: `_default_fetch` / `_default_embed`
    raise NotImplementedError so a misconfigured prod run dies loudly
    rather than silently writing nothing.
    """

    fetch: FetchFn
    embed: EmbedFn
    upsert_chunks: UpsertFn
    tombstone: TombstoneFn
    update_allowlist: AllowlistFn
    discover_fn: Callable[[], list[discover.DiscoveredUrl]] = discover.discover


def _default_fetch(url: str) -> FetchResult:
    raise NotImplementedError(
        "Pipeline.fetch not configured -- pass a real fetcher (or use "
        "build_requests_fetcher) when constructing Pipeline."
    )


def _default_embed(chunks: list[chunker.Chunk]) -> list[list[float]]:
    raise NotImplementedError(
        "Pipeline.embed not configured -- pass a real embedder when "
        "constructing Pipeline."
    )


def _default_upsert(
    chunks: list[chunker.Chunk],
    embeddings: list[list[float]],
    version: str,
) -> upsert.UpsertResult:
    raise NotImplementedError("Pipeline.upsert_chunks not configured")


def _default_tombstone(seen: set[str], version: str) -> upsert.UpsertResult:
    raise NotImplementedError("Pipeline.tombstone not configured")


def _default_allowlist(seen: list[tuple[str, int, str, Optional[str]]]) -> int:
    raise NotImplementedError("Pipeline.update_allowlist not configured")


# --- Real fetcher (lazy, requests-based) -------------------------------------


def build_requests_fetcher(cache_dir: Optional[Path] = None) -> FetchFn:
    """Build a real `requests`-backed fetcher.

    Caches raw HTML to `cache_dir / sha256(url).html` so a partial run
    doesn't re-hammer the source. Honors `config.TLS_SKIP_ALLOWLIST` --
    every TLS-skipped fetch logs a WARN so we notice when the cert is
    finally renewed.
    """
    import requests
    from urllib.parse import urlparse

    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    cache = cache_dir or Path(config.RAW_CACHE_DIR)
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(url: str) -> FetchResult:
        # Cache hit?
        cache_path = cache / f"{hashlib.sha256(url.encode()).hexdigest()}.html"
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8"), None, url, None

        host = urlparse(url).hostname or ""
        verify_tls = host not in config.TLS_SKIP_ALLOWLIST
        if not verify_tls:
            logger.warning(
                "fetching with TLS verification disabled",
                extra={"host": host, "url": url},
            )
        try:
            resp = session.get(
                url,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
                verify=verify_tls,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return None, None, None, f"{type(e).__name__}: {e}"

        html = resp.text
        cache_path.write_text(html, encoding="utf-8")
        return (
            html,
            resp.headers.get("Last-Modified"),
            resp.url,  # canonical post-redirect URL
            None,
        )

    return fetch


def run(
    dry_run: bool = False,
    campus_filter: Optional[str] = None,
    url_limit: Optional[int] = None,
    pipeline: Optional[Pipeline] = None,
) -> diff_report.DiffReport:
    """Run the full ETL pipeline once. Returns the diff report.

    `pipeline` defaults to the unconfigured Pipeline whose I/O methods
    raise NotImplementedError; callers must pass a real Pipeline (see
    `_build_prod_pipeline()`) or a stub Pipeline (see the smoke test).
    """
    pipeline = pipeline or Pipeline(
        fetch=_default_fetch,
        embed=_default_embed,
        upsert_chunks=_default_upsert,
        tombstone=_default_tombstone,
        update_allowlist=_default_allowlist,
    )

    started = dt.datetime.utcnow()
    report = diff_report.DiffReport(
        run_started_at=started,
        run_finished_at=started,  # placeholder; updated at end
        discovered_url_count=0,
    )

    # 1. Discover
    discovered = pipeline.discover_fn()
    if campus_filter:
        discovered = [d for d in discovered if d.campus == campus_filter]
    if url_limit:
        discovered = discovered[:url_limit]
    report.discovered_url_count = len(discovered)
    logger.info("discovered %d URLs", len(discovered))

    # 2-4. Fetch + extract + classify
    seen_urls: set[str] = set()
    seen_for_allowlist: list[tuple[str, int, str, Optional[str]]] = []
    classified_docs: list[tuple[extract.ExtractedDoc, classify.DocMetadata]] = []
    for d in discovered:
        html, last_mod, canonical, err = pipeline.fetch(d.url)
        if err or html is None:
            report.fetch_failures.append((d.url, err or "unknown"))
            continue
        report.fetched_url_count += 1
        # Use the post-redirect canonical URL when available -- otherwise
        # `/use/spaces/` and its target both end up indexed separately.
        canon_url = canonical or d.url
        seen_urls.add(canon_url)
        seen_for_allowlist.append((canon_url, 200, d.source, "text/html"))

        doc = extract.extract(html, canon_url, last_modified=last_mod)
        if doc.rejection_reason:
            report.extraction_rejects.append((canon_url, doc.rejection_reason))
            continue
        report.extracted_doc_count += 1

        meta = classify.classify(canon_url, doc.body_text)
        classified_docs.append((doc, meta))

    # 5-6. Chunk (dedupe happens at upsert step against existing index)
    all_chunks: list[chunker.Chunk] = []
    for doc, meta in classified_docs:
        chunks = chunker.chunk_document(doc, meta)
        all_chunks.extend(chunks)
    report.chunks_created = len(all_chunks)

    # 7-9. Embed + upsert + tombstone (DESTRUCTIVE -- skip on dry-run)
    if dry_run:
        logger.info("dry-run: skipping embed/upsert/tombstone/allowlist")
    else:
        embeddings = pipeline.embed(all_chunks)
        version = started.strftime("v%Y%m%d_%H%M")
        report.upsert = pipeline.upsert_chunks(all_chunks, embeddings, version)
        tomb = pipeline.tombstone(seen_urls, version)
        report.upsert.tombstoned_urls = tomb.tombstoned_urls
        report.upsert.gc_deleted_chunk_count = tomb.gc_deleted_chunk_count

        # 10. URL allowlist
        report.upsert.new_url_count = pipeline.update_allowlist(seen_for_allowlist)

    # 11. Diff report
    report.run_finished_at = dt.datetime.utcnow()
    diff_report.write_diff_report(report)
    return report


def _build_prod_pipeline() -> Pipeline:
    """Construct a Pipeline wired to the real OpenAI / Weaviate / Postgres
    clients. Imports are lazy so dev / sandbox runs without the deps don't
    blow up at module-import time.

    Wiring contract:
      - OpenAI: src/config/models.py::EMBEDDING_MODEL is the only model
        identifier this code may use. Confirm against live OpenAI docs
        per the freshness rule before changing.
      - Weaviate: a thin adapter implementing `WeaviateLike` (in
        upsert.py) wraps the v4 client so the ETL doesn't depend on
        client-version internals.
      - Postgres: a Prisma-backed `UrlSeenStore` adapter handles the
        upsert.
    """
    from openai import OpenAI  # type: ignore

    from src.config.models import EMBEDDING_MODEL  # type: ignore
    from src.weaviate.etl_adapter import WeaviateETLAdapter  # type: ignore
    from src.database.urlseen_adapter import PrismaUrlSeenStore  # type: ignore

    openai_client = OpenAI()
    weaviate = WeaviateETLAdapter()
    urlseen = PrismaUrlSeenStore()

    def embed(chunks: list[chunker.Chunk]) -> list[list[float]]:
        return upsert.embed_chunks(
            chunks, openai_client.embeddings, model=EMBEDDING_MODEL
        )

    return Pipeline(
        fetch=build_requests_fetcher(),
        embed=embed,
        upsert_chunks=upsert.make_upsert_step(weaviate),
        tombstone=upsert.make_tombstone_step(weaviate),
        update_allowlist=upsert.make_allowlist_step(urlseen),
    )


def _setup_logging(verbose: bool) -> None:
    """Wire up root logging for CLI runs.

    INFO by default; DEBUG with `--verbose`. One-line format keeps
    diff-report / checkpoint output readable in a terminal without
    drowning in tracebacks. Structlog is used by the serving stack
    (src/observability/logging.py); the ETL is a script, so plain
    stdlib logging is the right tool here.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the smart-chatbot ETL pipeline.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip embed/upsert/tombstone; only discover+extract+classify+chunk.")
    parser.add_argument("--campus", choices=list(config.SITEMAPS), default=None,
                        help="Restrict to one campus.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max URLs to process (for smoke testing).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    t0 = time.time()

    if args.dry_run:
        # Dry-run only needs the fetcher (real one is fine -- it's just
        # HTTP GETs); embed/upsert/tombstone/allowlist won't run.
        pipeline = Pipeline(
            fetch=build_requests_fetcher(),
            embed=_default_embed,
            upsert_chunks=_default_upsert,
            tombstone=_default_tombstone,
            update_allowlist=_default_allowlist,
        )
    else:
        try:
            pipeline = _build_prod_pipeline()
        except ImportError as e:
            logger.error(
                "prod pipeline cannot be wired: %s. "
                "Either install the missing deps or pass --dry-run.",
                e,
            )
            return 2

    try:
        report = run(
            dry_run=args.dry_run,
            campus_filter=args.campus,
            url_limit=args.limit,
            pipeline=pipeline,
        )
    except NotImplementedError as e:
        logger.error("step not configured: %s", e)
        return 2
    elapsed = time.time() - t0
    logger.info(
        "ETL run finished in %.1fs: %d new chunks, %d tombstoned URLs",
        elapsed,
        len(report.upsert.new_chunk_ids),
        len(report.upsert.tombstoned_urls),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
