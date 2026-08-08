"""
One-bookmark landing pages for the operator and for library staff.

Operator request 2026-07-17: "I can't remember all these URLs -- give me
one dashboard with links." Two audiences, two gates:

  GET /admin/          -- operator hub (ADMIN_API_TOKEN). Links to every
                          admin surface with the token already carried in
                          the query string, plus the shareable librarian
                          form link and the public probes.
  GET /librarian/      -- staff hub (LIBRARIAN_TICKET_CODE). The report
                          form plus a plain account of what happens after
                          they send it; new staff surfaces get added here
                          so staff only ever bookmark one URL.

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


def _card(title: str, desc: str, actions: str) -> str:
    return (f"<div class='card'><div class='q'>{ui.e(title)}</div>"
            f"<div><small class='dim'>{ui.e(desc)}</small></div>"
            f"<div class='acts'>{actions}</div></div>")


def _section(heading: str, blurb: str, cards: str) -> str:
    return (f"<h2>{ui.e(heading)}</h2>"
            f"<p class='sub'>{ui.e(blurb)}</p>{cards}")


def render_admin_hub(admin_key: str, librarian_code: str,
                     counts: "Optional[dict]" = None) -> str:
    """The operator dashboard.

    Rebuilt 2026-07-28: it used to be a flat list of card links, so the
    only way to answer "is there anything waiting for me?" was to open
    every page. Now the counts lead, colored by whether they need
    action, and the links live under them.

    Regrouped 2026-08-08, on the operator's report that the categories
    did not read clearly. Two things were wrong. The cards sat in one
    bucket called "Tools" that mixed working a queue, changing what the
    bot says, and watching it run -- three different jobs. And the stop
    button (/admin/service) had no link anywhere in the UI, so taking
    the bot out of service meant knowing the URL by heart. Sections are
    now named for the job, and service state leads the page.
    """
    from src.api.admin.killswitch_router import is_paused, pause_reason

    c = counts or {}
    k = f"?key={ui.e(admin_key)}"
    tickets = int(c.get("tickets") or 0)
    flagged = int(c.get("flagged") or 0)
    praised = int(c.get("praised") or 0)
    corrections = int(c.get("corrections") or 0)
    total_todo = tickets + flagged

    down = is_paused()
    banner = ""
    if down:
        banner = (
            "<div class='banner down'>"
            "<b>The bot is OUT OF SERVICE.</b>"
            "<div><small>Every question is being answered with a "
            "maintenance notice pointing patrons at Ask Us.</small></div>"
            f"<div class='acts'>{ui.action(f'/admin/service{k}', 'Put it back in service', primary=True)}</div>"
            f"<div style='margin-top:.5rem'><code>{ui.e(pause_reason())}</code></div>"
            "</div>"
        )

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

    # 1. The path a wrong answer travels: someone reports it -> you read
    #    the turn -> you change what the bot says. Same order on screen.
    wrong = _section(
        "When an answer is wrong",
        "Report comes in, you read the turn, you change what the bot says.",
        _card("Correction tickets",
              "Staff reports of wrong answers. Work them open → in "
              "progress → done; each links to the corrections tool.",
              ui.action(f"/admin/tickets/view{k}", "Open",
                        primary=tickets > 0))
        + _card("Flagged conversations",
                "Thumbs-down, refusals and low-confidence turns, with the "
                "patron's star rating and comment inline.",
                ui.action(f"/admin/review{k}", "Open", primary=flagged > 0))
        + _card("Manual corrections",
                "Suppress, replace, pin or blacklist a source. Takes "
                "effect on the next message — no deploy.",
                ui.action(f"/admin/corrections/view{k}", "Open")),
    )

    # 2. Everything about whether it is up and what it costs.
    running = _section(
        "Keep it running",
        "Is it up, what is it spending, and how to stop it.",
        _card("Service control",
              "The stop button. The bot keeps answering — with a "
              "maintenance notice — so the widget never shows a broken "
              "page. Survives a restart; recovery is one click."
              if not down else
              "The bot is out of service right now. Put it back here.",
              ui.action(f"/admin/service{k}",
                        "Put the bot back in service" if down
                        else "Take the bot out of service", primary=down))
        + _card("Cost dashboard",
                "Daily LLM spend by model and call site (nightly rollup).",
                ui.action(f"/admin/cost{k}", "Open"))
        + _card("Health checks",
                "Probes are public (no key) so an external monitor can "
                "poll them.",
                ui.action("/health/ready", "Dependency probes")
                + ui.action("/smoketest", "End-to-end smoke test")),
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
        f"{banner}<h1>Dashboard</h1><p class='lede'>{ui.e(headline)}</p>"
        f"<div class='stats'>{stats}</div>"
        f"{wrong}{running}{staff}"
        f"<p><small class='dim'>Bookmark this page — every link carries "
        f"your key.</small></p>"
    )
    return ui.page("Dashboard", body, current="/admin/", key=admin_key,
                   counts=counts)


def render_librarian_hub(code: str) -> str:
    """Staff hub. Deliberately has NO operator nav or counts.

    Changed 2026-08-08. The "Ask Us" card came out: it linked staff to
    the public Ask Us page, which is where staff already work -- it told
    them nothing they did not know and made the page look like a menu
    when it only ever had one thing to do on it.

    What went in instead answers the question staff actually keep
    asking, which is not "where do I report it" but "what does reporting
    it cost me". So the page now states plainly that the report is the
    whole job and nothing comes back to them.
    """
    k = f"?key={ui.e(code)}"
    report = (
        "<div class='card'><div class='q'>Report a wrong chatbot answer"
        "</div><div><small class='dim'>Paste what the bot said and what "
        "it should have said. Nothing else is required.</small></div>"
        f"<div class='acts'>"
        f"{ui.action(f'/librarian/ticket{k}', 'Open the form', primary=True)}"
        "</div></div>"
    )
    # Written flat and without an SLA on purpose: staff worry that a bad
    # bot answer becomes their follow-up work, and a promise we cannot
    # keep would confirm it. These four lines are all true today.
    after = (
        "<h2>What happens after you send it</h2>"
        "<p class='sub'>Reporting it is the whole job. Nothing comes back "
        "to you.</p>"
        "<div class='card'><ol style='margin:.2rem 0;padding-left:1.2rem'>"
        "<li>The report is stored and emailed to the maintainer as you "
        "send it.</li>"
        "<li>The maintainer fixes the source page, or overrides the "
        "answer directly.</li>"
        "<li>An override takes effect on the very next message &mdash; "
        "no deploy, no waiting for a release.</li>"
        "<li>You are not assigned anything and you do not need to follow "
        "up. If the fix needs something only you know, the maintainer "
        "emails you.</li>"
        "</ol></div>"
    )
    body = (
        "<h1>Smart Chatbot &mdash; staff hub</h1>"
        "<p class='lede'>Found the chatbot giving a wrong or outdated "
        "answer? Tell us here and the maintainer will fix it.</p>"
        f"{report}{after}"
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
