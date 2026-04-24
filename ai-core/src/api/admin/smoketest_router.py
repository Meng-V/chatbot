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

    `deps` must include `ask_bot`, a callable that runs one canned
    question through the full orchestrator (`(question: str) -> dict`).
    The orchestrator isn't wired yet, so in prod the app's startup
    will supply the real function; in dev this stays a stub.
    """
    try:
        from fastapi import APIRouter  # type: ignore
        from fastapi.responses import JSONResponse  # type: ignore
    except ImportError:
        return _Placeholder("/smoketest")

    router = APIRouter(tags=["ops"])
    ask_bot: Callable[[str], dict] = deps["ask_bot"]
    latency_budget_ms = deps.get(
        "latency_budget_ms", DEFAULT_LATENCY_BUDGET_MS
    )
    question = deps.get("question", DEFAULT_QUESTION)

    @router.get("/smoketest")
    async def smoketest() -> Any:
        result: SmoketestResult = run_smoketest(
            ask_bot=ask_bot,
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

    return router


class _Placeholder:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = ["build_smoketest_router"]
