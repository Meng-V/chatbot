"""
/smoketest endpoint. Hit every 5 minutes by an external uptime pinger
(UptimeRobot / BetterStack). Returns 200 when the synthetic question
produces a valid cited answer; 503 otherwise.

Not under /admin because the external pinger doesn't authenticate.
Lives in this package for discoverability -- the admin surfaces are
all in one place.

See plan: Operations -> Op 3 "Synthetic monitoring".
"""

from __future__ import annotations

from typing import Any, Callable

from src.observability.smoketest import (
    DEFAULT_LATENCY_BUDGET_MS,
    DEFAULT_QUESTION,
    SmoketestResult,
    run_smoketest,
)


def build_smoketest_router(deps: dict) -> Any:
    """Build the FastAPI router.

    `deps` must include `ask_bot` (legacy orchestrator) and optionally
    `ask_bot_v2` (the rebuilt v2 orchestrator via `run_turn`). Each
    callable runs one canned question through the full path and
    returns a dict; `run_smoketest` checks the shape + citation
    presence + latency.

    Endpoints registered:
      GET /smoketest      -- always; legacy path
      GET /smoketest/v2   -- registered only if `ask_bot_v2` is provided

    The split lets the external pinger (UptimeRobot / BetterStack)
    poll each path independently so a v2-only outage doesn't mask the
    legacy fallback's health, and vice versa.
    """
    try:
        from fastapi import APIRouter  # type: ignore
        from fastapi.responses import JSONResponse  # type: ignore
    except ImportError:
        return _Placeholder("/smoketest")

    router = APIRouter(tags=["ops"])
    ask_bot: Callable[[str], dict] = deps["ask_bot"]
    ask_bot_v2: Callable[[str], dict] | None = deps.get("ask_bot_v2")
    latency_budget_ms = deps.get(
        "latency_budget_ms", DEFAULT_LATENCY_BUDGET_MS
    )
    question = deps.get("question", DEFAULT_QUESTION)

    def _run(ask: Callable[[str], dict]) -> Any:
        result: SmoketestResult = run_smoketest(
            ask_bot=ask,
            question=question,
            latency_budget_ms=latency_budget_ms,
        )
        payload = {
            "passed": result.passed,
            "reason": result.reason,
            "latency_ms": result.latency_ms,
            "answer_preview": result.answer_preview,
            "checks": result.checks,
        }
        return JSONResponse(
            content=payload,
            status_code=200 if result.passed else 503,
        )

    @router.get("/smoketest")
    async def smoketest() -> Any:
        return _run(ask_bot)

    if ask_bot_v2 is not None:
        @router.get("/smoketest/v2")
        async def smoketest_v2() -> Any:
            return _run(ask_bot_v2)

    return router


class _Placeholder:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = ["build_smoketest_router"]
