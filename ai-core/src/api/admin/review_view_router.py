"""
Server-rendered, zero-dependency HTML review surface (plan Op 1 MVP).

The plan's Op 1 MVP is explicitly "Metabase/Retool + saved queries"
before a custom React SPA. We don't have Metabase to stand up, and a
React admin app is large + can't be verified offline -- so this is
the equivalent with NO new infra: two FastAPI routes returning plain
HTML that read the existing tables via review_queries. A librarian
opens a bookmarked link, sees the flagged conversations, clicks one,
reads id / time / full transcript / token usage / tools / handoff /
outcome, and reports the id+time to the maintainer.

SECURITY (this exposes raw conversation logs = user input + PII):
  * `make_token_guard`: fail-CLOSED. Requires the ADMIN_API_TOKEN
    secret via `X-Admin-Token` header OR `?key=` query param (the
    query param lets a librarian use a bookmarked browser link).
    main.py mounts the whole admin surface ONLY when ADMIN_API_TOKEN
    is set, so a misconfigured deploy can't leak conversation logs.
  * Every interpolated value is html.escape()'d. Conversation content
    is attacker-controllable user text rendered in the librarian's
    browser -- unescaped it would be stored XSS against staff.
"""

from __future__ import annotations

import html
from typing import Any

from src.api.admin.review_queries import conversation_detail, list_flagged

# Module-level so FastAPI/Starlette can resolve the `request: Request`
# annotation on the guard + handlers (it resolves annotations against
# THIS module's globals -- a function-local import is invisible to it
# and FastAPI then mis-treats `request` as a query param). starlette is
# always installed alongside fastapi; Any fallback keeps the module
# importable in a no-fastapi sandbox (router returns a placeholder
# there anyway).
try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001
    Request = Any  # type: ignore


def make_token_guard(expected_token: str):
    """FastAPI dependency: 401 unless the request carries the admin
    token. Fail-closed (empty expected_token -> always 401)."""
    from fastapi import HTTPException  # type: ignore

    async def guard(request: Request) -> None:
        supplied = (
            request.headers.get("x-admin-token")
            or request.query_params.get("key")
            or ""
        )
        if not expected_token or supplied != expected_token:
            raise HTTPException(status_code=401, detail="admin auth required")

    return guard


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


_STYLE = (
    "body{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#111}"
    "table{border-collapse:collapse;width:100%}"
    "td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;"
    "vertical-align:top}th{background:#f4f4f4}"
    "a{color:#06c;text-decoration:none}a:hover{text-decoration:underline}"
    ".tag{display:inline-block;padding:1px 6px;border-radius:3px;"
    "background:#eee;font-size:12px}.down{background:#fdd}"
    ".refuse{background:#fe8}.role{font-weight:600}"
    "pre{white-space:pre-wrap;background:#fafafa;padding:8px;"
    "border:1px solid #eee;border-radius:4px;margin:4px 0}"
)


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )


def build_review_view_router(deps: dict) -> Any:
    """`deps` = {"db": prisma, "guard": token-dependency}."""
    try:
        from fastapi import APIRouter, Depends  # type: ignore
        from fastapi.responses import HTMLResponse  # type: ignore
    except ImportError:
        class _P:
            prefix = "/admin/review"
            routes: list = []
        return _P()

    router = APIRouter(tags=["admin"])
    db = deps["db"]
    guard = deps["guard"]

    @router.get("/admin/review", response_class=HTMLResponse)
    async def review_list(
        filter: str = "flagged",
        limit: int = 50,
        key: str = "",
        _g=Depends(guard),
    ) -> Any:
        rows = await list_flagged(db, filter_preset=filter, limit=limit)
        opts = "".join(
            f"<a class='tag' href='/admin/review?filter={f}"
            f"{('&key=' + _e(key)) if key else ''}'>{f}</a> "
            for f in ("flagged", "thumbs_down", "refusal",
                      "low_confidence", "all")
        )
        trs = []
        for r in rows:
            cid = r.get("conversation_id") or ""
            flags = []
            if r.get("is_positive_rated") is False:
                flags.append("<span class='tag down'>thumbs-down</span>")
            if r.get("was_refusal"):
                flags.append(
                    f"<span class='tag refuse'>refusal:"
                    f"{_e(r.get('refusal_trigger'))}</span>")
            if r.get("confidence") == "low":
                flags.append("<span class='tag'>low-conf</span>")
            link = (
                f"/admin/review/{_e(cid)}"
                + (f"?key={_e(key)}" if key else "")
            )
            trs.append(
                f"<tr><td>{_e(r.get('time'))}</td>"
                f"<td>{_e(r.get('role'))}</td>"
                f"<td>{_e(r.get('preview'))}</td>"
                f"<td>{' '.join(flags)}</td>"
                f"<td><a href='{link}'>open</a><br>"
                f"<small>{_e(cid)}</small></td></tr>"
            )
        body = (
            f"<h2>Review queue &mdash; {len(rows)} flagged "
            f"(filter: {_e(filter)})</h2><p>{opts}</p>"
            f"<table><tr><th>time</th><th>role</th><th>preview</th>"
            f"<th>flags</th><th>conversation</th></tr>"
            f"{''.join(trs) or '<tr><td colspan=5>none</td></tr>'}"
            f"</table>"
        )
        return HTMLResponse(_page("Review queue", body))

    @router.get("/admin/review/{conversation_id}",
                response_class=HTMLResponse)
    async def review_detail(
        conversation_id: str,
        key: str = "",
        _g=Depends(guard),
    ) -> Any:
        d = await conversation_detail(db, conversation_id)
        back = "/admin/review" + (f"?key={_e(key)}" if key else "")
        if d is None:
            return HTMLResponse(
                _page("Not found",
                      f"<p>conversation not found.</p>"
                      f"<a href='{back}'>&larr; back</a>"),
                status_code=404,
            )
        msgs = "".join(
            f"<div><span class='role'>{_e(m['role'])}</span> "
            f"<small>{_e(m['time'])}</small>"
            + (" <span class='tag refuse'>refusal:"
               f"{_e(m['refusal_trigger'])}</span>" if m['was_refusal']
               else "")
            + (" <span class='tag down'>thumbs-down</span>"
               if m['is_positive_rated'] is False else "")
            + f"<pre>{_e(m['content'])}</pre></div>"
            for m in d["messages"]
        )
        toks = "".join(
            f"<tr><td>{_e(t['model'])}</td><td>{_e(t['call_site'])}</td>"
            f"<td>{_e(t['prompt'])}</td><td>{_e(t['cached_input'])}</td>"
            f"<td>{_e(t['completion'])}</td><td>{_e(t['total'])}</td></tr>"
            for t in d["token_usage"]
        ) or "<tr><td colspan=6>none</td></tr>"
        tools = "".join(
            f"<tr><td>{_e(t['agent'])}</td><td>{_e(t['tool'])}</td>"
            f"<td>{_e(t['success'])}</td><td>{_e(t['ms'])}ms</td>"
            f"<td>{_e(t['time'])}</td></tr>"
            for t in d["tools_called"]
        ) or "<tr><td colspan=5>none</td></tr>"
        ho = ", ".join(
            f"{_e(h['trigger'])} @ {_e(h['time'])}"
            for h in d["human_handoff"]
        ) or "none"
        o = d["outcome"]
        fb = d["feedback"]
        body = (
            f"<p><a href='{back}'>&larr; back to queue</a></p>"
            f"<h2>Conversation {_e(d['conversation_id'])}</h2>"
            f"<p><b>created:</b> {_e(d['created_at'])} &nbsp; "
            f"<b>updated:</b> {_e(d['updated_at'])} &nbsp; "
            f"<b>token total:</b> {_e(d['token_total'])} &nbsp; "
            f"<b>human-handoff:</b> {ho}</p>"
            f"<p><b>outcome:</b> refusal={_e(o['was_refusal'])} "
            f"trigger={_e(o['refusal_trigger'])} "
            f"confidence={_e(o['confidence'])} &nbsp; "
            f"<b>feedback:</b> "
            + (f"rating={_e(fb['rating'])} note={_e(fb['comment'])}"
               if fb else "none")
            + f"</p><h3>Transcript</h3>{msgs}"
            f"<h3>Token usage</h3><table><tr><th>model</th>"
            f"<th>call_site</th><th>prompt</th><th>cached</th>"
            f"<th>completion</th><th>total</th></tr>{toks}</table>"
            f"<h3>Tools called</h3><table><tr><th>agent</th>"
            f"<th>tool</th><th>ok</th><th>ms</th><th>time</th></tr>"
            f"{tools}</table>"
        )
        return HTMLResponse(_page(f"Conversation {conversation_id}", body))

    return router


__all__ = ["build_review_view_router", "make_token_guard"]
