"""
Admin CRUD for ManualCorrection rows (plan Op 2).

Endpoints:
  GET    /admin/corrections        -- list active corrections
  POST   /admin/corrections        -- create a new correction
  PATCH  /admin/corrections/{id}   -- deactivate or extend expiry
  DELETE /admin/corrections/{id}   -- soft-delete (active=false)

The four actions (suppress / replace / pin / blacklist) are validated
shape-wise here; runtime application happens in
src/synthesis/corrections.py.

See plan: Operations -> Op 2 "Content correction workflow".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.synthesis.corrections import CorrectionAction, CorrectionScope


VALID_ACTIONS: frozenset[CorrectionAction] = frozenset(
    ["suppress", "replace", "pin", "blacklist_url"]
)
VALID_SCOPES: frozenset[CorrectionScope] = frozenset(
    ["url", "chunk", "intent", "global"]
)

DEFAULT_EXPIRY_DAYS = 180
"""Corrections expire in 6 months by default. Librarians get reminded
to renew or drop them; stale ones fall off automatically."""


@dataclass(frozen=True)
class CorrectionInput:
    """Validated correction creation payload."""

    scope: CorrectionScope
    target: str
    action: CorrectionAction
    reason: str
    created_by: str
    replacement: Optional[str] = None
    query_pattern: Optional[str] = None
    expires_at: Optional[datetime] = None


def validate_correction(c: CorrectionInput) -> Optional[str]:
    """Return None if the correction is valid, else a reason string.

    Rules:
      - action must be one of VALID_ACTIONS
      - scope must be one of VALID_SCOPES
      - reason is required (no anonymous corrections)
      - created_by is required (audit trail)
      - replace actions require a replacement
      - pin actions require a query_pattern
      - blacklist_url requires scope=url
    """
    if c.action not in VALID_ACTIONS:
        return f"action must be one of {sorted(VALID_ACTIONS)}"
    if c.scope not in VALID_SCOPES:
        return f"scope must be one of {sorted(VALID_SCOPES)}"
    if not c.reason.strip():
        return "reason is required"
    if not c.created_by.strip():
        return "created_by is required"
    if c.action == "replace" and not c.replacement:
        return "replace action requires a replacement"
    if c.action == "pin" and not c.query_pattern:
        return "pin action requires a query_pattern"
    if c.action == "blacklist_url" and c.scope != "url":
        return "blacklist_url action requires scope=url"
    if c.action == "suppress" and c.scope != "chunk":
        return "suppress action requires scope=chunk"
    return None


def default_expiry(now: Optional[datetime] = None) -> datetime:
    """Default expires_at = now + 180 days. Kept as a helper rather
    than baked into the endpoint so tests can pass a fixed `now`.
    """
    now = now or datetime.now(timezone.utc)
    return now + timedelta(days=DEFAULT_EXPIRY_DAYS)


def build_corrections_router(deps: dict) -> Any:
    """Build the FastAPI router. See reviews_router for the pattern."""
    try:
        from fastapi import APIRouter, Depends, HTTPException  # type: ignore
    except ImportError:
        return _Placeholder("/admin/corrections")

    router = APIRouter(prefix="/admin/corrections", tags=["admin"])
    db = deps["db"]
    require_librarian = deps.get("require_librarian", lambda: None)

    @router.get("")
    async def list_corrections(
        active_only: bool = True,
        _user=Depends(require_librarian),
    ):
        """List corrections. Default active-only; pass active_only=false
        to see expired / deactivated ones for audit."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.post("")
    async def create_correction(
        payload: dict,
        _user=Depends(require_librarian),
    ):
        c = CorrectionInput(
            scope=payload["scope"],
            target=payload["target"],
            action=payload["action"],
            reason=payload["reason"],
            created_by=payload["created_by"],
            replacement=payload.get("replacement"),
            query_pattern=payload.get("query_pattern"),
            expires_at=payload.get("expires_at"),
        )
        err = validate_correction(c)
        if err:
            raise HTTPException(status_code=400, detail=err)
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.patch("/{correction_id}")
    async def update_correction(
        correction_id: int,
        payload: dict,
        _user=Depends(require_librarian),
    ):
        """Deactivate, extend expiry, or update the reason."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    @router.delete("/{correction_id}")
    async def deactivate_correction(
        correction_id: int,
        _user=Depends(require_librarian),
    ):
        """Soft-delete: set active=false. Row stays for audit."""
        raise HTTPException(status_code=501, detail="Not yet wired (week 7)")

    return router


class _Placeholder:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = [
    "CorrectionInput",
    "DEFAULT_EXPIRY_DAYS",
    "VALID_ACTIONS",
    "VALID_SCOPES",
    "build_corrections_router",
    "default_expiry",
    "validate_correction",
]
