"""
Offline tests for the /metrics endpoint + MetricsMiddleware.

Run: `python -m src.observability.test_metrics_endpoint` from ai-core/.

prometheus_client is intentionally NOT a hard requirement, so in this
venv it's absent -- which is exactly the merge-safety path we most
need to prove:

  1. /metrics serves a self-describing plaintext 200 (never 500s a
     scrape) when prometheus_client is missing.
  2. render_latest() returns (bytes, str) and never raises.
  3. The middleware never breaks a normal request.
  4. A handler exception still PROPAGATES (telemetry must not swallow
     errors -- Sentry / error handling must still see them).
  5. Endpoint labels are low-cardinality (route template, or the
     single `<unmatched>` bucket for 404s) -- never the raw path.
  6. The infra-poll skip set excludes /metrics and /health/live.

Uses Starlette's TestClient (httpx-backed) -- no network, no API.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.observability.metrics import render_latest
from src.observability.metrics_middleware import (
    MetricsMiddleware,
    _SKIP_ENDPOINTS,
    _endpoint_label,
)


def _app():
    from fastapi import FastAPI
    from src.api.metrics_router import build_metrics_router

    app = FastAPI()
    app.add_middleware(MetricsMiddleware)
    app.include_router(build_metrics_router())

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("handler exploded")

    return app


def _client():
    from starlette.testclient import TestClient

    return TestClient(_app())


def _prom_installed() -> bool:
    try:
        import prometheus_client  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def test_metrics_endpoint_200_environment_aware() -> None:
    """/metrics must be a non-500 200 in BOTH environments. The suite
    runs where prometheus_client is absent (minimal CI) AND where it's
    installed (dev/prod) -- assert the correct behavior for whichever
    this is, not a fixed one."""
    r = _client().get("/metrics")
    assert r.status_code == 200, r.status_code
    if _prom_installed():
        # Real Prometheus exposition: scrape-able text with our metric
        # names / HELP/TYPE headers. (Counters may be zero-valued until
        # a request flows, but the metric families are still emitted.)
        assert "chatbot_" in r.text or "# HELP" in r.text or r.text == "", (
            r.headers.get("content-type"), r.text[:200],
        )
    else:
        assert r.headers["content-type"].startswith("text/plain")
        assert "prometheus_client not installed" in r.text


def test_render_latest_contract() -> None:
    body, ctype = render_latest()
    assert isinstance(body, (bytes, bytearray)), type(body)
    assert isinstance(ctype, str) and ctype


def test_normal_request_unaffected_by_middleware() -> None:
    r = _client().get("/ok")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_handler_exception_still_propagates() -> None:
    """Telemetry must not swallow errors. TestClient re-raises server
    exceptions by default; the middleware records a 500 then re-raises,
    so this must surface the original RuntimeError."""
    raised = False
    try:
        _client().get("/boom")
    except RuntimeError as e:
        raised = "handler exploded" in str(e)
    except Exception:  # noqa: BLE001
        raised = True  # some wrapping is fine; swallowing is not
    assert raised, "middleware swallowed a handler exception"


def test_endpoint_label_low_cardinality() -> None:
    class _R:
        path = "/use/{slug}"

    class _Req:
        def __init__(self, scope):
            self.scope = scope

    assert _endpoint_label(_Req({"route": _R()})) == "/use/{slug}"
    assert _endpoint_label(_Req({})) == "<unmatched>"


def test_infra_polls_are_skipped() -> None:
    assert "/metrics" in _SKIP_ENDPOINTS
    assert "/health/live" in _SKIP_ENDPOINTS


def main() -> int:
    tests = [
        test_metrics_endpoint_200_environment_aware,
        test_render_latest_contract,
        test_normal_request_unaffected_by_middleware,
        test_handler_exception_still_propagates,
        test_endpoint_label_low_cardinality,
        test_infra_polls_are_skipped,
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
