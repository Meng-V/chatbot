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
                 "/librarian/ticket?key=staffcode"):
        assert path in r.text, path


def test_librarian_hub_scoped_to_staff():
    c = _client()
    r = c.get("/librarian/?key=staffcode")
    assert r.status_code == 200
    assert "/librarian/ticket?key=staffcode" in r.text
    # no admin surfaces leak into the staff page
    assert "/admin/" not in r.text.replace("/admin/?", "")
    assert "admintok" not in r.text
