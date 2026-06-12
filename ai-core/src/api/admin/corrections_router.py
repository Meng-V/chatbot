"""
Admin CRUD for ManualCorrection rows (plan Op 2) -- the librarian
"fix a wrong answer without a deploy" workflow.

Endpoints (token-gated, fail-closed -- mounted only when ADMIN_API_TOKEN
is set):
  GET    /admin/corrections           -- list (active by default)
  POST   /admin/corrections           -- create (validated)
  PATCH  /admin/corrections/{id}      -- deactivate/reactivate, extend expiry, edit reason
  DELETE /admin/corrections/{id}      -- soft-delete (active=false; row kept for audit)
  GET    /admin/corrections/view      -- librarian-facing HTML form + table

Corrections take effect ON THE NEXT TURN: the serving path re-reads
active rows per request (verified on the prod execution path 2026-06-10).
Runtime application lives in src/synthesis/corrections.py.

The four actions, mapped to failure modes (plan Op 2):
  suppress       chunk is wrong/stale        -> retrieval drops that chunk_id
  replace        page itself is wrong        -> chunk text swapped for the fix
  pin            bot misses canonical page   -> chunk pinned to rank 1 for a query regex
  blacklist_url  bot cited a bad/dead URL    -> URL filtered + validator rejects it
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


def _parse_expiry(raw: Any) -> Optional[datetime]:
    """ISO string / datetime -> aware datetime (None passes through)."""
    if raw is None or isinstance(raw, datetime):
        return raw
    dt = datetime.fromisoformat(str(raw))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _bust_serving_cache() -> None:
    """Invalidate the serving-side TTL cache so a write is live on the
    very next bot turn in this process (cross-process workers converge
    within CACHE_TTL_SECONDS). Import is local + failure-tolerant so the
    admin API never 500s because of the serving layer."""
    try:
        from src.database.corrections_adapter import _invalidate_module_cache
        _invalidate_module_cache()
    except Exception:  # pragma: no cover
        pass


def _row(r: Any) -> dict:
    """Prisma ManualCorrection -> JSON-safe dict (snake_case)."""
    return {
        "id": r.id,
        "scope": r.scope,
        "target": r.target,
        "action": r.action,
        "replacement": r.replacement,
        "query_pattern": r.queryPattern,
        "reason": r.reason,
        "created_by": r.createdBy,
        "created_at": r.createdAt.isoformat() if r.createdAt else None,
        "expires_at": r.expiresAt.isoformat() if r.expiresAt else None,
        "active": r.active,
        "fire_count": r.fireCount,
    }


def build_corrections_router(deps: dict) -> Any:
    """Build the FastAPI router. `deps` = {"db": prisma_client,
    "require_librarian": token-dependency} (same shape as reviews_router)."""
    try:
        from fastapi import APIRouter, Depends, HTTPException  # type: ignore
        from fastapi.responses import HTMLResponse  # type: ignore
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
        where = {"active": True} if active_only else {}
        rows = await db.manualcorrection.find_many(
            where=where, order={"createdAt": "desc"}, take=200,
        )
        return {"corrections": [_row(r) for r in rows], "count": len(rows)}

    @router.post("", status_code=201)
    async def create_correction(
        payload: dict,
        _user=Depends(require_librarian),
    ):
        try:
            c = CorrectionInput(
                scope=payload["scope"],
                target=payload["target"],
                action=payload["action"],
                reason=payload.get("reason", ""),
                created_by=payload.get("created_by", ""),
                replacement=payload.get("replacement") or None,
                query_pattern=payload.get("query_pattern") or None,
                expires_at=_parse_expiry(payload.get("expires_at")),
            )
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"missing field {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"bad expires_at: {e}")
        err = validate_correction(c)
        if err:
            raise HTTPException(status_code=400, detail=err)
        row = await db.manualcorrection.create(data={
            "scope": c.scope,
            "target": c.target,
            "action": c.action,
            "replacement": c.replacement,
            "queryPattern": c.query_pattern,
            "reason": c.reason,
            "createdBy": c.created_by,
            "expiresAt": c.expires_at or default_expiry(),
        })
        _bust_serving_cache()
        return {"created": _row(row), "note": "takes effect on the next bot turn"}

    @router.patch("/{correction_id}")
    async def update_correction(
        correction_id: str,
        payload: dict,
        _user=Depends(require_librarian),
    ):
        """Deactivate/reactivate, extend expiry, or update the reason."""
        existing = await db.manualcorrection.find_unique(
            where={"id": correction_id})
        if existing is None:
            raise HTTPException(status_code=404, detail="no such correction")
        data: dict = {}
        if "active" in payload:
            data["active"] = bool(payload["active"])
        if payload.get("expires_at"):
            try:
                data["expiresAt"] = _parse_expiry(payload["expires_at"])
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"bad expires_at: {e}")
        if payload.get("reason"):
            data["reason"] = str(payload["reason"])
        if not data:
            raise HTTPException(
                status_code=400,
                detail="nothing to update (allowed: active, expires_at, reason)")
        row = await db.manualcorrection.update(
            where={"id": correction_id}, data=data)
        _bust_serving_cache()
        return {"updated": _row(row)}

    @router.delete("/{correction_id}")
    async def deactivate_correction(
        correction_id: str,
        _user=Depends(require_librarian),
    ):
        """Soft-delete: set active=false. Row stays for audit."""
        existing = await db.manualcorrection.find_unique(
            where={"id": correction_id})
        if existing is None:
            raise HTTPException(status_code=404, detail="no such correction")
        row = await db.manualcorrection.update(
            where={"id": correction_id}, data={"active": False})
        _bust_serving_cache()
        return {"deactivated": _row(row)}

    @router.get("/view", response_class=HTMLResponse)
    async def corrections_view(_user=Depends(require_librarian)):
        """Librarian-facing form + table. Open as
        /admin/corrections/view with the x-admin-token header, or
        ?key=... in the URL (same guard convention as
        /admin/review). The page calls the JSON endpoints via fetch."""
        return HTMLResponse(_VIEW_HTML)

    return router


_VIEW_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Manual Corrections</title>
<style>
 body{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}
 h1{font-size:1.3rem} .hint{color:#555;font-size:.9rem;margin-bottom:1rem}
 form{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:.6rem;
      border:1px solid #ccc;border-radius:8px;padding:1rem;margin-bottom:1.5rem}
 label{font-size:.8rem;color:#333;display:block}
 input,select,textarea{width:100%;padding:.4rem;font-size:.9rem;box-sizing:border-box}
 textarea{grid-column:1/-1;min-height:60px}
 button{padding:.5rem 1rem;cursor:pointer}
 table{border-collapse:collapse;width:100%;font-size:.85rem}
 th,td{border:1px solid #ddd;padding:.4rem;text-align:left;vertical-align:top}
 th{background:#f5f5f5} .ok{color:#0a0} .err{color:#c00;font-weight:600}
 .deact{color:#c00;cursor:pointer;background:none;border:1px solid #c00;border-radius:4px}
</style></head><body>
<h1>Manual Corrections</h1>
<p class="hint">Fix a wrong bot answer without a deploy. Takes effect on the
next question anyone asks. <b>suppress</b>=hide a bad chunk ·
<b>replace</b>=swap a chunk's text · <b>pin</b>=force a page to rank #1 for
matching questions · <b>blacklist_url</b>=never cite this URL again.
All corrections auto-expire in 180 days unless extended.</p>
<form id="f">
  <div><label>action</label><select name="action">
    <option>blacklist_url</option><option>suppress</option>
    <option>replace</option><option>pin</option></select></div>
  <div><label>scope</label><select name="scope">
    <option>url</option><option>chunk</option>
    <option>intent</option><option>global</option></select></div>
  <div><label>target (the URL / chunk_id / intent)</label>
    <input name="target" required placeholder="https://... or chunk id"></div>
  <div><label>your email (audit trail, required)</label>
    <input name="created_by" required placeholder="you@miamioh.edu"></div>
  <div><label>query_pattern (pin only)</label>
    <input name="query_pattern" placeholder="regex, e.g. printing|print"></div>
  <div><label>replacement text (replace only)</label>
    <input name="replacement"></div>
  <textarea name="reason" required
    placeholder="reason (required) -- what is wrong and why"></textarea>
  <button type="submit">File correction</button>
  <span id="msg"></span>
</form>
<table id="t"><thead><tr><th>action</th><th>scope</th><th>target</th>
<th>reason</th><th>by</th><th>expires</th><th>fired</th><th></th></tr></thead>
<tbody></tbody></table>
<script>
const token = new URLSearchParams(location.search).get("key") || "";
const H = {"Content-Type":"application/json","x-admin-token":token};
async function load(){
  const r = await fetch("/admin/corrections",{headers:H});
  const d = await r.json();
  const tb = document.querySelector("#t tbody"); tb.innerHTML = "";
  for (const c of (d.corrections||[])) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${c.action}</td><td>${c.scope}</td>
      <td style="max-width:260px;word-break:break-all">${c.target}</td>
      <td>${c.reason}</td><td>${c.created_by}</td>
      <td>${(c.expires_at||"").slice(0,10)}</td><td>${c.fire_count}</td>
      <td><button class="deact" data-id="${c.id}">deactivate</button></td>`;
    tb.appendChild(tr);
  }
  tb.querySelectorAll(".deact").forEach(b=>b.onclick=async()=>{
    if(!confirm("Deactivate this correction?"))return;
    await fetch("/admin/corrections/"+b.dataset.id,{method:"DELETE",headers:H});
    load();
  });
}
document.getElementById("f").onsubmit = async (e)=>{
  e.preventDefault();
  const fd = Object.fromEntries(new FormData(e.target).entries());
  const r = await fetch("/admin/corrections",{method:"POST",headers:H,
    body:JSON.stringify(fd)});
  const m = document.getElementById("msg");
  if(r.ok){ m.textContent="✓ filed -- live on the next question";
    m.className="ok"; e.target.reset(); load(); }
  else { const d = await r.json().catch(()=>({detail:r.status}));
    m.textContent="✗ "+(d.detail||"error"); m.className="err"; }
};
load();
</script></body></html>"""


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
