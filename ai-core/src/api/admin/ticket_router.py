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

import html
import logging
from typing import Any

try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001 -- keep importable in a no-fastapi sandbox
    Request = Any  # type: ignore

logger = logging.getLogger("ticket_router")

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

_PAGE_CSS = """
body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;
padding:0 1rem;color:#222}
h1{font-size:1.3rem}
label{display:block;margin:.9rem 0 .25rem;font-weight:600}
input[type=text],input[type=email],textarea{width:100%;padding:.5rem;
border:1px solid #bbb;border-radius:4px;font:inherit;box-sizing:border-box}
textarea{min-height:6rem}
button{margin-top:1.2rem;padding:.6rem 1.4rem;font:inherit;cursor:pointer;
background:#b61e2e;color:#fff;border:0;border-radius:4px}
.err{background:#fdecea;border:1px solid #e0a9a9;padding:.7rem;border-radius:4px}
.ok{background:#e8f5e9;border:1px solid #a5d6a7;padding:.9rem;border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
td,th{border:1px solid #ddd;padding:.45rem;vertical-align:top;text-align:left}
tr.done{opacity:.55}
small{color:#666}
"""


def render_form(key: str, values: dict | None = None,
                errors: list[str] | None = None) -> str:
    v = values or {}
    err_html = ""
    if errors:
        items = "".join(f"<li>{html.escape(e)}</li>" for e in errors)
        err_html = f'<div class="err"><ul>{items}</ul></div>'
    rows = []
    for name, label, required, textarea in _FORM_FIELDS:
        val = html.escape(v.get(name, ""))
        req = " *" if required else ""
        rows.append(f'<label for="{name}">{html.escape(label)}{req}</label>')
        if textarea:
            rows.append(f'<textarea id="{name}" name="{name}">{val}</textarea>')
        else:
            rows.append(f'<input type="text" id="{name}" name="{name}" value="{val}">')
    return (
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>Report a wrong chatbot answer</title><style>{_PAGE_CSS}</style>"
        f"<h1>Report a wrong chatbot answer</h1>"
        f"<p>Spotted the Smart Chatbot giving a wrong or outdated answer? "
        f"Describe it below — the report goes straight to the maintainer "
        f"(<a href='mailto:qum@miamioh.edu'>qum@miamioh.edu</a>).</p>"
        f"{err_html}"
        f"<form method='post'>"
        f"<input type='hidden' name='key' value='{html.escape(key)}'>"
        f"{''.join(rows)}"
        f"<button type='submit'>Submit report</button>"
        f"</form>"
    )


def render_thanks(ticket_id: str, email_sent: bool, key: str) -> str:
    mail_note = (
        "The maintainer has been emailed."
        if email_sent else
        "The report is saved; the email notification could not be sent "
        "right now, but the maintainer will still see it in the queue."
    )
    return (
        f"<!doctype html><meta charset='utf-8'><title>Report received</title>"
        f"<style>{_PAGE_CSS}</style>"
        f"<h1>Thank you!</h1>"
        f"<div class='ok'>Your report was received (id "
        f"<code>{html.escape(ticket_id)}</code>). {html.escape(mail_note)}</div>"
        f"<p><a href='/librarian/ticket?key={html.escape(key)}'>Report another</a></p>"
    )


_STATUS_NEXT = {"open": "reviewed", "reviewed": "done", "done": "open"}


def render_admin_list(tickets: list[dict], token_qs: str) -> str:
    rows = []
    for t in tickets:
        tid = html.escape(str(t.get("id", "")))
        status = html.escape(str(t.get("status", "open")))
        nxt = _STATUS_NEXT.get(t.get("status", "open"), "reviewed")
        mail = "✉️" if t.get("emailSent") else "⚠️ no email"
        rows.append(
            f"<tr class='{status}'>"
            f"<td><small>{html.escape(str(t.get('createdAt', ''))[:16])}</small><br>"
            f"<b>{status}</b><br><small>{mail}</small><br>"
            f"<a href='/admin/tickets/{tid}/mark?{token_qs}'>mark {nxt}</a></td>"
            f"<td>{html.escape(str(t.get('librarianName', '')))}<br>"
            f"<small>{html.escape(str(t.get('librarianEmail', '')))}</small></td>"
            f"<td><b>Q:</b> {html.escape(str(t.get('question', '')))}<br>"
            f"<b>Bot:</b> {html.escape(str(t.get('botAnswer', '')))}<br>"
            f"<b>Should:</b> {html.escape(str(t.get('expectedAnswer', '')))}<br>"
            f"<small>{html.escape(str(t.get('sourceUrl', '')))}</small></td>"
            f"</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='3'>No tickets.</td></tr>"
    return (
        f"<!doctype html><meta charset='utf-8'><title>Correction tickets</title>"
        f"<style>{_PAGE_CSS}</style><h1>Correction tickets</h1>"
        f"<table><tr><th>status</th><th>from</th><th>report</th></tr>{body}</table>"
    )


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
        rows = await db.correctionticket.find_many(
            order={"createdAt": "desc"}, take=200,
        )
        token_qs = "key=" + request.query_params.get("key", "")
        return HTMLResponse(render_admin_list(
            [r.model_dump() if hasattr(r, "model_dump") else vars(r) for r in rows],
            token_qs,
        ))

    @router.get("/admin/tickets/{ticket_id}/mark", response_class=HTMLResponse,
                dependencies=[Depends(admin_guard)])
    async def ticket_mark(ticket_id: str, request: Request):
        row = await db.correctionticket.find_unique(where={"id": ticket_id})
        if row is None:
            raise HTTPException(status_code=404, detail="no such ticket")
        nxt = _STATUS_NEXT.get(row.status, "reviewed")
        from datetime import datetime, timezone
        await db.correctionticket.update(where={"id": ticket_id}, data={
            "status": nxt,
            "reviewedAt": datetime.now(timezone.utc),
        })
        token_qs = "key=" + request.query_params.get("key", "")
        return HTMLResponse(
            f"<!doctype html><meta http-equiv='refresh' "
            f"content='0;url=/admin/tickets/view?{token_qs}'>ok"
        )

    return router
