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

import html
from typing import Any

try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001
    Request = Any  # type: ignore


_CSS = """
body{font-family:system-ui,sans-serif;max-width:680px;margin:2rem auto;
padding:0 1rem;color:#222}
h1{font-size:1.35rem} h2{font-size:1.05rem;margin-top:1.6rem;color:#555}
a.card{display:block;padding:.8rem 1rem;margin:.5rem 0;border:1px solid #ddd;
border-radius:6px;text-decoration:none;color:#1a4480}
a.card:hover{background:#f6f8fa}
a.card b{display:block;color:#111}
a.card small{color:#666}
code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}
.note{background:#fff8e1;border:1px solid #e6d9a8;padding:.7rem;
border-radius:4px;font-size:.9rem}
"""


def _card(href: str, title: str, desc: str) -> str:
    return (f"<a class='card' href='{html.escape(href)}'>"
            f"<b>{html.escape(title)}</b>"
            f"<small>{html.escape(desc)}</small></a>")


def render_admin_hub(admin_key: str, librarian_code: str) -> str:
    k = f"?key={html.escape(admin_key)}"
    lib_url = f"/librarian/ticket?key={html.escape(librarian_code)}" \
        if librarian_code else ""
    cards_ops = [
        _card(f"/admin/tickets/view{k}", "Correction tickets",
              "Librarian 'wrong answer' reports — review queue"),
        _card(f"/admin/review{k}", "Flagged conversations",
              "Thumbs-down / low-confidence turns, full transcripts"),
        _card(f"/admin/corrections/view{k}", "Manual corrections",
              "Suppress / replace / pin / blacklist — fixes without a deploy"),
        _card(f"/admin/cost{k}", "Cost dashboard",
              "Daily LLM spend by model and call site (nightly rollup)"),
    ]
    cards_health = [
        _card("/health/ready", "Readiness probes",
              "Postgres / Weaviate / OpenAI / LibCal / LibGuides, live"),
        _card("/smoketest", "Smoke test",
              "Canned question through the serving orchestrator (strict citation check)"),
    ]
    staff = (
        f"<h2>Share with library staff</h2>"
        + (_card(lib_url, "Report a wrong answer (staff form)",
                 "This is the link to distribute to librarians — code included")
           if lib_url else
           "<div class='note'>LIBRARIAN_TICKET_CODE is not set — the staff "
           "form is closed.</div>")
    )
    return (f"<!doctype html><meta charset='utf-8'><title>Chatbot admin</title>"
            f"<style>{_CSS}</style><h1>Smart Chatbot — operator hub</h1>"
            f"<h2>Operations</h2>{''.join(cards_ops)}"
            f"<h2>Health</h2>{''.join(cards_health)}"
            f"{staff}"
            f"<p><small>Bookmark this page — the links carry your key.</small></p>")


def render_librarian_hub(code: str) -> str:
    k = f"?key={html.escape(code)}"
    cards = [
        _card(f"/librarian/ticket{k}", "Report a wrong chatbot answer",
              "Goes straight to the maintainer (stored + emailed)"),
        _card("https://www.lib.miamioh.edu/research/research-support/ask/",
              "Ask Us — talk to a librarian",
              "For questions the bot should hand off"),
    ]
    return (f"<!doctype html><meta charset='utf-8'><title>Chatbot staff hub</title>"
            f"<style>{_CSS}</style><h1>Smart Chatbot — staff hub</h1>"
            f"{''.join(cards)}"
            f"<p><small>Bookmark this page — the links carry the access "
            f"code.</small></p>")


def build_hub_router(deps: dict):
    from fastapi import APIRouter, HTTPException  # type: ignore
    from fastapi.responses import HTMLResponse  # type: ignore

    admin_token: str = (deps.get("admin_token") or "").strip()
    librarian_code: str = (deps.get("librarian_code") or "").strip()
    router = APIRouter(tags=["hub"])

    @router.get("/admin/", response_class=HTMLResponse)
    @router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_hub(request: Request):
        supplied = request.query_params.get("key", "")
        if not admin_token or supplied != admin_token:
            raise HTTPException(status_code=401, detail="admin token required")
        return HTMLResponse(render_admin_hub(supplied, librarian_code))

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
