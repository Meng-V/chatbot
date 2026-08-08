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
    async def corrections_view(key: str = "", _user=Depends(require_librarian)):
        """Librarian-facing form + table. Open as
        /admin/corrections/view with the x-admin-token header, or
        ?key=... in the URL (same guard convention as
        /admin/review). The page calls the JSON endpoints via fetch.

        `key` is accepted so the page can render inside the shared admin
        shell with a working nav; the guard has already checked it."""
        from src.api.admin import admin_ui as ui

        return HTMLResponse(ui.page(
            "Corrections", _VIEW_BODY,
            current="/admin/corrections/view", key=key))

    return router


# The form, rebuilt 2026-08-08 after the operator reported it was too
# complicated to attempt ("特别复杂"). Three things were wrong with it.
#
# 1. It asked for `scope` next to `action`, a 4x4 grid of which only a
#    handful of cells are legal -- validate_correction rejects
#    blacklist_url+chunk and suppress+url, and apply_corrections never
#    READS scope except for pin (it matches on action+target alone).
#    scope=intent and scope=global are read nowhere at all, so choosing
#    them files a correction that silently never fires. So the field is
#    gone: the task determines the scope, and pin -- the one action where
#    scope is a real choice -- asks the question in words instead.
# 2. Both conditional fields were always visible and labelled with the
#    condition ("query_pattern (pin only)"), which reads as "most of this
#    form does not apply to you" no matter which task you picked.
# 3. The action names were the internal vocabulary. A librarian has no
#    reason to know that hiding a bad paragraph is called "suppress".
#
# It also silently dropped the `target` prefill that the ticket page has
# been sending since the ticket redesign (?target=<source_url>) -- the JS
# only ever read `key`. That handoff works now.
_VIEW_BODY = """
<h1>Corrections</h1>
<p class="lede">Change what the bot says without a deploy. Every
correction takes effect on the next question anyone asks, and expires by
itself after 180 days unless you extend it.</p>

<form id="f" class="card">
  <label for="task">What do you need to do?</label>
  <select id="task" name="task">
    <option value="blacklist_url">Stop the bot using a page — it is wrong, dead, or not ours to cite</option>
    <option value="pin">Send certain questions to a page first — the bot keeps missing it</option>
    <option value="replace">Fix the wording of one passage — the page is right but the bot quotes it badly</option>
    <option value="suppress">Hide one passage — it is wrong or out of date</option>
  </select>

  <div data-for="pin">
    <label for="pinby">What are you pinning?</label>
    <select id="pinby" name="pinby">
      <option value="url">A page, by its address</option>
      <option value="chunk">One passage, by its id</option>
    </select>
  </div>

  <div data-for="blacklist_url pin-url">
    <label for="t_url">Page address</label>
    <input id="t_url" name="t_url" type="text"
           placeholder="https://www.lib.miamioh.edu/...">
  </div>

  <div data-for="suppress replace pin-chunk">
    <label for="t_chunk">Passage id</label>
    <input id="t_chunk" name="t_chunk" type="text" placeholder="chunk id">
    <small class="dim">Shown under each cited source on the Flagged
    page.</small>
  </div>

  <div data-for="pin">
    <label for="query_pattern">Which questions should this fire on?</label>
    <input id="query_pattern" name="query_pattern"
           placeholder="printing|print|printer">
    <small class="dim">Words to look for in the student's question. Use
    <code>|</code> between alternatives. Case does not matter.</small>
  </div>

  <div data-for="replace">
    <label for="replacement">What the passage should say instead</label>
    <textarea id="replacement" name="replacement"></textarea>
  </div>

  <label for="created_by">Your email</label>
  <input id="created_by" name="created_by" type="email" required
         placeholder="you@miamioh.edu">

  <label for="reason">Why — what is wrong with the current answer?</label>
  <textarea id="reason" name="reason" required></textarea>

  <div class="acts">
    <button type="submit">File correction</button>
    <span id="msg"></span>
  </div>
</form>

<h2>Corrections in force</h2>
<table id="t"><thead><tr><th>what it does</th><th>applies to</th>
<th>why</th><th>filed by</th><th>expires</th><th>times used</th>
<th></th></tr></thead><tbody></tbody></table>

<script>
const qs = new URLSearchParams(location.search);
const token = qs.get("key") || "";
const H = {"Content-Type":"application/json","x-admin-token":token};

// Plain-language labels for the table, so the list reads the same way
// the form does rather than in the storage vocabulary.
const DOES = {
  blacklist_url: "never cite this page",
  suppress: "hide this passage",
  replace: "reword this passage",
  pin: "show first for matching questions",
};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));

const task = document.getElementById("task");
const pinby = document.getElementById("pinby");

// Show only the fields the chosen task actually uses. `pin` needs either
// the URL box or the chunk box depending on what is being pinned, hence
// the pin-url / pin-chunk tokens.
function sync() {
  const t = task.value;
  const on = new Set([t, t === "pin" ? "pin-" + pinby.value : ""]);
  document.querySelectorAll("[data-for]").forEach((el) => {
    const show = el.dataset.for.split(" ").some((tok) => on.has(tok));
    el.hidden = !show;
    el.querySelectorAll("input,textarea,select").forEach((f) => {
      f.disabled = !show;              // keeps hidden fields out of FormData
    });
  });
}
task.onchange = sync;
pinby.onchange = sync;

// Two pages hand off to this form: the ticket page arrives with the
// offending page address, the Flagged page with a passage id. Pick the
// box from the task so the value lands where it belongs.
const preAction = qs.get("action");
if (preAction && DOES[preAction]) task.value = preAction;
const preTarget = qs.get("target");
if (preTarget) {
  const box = scopeFor(task.value) === "url" ? "t_url" : "t_chunk";
  document.getElementById(box).value = preTarget;
}
sync();

async function load() {
  const r = await fetch("/admin/corrections", {headers: H});
  const d = await r.json();
  const tb = document.querySelector("#t tbody");
  tb.innerHTML = "";
  for (const c of (d.corrections || [])) {
    const applies = c.action === "pin" && c.query_pattern
      ? esc(c.target) + "<br><small>questions matching <code>"
        + esc(c.query_pattern) + "</code></small>"
      : esc(c.target);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(DOES[c.action] || c.action)}</td>
      <td style="max-width:280px;word-break:break-all">${applies}</td>
      <td>${esc(c.reason)}</td><td>${esc(c.created_by)}</td>
      <td>${esc((c.expires_at || "").slice(0, 10))}</td>
      <td>${esc(c.fire_count)}</td>
      <td><a class="btn ghost" href="#" data-id="${esc(c.id)}">remove</a></td>`;
    tb.appendChild(tr);
  }
  tb.querySelectorAll("[data-id]").forEach((b) => b.onclick = async (ev) => {
    ev.preventDefault();
    if (!confirm("Stop applying this correction?")) return;
    await fetch("/admin/corrections/" + b.dataset.id,
                {method: "DELETE", headers: H});
    load();
  });
}

// scope is derived, never asked. blacklist_url is url-scoped by rule;
// suppress and replace match on chunk id; pin is whichever the operator
// said they were pinning.
function scopeFor(t) {
  if (t === "blacklist_url") return "url";
  if (t === "pin") return pinby.value;
  return "chunk";
}

document.getElementById("f").onsubmit = async (e) => {
  e.preventDefault();
  const m = document.getElementById("msg");
  const t = task.value;
  const scope = scopeFor(t);
  const target = (scope === "url"
    ? document.getElementById("t_url").value
    : document.getElementById("t_chunk").value).trim();
  if (!target) {
    m.textContent = scope === "url"
      ? "Enter the page address." : "Enter the passage id.";
    m.className = "err";
    return;
  }
  const body = {
    action: t,
    scope: scope,
    target: target,
    reason: document.getElementById("reason").value,
    created_by: document.getElementById("created_by").value,
  };
  if (t === "pin") body.query_pattern = document.getElementById("query_pattern").value;
  if (t === "replace") body.replacement = document.getElementById("replacement").value;

  const r = await fetch("/admin/corrections",
                        {method: "POST", headers: H, body: JSON.stringify(body)});
  if (r.ok) {
    m.textContent = "Filed — live on the next question.";
    m.className = "ok";
    e.target.reset();
    sync();
    load();
  } else {
    const d = await r.json().catch(() => ({detail: r.status}));
    m.textContent = String(d.detail || "error");
    m.className = "err";
  }
};
load();
</script>"""


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
