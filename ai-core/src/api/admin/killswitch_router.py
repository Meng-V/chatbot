"""
One-click shutdown, as promised to colleagues: a single page with a button
that takes the bot out of service, and another that puts it back.

WHY A FLAG AND NOT `systemctl stop`
    Stopping the process would make the widget on the library website fail
    with a network error -- a patron sees a broken page and no explanation.
    This keeps the service up and answers every turn with a maintenance
    notice instead, so the page still works and says something honest.

    It also means recovery is one click by the operator rather than a shell
    on the server, which is the point of "one-click".

THE FLAG IS A FILE, ON PURPOSE
    `data/SERVICE_PAUSED` on disk, not a variable:
      * it SURVIVES a restart -- if the bot is paused because it is
        misbehaving, a crash-restart must not quietly put it back in service
      * it can be set or cleared without this router, by touching or deleting
        the file, so a stuck web surface never leaves the operator without a
        way out
      * every worker sees the same state, which a per-process variable would
        not guarantee

FAIL-CLOSED AUTH
    Mounted only when `ADMIN_API_TOKEN` is set, and every route is behind the
    same guard as the rest of /admin.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_FLAG_PATH = Path(
    os.getenv("SERVICE_PAUSE_FLAG",
              str(Path(__file__).resolve().parents[3] / "data" / "SERVICE_PAUSED"))
)

PAUSED_MESSAGE = (
    "The library chatbot is temporarily unavailable for maintenance. "
    "For help right now, please use Ask Us to reach a librarian: "
    "https://www.lib.miamioh.edu/research/research-support/ask/"
)


def is_paused() -> bool:
    """Cheap enough to call on every turn (a stat, no read)."""
    try:
        return _FLAG_PATH.exists()
    except Exception:  # noqa: BLE001 -- never let this decide by raising
        return False


def pause_reason() -> str:
    try:
        return _FLAG_PATH.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""


def pause(who: str = "operator", note: str = "") -> None:
    _FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _FLAG_PATH.write_text(
        f"paused_at: {stamp}\npaused_by: {who}\nnote: {note}\n",
        encoding="utf-8")
    logger.warning("SERVICE PAUSED by %s: %s", who, note or "(no note)")


def resume(who: str = "operator") -> None:
    try:
        _FLAG_PATH.unlink()
        logger.warning("SERVICE RESUMED by %s", who)
    except FileNotFoundError:
        pass


def build_killswitch_router(deps: dict):
    """`deps` needs `guard` -- the same token dependency as /admin/review."""
    from fastapi import APIRouter, Depends, Form  # type: ignore
    from fastapi.responses import HTMLResponse, RedirectResponse  # type: ignore

    guard = deps["guard"]
    router = APIRouter(prefix="/admin", tags=["admin"])

    def _page(key: str) -> str:
        from src.api.admin.admin_ui import e, page

        paused = is_paused()
        reason = e(pause_reason()) if paused else ""
        if paused:
            body = f"""
            <div style="border:2px solid #b61e2e;padding:1.25rem;border-radius:8px">
              <h2 style="margin-top:0;color:#b61e2e">The bot is OUT OF SERVICE</h2>
              <p>Every question is being answered with a maintenance notice
                 pointing patrons at Ask Us. The widget still loads — nobody
                 sees a broken page.</p>
              <pre style="background:#f6f6f6;padding:.75rem">{reason}</pre>
              <form method="post" action="/admin/service/resume?key={e(key)}">
                <button style="background:#136f3b;color:#fff;border:0;
                    padding:.7rem 1.4rem;font-size:1rem;border-radius:6px">
                  Put the bot back in service</button>
              </form>
            </div>"""
        else:
            body = """
            <div style="border:1px solid #ccc;padding:1.25rem;border-radius:8px">
              <h2 style="margin-top:0">The bot is in service</h2>
              <p>Use this only if the bot is doing something wrong and you
                 need it to stop <em>now</em>. It keeps answering — with a
                 maintenance notice — so the page on the library site does not
                 break.</p>
              <form method="post" action="/admin/service/pause?key=KEY">
                <input name="note" placeholder="why (optional, for the log)"
                       style="padding:.5rem;width:60%">
                <button style="background:#b61e2e;color:#fff;border:0;
                    padding:.7rem 1.4rem;font-size:1rem;border-radius:6px">
                  Take the bot out of service</button>
              </form>
            </div>"""
            body = body.replace("KEY", e(key))
        return page("Service control", body, key=key)

    @router.get("/service", response_class=HTMLResponse)
    async def service_page(key: str = "", _u=Depends(guard)):
        return HTMLResponse(_page(key))

    @router.post("/service/pause")
    async def do_pause(key: str = "", note: str = Form(""), _u=Depends(guard)):
        pause(who="admin-ui", note=note)
        return RedirectResponse(f"/admin/service?key={key}", status_code=303)

    @router.post("/service/resume")
    async def do_resume(key: str = "", _u=Depends(guard)):
        resume(who="admin-ui")
        return RedirectResponse(f"/admin/service?key={key}", status_code=303)

    return router


__all__ = ["PAUSED_MESSAGE", "build_killswitch_router", "is_paused",
           "pause", "pause_reason", "resume"]
