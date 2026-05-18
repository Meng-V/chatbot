"""
Unit tests for src.observability.sentry.

Run: `python -m src.observability.test_sentry` from ai-core/.

These verify the load-bearing SAFETY contract -- the reason this is
mergeable before any DSN/dependency exists:

  1. No DSN            -> no-op, returns False, never raises.
  2. Blank/whitespace DSN -> treated as no DSN.
  3. DSN set but sentry-sdk unimportable -> no-op, returns False,
     never raises (the app must boot even if the obs dep is missing).
  4. Idempotent: a second call short-circuits to True without
     re-reading env or re-importing the SDK.

Hermetic: NONE of these call `sentry_sdk.init` (no DSN / forced
ImportError / idempotent short-circuit), so the suite passes whether
or not sentry-sdk is installed in the venv and never mutates real
Sentry global state.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.observability import sentry as S


def _reset(monkeypatch_env: dict | None = None) -> None:
    """Reset module init state + scrub Sentry env for a clean test."""
    S._INITIALIZED = False
    import os
    for k in (
        "SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE", "NODE_ENV",
    ):
        os.environ.pop(k, None)
    for k, v in (monkeypatch_env or {}).items():
        os.environ[k] = v


def test_no_dsn_is_noop() -> None:
    _reset()
    assert S.init_sentry() is False
    assert S.is_initialized() is False


def test_blank_dsn_is_noop() -> None:
    _reset({"SENTRY_DSN": "   "})
    assert S.init_sentry() is False
    assert S.is_initialized() is False


def test_import_guard_when_sdk_missing_does_not_raise() -> None:
    """DSN set but `import sentry_sdk` fails -> the app must still boot.
    Setting sys.modules['sentry_sdk']=None makes `import sentry_sdk`
    raise ImportError, simulating a not-installed dependency."""
    _reset({"SENTRY_DSN": "https://abc@o0.ingest.sentry.io/0"})
    saved = sys.modules.get("sentry_sdk", "MISSING")
    sys.modules["sentry_sdk"] = None  # forces ImportError on import
    try:
        result = S.init_sentry()  # must NOT raise
    finally:
        if saved == "MISSING":
            sys.modules.pop("sentry_sdk", None)
        else:
            sys.modules["sentry_sdk"] = saved
    assert result is False
    assert S.is_initialized() is False


def test_idempotent_short_circuits() -> None:
    """If already initialized, a second call returns True immediately
    without touching env or the SDK (uvicorn --reload / re-import)."""
    _reset()
    S._INITIALIZED = True
    assert S.init_sentry() is True
    assert S.is_initialized() is True
    _reset()  # leave global state clean for any later test


def main() -> int:
    tests = [
        test_no_dsn_is_noop,
        test_blank_dsn_is_noop,
        test_import_guard_when_sdk_missing_does_not_raise,
        test_idempotent_short_circuits,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
