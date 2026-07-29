"""
Step 11 of the ETL pipeline: write a human-readable diff report.

The diff report is what a librarian reads to APPROVE a refresh. Without
it, "the ETL ran successfully" is information-free; with it, the librarian
can see exactly which pages were added, changed, tombstoned, or rejected,
and why.

Output: Markdown file at ai-core/data/diffs/{date}.md, optionally posted
to Slack/email (TODO: hook up).

See plan: Data preparation playbook §4 step 11.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .upsert import UpsertResult

logger = logging.getLogger(__name__)


@dataclass
class DiffReport:
    """Aggregate of one ETL run's outcome. Fed to render_markdown()."""

    run_started_at: dt.datetime
    run_finished_at: dt.datetime
    discovered_url_count: int
    rejected_urls: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    fetched_url_count: int = 0
    fetch_failures: list[tuple[str, str]] = field(default_factory=list)  # (url, error)
    extracted_doc_count: int = 0
    extraction_rejects: list[tuple[str, str]] = field(default_factory=list)
    chunks_created: int = 0
    chunks_dropped_short: int = 0
    upsert: UpsertResult = field(default_factory=UpsertResult)
    cost_estimate_usd: float = 0.0


def render_markdown(report: DiffReport) -> str:
    """Render a DiffReport as a readable Markdown doc.

    The shape mirrors what librarians need to skim in 60 seconds:
      - Top-line counts
      - Things that DIDN'T make it (rejections), grouped by reason
      - Things that DID make it (added/changed URLs), with click-throughs
      - Tombstones (URLs that disappeared from the source site)
    """
    duration = (report.run_finished_at - report.run_started_at).total_seconds()
    lines: list[str] = []

    lines.append(f"# ETL Diff Report — {report.run_finished_at:%Y-%m-%d %H:%M UTC}")
    lines.append("")
    lines.append(f"_Run duration: {duration:.0f}s · estimated cost: ${report.cost_estimate_usd:.2f}_")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Discovered URLs: **{report.discovered_url_count}**")
    lines.append(f"- Fetched: **{report.fetched_url_count}** ({len(report.fetch_failures)} failed)")
    lines.append(f"- Extracted docs: **{report.extracted_doc_count}** "
                 f"({len(report.extraction_rejects)} rejected at extract step)")
    lines.append(f"- Chunks created: **{report.chunks_created}** "
                 f"(dropped {report.chunks_dropped_short} as too short)")
    preview = report.upsert.weaviate_collection_version == "(preview)"
    verb = "would be" if preview else ""
    lines.append(f"- New or rewritten chunks{' that ' + verb + ' indexed' if preview else ' indexed'}: "
                 f"**{len(report.upsert.new_chunk_ids)}**")
    lines.append(f"- Unchanged (already in the index): "
                 f"**{len(report.upsert.deduped_chunk_ids)}**")
    if preview:
        lines.append(f"- No longer produced by the crawl: "
                     f"**{report.upsert.orphaned_chunk_count}**")
        lines.append(f"- Live chunks in the serving index: "
                     f"**{report.upsert.total_chunks_in_index}**")
    else:
        # Name the collection this run WROTE. Without it the report records
        # what happened but not where, and on 2026-07-29 that gap cost a
        # good corpus: nothing on disk distinguished the successful apply's
        # collection from the four partial ones left by earlier attempts,
        # so a cleanup swept all five. The header timestamp is the FINISH
        # time while the collection is named for the START time, which is
        # why it cannot be reconstructed by reading the filename either.
        lines.append(f"- Written to collection: "
                     f"**Chunk_v{report.upsert.weaviate_collection_version}** "
                     f"(not serving until promoted)")
        lines.append(f"- Changed chunks re-indexed: "
                     f"**{len(report.upsert.changed_chunk_ids)}**")
        lines.append(f"- Tombstoned URLs: **{len(report.upsert.tombstoned_urls)}**")
        lines.append(f"- Hard-deleted (>30d tombstoned): "
                     f"**{report.upsert.gc_deleted_chunk_count}**")
        lines.append(f"- New URLs added to allowlist: "
                     f"**{report.upsert.new_url_count}**")
        _failed = getattr(report.upsert, "failed_chunk_ids", [])
        if _failed:
            lines.append(f"- ⚠️ Chunks that FAILED to index: **{len(_failed)}** "
                         f"(the run continued; see the log for URLs)")
    lines.append("")
    if preview:
        # Without this note a librarian reads "0 changed" as "nothing
        # changed on the website", which is the opposite of the truth.
        lines.append("> **How to read this.** `chunk_id` is derived from the "
                     "page URL, the position, and a hash of the text, so "
                     "EDITED text does not show up as \"changed\" -- it "
                     "appears as a new chunk and orphans the old one. Read "
                     "the first and third numbers together: they are the "
                     "size of the rewrite, not two separate events.")
        lines.append("")
        lines.append("> Nothing has been written. This is a dry run against "
                     "the live index; approving this diff is what authorises "
                     "the write.")
        lines.append("")

    if report.upsert.tombstoned_urls:
        lines.append("## ⚠️ Tombstoned URLs (no longer in source sitemaps)")
        lines.append("")
        for url in sorted(report.upsert.tombstoned_urls)[:50]:
            lines.append(f"- {url}")
        if len(report.upsert.tombstoned_urls) > 50:
            lines.append(f"- ... and {len(report.upsert.tombstoned_urls) - 50} more")
        lines.append("")

    if report.fetch_failures:
        lines.append("## ❌ Fetch failures")
        lines.append("")
        for url, err in report.fetch_failures[:30]:
            lines.append(f"- `{url}` — {err}")
        if len(report.fetch_failures) > 30:
            lines.append(f"- ... and {len(report.fetch_failures) - 30} more")
        lines.append("")

    if report.extraction_rejects:
        # Group by reason so the librarian can see patterns.
        by_reason: dict[str, list[str]] = {}
        for url, reason in report.extraction_rejects:
            by_reason.setdefault(reason, []).append(url)
        lines.append("## ❌ Extraction rejects")
        lines.append("")
        for reason, urls in sorted(by_reason.items()):
            lines.append(f"### {reason} ({len(urls)})")
            for url in urls[:10]:
                lines.append(f"- {url}")
            if len(urls) > 10:
                lines.append(f"- ... and {len(urls) - 10} more")
            lines.append("")

    if report.rejected_urls:
        # These are URLs the EXCLUDE list filtered out -- usually news/events.
        # Useful as a sanity check ("we're correctly skipping news") but
        # voluminous; collapse by reason.
        by_reason = {}
        for url, reason in report.rejected_urls:
            by_reason.setdefault(reason, []).append(url)
        lines.append("## URLs filtered (by exclusion rule)")
        lines.append("")
        for reason, urls in sorted(by_reason.items()):
            lines.append(f"- `{reason}`: {len(urls)} URLs")
        lines.append("")

    return "\n".join(lines)


def write_diff_report(report: DiffReport) -> Path:
    """Persist the diff report to ai-core/data/diffs/{date}.md."""
    out_dir = Path(config.DIFF_REPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{report.run_finished_at:%Y-%m-%d_%H%M}.md"
    path = out_dir / fname
    path.write_text(render_markdown(report), encoding="utf-8")
    logger.info("diff report written", extra={"path": str(path)})
    return path
