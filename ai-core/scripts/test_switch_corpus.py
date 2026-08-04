"""Tests for the corpus switch.

The switch exists because three separate things have gone wrong around
promotion, and every test below is one of them:

  * promoting made the predecessor non-serving, so a cleanup script deleted
    19,972 good chunks (2026-07-29);
  * two half-written collections sat in the DB looking like finished refreshes,
    one 39% smaller than serving (2026-07-31);
  * a broken promotion leaves the service HEALTHY while every content answer
    becomes a refusal, so "systemctl says active" proves nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import switch_corpus as sc
from scripts.etl.cleanup_collections import _protected_as_rollback


# --- refusals -----------------------------------------------------------


def test_refuses_a_collection_that_does_not_exist(monkeypatch, capsys):
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_a", "Chunk_b"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_a")
    assert sc.cmd_to("Chunk_typo", force=False, note="") == 2
    assert "does not exist" in capsys.readouterr().out


def test_refuses_a_collection_too_small_to_be_a_corpus(monkeypatch, capsys):
    """The 12,480-chunk half-written build. A count in single digits is not a
    judgement call -- it is a broken write."""
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_tiny"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_old")
    monkeypatch.setattr(sc, "stats", lambda c: (
        {"chunks": 20608, "pages": 419, "pdf_chunks": 19700} if c == "Chunk_old"
        else {"chunks": 3, "pages": 2, "pdf_chunks": 0}))
    assert sc.cmd_to("Chunk_tiny", force=False, note="") == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "broken or half-written" in out


def test_refuses_a_big_page_coverage_drop_without_force(monkeypatch, capsys):
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_new"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_old")
    monkeypatch.setattr(sc, "stats", lambda c: (
        {"chunks": 20608, "pages": 419, "pdf_chunks": 19700} if c == "Chunk_old"
        else {"chunks": 173, "pages": 94, "pdf_chunks": 0}))
    assert sc.cmd_to("Chunk_new", force=False, note="") == 2
    out = capsys.readouterr().out
    assert "page coverage drops to 22%" in out
    assert "--force" in out


def test_a_deliberate_rebuild_goes_through_with_force(monkeypatch, tmp_path, capsys):
    """The 2026-08-04 rebuild really is 419 -> 94 pages, and really is correct:
    news, PDFs and duplicate vanity URLs removed. The guard must be overridable
    or it blocks the promotion it was written to protect."""
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_new"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_old")
    monkeypatch.setattr(sc, "stats", lambda c: (
        {"chunks": 20608, "pages": 419, "pdf_chunks": 19700} if c == "Chunk_old"
        else {"chunks": 173, "pages": 94, "pdf_chunks": 0}))
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sc, "env_set", lambda v: None)
    monkeypatch.setattr(sc, "restart_and_verify", lambda **k: (True, "healthy"))
    assert sc.cmd_to("Chunk_new", force=True, note="rebuild") == 0
    assert "proceeding because --force" in capsys.readouterr().out


# --- the rollback contract ---------------------------------------------


def test_the_predecessor_is_recorded_before_anything_changes(monkeypatch, tmp_path):
    """Recorded BEFORE the .env write, so a crash mid-switch still leaves a
    rollback target on disk."""
    state = tmp_path / "state.json"
    order = []
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_new"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_old")
    monkeypatch.setattr(sc, "stats", lambda c: {"chunks": 500, "pages": 100, "pdf_chunks": 0})
    monkeypatch.setattr(sc, "STATE_PATH", state)
    monkeypatch.setattr(sc, "env_set", lambda v: order.append("env"))
    monkeypatch.setattr(sc, "restart_and_verify", lambda **k: (True, "ok"))
    _orig = sc.save_state
    monkeypatch.setattr(sc, "save_state", lambda s: (order.append("state"), _orig(s))[1])
    sc.cmd_to("Chunk_new", force=False, note="")
    assert order.index("state") < order.index("env"), order
    assert json.loads(state.read_text())["history"][-1]["from"] == "Chunk_old"


def test_a_switch_that_fails_verification_rolls_itself_back(monkeypatch, tmp_path, capsys):
    """Health alone is not proof. If retrieval is dead the switch must undo
    itself rather than leave every content answer as a refusal."""
    sets = []
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_new"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_old")
    monkeypatch.setattr(sc, "stats", lambda c: {"chunks": 500, "pages": 100, "pdf_chunks": 0})
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(sc, "env_set", lambda v: sets.append(v))
    monkeypatch.setattr(sc, "restart_and_verify",
                        lambda **k: (False, "retrieval is dead"))
    assert sc.cmd_to("Chunk_new", force=False, note="") == 1
    assert sets == ["Chunk_new", "Chunk_old"], sets
    assert "ROLLING BACK" in capsys.readouterr().out


def test_rollback_returns_to_the_recorded_predecessor(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"history": [
        {"at": "2026-08-04T05:00:00+00:00", "from": "Chunk_old", "to": "Chunk_new"}
    ]}))
    sets = []
    monkeypatch.setattr(sc, "STATE_PATH", state)
    monkeypatch.setattr(sc, "collections", lambda: ["Chunk_old", "Chunk_new"])
    monkeypatch.setattr(sc, "env_current", lambda: "Chunk_new")
    monkeypatch.setattr(sc, "stats", lambda c: {"chunks": 500, "pages": 100, "pdf_chunks": 0})
    monkeypatch.setattr(sc, "env_set", lambda v: sets.append(v))
    monkeypatch.setattr(sc, "restart_and_verify", lambda **k: (True, "ok"))
    assert sc.cmd_rollback(force=True) == 0
    assert sets == ["Chunk_old"]


def test_rollback_with_no_history_refuses(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "nothing.json")
    assert sc.cmd_rollback(force=False) == 2
    assert "No recorded switch" in capsys.readouterr().out


# --- and the cleanup script must not eat the rollback target ------------


def test_cleanup_protects_the_rollback_target(tmp_path):
    """The direct fix for 2026-07-29. Promotion makes the predecessor
    non-serving; under the old rule that alone made it a deletion candidate.

    Calls the real function with the state file redirected -- an earlier
    version of this test reimplemented the logic inline, which tested nothing.
    """
    state = tmp_path / "serving_corpus.json"
    state.write_text(json.dumps({"history": [
        {"at": "2026-08-04T05:00:00+00:00",
         "from": "Chunk_vv20260514_1929", "to": "Chunk_vv20260804_0246"}
    ]}))
    protected, warnings = _protected_as_rollback(state)
    assert protected == {"Chunk_vv20260514_1929"}
    assert warnings == []


def test_cleanup_protects_nothing_once_you_have_rolled_back(tmp_path):
    """Having rolled back, the collection you abandoned is disposable again."""
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"history": [
        {"from": "Chunk_a", "to": "Chunk_b", "rolled_back": True}
    ]}))
    assert _protected_as_rollback(state)[0] == set()


def test_cleanup_warns_rather_than_silently_protecting_nothing(tmp_path):
    """An unreadable state file must SAY that a rollback target is now
    deletable. Silence here is how the 19,972 chunks went."""
    state = tmp_path / "broken.json"
    state.write_text("{not json")
    protected, warnings = _protected_as_rollback(state)
    assert protected == set()
    assert warnings and "rollback target" in warnings[0]


def test_cleanup_with_no_state_file_is_quiet(tmp_path):
    """Before the first switch there is nothing to protect and nothing to warn
    about -- this must not become a permanent scary message."""
    assert _protected_as_rollback(tmp_path / "absent.json") == (set(), [])
