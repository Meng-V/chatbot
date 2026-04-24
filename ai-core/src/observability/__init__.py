"""
Observability: structured logs, metrics, request-id propagation.

Three modules, all pure-stdlib so they import cleanly even when
optional deps (structlog, prometheus_client) aren't installed -- those
are wired in lazily via try/except so dev / test environments don't
need them.

  - logging.py  -- structlog setup + request-id ContextVar
  - metrics.py  -- Prometheus metric definitions (lazy import)
  - smoketest.py -- synthetic-monitoring helper that runs a canned
                    question end-to-end

See plan: Operations -> Op 3 (system logs and observability).
"""

from src.observability.logging import (
    bind_request_context,
    get_logger,
    new_request_id,
    request_id_var,
    setup_logging,
)
from src.observability.metrics import (
    record_llm_call,
    record_request,
    record_tool_call,
)
from src.observability.smoketest import SmoketestResult, run_smoketest

__all__ = [
    "SmoketestResult",
    "bind_request_context",
    "get_logger",
    "new_request_id",
    "record_llm_call",
    "record_request",
    "record_tool_call",
    "request_id_var",
    "run_smoketest",
    "setup_logging",
]
