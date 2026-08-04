"""The spend ledger's failure behaviour, which is the part that matters.

The arithmetic is cost_rollup's and already tested there. What is new here
is *when the ledger is allowed to fail*, and the two answers are opposite
on purpose:

  record_eval_spend  must NEVER raise -- it is called at the end of a
                     100-minute run whose results are already on disk.
  read_spend         must return None, not zeros -- zeros read as a quiet
                     month and would let the guard clear a level it should
                     be holding.
"""
from __future__ import annotations

import datetime as _dt

from src.observability import spend_ledger as SL


def test_month_start():
    assert SL._month_start(_dt.date(2026, 8, 17)) == _dt.date(2026, 8, 1)
    assert SL._month_start(_dt.date(2026, 1, 1)) == _dt.date(2026, 1, 1)


def test_total_is_both_purses():
    s = SL.Spend(serving_mtd=40.0, eval_mtd=12.0)
    assert s.total_mtd == 52.0


def test_recording_nothing_is_a_success_not_a_db_round_trip(monkeypatch):
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not touch the DB for an empty batch")

    monkeypatch.setattr(SL.asyncio, "run", boom)
    assert SL.record_eval_spend([]) is True
    assert called["n"] == 0


async def _boom(*a, **k):
    raise RuntimeError("db is gone")


def test_record_eval_spend_never_raises(monkeypatch):
    """A dead DB must not kill a run that has already produced its results."""
    monkeypatch.setattr(SL, "_arecord_eval_spend", _boom)
    assert SL.record_eval_spend(
        [{"model": "gpt-5.6-terra", "input_tokens": 1000,
          "cached_input_tokens": 0, "output_tokens": 100, "calls": 1}]
    ) is False


def test_read_spend_returns_none_not_zeros_on_failure(monkeypatch):
    """Zeros would look like a quiet month and clear a degrade level."""
    monkeypatch.setattr(SL, "_aread_spend", _boom)
    got = SL.read_spend()
    assert got is None
    assert got != SL.Spend(), "an empty Spend() is the dangerous wrong answer"


def test_eval_call_site_is_distinct_from_serving_call_sites():
    """DailyCost's unique key is (date, model, callSite). If "eval" collided
    with a serving call site, the rollup and the eval would overwrite each
    other's rows."""
    serving_sites = {"agent_loop", "synthesizer", "clarifier", "judge",
                     "embedding", "v2_turn"}
    assert SL.EVAL_CALL_SITE not in serving_sites
