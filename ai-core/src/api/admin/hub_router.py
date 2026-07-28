"""
One-bookmark landing pages for the operator and for library staff.

Operator request 2026-07-17: "I can't remember all these URLs -- give me
one dashboard with links." Two audiences, two gates:

  GET /admin/          -- operator hub (ADMIN_API_TOKEN). Links to every
                          admin surface with the token already carried in
                          the query string, plus the shareable librarian
                          form link and the public probes.
  GET /librarian/      -- staff hub (LIBRARIAN_TICKET_CODE). Today that's
                          the correction-ticket form plus the public
                          library help links; new staff surfaces get added
                          here so staff only ever bookmark one URL.

Same zero-dependency server-rendered HTML approach as the other admin
views; the only interpolated secrets are the ones the visitor already
presented (their own key).
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001
    Request = Any  # type: ignore


from src.api.admin import admin_ui as ui


def render_admin_hub(admin_key: str, librarian_code: str,
                     counts: "Optional[dict]" = None) -> str:
    """The operator dashboard.

    Rebuilt 2026-07-28: it used to be a flat list of card links, so the
    only way to answer "is there anything waiting for me?" was to open
    every page. Now the counts lead, colored by whether they need
    action, and the links live under them.
    """
    c = counts or {}
    k = f"?key={ui.e(admin_key)}"
    tickets = int(c.get("tickets") or 0)
    flagged = int(c.get("flagged") or 0)
    praised = int(c.get("praised") or 0)
    corrections = int(c.get("corrections") or 0)
    total_todo = tickets + flagged

    stats = (
        ui.stat_card(f"/admin/tickets/view{k}", tickets,
                     "staff tickets to work", needs=tickets > 0)
        + ui.stat_card(f"/admin/review{k}", flagged,
                       "flagged turns to review", needs=flagged > 0)
        + ui.stat_card(f"/admin/review?filter=thumbs_up&key={ui.e(admin_key)}",
                       praised, "thumbs-up to skim")
        + ui.stat_card(f"/admin/corrections/view{k}", corrections,
                       "corrections live now")
    )
    headline = (
        "Nothing needs you right now."
        if total_todo == 0 else
        f"{total_todo} item{'s' if total_todo != 1 else ''} waiting on you."
    )

    tools = "".join(
        f"<div class='card'><div class='q'>{ui.e(title)}</div>"
        f"<div><small class='dim'>{ui.e(desc)}</small></div>"
        f"<div class='acts'>{ui.action(href, 'Open', primary=primary)}</div>"
        f"</div>"
        for href, title, desc, primary in [
            (f"/admin/tickets/view{k}", "Correction tickets",
             "Staff reports of wrong answers. Work them open → in "
             "progress → done; each links to the corrections tool.",
             tickets > 0),
            (f"/admin/review{k}", "Flagged conversations",
             "Thumbs-down, refusals and low-confidence turns, with the "
             "patron's star rating and comment inline.", flagged > 0),
            (f"/admin/corrections/view{k}", "Manual corrections",
             "Suppress, replace, pin or blacklist a source. Takes effect "
             "on the next message — no deploy.", False),
            (f"/admin/cost{k}", "Cost dashboard",
             "Daily LLM spend by model and call site (nightly rollup).",
             False),
        ]
    )

    health = (
        "<div class='card'><div class='q'>Health checks</div>"
        "<div class='acts'>"
        + ui.action("/health/ready", "Dependency probes")
        + ui.action("/smoketest", "End-to-end smoke test")
        + "</div><div><small class='dim'>Probes are public (no key) so an "
          "external monitor can poll them.</small></div></div>"
    )

    staff_link = (
        f"/librarian/?key={ui.e(librarian_code)}" if librarian_code else ""
    )
    staff = (
        "<h2>Share with library staff</h2>"
        + (f"<div class='card'><div class='q'>Staff hub</div>"
           f"<div><small class='dim'>Send library staff THIS link — it "
           f"carries their access code and shows no admin surfaces.</small>"
           f"</div><div class='acts'>"
           f"{ui.action(staff_link, 'Open staff hub')}</div>"
           f"<div style='margin-top:.5rem'><code>{ui.e(staff_link)}</code>"
           f"</div></div>"
           if staff_link else
           "<div class='note'>LIBRARIAN_TICKET_CODE is not set — the "
           "staff form is closed.</div>")
    )

    body = (
        f"<h1>Dashboard</h1><p class='lede'>{ui.e(headline)}</p>"
        f"<div class='stats'>{stats}</div>"
        f"<h2>Tools</h2>{tools}{health}{staff}"
        f"<p><small class='dim'>Bookmark this page — every link carries "
        f"your key.</small></p>"
    )
    return ui.page("Dashboard", body, current="/admin/", key=admin_key,
                   counts=counts)


def render_librarian_hub(code: str) -> str:
    """Staff hub. Deliberately has NO operator nav or counts."""
    k = f"?key={ui.e(code)}"
    cards = "".join(
        f"<div class='card'><div class='q'>{ui.e(title)}</div>"
        f"<div><small class='dim'>{ui.e(desc)}</small></div>"
        f"<div class='acts'>{ui.action(href, label, primary=primary)}</div>"
        f"</div>"
        for href, title, desc, label, primary in [
            (f"/librarian/ticket{k}", "Report a wrong chatbot answer",
             "Goes straight to the maintainer — stored and emailed.",
             "Open the form", True),
            ("https://www.lib.miamioh.edu/research/research-support/ask/",
             "Ask Us", "For questions the bot should hand off to a person.",
             "Ask Us", False),
        ]
    )
    body = (
        "<h1>Smart Chatbot &mdash; staff hub</h1>"
        "<p class='lede'>Found the chatbot giving a wrong or outdated "
        "answer? Tell us here and the maintainer will fix it.</p>"
        f"{cards}"
        "<p><small class='dim'>Bookmark this page &mdash; the links carry "
        "the access code.</small></p>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Staff hub — Miami University Libraries</title>"
        f"<style>{ui.STYLE}</style></head><body>"
        "<header class='top'><div class='wrap'><b>Smart Chatbot</b>"
        "<span style='opacity:.85'>library staff</span></div></header>"
        f"<main>{body}</main></body></html>"
    )


def build_hub_router(deps: dict):
    from fastapi import APIRouter, HTTPException  # type: ignore
    from fastapi.responses import HTMLResponse  # type: ignore

    admin_token: str = (deps.get("admin_token") or "").strip()
    librarian_code: str = (deps.get("librarian_code") or "").strip()
    db = deps.get("db")
    router = APIRouter(tags=["hub"])

    @router.get("/admin/", response_class=HTMLResponse)
    @router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_hub(request: Request):
        supplied = request.query_params.get("key", "")
        if not admin_token or supplied != admin_token:
            raise HTTPException(status_code=401, detail="admin token required")
        counts = None
        if db is not None:
            from src.api.admin.review_queries import dashboard_counts
            counts = await dashboard_counts(db)
        return HTMLResponse(
            render_admin_hub(supplied, librarian_code, counts))

    @router.get("/librarian/", response_class=HTMLResponse)
    @router.get("/librarian", response_class=HTMLResponse, include_in_schema=False)
    async def librarian_hub(request: Request):
        supplied = request.query_params.get("key", "")
        if not librarian_code or supplied != librarian_code:
            raise HTTPException(
                status_code=401,
                detail="Missing or wrong access code. Ask the library web "
                       "services team for the staff-hub link.",
            )
        return HTMLResponse(render_librarian_hub(supplied))

    return router
