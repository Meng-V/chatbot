"""
Per-request request_id middleware (plan Op 3: "One request_id UUID
generated at the FastAPI middleware layer, propagated through
orchestrator -> tools -> LLM client -> memory writes. Every line
carries it.").

src/observability/logging.py already has new_request_id(),
bind_request_context(), the ContextVar, and the structlog processor
that merges request context into every line -- its bind_request_context
docstring literally says "Call once at the FastAPI middleware
boundary". That middleware just didn't exist: bind was only called
inside the v2 orchestrator, so the legacy /ask path, every other
endpoint, and any logging BEFORE the orchestrator runs had no
request_id. This closes that.

Behavior:
  * Reuse an upstream X-Request-ID (proxy / distributed trace) ONLY
    if it's safe -- ^[A-Za-z0-9._-]{1,128}$. A client-controlled
    header that flows into every log line is a log-injection /
    unbounded-value vector; reject anything else and mint a fresh id.
  * Bind it before call_next so all structlog lines in the request
    carry it; also expose on request.state.request_id.
  * Echo it back as X-Request-ID so the browser / Sentry / curl can
    correlate a user report to server logs.
  * Telemetry never breaks a request: a handler exception is
    re-raised (already bound, so the error log carries the id);
    binding failure degrades to "no id" rather than 500.
"""

from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware

from src.observability.logging import bind_request_context, new_request_id

_HEADER = "X-Request-ID"
# Conservative: ids appear verbatim in every log line. Bounded length,
# log-safe charset. Anything else -> we mint our own.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _resolve_id(request) -> str:
    incoming = request.headers.get(_HEADER, "")
    if incoming and _SAFE_ID.match(incoming):
        return incoming
    return new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = _resolve_id(request)
        try:
            bind_request_context(request_id=rid)
            request.state.request_id = rid
        except Exception:  # noqa: BLE001 -- never 500 over telemetry
            pass

        response = await call_next(request)

        try:
            response.headers[_HEADER] = rid
        except Exception:  # noqa: BLE001
            pass
        return response


__all__ = ["RequestIdMiddleware"]
