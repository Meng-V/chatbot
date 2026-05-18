"""
Offline tests for RequestIdMiddleware.

Run: `python -m src.observability.test_request_id_middleware` (ai-core/).

Contract:
  1. A response always carries X-Request-ID.
  2. No/blank upstream header -> a fresh 32-hex id is minted.
  3. A SAFE upstream id (proxy / distributed trace) is reused verbatim.
  4. An UNSAFE upstream id (too long / bad chars / newline) is
     rejected and a fresh id minted (log-injection / unbounded-value
     defense).
  5. The id reaches the handler BOTH via request.state.request_id AND
     via the logging ContextVar (request_id_var) -- the latter guards
     the known BaseHTTPMiddleware contextvar-propagation caveat; if
     this assertion ever fails the middleware must become pure-ASGI.
  6. A handler exception still propagates (telemetry never swallows).

Starlette TestClient -- no network, no API, no DSN.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from src.observability.logging import request_id_var
from src.observability.request_id_middleware import RequestIdMiddleware

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _client():
    # NOTE: FastAPI resolves a handler's annotations against the
    # MODULE globals, so `Request` MUST be imported at module scope --
    # a function-local import makes `request: Request` unresolvable
    # and FastAPI then treats it as a query param (422). This bit the
    # first draft of this test; keep these imports at top level.
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    async def echo(request: Request):
        return {
            "state": getattr(request.state, "request_id", None),
            "ctx": request_id_var.get(),
        }

    @app.get("/boom")
    async def boom():
        raise RuntimeError("handler exploded")

    return TestClient(app)


def test_generates_id_when_absent() -> None:
    r = _client().get("/echo")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid and _HEX32.match(rid), rid


def test_reuses_safe_upstream_id() -> None:
    safe = "trace-abc.123_DEF"
    r = _client().get("/echo", headers={"X-Request-ID": safe})
    assert r.headers.get("X-Request-ID") == safe
    assert r.json()["state"] == safe


def test_rejects_unsafe_upstream_id() -> None:
    for bad in ("x" * 200, "bad id with spaces", "inject\nlogline", "a;b|c"):
        r = _client().get("/echo", headers={"X-Request-ID": bad})
        out = r.headers.get("X-Request-ID")
        assert out != bad and _HEX32.match(out or ""), (bad, out)


def test_id_reaches_handler_state_and_contextvar() -> None:
    r = _client().get("/echo")
    body = r.json()
    rid = r.headers["X-Request-ID"]
    assert body["state"] == rid, ("state mismatch", body, rid)
    # The load-bearing one: structlog lines emitted inside the handler
    # only carry the id if the ContextVar propagated past
    # BaseHTTPMiddleware. If this fails -> rewrite as pure ASGI.
    assert body["ctx"] == rid, ("ContextVar did not propagate", body, rid)


def test_handler_exception_still_propagates() -> None:
    raised = False
    try:
        _client().get("/boom")
    except RuntimeError as e:
        raised = "handler exploded" in str(e)
    except Exception:  # noqa: BLE001
        raised = True
    assert raised, "middleware swallowed a handler exception"


def main() -> int:
    tests = [
        test_generates_id_when_absent,
        test_reuses_safe_upstream_id,
        test_rejects_unsafe_upstream_id,
        test_id_reaches_handler_state_and_contextvar,
        test_handler_exception_still_propagates,
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
