"""Tests for data_health's reporting contract.

WHY: `--quiet` meant "no stdout at all", so under cron it wrote a 0-byte log
forever. That file is indistinguishable from "the check never ran" -- and it
cost real time: an 81-day-old corpus was being reported there every morning
and read as silence. The email path was working the whole time; the log was
the thing lying.
"""
from __future__ import annotations

import scripts.data_health as dh


def _finding(name, ok, summary="s", detail=()):
    return dh.Finding(name, ok, summary, list(detail))


def _run(monkeypatch, findings, quiet, capsys, sent=None):
    monkeypatch.setattr(dh, "CHECKS", [lambda f=f: f for f in findings])
    calls = []

    def _fake_send(subject, body):
        calls.append((subject, body))
    monkeypatch.setattr("src.observability.alerting.send_alert_email", _fake_send)
    code = dh.main(force_email=False, quiet=quiet)
    if sent is not None:
        sent.extend(calls)
    return code, capsys.readouterr().out


def test_quiet_prints_nothing_when_every_check_passes(monkeypatch, capsys):
    """An empty log must genuinely mean all clear -- that is the whole point
    of keeping quiet mode quiet."""
    code, out = _run(monkeypatch, [_finding("a", True), _finding("b", True)],
                     quiet=True, capsys=capsys)
    assert out.strip() == ""
    assert code == 0


def test_quiet_still_prints_the_things_that_need_a_human(monkeypatch, capsys):
    """The regression: 0-byte log while the corpus aged 81 days."""
    code, out = _run(monkeypatch, [
        _finding("all good", True, "fine"),
        _finding("corpus freshness", False, "the search index is 81 days old",
                 ["a librarian must sign the .approval file"]),
    ], quiet=True, capsys=capsys)
    assert "corpus freshness" in out
    assert "81 days old" in out
    assert "[ACT]" in out
    assert "a librarian must sign" in out, "detail lines carry the action"
    assert code == 1


def test_quiet_omits_the_passing_checks(monkeypatch, capsys):
    """Quiet is still quiet: OK rows stay out so the log is all signal."""
    _, out = _run(monkeypatch, [
        _finding("roster vs CSV", True, "74 people, matches"),
        _finding("corpus freshness", False, "81 days old"),
    ], quiet=True, capsys=capsys)
    assert "roster vs CSV" not in out
    assert "[OK ]" not in out


def test_verbose_prints_everything(monkeypatch, capsys):
    _, out = _run(monkeypatch, [
        _finding("roster vs CSV", True, "74 people, matches"),
        _finding("corpus freshness", False, "81 days old"),
    ], quiet=False, capsys=capsys)
    assert "roster vs CSV" in out and "corpus freshness" in out


def test_problems_are_emailed_in_quiet_mode_too(monkeypatch, capsys):
    """Quiet only ever governed stdout; the notification is the real channel
    and must not depend on it."""
    sent = []
    _run(monkeypatch, [_finding("corpus freshness", False, "81 days old")],
         quiet=True, capsys=capsys, sent=sent)
    assert len(sent) == 1
    assert "1 thing(s) need you" in sent[0][0]
    assert "81 days old" in sent[0][1]


def test_exit_code_reports_whether_anything_needs_action(monkeypatch, capsys):
    ok, _ = _run(monkeypatch, [_finding("a", True)], quiet=True, capsys=capsys)
    bad, _ = _run(monkeypatch, [_finding("a", False)], quiet=True, capsys=capsys)
    assert (ok, bad) == (0, 1)


def test_a_check_that_raises_becomes_a_finding_not_a_crash(monkeypatch, capsys):
    def _boom():
        raise RuntimeError("weaviate is down")
    monkeypatch.setattr(dh, "CHECKS", [_boom, lambda: _finding("b", True)])
    monkeypatch.setattr("src.observability.alerting.send_alert_email",
                        lambda *a, **k: None)
    code = dh.main(force_email=False, quiet=True)
    out = capsys.readouterr().out
    assert code == 1
    assert "the check itself failed" in out
    assert "weaviate is down" in out
    assert "_boom" in out
