"""
Admin endpoints for the librarian-review workflow (plan Op 1).

Endpoints:
  GET  /admin/reviews              -- list recent conversations scoped
                                      to the librarian's subject/campus,
                                      paginated, sortable, with saved
                                      filter presets (confidence=low,
                                      user_rating=down, cross-campus
                                      refusals).
  POST /admin/reviews              -- submit a verdict on one turn.
                                      Writes to LibrarianReview.
  GET  /admin/reviews/queue-count  -- unreviewed count for the weekly
                                      digest email.

Pure function `build_reviews_router(deps) -> APIRouter`; FastAPI and
Prisma are lazy-imported so the module is importable without them.

See plan: Operations -> Op 1 "Subject-librarian dialog review".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ReviewVerdict:
    """One librarian verdict submission (shape independent of FastAPI
    so the handler is testable without the web framework)."""

    message_id: str
    librarian_id: int
    verdict: str
    """One of: correct | partial | wrong | should_refuse."""

    note: Optional[str] = None


VALID_VERDICTS = frozenset({"correct", "partial", "wrong", "should_refuse"})


def validate_verdict(v: ReviewVerdict) -> Optional[str]:
    """Return None on valid, else a reason string."""
    if v.verdict not in VALID_VERDICTS:
        return f"verdict must be one of {sorted(VALID_VERDICTS)}; got {v.verdict!r}"
    if not v.message_id:
        return "message_id is required"
    if v.librarian_id <= 0:
        return "librarian_id must be positive"
    if v.note is not None and len(v.note) > 2000:
        return "note exceeds 2000 characters"
    return None


def build_reviews_router(deps: dict) -> Any:
    """Build the FastAPI router with handlers bound to `deps`.

    `deps` is a plain dict so tests can inject stubs; prod passes
    `{"db": prisma_client, "require_librarian": auth_dep}`.

    Returns a FastAPI `APIRouter`, or a placeholder object with a
    `.routes` attribute in the sandbox if fastapi isn't importable.
    """
    try:
        from fastapi import APIRouter, Depends, HTTPException  # type: ignore
    except ImportError:
        return _PlaceholderRouter(
            "/admin/reviews",
            reason="fastapi not installed -- router cannot be built",
        )

    router = APIRouter(prefix="/admin/reviews", tags=["admin"])
    db = deps["db"]
    require_librarian = deps.get("require_librarian", lambda: None)

    @router.get("")
    async def list_reviews(
        campus: Optional[str] = None,
        subject_id: Optional[int] = None,
        filter_preset: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        _user=Depends(require_librarian),
    ):
        """List recent conversations this librarian should review.

        Filter presets:
          - `low_confidence`  -- Message.confidence == 'low'
          - `thumbs_down`     -- Message.userRating == 'down'
          - `cross_campus`    -- refusalTrigger == 'cross_campus_mismatch'
        """
        # TODO(week 7): wire Prisma query: Message join ChunkProvenance
        # join Librarian via subject so we can scope by librarian's
        # subjects + campus. Returns list of {message_id, question,
        # answer, citations, confidence, scope, refusal_trigger}.
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.post("")
    async def submit_verdict(
        verdict: dict,
        _user=Depends(require_librarian),
    ):
        """Submit a LibrarianReview row. Body matches ReviewVerdict."""
        v = ReviewVerdict(
            message_id=str(verdict["message_id"]),
            librarian_id=int(verdict["librarian_id"]),
            verdict=str(verdict["verdict"]),
            note=verdict.get("note"),
        )
        err = validate_verdict(v)
        if err:
            raise HTTPException(status_code=400, detail=err)
        # TODO(week 7): db.librarianreview.create({...})
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.get("/queue-count")
    async def queue_count(
        librarian_id: int,
        _user=Depends(require_librarian),
    ):
        """Count of unreviewed turns for the Monday-morning digest email."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    return router


class _PlaceholderRouter:
    """Shim returned when FastAPI isn't installed. Imports resolve; a
    prod deploy without FastAPI would still fail at app.include_router
    time, which is the desired fail-loud behavior.
    """

    def __init__(self, prefix: str, reason: str) -> None:
        self.prefix = prefix
        self.reason = reason
        self.routes: list = []


__all__ = [
    "ReviewVerdict",
    "VALID_VERDICTS",
    "build_reviews_router",
    "validate_verdict",
]
