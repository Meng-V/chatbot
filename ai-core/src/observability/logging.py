"""
Structured logging setup + request-id propagation.

Every request gets a UUID at the FastAPI middleware boundary; that id
is bound into a `ContextVar` so every log line within the request
carries it without explicit threading. The forensic spine that lets
"why did this query produce a refusal?" be answered by grepping the
log for one id.

Uses `structlog` when installed; falls back to stdlib `logging` with a
JSON formatter when not. Either way the on-the-wire format is JSON,
so log shipping (Loki / Datadog / files+logrotate) doesn't care which
mode we're in.

See plan: Operations -> Op 3 -> "Structured logging".
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Optional


# --- Request context ------------------------------------------------------

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
"""The current request's id. Set by FastAPI middleware on entry, read
by every log call within the request. Use `bind_request_context()` to
set; use `get_logger()` to read."""

# Additional fields that propagate through one request. Kept as a
# single ContextVar (a dict) rather than one var per field so adding
# a new field doesn't ripple through the codebase.
_request_context_var: ContextVar[dict] = ContextVar(
    "request_context", default={}
)


def new_request_id() -> str:
    """Generate a fresh request id. Hex UUID without dashes -- shorter
    in log lines, still unique."""
    return uuid.uuid4().hex


def bind_request_context(
    *, request_id: Optional[str] = None, **fields: Any
) -> None:
    """Bind request-scoped fields into the current context.

    Call once at the FastAPI middleware boundary with the request id;
    later steps (intent, scope, model_used) bind their fields as they
    learn them. Each call merges into the existing context rather
    than replacing.

    Note: ContextVar.set returns a token that can be reset; we don't
    track it here because requests are short-lived and the var is
    reset implicitly by FastAPI's per-request task scope.
    """
    rid = request_id or request_id_var.get() or new_request_id()
    request_id_var.set(rid)
    cur = dict(_request_context_var.get())
    cur.update(fields)
    cur["request_id"] = rid
    _request_context_var.set(cur)


# --- Logger setup ---------------------------------------------------------


_SETUP_DONE = False


def setup_logging(
    *, level: str = "INFO", json_output: bool = True
) -> None:
    """Configure root logging. Idempotent.

    Args:
        level: Standard logging level name.
        json_output: True -> emit JSON lines (prod). False -> emit
            human-readable lines (dev).
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
            )
        )

    # Try structlog first; fall back to stdlib if it's not installed.
    try:
        import structlog  # type: ignore

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                _bind_request_context_processor,
                structlog.processors.JSONRenderer()
                if json_output
                else structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level)
            ),
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
    except ImportError:
        # Pure-stdlib fallback: install JSONFormatter on root.
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(level)

    _SETUP_DONE = True


def _bind_request_context_processor(_logger, _name, event_dict):
    """structlog processor: merge request context into every event."""
    ctx = _request_context_var.get()
    if ctx:
        event_dict.update(ctx)
    return event_dict


class _JSONFormatter(logging.Formatter):
    """Stdlib-only JSON formatter used when structlog isn't installed.

    Includes request context fields automatically by reading from the
    ContextVars at format time.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = _request_context_var.get()
        if ctx:
            payload.update(ctx)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Allow callers to attach extra fields via logger.info("...", extra={...})
        for key in ("intent", "scope_campus", "tool", "model_used"):
            v = getattr(record, key, None)
            if v is not None:
                payload[key] = v
        return json.dumps(payload, default=str)


def get_logger(name: str = "chatbot") -> Any:
    """Return a logger. Uses structlog when available, stdlib otherwise."""
    try:
        import structlog  # type: ignore

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


__all__ = [
    "bind_request_context",
    "get_logger",
    "new_request_id",
    "request_id_var",
    "setup_logging",
]
