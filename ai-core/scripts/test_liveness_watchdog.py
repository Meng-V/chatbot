"""The watchdog's own logic. Its whole value is behaving correctly on the
one day it matters, so the transition rules are tested rather than trusted.
"""
from __future__ import annotations

import json

import pytest

from scripts import liveness_watchdog as W


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "STATE_PATH", tmp_path / "wd.json")
    sent: list = []
    monkeypatch.setattr(W, "_mail", lambda s, b: sent.append((s, b)) or True)
    monkeypatch.setattr(W, "_systemctl", lambda *a: "active")
    yield sent


def _probe(alive, detail="x"):
    return lambda: (alive, detail)


def test_healthy_check_sends_nothing(_isolate, monkeypatch):
    monkeypatch.setattr(W, "probe", _probe(True))
    assert W.main([]) == 0
    assert _isolate == []


def test_one_failure_does_not_alert(_isolate, monkeypatch):
    """A single slow response during a restart must not mail anyone."""
    monkeypatch.setattr(W, "probe", _probe(False, "timeout"))
    assert W.main([]) == 1
    assert _isolate == []


def test_second_consecutive_failure_alerts_once(_isolate, monkeypatch):
    monkeypatch.setattr(W, "probe", _probe(False, "connection refused"))
    W.main([]); W.main([])
    assert len(_isolate) == 1
    assert "DOWN" in _isolate[0][0]
    # ...and stays quiet while it remains down.
    W.main([]); W.main([])
    assert len(_isolate) == 1, "down is a transition, not a heartbeat"


def test_recovery_is_also_reported(_isolate, monkeypatch):
    monkeypatch.setattr(W, "probe", _probe(False))
    W.main([]); W.main([])
    monkeypatch.setattr(W, "probe", _probe(True))
    assert W.main([]) == 0
    assert len(_isolate) == 2
    assert "recovered" in _isolate[1][0]


def test_the_systemd_gave_up_case_is_called_out(_isolate, monkeypatch):
    """The reason this script exists: after 5 failed starts in 60s systemd
    stops retrying and the in-app monitors are dead with the process."""
    monkeypatch.setattr(W, "probe", _probe(False))
    monkeypatch.setattr(W, "_systemctl", lambda *a: "failed")
    W.main([]); W.main([])
    subject, body = _isolate[0]
    assert "failed" in subject
    assert "systemd is NOT retrying" in body
    assert "reset-failed" in body, "the mail must carry the revive command"


def test_no_restart_without_the_flag(_isolate, monkeypatch):
    calls = []
    monkeypatch.setattr(W, "probe", _probe(False))
    monkeypatch.setattr(W, "_systemctl",
                        lambda *a: calls.append(a) or ("failed" if a[0] == "is-active" else ""))
    W.main([]); W.main([])
    assert not any("restart" in c for c in calls), "recovery must be opt-in"


def test_try_restart_recovers_once_then_respects_the_cooldown(_isolate, monkeypatch, tmp_path):
    calls = []

    def fake(*a):
        calls.append(a[0])
        return "failed" if a[0] == "is-active" else ""

    monkeypatch.setattr(W, "probe", _probe(False))
    monkeypatch.setattr(W, "_systemctl", fake)
    W.main(["--try-restart"]); W.main(["--try-restart"])
    assert calls.count("restart") == 1
    assert "reset-failed" in calls
    # A third check inside the cooldown must NOT restart again -- otherwise a
    # broken dependency becomes a restart loop that hides the real fault.
    W.main(["--try-restart"])
    assert calls.count("restart") == 1
    state = json.loads((tmp_path / "wd.json").read_text())
    assert "less than" in state["last_action"]


def test_a_non_200_is_down_even_though_the_port_answered(monkeypatch, _isolate):
    """uvicorn can be listening while the app is wedged."""
    class _R:
        status = 503
        def read(self, n): return b"unhealthy"
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(W.urllib.request, "urlopen", lambda *a, **k: _R())
    alive, detail = W.probe()
    assert alive is False
    assert "503" in detail


def test_dry_run_writes_nothing_and_sends_nothing(_isolate, monkeypatch, tmp_path):
    monkeypatch.setattr(W, "probe", _probe(False))
    W.main(["--dry-run"]); W.main(["--dry-run"])
    assert _isolate == []
    assert not (tmp_path / "wd.json").exists()


def test_corrupt_state_does_not_stop_the_watch(_isolate, monkeypatch, tmp_path):
    (tmp_path / "wd.json").write_text("{ not json")
    monkeypatch.setattr(W, "probe", _probe(True))
    assert W.main([]) == 0
