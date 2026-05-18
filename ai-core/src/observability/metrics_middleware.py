"""
HTTP request-metrics middleware (plan Op 3: "Per HTTP endpoint:
request rate, latency p50/p95/p99, error rate").

`metrics.py` defines the counters and `record_request()`, but nothing
timed the HTTP layer -- the v2 orchestrator records its own turn, yet
the FastAPI request boundary (every endpoint, the legacy /ask path,
errors) was unmeasured. This middleware closes that.

Design rules:
  * Label `endpoint` with the matched ROUTE TEMPLATE (e.g.
    `/health/ready`), never the raw path -- raw paths carry
    conversation ids and would explode Prometheus cardinality.
    Unmatched (404) collapses to a single `<unmatched>` label.
  * Telemetry must never break a request: the record_request call is
    wrapped; an exception in the handler is recorded as status 500
    and then RE-RAISED (Sentry / error handling must still see it).
  * Skip the high-frequency infra polls (`/metrics` scrape every
    ~15s, `/health/live` liveness every few s) -- counting them
    drowns real-traffic rate/latency signal. Standard scrape hygiene.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from src.observability.metrics import record_request

# Infra polling endpoints excluded from request metrics so they don't
# dominate rate/latency. Matched against the resolved route template.
_SKIP_ENDPOINTS = frozenset({"/metrics", "/health/live"})


def _endpoint_label(request) -> str:
    """Low-cardinality label: the matched route's path template, or
    `<unmatched>` for 404s (never the raw URL path)."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "<unmatched>"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Handler blew up: record as a 500 for this endpoint, then
            # re-raise so the normal error path + Sentry still fire.
            latency_s = time.perf_counter() - start
            self._safe_record(request, "500", latency_s)
            raise

        latency_s = time.perf_counter() - start
        self._safe_record(request, str(response.status_code), latency_s)
        return response

    @staticmethod
    def _safe_record(request, status: str, latency_s: float) -> None:
        try:
            endpoint = _endpoint_label(request)
            if endpoint in _SKIP_ENDPOINTS:
                return
            record_request(
                endpoint=endpoint, status=status, latency_s=latency_s
            )
        except Exception:  # noqa: BLE001 -- telemetry never breaks a request
            return


__all__ = ["MetricsMiddleware"]
