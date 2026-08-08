"""The OpenAI readiness probe must not page a human over one dropped packet.

Written after 2026-08-07, when the operator got eight "dependency DOWN
(openai)" emails in a day while OpenAI's status page was clean and all 332
real API calls that day succeeded.

Measured cause: the probe opens a fresh httpx client per check, and roughly
one new connection in ten stalls during DNS/TCP/TLS setup and never recovers
-- while the next attempt to the same IP returns in ~90ms. Successful probes
sat at p50 ~390ms; failures were always the full timeout, never in between.

The real client (OpenAI(timeout=30.0, max_retries=2), pooled connection)
absorbs exactly this jitter, which is why students noticed nothing. These
tests pin the probe to the same posture.
"""
from __future__ import annotations

import asyncio

import pytest

from src.api.readiness_router import make_openai_probe


def _run(coro):
    return asyncio.run(coro)


def test_a_single_dropped_connection_does_not_report_down():
    """The whole point. One failure then success must read as healthy."""
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("connection reset by peer")

    result = _run(make_openai_probe(flaky)())
    assert result.passed, result.detail
    assert calls["n"] == 2, "it should have retried exactly once"
    assert "attempt 2" in (result.detail or ""), (
        "a recovered-on-retry probe should say so, otherwise a genuinely "
        "flaky network looks identical to a clean one"
    )


def test_a_single_timeout_does_not_report_down():
    calls = {"n": 0}

    async def slow_once():
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(30)     # exceeds the probe budget

    result = _run(make_openai_probe(slow_once)())
    assert result.passed
    assert calls["n"] == 2


def test_a_sustained_outage_still_reports_down():
    """Retry must not paper over a real outage."""
    async def always_fails():
        raise ConnectionError("no route to host")

    result = _run(make_openai_probe(always_fails)())
    assert not result.passed
    assert result.name == "openai"


def test_the_failure_detail_says_what_actually_went_wrong():
    """The alert email said only "openai: unhealthy", which is why the
    operator could not tell a timeout from a 401 from a 429."""
    async def bad_key():
        raise PermissionError("HTTP 401 invalid_api_key")

    result = _run(make_openai_probe(bad_key)())
    assert not result.passed
    d = result.detail or ""
    assert "PermissionError" in d
    assert "401" in d
    assert "attempt 2/2" in d, "say how many tries it got, not just the last error"


def test_a_healthy_probe_stays_quiet():
    """No detail noise on the happy path -- first-attempt success is the norm
    and should not clutter the status block."""
    async def fine():
        return None

    result = _run(make_openai_probe(fine)())
    assert result.passed
    assert result.detail is None
    assert result.latency_ms is not None


def test_the_budget_is_wide_enough_for_a_slow_handshake():
    """p50 is ~390ms. A probe that takes 6s is slow, not down -- the old 5s
    ceiling turned an occasional slow TLS handshake into a page."""
    async def slow_but_fine():
        await asyncio.sleep(6.0)

    result = _run(make_openai_probe(slow_but_fine)())
    assert result.passed, "6s must fit inside the budget"
