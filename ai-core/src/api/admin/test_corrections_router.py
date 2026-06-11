"""Endpoint tests for the ManualCorrection CRUD (backlog D1).

Covers the librarian workflow end to end against a fake Prisma handle:
create (valid + each validation failure) -> list -> patch -> soft-delete,
plus the token gate (401 without the header) and the HTML view.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent.parent
sys.path.insert(0, str(_AI_CORE))

import pytest  # noqa: E402

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.admin.corrections_router import build_corrections_router  # noqa: E402
from src.api.admin.review_view_router import make_token_guard  # noqa: E402


class _FakeTable:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}
        self._n = 0

    async def find_many(self, where=None, order=None, take=None):
        rows = list(self.rows.values())
        if where and "active" in where:
            rows = [r for r in rows if r.active == where["active"]]
        return rows

    async def find_unique(self, where):
        return self.rows.get(where["id"])

    async def create(self, data):
        self._n += 1
        row = SimpleNamespace(
            id=f"c-{self._n}",
            scope=data["scope"], target=data["target"],
            action=data["action"], replacement=data.get("replacement"),
            queryPattern=data.get("queryPattern"), reason=data["reason"],
            createdBy=data["createdBy"],
            createdAt=datetime.now(timezone.utc),
            expiresAt=data["expiresAt"], active=True, fireCount=0,
        )
        self.rows[row.id] = row
        return row

    async def update(self, where, data):
        row = self.rows[where["id"]]
        for k, v in data.items():
            setattr(row, k, v)
        return row


def _client() -> tuple[TestClient, _FakeTable]:
    table = _FakeTable()
    db = SimpleNamespace(manualcorrection=table)
    app = FastAPI()
    app.include_router(build_corrections_router({
        "db": db, "require_librarian": make_token_guard("sekrit"),
    }))
    return TestClient(app), table


H = {"x-admin-token": "sekrit"}
GOOD = {
    "scope": "url", "target": "https://x.example/dead",
    "action": "blacklist_url", "reason": "404s since June",
    "created_by": "qum@miamioh.edu",
}


def test_requires_token() -> None:
    c, _ = _client()
    assert c.get("/admin/corrections").status_code == 401
    assert c.post("/admin/corrections", json=GOOD).status_code == 401


def test_create_list_deactivate_cycle() -> None:
    c, table = _client()
    r = c.post("/admin/corrections", json=GOOD, headers=H)
    assert r.status_code == 201, r.text
    body = r.json()["created"]
    assert body["active"] is True
    assert body["expires_at"]  # default 180d applied
    cid = body["id"]

    r = c.get("/admin/corrections", headers=H)
    assert r.json()["count"] == 1

    r = c.delete(f"/admin/corrections/{cid}", headers=H)
    assert r.status_code == 200
    assert r.json()["deactivated"]["active"] is False
    # active-only list is now empty; audit list still shows it
    assert c.get("/admin/corrections", headers=H).json()["count"] == 0
    assert c.get("/admin/corrections?active_only=false",
                 headers=H).json()["count"] == 1


def test_validation_errors_are_400() -> None:
    c, _ = _client()
    for bad, msg in [
        ({**GOOD, "reason": "  "}, "reason"),
        ({**GOOD, "created_by": ""}, "created_by"),
        ({**GOOD, "action": "replace"}, "replacement"),
        ({**GOOD, "action": "pin"}, "query_pattern"),
        ({**GOOD, "action": "suppress"}, "scope=chunk"),
        ({**GOOD, "action": "nuke"}, "action must be"),
    ]:
        r = c.post("/admin/corrections", json=bad, headers=H)
        assert r.status_code == 400, (bad, r.text)
        assert msg in r.json()["detail"]


def test_patch_extend_and_reactivate() -> None:
    c, _ = _client()
    cid = c.post("/admin/corrections", json=GOOD, headers=H).json()["created"]["id"]
    new_exp = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    r = c.patch(f"/admin/corrections/{cid}", headers=H,
                json={"active": False, "expires_at": new_exp,
                      "reason": "extended after review"})
    assert r.status_code == 200
    u = r.json()["updated"]
    assert u["active"] is False and u["reason"] == "extended after review"
    assert c.patch(f"/admin/corrections/{cid}", headers=H,
                   json={}).status_code == 400
    assert c.patch("/admin/corrections/nope", headers=H,
                   json={"active": True}).status_code == 404


def test_view_html_served() -> None:
    c, _ = _client()
    r = c.get("/admin/corrections/view", headers=H)
    assert r.status_code == 200
    assert "Manual Corrections" in r.text and "File correction" in r.text
