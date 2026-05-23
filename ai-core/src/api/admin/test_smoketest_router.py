"""Tests for build_smoketest_router.

Covers the dual-endpoint behavior added 2026-05-22:
  - /smoketest is always present (legacy path monitoring)
  - /smoketest/v2 is registered ONLY when `ask_bot_v2` is provided,
    so a legacy-only deploy doesn't expose a broken v2 endpoint
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.admin.smoketest_router import build_smoketest_router


def _passing_ask(question: str) -> dict:
    return {
        "answer": "King opens at 7am [1].",
        "citations": [{"n": 1, "url": "https://www.lib.miamioh.edu/about/locations/hours/", "snippet": "King 7am"}],
        "is_refusal": False,
    }


def _refusal_ask(question: str) -> dict:
    return {"answer": "I don't have a reliable answer.", "citations": [], "is_refusal": True}


def _mount(deps: dict) -> TestClient:
    app = FastAPI()
    app.include_router(build_smoketest_router(deps))
    return TestClient(app)


def test_legacy_only_no_v2_route():
    client = _mount({"ask_bot": _passing_ask})
    # Legacy passes
    r = client.get("/smoketest")
    assert r.status_code == 200
    assert r.json()["passed"] is True
    # v2 NOT registered
    r2 = client.get("/smoketest/v2")
    assert r2.status_code == 404


def test_v2_route_registered_when_ask_bot_v2_provided():
    client = _mount({"ask_bot": _passing_ask, "ask_bot_v2": _passing_ask})
    r = client.get("/smoketest/v2")
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] is True
    assert "King opens" in body["answer_preview"]


def test_v2_endpoint_503s_when_v2_fails_but_legacy_still_200s():
    # If only v2 is degraded (e.g., LibCal down for v2 path), the
    # external pinger should see 503 for /smoketest/v2 and 200 for
    # /smoketest. That's the point of two endpoints.
    client = _mount({"ask_bot": _passing_ask, "ask_bot_v2": _refusal_ask})
    assert client.get("/smoketest").status_code == 200
    r = client.get("/smoketest/v2")
    # Refusal is a hard-fail signal for smoketest (see run_smoketest)
    assert r.status_code == 503


def test_each_endpoint_uses_its_own_callable():
    """ Guards against a refactor accidentally routing both endpoints
    through the same callable. """
    calls = {"legacy": 0, "v2": 0}

    def legacy(q):
        calls["legacy"] += 1
        return _passing_ask(q)

    def v2(q):
        calls["v2"] += 1
        return _passing_ask(q)

    client = _mount({"ask_bot": legacy, "ask_bot_v2": v2})
    client.get("/smoketest")
    client.get("/smoketest/v2")
    assert calls == {"legacy": 1, "v2": 1}
