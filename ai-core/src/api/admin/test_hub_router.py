"""Tests for the operator/staff hub landing pages."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent.parent
sys.path.insert(0, str(_AI_CORE))

import pytest  # noqa: E402

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.admin.hub_router import build_hub_router  # noqa: E402


def _client(admin="admintok", code="staffcode"):
    app = FastAPI()
    app.include_router(build_hub_router({
        "admin_token": admin, "librarian_code": code,
    }))
    return TestClient(app)


def test_hubs_fail_closed():
    c = _client()
    assert c.get("/admin/").status_code == 401
    assert c.get("/admin/?key=wrong").status_code == 401
    assert c.get("/librarian/").status_code == 401
    # empty configured secrets stay closed
    c2 = _client(admin="", code="")
    assert c2.get("/admin/?key=").status_code == 401
    assert c2.get("/librarian/?key=").status_code == 401


def test_admin_hub_links_carry_key_and_list_surfaces():
    c = _client()
    r = c.get("/admin/?key=admintok")
    assert r.status_code == 200
    for path in ("/admin/tickets/view?key=admintok",
                 "/admin/review?key=admintok",
                 "/admin/corrections/view?key=admintok",
                 "/admin/cost?key=admintok",
                 "/smoketest",
                 # the dashboard shares the staff HUB, not the bare form:
                 # one link for staff to bookmark, and it shows them no
                 # admin surfaces (redesign 2026-07-28)
                 "/librarian/?key=staffcode"):
        assert path in r.text, path
    # counts render as the lead element, colored by whether work waits
    assert "waiting on you" in r.text or "Nothing needs you" in r.text


def test_the_stop_button_is_reachable_from_the_dashboard():
    """It shipped with no link anywhere in the UI, so taking the bot out
    of service required knowing the URL. During an incident that is
    exactly when nobody remembers it."""
    c = _client()
    r = c.get("/admin/?key=admintok")
    assert "/admin/service?key=admintok" in r.text


def test_an_out_of_service_bot_says_so_at_the_top(tmp_path, monkeypatch):
    """The dashboard has to answer "is it up?" before anything else."""
    from src.api.admin import killswitch_router as ks

    flag = tmp_path / "SERVICE_PAUSED"
    monkeypatch.setattr(ks, "_FLAG_PATH", flag)
    c = _client()

    assert "OUT OF SERVICE" not in c.get("/admin/?key=admintok").text

    ks.pause(who="test", note="bad hours answer")
    body = c.get("/admin/?key=admintok").text
    assert "OUT OF SERVICE" in body
    # the banner precedes the queue counts, not buried under them
    headline = next(s for s in ("waiting on you", "Nothing needs you")
                    if s in body)
    assert body.index("OUT OF SERVICE") < body.index(headline)
    assert "bad hours answer" in body, "say why it was paused"
    assert "Put it back in service" in body


def test_dashboard_groups_tools_by_job():
    """One flat "Tools" bucket mixed three different jobs; the operator
    could not tell from the headings which card did what."""
    c = _client()
    r = c.get("/admin/?key=admintok")
    assert "When an answer is wrong" in r.text
    assert "Keep it running" in r.text
    assert "<h2>Tools</h2>" not in r.text


def test_librarian_hub_scoped_to_staff():
    c = _client()
    r = c.get("/librarian/?key=staffcode")
    assert r.status_code == 200
    assert "/librarian/ticket?key=staffcode" in r.text
    # no admin surfaces leak into the staff page
    assert "/admin/" not in r.text.replace("/admin/?", "")
    assert "admintok" not in r.text


def test_staff_hub_drops_ask_us_and_says_what_reporting_costs_them():
    """Staff already live on the Ask Us page -- linking it told them
    nothing. What they actually want to know is whether reporting a bad
    answer lands follow-up work on them."""
    c = _client()
    r = c.get("/librarian/?key=staffcode")
    assert "research-support/ask" not in r.text
    assert "What happens after you send it" in r.text
    assert "do not need to follow" in r.text
