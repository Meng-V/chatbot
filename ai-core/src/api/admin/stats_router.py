"""
Admin aggregate-health endpoints (plan Op 1 "Aggregate health view").

Endpoints:
  GET /admin/stats/by-subject    -- per-subject correct-rate
  GET /admin/stats/by-source-url -- per-source-URL correct-rate
  GET /admin/stats/trends        -- daily correct-rate + refusal-rate
  GET /admin/stats/cache-health  -- rolling cache-hit rate

All queries are read-only and cache-friendly. Caller passes the time
window as a query param; default is last 30 days.

Status: SCAFFOLD. Queries are sketched as SQL-shaped docstrings on the
handlers; implementation lands in week 7 with the full review UI.
"""

from __future__ import annotations

from typing import Any, Optional


def build_stats_router(deps: dict) -> Any:
    """Build the FastAPI stats router."""
    try:
        from fastapi import APIRouter, Depends, HTTPException  # type: ignore
    except ImportError:
        return _Placeholder("/admin/stats")

    router = APIRouter(prefix="/admin/stats", tags=["admin"])
    db = deps["db"]
    require_librarian = deps.get("require_librarian", lambda: None)

    @router.get("/by-subject")
    async def by_subject(
        days: int = 30,
        _user=Depends(require_librarian),
    ):
        """Per-subject correct-rate over the last `days` days.

        Query shape:
            SELECT subject.name,
                   count(*) FILTER (WHERE verdict='correct') AS correct,
                   count(*) AS total
            FROM LibrarianReview lr
            JOIN Message m ON m.id = lr.message_id
            JOIN ChunkProvenance cp ON cp.chunk_id = ANY(m.cited_chunk_ids)
            JOIN SubjectChunk sc ON sc.source_url = cp.source_url
            JOIN Subject ON subject.id = sc.subject_id
            WHERE lr.reviewed_at > now() - interval '{days} days'
            GROUP BY subject.name;
        """
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.get("/by-source-url")
    async def by_source_url(
        days: int = 30,
        min_citations: int = 5,
        _user=Depends(require_librarian),
    ):
        """Per-source-URL correct-rate -- polluted sources rise to the
        top. min_citations avoids ranking URLs cited once."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.get("/trends")
    async def trends(
        days: int = 30,
        _user=Depends(require_librarian),
    ):
        """Daily timeseries: correct_rate, refusal_rate, thumbs_down_rate."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.get("/cache-health")
    async def cache_health(
        hours: int = 24,
        _user=Depends(require_librarian),
    ):
        """Rolling `cached_input_tokens / input_tokens` over the last
        `hours` hours, broken down by call_site.

        Alerting: dash below 0.4 for 1 hour = Slack alert (per plan
        Op 3 "Alerting (escalation tiers)").
        """
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    return router


class _Placeholder:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = ["build_stats_router"]
