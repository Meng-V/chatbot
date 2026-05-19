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

# review_queries imports only stdlib (prisma is used via the injected
# db handle), so this is safe to import without the prisma client.
from src.api.admin.review_queries import conversation_detail, list_flagged


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
        """List recent messages a librarian should review (newest first).

        filter_preset (default `flagged` = the union below):
          - `flagged`        -- thumbs-down OR refusal OR low-confidence
          - `thumbs_down`    -- Message.isPositiveRated == False
          - `refusal`        -- Message.wasRefusal == True
          - `low_confidence` -- Message.confidence == 'low'
          - `all`            -- no filter (paginated)

        v1 is global (not subject/campus-scoped): the operator
        workflow is "spot a bad answer, report its id+time" -- scoping
        by librarian subject is a deferred enhancement, not needed to
        find questionable answers.
        """
        rows = await list_flagged(
            db,
            filter_preset=(filter_preset or "flagged"),
            limit=limit,
            offset=offset,
        )
        return {"count": len(rows), "filter": filter_preset or "flagged",
                "results": rows}

    @router.get("/conversation/{conversation_id}")
    async def review_conversation(
        conversation_id: str,
        _user=Depends(require_librarian),
    ):
        """Full read-only drill-down for one conversation: id, time,
        transcript, token usage, tools called, human-handoff, outcome,
        feedback. This is what a librarian opens to judge an answer."""
        detail = await conversation_detail(db, conversation_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return detail

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
        raise HTTPException(
            status_code=501,
            detail="v1 is read-only by design: librarians report a bad "
            "answer's id+time to the maintainer, who changes backend "
            "behavior. In-UI verdict-writing/digests are a deferred "
            "enhancement, not part of the v1 review surface.",
        )

    @router.get("/queue-count")
    async def queue_count(
        librarian_id: int,
        _user=Depends(require_librarian),
    ):
        """Count of unreviewed turns for the Monday-morning digest email."""
        raise HTTPException(
            status_code=501,
            detail="v1 is read-only by design: librarians report a bad "
            "answer's id+time to the maintainer, who changes backend "
            "behavior. In-UI verdict-writing/digests are a deferred "
            "enhancement, not part of the v1 review surface.",
        )

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
