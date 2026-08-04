"""The budget ladder: thresholds, hysteresis, and failing open.

The dangerous bugs here are not crashes, they are quiet wrong answers:
a threshold off by one rung silently stops protecting the ceiling, and a
state file that fails CLOSED takes the bot away from every student because
of a JSON typo. Both are tested explicitly.
"""
from __future__ import annotations

import datetime as _dt
import json

from src.config import budget as B


def _aug(day: int = 15) -> _dt.date:
    return _dt.date(2026, 8, day)  # 31 days -> $75/31 = $2.4194/day


# --- the two purses ------------------------------------------------------


def test_the_split_is_75_25():
    assert B.MONTHLY_SERVING_USD == 75.00
    assert B.MONTHLY_EVAL_USD == 25.00
    assert B.MONTHLY_TOTAL_USD == 100.00


def test_daily_line_divides_the_student_purse_by_the_real_month_length():
    """Not a hardcoded 30: a $2.50 line in February would overspend the purse."""
    assert B.daily_serving_line(_dt.date(2026, 8, 1)) == 75.0 / 31
    assert B.daily_serving_line(_dt.date(2026, 2, 1)) == 75.0 / 28
    assert B.daily_serving_line(_dt.date(2026, 4, 1)) == 75.0 / 30


# --- the ladder ----------------------------------------------------------


def test_quiet_day_is_normal():
    lvl, _ = B.level_for(serving_today=0.10, serving_mtd=3.00, when=_aug())
    assert lvl == B.L_NORMAL


def test_daily_line_breach_alerts_but_changes_nothing_for_students():
    line = B.daily_serving_line(_aug())
    lvl, reason = B.level_for(serving_today=line * 1.01, serving_mtd=5.0,
                              when=_aug())
    assert lvl == B.L_ALERT
    assert "daily line" in reason
    st = B.BudgetState(level=lvl)
    assert st.force_cheap_model is False
    assert st.refuse_new_conversations is False
    assert st.rate_max == B.RATE_MAX_NORMAL


def test_one_and_a_half_days_of_spend_forces_the_cheap_model():
    line = B.daily_serving_line(_aug())
    lvl, _ = B.level_for(serving_today=line * 1.6, serving_mtd=5.0, when=_aug())
    assert lvl == B.L_CHEAP
    st = B.BudgetState(level=lvl)
    assert st.force_cheap_model is True
    # Degrading quality must NOT also throttle or refuse -- that is two
    # more rungs up, and conflating them would punish students at the
    # first sign of a busy day.
    assert st.rate_max == B.RATE_MAX_NORMAL
    assert st.refuse_new_conversations is False


def test_a_runaway_day_tightens_the_limits():
    line = B.daily_serving_line(_aug())
    lvl, _ = B.level_for(serving_today=line * 3.0, serving_mtd=5.0, when=_aug())
    assert lvl == B.L_TIGHTEN
    st = B.BudgetState(level=lvl)
    assert st.rate_max == B.RATE_MAX_TIGHTENED < B.RATE_MAX_NORMAL
    assert st.max_turns == B.MAX_TURNS_TIGHTENED < B.MAX_TURNS_NORMAL
    assert st.refuse_new_conversations is False, (
        "one expensive day must never take the service away from students"
    )


def test_only_an_exhausted_monthly_purse_refuses_students():
    line = B.daily_serving_line(_aug())
    # A colossal single day: still not a refusal.
    lvl, _ = B.level_for(serving_today=line * 50, serving_mtd=20.0, when=_aug())
    assert lvl == B.L_TIGHTEN
    # The purse actually running out: refusal.
    lvl, reason = B.level_for(serving_today=0.5, serving_mtd=75.0, when=_aug())
    assert lvl == B.L_REFUSE
    assert "month-to-date" in reason
    assert B.BudgetState(level=lvl).refuse_new_conversations is True


def test_monthly_thresholds_are_where_the_design_says():
    for mtd, want in ((52.50, B.L_ALERT),      # 70%
                      (63.75, B.L_CHEAP),      # 85%
                      (71.25, B.L_TIGHTEN),    # 95%
                      (75.00, B.L_REFUSE)):    # 100%
        lvl, _ = B.level_for(serving_today=0.0, serving_mtd=mtd, when=_aug())
        assert lvl == want, (mtd, lvl, want)


def test_the_higher_of_the_two_triggers_wins():
    """A quiet day inside an exhausted month must not read as normal."""
    lvl, _ = B.level_for(serving_today=0.0, serving_mtd=74.0, when=_aug())
    assert lvl == B.L_TIGHTEN
    # ...and a wild day inside a quiet month must not read as normal either.
    line = B.daily_serving_line(_aug())
    lvl, _ = B.level_for(serving_today=line * 2.6, serving_mtd=1.0, when=_aug())
    assert lvl == B.L_TIGHTEN


# --- hysteresis ----------------------------------------------------------


def test_escalation_is_never_delayed():
    """Money is leaving; there is nothing to be gained by waiting."""
    assert B.apply_hysteresis(B.L_REFUSE, B.L_NORMAL, serving_today=0.0,
                              serving_mtd=80.0, when=_aug()) == B.L_REFUSE


def test_recovery_needs_clearance_below_the_trigger():
    """Just under the line is not enough, or the guard flaps and mails
    on every 15-minute crossing."""
    # 85% of $75 = $63.75. Just below it -> hold at cheap.
    assert B.apply_hysteresis(B.L_ALERT, B.L_CHEAP, serving_today=0.0,
                              serving_mtd=63.00, when=_aug()) == B.L_CHEAP
    # 10% clear of the trigger ($57.37) -> allowed to step down.
    assert B.apply_hysteresis(B.L_ALERT, B.L_CHEAP, serving_today=0.0,
                              serving_mtd=50.00, when=_aug()) == B.L_ALERT


def test_recovery_steps_down_one_rung_at_a_time():
    """From refusing to normal in one hop would swing the service wide open
    on a single reading."""
    got = B.apply_hysteresis(B.L_NORMAL, B.L_REFUSE, serving_today=0.0,
                             serving_mtd=0.0, when=_aug())
    assert got == B.L_TIGHTEN


# --- state file ----------------------------------------------------------


def test_state_roundtrips(tmp_path):
    p = tmp_path / "state.json"
    st = B.BudgetState(level=B.L_CHEAP, reason="because", serving_mtd=64.0,
                       serving_today=1.0, eval_mtd=12.0, month="2026-08",
                       checked_at=_dt.datetime.now().astimezone().isoformat())
    B.write_state(st, p)
    back = B.read_state(p)
    assert back.level == B.L_CHEAP
    assert back.force_cheap_model is True
    assert back.serving_mtd == 64.0
    assert back.missing is False
    assert back.stale is False


def test_write_is_atomic_and_leaves_no_temp_file(tmp_path):
    p = tmp_path / "state.json"
    B.write_state(B.BudgetState(level=B.L_ALERT, month="2026-08"), p)
    assert p.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_missing_state_fails_open(tmp_path):
    st = B.read_state(tmp_path / "nope.json")
    assert st.level == B.L_NORMAL
    assert st.missing is True
    assert st.refuse_new_conversations is False


def test_corrupt_state_fails_open_not_closed(tmp_path):
    """A JSON typo must not refuse every student. See FAIL OPEN, LOUDLY."""
    p = tmp_path / "state.json"
    p.write_text("{ this is not json")
    st = B.read_state(p)
    assert st.level == B.L_NORMAL
    assert st.refuse_new_conversations is False
    p.write_text('"a bare string, not an object"')
    assert B.read_state(p).level == B.L_NORMAL


def test_stale_state_keeps_its_level_rather_than_reverting(tmp_path):
    """A broken cron must not quietly un-throttle a runaway month."""
    p = tmp_path / "state.json"
    old = (_dt.datetime.now().astimezone()
           - _dt.timedelta(seconds=B.STALE_AFTER_S + 60))
    p.write_text(json.dumps({
        "level": B.L_TIGHTEN, "reason": "r", "serving_mtd": 72.0,
        "serving_today": 0.1, "eval_mtd": 1.0,
        "month": _dt.date.today().strftime("%Y-%m"),
        "checked_at": old.isoformat(),
    }))
    st = B.read_state(p)
    assert st.stale is True
    assert st.level == B.L_TIGHTEN, "staleness is reported, not corrected"


def test_last_months_state_does_not_throttle_this_month(tmp_path):
    """The purse refills at midnight on the 1st; nobody should still be
    refused on last month's numbers."""
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "level": B.L_REFUSE, "reason": "purse empty", "serving_mtd": 80.0,
        "serving_today": 0.0, "eval_mtd": 25.0, "month": "2020-01",
        "checked_at": _dt.datetime.now().astimezone().isoformat(),
    }))
    st = B.read_state(p)
    assert st.level == B.L_NORMAL
    assert st.refuse_new_conversations is False


def test_state_json_denormalises_the_knobs():
    """An operator reading the file by eye, or any other process, should not
    have to re-derive the ladder."""
    d = B.BudgetState(level=B.L_TIGHTEN).to_json()
    assert d["force_cheap_model"] is True
    assert d["rate_max"] == B.RATE_MAX_TIGHTENED
    assert d["max_turns"] == B.MAX_TURNS_TIGHTENED
    assert d["refuse_new_conversations"] is False
    assert d["level_name"] == "tightened"


def test_current_state_is_cached_but_resettable(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    monkeypatch.setattr(B, "STATE_PATH", p)
    B.reset_cache()
    B.write_state(B.BudgetState(level=B.L_NORMAL, month="2026-08"), p)
    assert B.current_state().level == B.L_NORMAL
    B.write_state(B.BudgetState(level=B.L_REFUSE, month="2026-08"), p)
    assert B.current_state().level == B.L_NORMAL, "served from cache"
    B.reset_cache()
    assert B.current_state().level == B.L_REFUSE


def test_every_rung_says_what_changes():
    """The text goes into the alert email and the report; an empty one there
    is a rung nobody can act on."""
    for r in B.LADDER:
        assert r.what_changes.strip()
        assert r.level in B.LEVEL_NAMES
    assert {r.level for r in B.LADDER} == {B.L_ALERT, B.L_CHEAP,
                                          B.L_TIGHTEN, B.L_REFUSE}
