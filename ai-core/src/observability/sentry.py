"""
Sentry error tracking for the FastAPI backend.

Plan: Operations -> Op 3 -> "Exception tracking. Sentry ... on both
FastAPI backend and React frontend." Listed as NON-NEGOTIABLE on day
one of launch (Op 3 minimum viable version + robustness-ladder Gap 6):
without it, errors don't surface until a user complains about a 500.

Design contract (so this is safe to merge BEFORE any DSN exists and
BEFORE the sentry-sdk dependency is installed):

  * No `SENTRY_DSN` env  -> complete no-op (returns False).
  * `sentry_sdk` not importable -> complete no-op (returns False),
    one INFO line, never raises. The dependency is declared in
    pyproject, but the runtime guard means a not-yet-`pip install`ed
    environment (CI, a dev box, the operator mid-upgrade) still boots
    the app identically.
  * Idempotent: a second call is a no-op (uvicorn --reload / test
    re-import won't double-init).

So merging this changes runtime behavior by exactly zero until an
operator sets SENTRY_DSN. "Better, not worse" by construction.

Privacy: `send_default_pii=False` — this bot handles student
questions; we do NOT want message bodies / IPs shipped to a third
party. Error type + stack trace + release tag is the signal; the
content is not.

Tracing: `traces_sample_rate` defaults to 0.0 (errors only). Perf
tracing is opt-in via env because it adds request volume/cost and the
day-one need is "we find out about exceptions", not APM.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level idempotency guard. uvicorn --reload, pytest re-imports,
# and a defensive double-call from main all must not re-init Sentry
# (sentry_sdk tolerates it but we keep the contract explicit + cheap).
_INITIALIZED = False


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def init_sentry() -> bool:
    """Initialize Sentry if (and only if) a DSN is configured and the
    SDK is importable. Returns True iff Sentry is now active.

    Call ONCE, as early as possible in process startup (before the
    FastAPI app object is created) so sentry-sdk's auto-enabled
    FastAPI/Starlette integration instruments the whole request path.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return True

    dsn = _env("SENTRY_DSN")
    if not dsn:
        logger.info("Sentry disabled: SENTRY_DSN not set (no-op).")
        return False

    try:
        import sentry_sdk  # type: ignore
    except Exception as e:  # noqa: BLE001 -- ImportError or partial install
        # Declared in pyproject; if it's somehow not installed we must
        # NOT take the app down for a missing observability dep.
        logger.warning(
            "Sentry DSN set but sentry-sdk unavailable (%s); skipping. "
            "`pip install 'sentry-sdk[fastapi]'` to enable.",
            e,
        )
        return False

    # Environment + release are best-effort tags. NODE_ENV is what the
    # rest of main.py already keys CORS off, so reuse it for parity.
    environment = (
        _env("SENTRY_ENVIRONMENT")
        or _env("NODE_ENV", "development")
    )
    release: Optional[str] = _env("SENTRY_RELEASE") or None

    try:
        traces_sample_rate = float(_env("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    except ValueError:
        traces_sample_rate = 0.0

    try:
        # Minimal init: let sentry-sdk auto-enable the FastAPI/Starlette
        # integrations (it detects them). We deliberately do NOT hard-
        # import a specific integration module path -- those move
        # between sentry-sdk majors and a bad import here would defeat
        # the whole "never take the app down for observability" rule.
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            # Privacy: never ship message bodies / headers / IPs.
            send_default_pii=False,
        )
    except Exception as e:  # noqa: BLE001 -- never let telemetry crash boot
        logger.warning("Sentry init failed (%s); continuing without it.", e)
        return False

    _INITIALIZED = True
    logger.info(
        "Sentry initialized (env=%s, release=%s, traces=%.3f).",
        environment, release or "(unset)", traces_sample_rate,
    )
    return True


def is_initialized() -> bool:
    """True iff `init_sentry()` successfully activated Sentry. Lets
    tests / health surfaces report Sentry status without poking
    sentry_sdk internals."""
    return _INITIALIZED
