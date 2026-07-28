"""
Librarian correction tickets -- "the bot answered this wrong" reports.

Why: librarians who spot a wrong answer had no channel to report it
(operator request 2026-07-16). This gives them a bookmarkable form;
every submission is stored in Postgres (CorrectionTicket) AND emailed
to the operator via src/observability/alerting.py, so nothing depends
on the operator polling a dashboard.

Surfaces:
  GET  /librarian/ticket        -- the submission form (librarian-facing)
  POST /librarian/ticket        -- submit; stores + emails; confirmation page
  GET  /admin/tickets/view      -- operator list, newest first (admin token)
  GET  /admin/tickets/{id}/mark -- flip status open->reviewed->done (admin token)

SECURITY:
  * The librarian surface is gated by LIBRARIAN_TICKET_CODE (a shared
    access code the operator distributes to library staff). Fail-closed:
    main.py mounts it only when the code is set, and the guard 401s on
    a missing/wrong code. The code rides `?key=` so the form can be a
    browser bookmark -- same pattern as the admin token guard.
  * The admin list is behind the existing ADMIN_API_TOKEN guard.
  * Every interpolated value is html.escape()'d -- ticket content is
    staff-typed but may quote attacker-influenced bot output.
  * The email send NEVER blocks ticket creation: the row is written
    first; a failed email is recorded as emailSent=false and shows up
    in the admin list so it can't get lost silently.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.api.admin import admin_ui as ui

try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001 -- keep importable in a no-fastapi sandbox
    Request = Any  # type: ignore

logger = logging.getLogger("ticket_router")


def key_present(request) -> bool:
    return bool(request.query_params.get("key"))

_MAX_FIELD = 8000  # hard cap per field; keeps a paste-bomb out of the DB

_FORM_FIELDS = (
    # (form name, label, required, textarea?)
    ("librarian_name", "Your name", True, False),
    ("librarian_email", "Your Miami email", True, False),
    ("question", "What the patron asked", True, True),
    ("bot_answer", "What the chatbot answered (paste it)", True, True),
    ("expected_answer", "What it SHOULD say / where the correct info lives", True, True),
    ("source_url", "Supporting URL (optional)", False, False),
)


def validate_ticket(form: dict) -> tuple[dict, list[str]]:
    """Pure validation: returns (clean_values, errors). No I/O."""
    clean: dict = {}
    errors: list[str] = []
    for name, label, required, _ta in _FORM_FIELDS:
        val = str(form.get(name) or "").strip()
        if len(val) > _MAX_FIELD:
            val = val[:_MAX_FIELD]
        if required and not val:
            errors.append(f"“{label}” is required.")
        clean[name] = val
    email = clean.get("librarian_email", "")
    if email and ("@" not in email or " " in email):
        errors.append("Please give a valid email address.")
    url = clean.get("source_url", "")
    if url and not url.lower().startswith(("http://", "https://")):
        errors.append("The supporting URL must start with http:// or https://.")
    return clean, errors


def ticket_email_body(t: dict) -> str:
    """Plain-text operator email for one ticket. Pure."""
    return (
        f"New chatbot correction ticket ({t.get('id', '?')})\n"
        f"From: {t.get('librarian_name')} <{t.get('librarian_email')}>\n"
        f"\n"
        f"PATRON ASKED:\n{t.get('question')}\n"
        f"\n"
        f"BOT ANSWERED:\n{t.get('bot_answer')}\n"
        f"\n"
        f"SHOULD BE:\n{t.get('expected_answer')}\n"
        f"\n"
        f"Supporting URL: {t.get('source_url') or '(none)'}\n"
        f"\n"
        f"Review queue: /admin/tickets/view\n"
    )


# --- HTML rendering (zero-dependency, same approach as review_view) -------

def render_form(key: str, values: dict | None = None,
                errors: list[str] | None = None) -> str:
    v = values or {}
    err_html = ""
    if errors:
        items = "".join(f"<li>{ui.e(x)}</li>" for x in errors)
        err_html = (f"<div class='card attn'><b>Please fix:</b>"
                    f"<ul>{items}</ul></div>")
    rows = []
    for name, label, required, textarea in _FORM_FIELDS:
        val = ui.e(v.get(name, ""))
        req = " *" if required else ""
        rows.append(f"<label for='{name}'>{ui.e(label)}{req}</label>")
        if textarea:
            rows.append(f"<textarea id='{name}' name='{name}'>{val}</textarea>")
        else:
            rows.append(
                f"<input type='text' id='{name}' name='{name}' value='{val}'>")
    body = (
        "<h1>Report a wrong chatbot answer</h1>"
        "<p class='lede'>Spotted the Smart Chatbot giving a wrong or "
        "outdated answer? Describe it below &mdash; the report goes straight "
        "to the maintainer (<a href='mailto:qum@miamioh.edu'>qum@miamioh.edu"
        "</a>).</p>"
        f"{err_html}"
        "<div class='card'><form method='post'>"
        f"<input type='hidden' name='key' value='{ui.e(key)}'>"
        f"{''.join(rows)}"
        "<div style='margin-top:1.2rem'>"
        "<button type='submit'>Submit report</button></div>"
        "</form></div>"
    )
    return _staff_page("Report a wrong answer", body)


def render_thanks(ticket_id: str, email_sent: bool, key: str) -> str:
    mail_note = (
        "The maintainer has been emailed."
        if email_sent else
        "The report is saved; the email notification could not be sent "
        "right now, but the maintainer will still see it in the queue."
    )
    body = (
        "<h1>Thank you!</h1>"
        f"<div class='card'><p>Your report was received "
        f"(id <code>{ui.e(ticket_id)}</code>). {ui.e(mail_note)}</p>"
        f"<div class='acts'>"
        f"{ui.action('/librarian/ticket?key=' + ui.e(key), 'Report another', primary=True)}"
        f"{ui.action('/librarian/?key=' + ui.e(key), 'Back to staff hub')}"
        f"</div></div>"
    )
    return _staff_page("Report received", body)


def _staff_page(title: str, body: str) -> str:
    """Staff pages share the visual language but NOT the operator nav --
    library staff must never see links into the admin console."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{ui.e(title)} — Miami University Libraries</title>"
        f"<style>{ui.STYLE}</style></head><body>"
        "<header class='top'><div class='wrap'><b>Smart Chatbot</b>"
        "<span style='opacity:.85'>library staff</span></div></header>"
        f"<main>{body}</main></body></html>"
    )


# Explicit states, explicit transitions. This used to be a single
# "mark <next>" link cycling open -> reviewed -> done -> OPEN, so a
# finished ticket silently reopened on an extra click and there was no
# way to jump straight to done (operator: "the handoffs are muddled",
# 2026-07-28). Now every transition is its own button.
VALID_STATUSES = ("open", "in_progress", "done")
_LEGACY_STATUS = {"reviewed": "in_progress"}


def normalize_status(status: object) -> str:
    """Map stored values (incl. the legacy 'reviewed') onto the current
    three. Unknown values fall back to open so a row is never stranded
    in a state the UI can't act on."""
    s = str(status or "open").strip().lower()
    s = _LEGACY_STATUS.get(s, s)
    return s if s in VALID_STATUSES else "open"


def _ticket_actions(tid: str, status: str, kq: str) -> str:
    """The transitions available FROM `status`, as labelled buttons."""
    base = f"/admin/tickets/{tid}/status?{kq}"
    if status == "open":
        return (ui.action(f"{base}&to=in_progress", "Start working",
                          primary=True)
                + ui.action(f"{base}&to=done", "Mark done"))
    if status == "in_progress":
        return (ui.action(f"{base}&to=done", "Mark done", primary=True)
                + ui.action(f"{base}&to=open", "Back to open", ghost=True))
    return ui.action(f"{base}&to=open", "Reopen", ghost=True)


def render_admin_list(tickets: list[dict], key: str,
                      counts: "Optional[dict]" = None,
                      show_done: bool = False) -> str:
    kq = f"key={ui.e(key)}" if key else ""
    kq_amp = f"?{kq}" if kq else ""
    cards = []
    for t in tickets:
        tid = str(t.get("id", ""))
        status = normalize_status(t.get("status"))
        mail_pill = (
            "" if t.get("emailSent")
            else " <span class='pill warn'>email failed</span>"
        )
        src = str(t.get("sourceUrl") or "").strip()
        # The handoff the old page was missing: from a ticket straight to
        # the tool that fixes it, with the ticket's URL prefilled.
        fix_href = "/admin/corrections/view" + (f"?{kq}" if kq else "")
        if src:
            sep = "&" if kq else "?"
            fix_href = f"/admin/corrections/view{kq_amp}{sep}target={ui.e(src)}"
        cards.append(
            f"<div class='card{' attn' if status == 'open' else ''}'>"
            f"<div class='meta'>{ui.pill(status, extra=mail_pill)}"
            f"<span>{ui.e(str(t.get('createdAt', ''))[:16])}</span>"
            f"<span>{ui.e(t.get('librarianName'))} "
            f"&lt;{ui.e(t.get('librarianEmail'))}&gt;</span></div>"
            f"<div class='q'>{ui.e(t.get('question'))}</div>"
            f"<dl>"
            f"<dt>Bot said</dt><dd>{ui.e(t.get('botAnswer'))}</dd>"
            f"<dt>Should say</dt><dd>{ui.e(t.get('expectedAnswer'))}</dd>"
            + (f"<dt>Source</dt><dd><a href='{ui.e(src)}'>{ui.e(src)}</a></dd>"
               if src else "")
            + f"</dl>"
            f"<div class='acts'>{_ticket_actions(tid, status, kq)}"
            f"{ui.action(fix_href, 'Fix content →')}</div>"
            f"</div>"
        )
    toggle = ui.action(
        f"/admin/tickets/view?{kq}" + ("" if show_done else "&show=all"),
        "Hide finished" if show_done else "Show finished too", ghost=True)
    body = (
        f"<h1>Correction tickets</h1>"
        f"<p class='lede'>Reports from library staff. Work them "
        f"open &rarr; in progress &rarr; done; each ticket links straight "
        f"to the corrections tool.</p>"
        f"<div class='acts' style='margin-bottom:1rem'>{toggle}</div>"
        + ("".join(cards) or ui.empty(
            "No tickets waiting. Staff submit them from the librarian hub."))
    )
    return ui.page("Correction tickets", body,
                   current="/admin/tickets/view", key=key, counts=counts)


# --- Router builder --------------------------------------------------------


def build_ticket_router(deps: dict):
    """Mount the ticket surfaces. deps: db, guard (admin), librarian_code."""
    from fastapi import APIRouter, Depends, HTTPException  # type: ignore
    from fastapi.responses import HTMLResponse  # type: ignore

    db = deps["db"]
    admin_guard = deps["guard"]
    librarian_code: str = (deps.get("librarian_code") or "").strip()

    router = APIRouter(tags=["tickets"])

    async def librarian_guard(request: Request) -> str:
        """Fail-closed shared-code gate for the librarian surface."""
        supplied = request.query_params.get("key", "")
        if not supplied and request.method == "POST":
            form = await request.form()
            supplied = str(form.get("key") or "")
        if not librarian_code or supplied != librarian_code:
            raise HTTPException(
                status_code=401,
                detail="Missing or wrong access code. Ask the library web "
                       "services team for the ticket-form link.",
            )
        return supplied

    @router.get("/librarian/ticket", response_class=HTMLResponse)
    async def ticket_form(request: Request):
        key = await librarian_guard(request)
        return HTMLResponse(render_form(key))

    @router.post("/librarian/ticket", response_class=HTMLResponse)
    async def ticket_submit(request: Request):
        key = await librarian_guard(request)
        form = dict(await request.form())
        clean, errors = validate_ticket(form)
        if errors:
            return HTMLResponse(render_form(key, clean, errors), status_code=422)

        row = await db.correctionticket.create(data={
            "librarianName": clean["librarian_name"],
            "librarianEmail": clean["librarian_email"],
            "question": clean["question"],
            "botAnswer": clean["bot_answer"],
            "expectedAnswer": clean["expected_answer"],
            "sourceUrl": clean["source_url"],
        })

        # Email AFTER the row is durable; a mail failure must not lose
        # the ticket (send_alert_email never raises).
        from src.observability.alerting import send_alert_email
        sent = send_alert_email(
            subject=f"\U0001f4cb Chatbot correction ticket from "
                    f"{clean['librarian_name']}",
            body=ticket_email_body({**clean, "id": row.id}),
        )
        if sent:
            await db.correctionticket.update(
                where={"id": row.id}, data={"emailSent": True},
            )
        return HTMLResponse(render_thanks(row.id, sent, key))

    @router.get("/admin/tickets/view", response_class=HTMLResponse,
                dependencies=[Depends(admin_guard)])
    async def tickets_list(request: Request):
        key = request.query_params.get("key", "")
        show_done = request.query_params.get("show", "") == "all"
        where = {} if show_done else {"status": {"not": "done"}}
        rows = await db.correctionticket.find_many(
            where=where, order={"createdAt": "desc"}, take=200,
        )
        from src.api.admin.review_queries import dashboard_counts
        counts = await dashboard_counts(db)
        return HTMLResponse(render_admin_list(
            [r.model_dump() if hasattr(r, "model_dump") else vars(r)
             for r in rows],
            key, counts=counts, show_done=show_done,
        ))

    @router.get("/admin/tickets/{ticket_id}/status",
                response_class=HTMLResponse,
                dependencies=[Depends(admin_guard)])
    async def ticket_set_status(ticket_id: str, request: Request):
        """Set an EXPLICIT target state (?to=open|in_progress|done).

        Replaces the old cycling /mark endpoint, which advanced to
        whatever came next and wrapped done back to open -- so a
        finished ticket could silently reopen (operator report
        2026-07-28). An unknown/absent target is rejected rather than
        guessed at.
        """
        target = normalize_status(request.query_params.get("to"))
        if request.query_params.get("to") not in VALID_STATUSES:
            raise HTTPException(status_code=400,
                                detail=f"to= must be one of {VALID_STATUSES}")
        row = await db.correctionticket.find_unique(where={"id": ticket_id})
        if row is None:
            raise HTTPException(status_code=404, detail="no such ticket")
        from datetime import datetime, timezone
        data: dict = {"status": target}
        # reviewedAt records when it LEFT the open pile; reopening clears
        # it so the timestamp never contradicts the status.
        data["reviewedAt"] = (
            None if target == "open" else datetime.now(timezone.utc)
        )
        await db.correctionticket.update(where={"id": ticket_id}, data=data)
        back = "/admin/tickets/view" + (
            f"?key={request.query_params.get('key', '')}" if key_present(request)
            else "")
        return HTMLResponse(
            f"<!doctype html><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='0;url={ui.e(back)}'>ok"
        )

    return router
