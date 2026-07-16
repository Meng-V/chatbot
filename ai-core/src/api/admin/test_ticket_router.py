"""Endpoint tests for the librarian correction-ticket surfaces.

Covers: the shared-code gate (fail-closed), form render, submit
(valid + validation failures), the email hook (stubbed; a mail failure
must not lose the ticket), the admin queue view + status cycling.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent.parent
sys.path.insert(0, str(_AI_CORE))

import pytest  # noqa: E402

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.admin.review_view_router import make_token_guard  # noqa: E402
from src.api.admin.ticket_router import (  # noqa: E402
    build_ticket_router,
    ticket_email_body,
    validate_ticket,
)


class _FakeTickets:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}
        self._n = 0

    async def create(self, data):
        self._n += 1
        row = SimpleNamespace(
            id=f"t-{self._n}",
            createdAt=datetime.now(timezone.utc),
            librarianName=data["librarianName"],
            librarianEmail=data["librarianEmail"],
            question=data["question"],
            botAnswer=data["botAnswer"],
            expectedAnswer=data["expectedAnswer"],
            sourceUrl=data.get("sourceUrl", ""),
            status="open", reviewedAt=None, emailSent=False,
        )
        self.rows[row.id] = row
        return row

    async def update(self, where, data):
        row = self.rows[where["id"]]
        for k, v in data.items():
            setattr(row, k, v)
        return row

    async def find_unique(self, where):
        return self.rows.get(where["id"])

    async def find_many(self, order=None, take=None):
        return list(self.rows.values())


def _mk_client(monkeypatch, sent_log=None, send_ok=True, code="opensesame"):
    db = SimpleNamespace(correctionticket=_FakeTickets())
    app = FastAPI()
    app.include_router(build_ticket_router({
        "db": db,
        "guard": make_token_guard("admintoken"),
        "librarian_code": code,
    }))
    import src.observability.alerting as alerting

    def _fake_send(subject, body):
        if sent_log is not None:
            sent_log.append((subject, body))
        return send_ok

    monkeypatch.setattr(alerting, "send_alert_email", _fake_send)
    return TestClient(app), db


_VALID = {
    "librarian_name": "Jane Doe",
    "librarian_email": "doej@miamioh.edu",
    "question": "When does King close?",
    "bot_answer": "King closes at 2am.",
    "expected_answer": "King closes at 9pm in summer -- see the hours page.",
    "source_url": "https://www.lib.miamioh.edu/about/locations/hours/",
}


def test_validate_ticket_pure():
    clean, errors = validate_ticket(_VALID)
    assert not errors and clean["librarian_name"] == "Jane Doe"
    _, errors = validate_ticket({**_VALID, "librarian_email": "not-an-email"})
    assert any("email" in e for e in errors)
    _, errors = validate_ticket({**_VALID, "question": ""})
    assert any("required" in e for e in errors)
    _, errors = validate_ticket({**_VALID, "source_url": "ftp://x"})
    assert any("http" in e for e in errors)


def test_email_body_contains_all_fields():
    body = ticket_email_body({**{k.replace("_", ""): v for k, v in _VALID.items()},
                              **_VALID, "id": "t-9"})
    for needle in ("t-9", "Jane Doe", "King closes at 2am", "hours page"):
        assert needle in body


def test_librarian_gate_fail_closed(monkeypatch):
    client, _ = _mk_client(monkeypatch)
    assert client.get("/librarian/ticket").status_code == 401
    assert client.get("/librarian/ticket?key=wrong").status_code == 401
    # empty configured code stays closed even with an empty supplied key
    client2, _ = _mk_client(monkeypatch, code="")
    assert client2.get("/librarian/ticket?key=").status_code == 401


def test_form_renders_with_key(monkeypatch):
    client, _ = _mk_client(monkeypatch)
    r = client.get("/librarian/ticket?key=opensesame")
    assert r.status_code == 200
    assert "Report a wrong chatbot answer" in r.text


def test_submit_stores_and_emails(monkeypatch):
    sent = []
    client, db = _mk_client(monkeypatch, sent_log=sent)
    r = client.post("/librarian/ticket?key=opensesame", data=_VALID)
    assert r.status_code == 200 and "Thank you" in r.text
    assert len(db.correctionticket.rows) == 1
    row = next(iter(db.correctionticket.rows.values()))
    assert row.emailSent is True
    assert len(sent) == 1 and "Jane Doe" in sent[0][0]


def test_submit_survives_email_failure(monkeypatch):
    client, db = _mk_client(monkeypatch, send_ok=False)
    r = client.post("/librarian/ticket?key=opensesame", data=_VALID)
    assert r.status_code == 200
    row = next(iter(db.correctionticket.rows.values()))
    assert row.emailSent is False  # kept, flagged for the admin queue
    assert "could not be sent" in r.text


def test_submit_validation_errors_rerender(monkeypatch):
    client, db = _mk_client(monkeypatch)
    r = client.post("/librarian/ticket?key=opensesame",
                    data={**_VALID, "question": ""})
    assert r.status_code == 422 and "required" in r.text
    assert len(db.correctionticket.rows) == 0


def test_admin_queue_and_status_cycle(monkeypatch):
    client, db = _mk_client(monkeypatch)
    client.post("/librarian/ticket?key=opensesame", data=_VALID)
    # queue requires the admin token, not the librarian code
    assert client.get("/admin/tickets/view").status_code == 401
    r = client.get("/admin/tickets/view?key=admintoken")
    assert r.status_code == 200 and "Jane Doe" in r.text
    tid = next(iter(db.correctionticket.rows))
    client.get(f"/admin/tickets/{tid}/mark?key=admintoken")
    assert db.correctionticket.rows[tid].status == "reviewed"
    client.get(f"/admin/tickets/{tid}/mark?key=admintoken")
    assert db.correctionticket.rows[tid].status == "done"


def test_html_escapes_ticket_content(monkeypatch):
    client, _ = _mk_client(monkeypatch)
    evil = {**_VALID, "question": "<script>alert(1)</script>"}
    client.post("/librarian/ticket?key=opensesame", data=evil)
    r = client.get("/admin/tickets/view?key=admintoken")
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
