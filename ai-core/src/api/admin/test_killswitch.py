"""The one-click shutdown promised to colleagues.

Two properties matter more than the button working:
  * a PAUSED bot must stay paused across a restart -- if it was paused
    because it was misbehaving, a crash-restart must not put it back in
    service silently
  * the flag must be clearable WITHOUT this router, so a broken web surface
    never leaves the operator with no way out
"""

import pytest

from src.api.admin import killswitch_router as ks


@pytest.fixture(autouse=True)
def flag(tmp_path, monkeypatch):
    p = tmp_path / "SERVICE_PAUSED"
    monkeypatch.setattr(ks, "_FLAG_PATH", p)
    yield p


def test_starts_in_service(flag):
    assert ks.is_paused() is False


def test_pause_then_resume(flag):
    ks.pause(who="test", note="because")
    assert ks.is_paused() is True
    assert "because" in ks.pause_reason()
    assert "paused_by: test" in ks.pause_reason()
    ks.resume(who="test")
    assert ks.is_paused() is False


def test_the_flag_is_a_file_so_it_survives_a_restart(flag):
    """A module-level variable would be lost on restart, silently putting a
    deliberately-paused bot back in front of patrons."""
    ks.pause(who="test")
    assert flag.exists(), "the state must be on disk, not in memory"
    # simulate a fresh process: nothing in memory, flag still there
    assert ks.is_paused() is True


def test_it_can_be_cleared_without_the_web_ui(flag):
    """Escape hatch: if the admin page is broken, deleting the file works."""
    ks.pause(who="test")
    flag.unlink()
    assert ks.is_paused() is False


def test_resuming_when_not_paused_is_harmless(flag):
    ks.resume(who="test")          # no exception
    assert ks.is_paused() is False


def test_a_broken_flag_path_fails_open(monkeypatch):
    """If the check itself breaks, the bot must keep SERVING -- an
    observability bug must not take the service down."""
    class Boom:
        def exists(self):
            raise OSError("disk gone")
    monkeypatch.setattr(ks, "_FLAG_PATH", Boom())
    assert ks.is_paused() is False


def test_the_patron_message_points_somewhere_useful():
    """A maintenance notice that just says "unavailable" wastes the turn."""
    assert "Ask Us" in ks.PAUSED_MESSAGE
    assert "lib.miamioh.edu" in ks.PAUSED_MESSAGE
