"""Two alert tiers: interrupt a person, or wait for the digest.

The bug this guards against is not a crash. It is handing colleagues 30-50
emails a day, which produces a filter rule and the belief that somebody is
watching. So what matters is that URGENT_KINDS stays small and that
everything else really does end up in the queue instead of the inbox.
"""
from __future__ import annotations

import json

import pytest

from src.observability import incident_alerts as IA


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(IA, "DIGEST_PATH", tmp_path / "digest.jsonl")
    IA._last_sent.clear()
    IA._suppressed.clear()
    sent: list = []
    monkeypatch.setattr(
        "src.observability.alerting.send_alert_email",
        lambda subject, body, to=None: sent.append((subject, to)) or True,
    )
    yield sent
    IA._last_sent.clear()
    IA._suppressed.clear()


def test_urgent_set_is_small_and_specific():
    """Its whole value is that a message from it is worth interrupting for."""
    assert IA.URGENT_KINDS == {"health", "budget_exhausted"}


def test_urgent_kinds_are_emailed_immediately(_isolate):
    assert IA._send("health", "dependency down", "body") is True
    assert len(_isolate) == 1


def test_everything_else_is_queued_not_emailed(_isolate, tmp_path):
    for kind in ("thumbs_down", "low_rating", "suspicious_message",
                 "rate_limit_abuse", "budget_level"):
        assert IA._send(kind, f"{kind} happened", "body") is True
    assert _isolate == [], "non-urgent alerts must not reach the inbox"
    rows = [json.loads(l) for l in
            (tmp_path / "digest.jsonl").read_text().splitlines() if l.strip()]
    assert {r["kind"] for r in rows} == {
        "thumbs_down", "low_rating", "suspicious_message",
        "rate_limit_abuse", "budget_level"}


def test_a_refused_injection_attempt_does_not_page_anyone(_isolate):
    """The commitment was that suspicious activity reaches us, not that it
    wakes us. The bot already refused it."""
    IA._send("suspicious_message", "injection attempt", "body")
    assert _isolate == []


def test_urgent_recipients_falls_back_to_the_default(monkeypatch):
    """Nothing changes until ALERT_EMAIL_TO_URGENT is deliberately set, so
    the handover is one env var and not a code change."""
    monkeypatch.delenv("ALERT_EMAIL_TO_URGENT", raising=False)
    assert IA.urgent_recipients() is None
    monkeypatch.setenv("ALERT_EMAIL_TO_URGENT", "  ")
    assert IA.urgent_recipients() is None
    monkeypatch.setenv("ALERT_EMAIL_TO_URGENT", "a@x.edu, b@x.edu")
    assert IA.urgent_recipients() == "a@x.edu, b@x.edu"


def test_urgent_send_uses_the_wider_list(_isolate, monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_TO_URGENT", "a@x.edu, b@x.edu")
    IA._send("health", "down", "body")
    assert _isolate[0][1] == "a@x.edu, b@x.edu"


def test_queue_failure_is_reported_not_swallowed(monkeypatch, tmp_path):
    """A queue we cannot write to must return False so the caller's log says
    so -- silence here would read as 'nothing happened'."""
    monkeypatch.setattr(IA, "DIGEST_PATH", tmp_path / "nope")
    (tmp_path / "nope").mkdir()          # a directory, so open('a') fails
    assert IA._send("thumbs_down", "s", "b") is False


def test_digest_builds_a_summary_with_counts():
    from scripts.alert_digest import build
    rows = [{"at": "2026-08-04T09:00:00", "kind": "thumbs_down",
             "subject": f"s{i}", "body": "b"} for i in range(9)]
    rows.append({"at": "2026-08-04T10:00:00", "kind": "rate_limit_abuse",
                 "subject": "abuse", "body": "b"})
    subject, body = build(rows)
    assert "10 event(s)" in subject
    assert "thumbs_down x9" in subject
    assert "and 4 more of this kind" in body, (
        "long runs must collapse to a count, not print all nine"
    )
    assert "rate_limit_abuse" in body
