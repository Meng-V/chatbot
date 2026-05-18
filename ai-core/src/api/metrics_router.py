"""
GET /metrics -- Prometheus exposition endpoint (plan Op 3 "Metrics").

`src/observability/metrics.py` already DEFINES the counters/histograms
and the record_* recording API, and the v2 orchestrator already calls
them -- but nothing EXPOSED them for Prometheus to scrape and nothing
timed the HTTP layer. This router (plus MetricsMiddleware) closes that
"module exists, orphaned" gap.

Follows the dependency-injected `build_*_router(deps)` convention used
by readiness_router / smoketest_router, including the FastAPI-missing
`_Placeholder` fallback so a dev/sandbox import never crashes.

Safe by construction: `render_latest()` no-ops to a self-explaining
plaintext 200 when prometheus_client isn't installed, so mounting
this changes nothing until the (pyproject-declared) dep is present.
"""

from __future__ import annotations

from typing import Any, Optional

from src.observability.metrics import render_latest


def build_metrics_router(deps: Optional[dict] = None) -> Any:
    """Build the /metrics router.

    `deps` is unused today (the endpoint is pure exposition) but kept
    for parity with the other build_*_router factories and so a future
    custom registry can be injected in tests without a signature break.
    """
    try:
        from fastapi import APIRouter  # type: ignore
        from fastapi.responses import Response  # type: ignore
    except ImportError:
        return _Placeholder("/metrics")

    router = APIRouter(tags=["ops"])

    @router.get("/metrics")
    async def metrics() -> Any:
        body, content_type = render_latest()
        # Always 200: a scrape endpoint that 500s just turns one
        # outage into two (the app's AND the monitoring's). The body
        # self-describes when prometheus_client is absent.
        return Response(content=body, media_type=content_type)

    return router


class _Placeholder:
    """FastAPI-not-installed fallback so `import` doesn't crash dev."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = ["build_metrics_router"]
