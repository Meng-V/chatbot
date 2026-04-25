"""
Unit tests for the request-id ContextVar plumbing.

Run: `python -m src.observability.test_logging` from ai-core/.

The full structlog setup is integration-tested (it actually has to
write to stdout); these tests cover the request-context ContextVar
glue, which is what makes "every log line in this request carries the
same id" actually work.

Tests:
  1. new_request_id returns a hex string of stable shape (32 chars).
  2. new_request_id calls produce different ids.
  3. bind_request_context with explicit id sets it.
  4. bind_request_context without id auto-generates one.
  5. bind_request_context preserves the existing id on subsequent calls.
  6. bind_request_context merges fields from multiple calls.
  7. ContextVar isolates per-task (asyncio).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.observability.test_logging`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.observability.logging import (  # noqa: E402
    _request_context_var,
    bind_request_context,
    new_request_id,
    request_id_var,
)


def _reset() -> None:
    request_id_var.set(None)
    _request_context_var.set({})


def test_new_request_id_shape() -> None:
    rid = new_request_id()
    assert isinstance(rid, str)
    assert len(rid) == 32
    # UUID hex is all lowercase hex digits.
    assert all(c in "0123456789abcdef" for c in rid)


def test_new_request_id_uniqueness() -> None:
    ids = {new_request_id() for _ in range(100)}
    assert len(ids) == 100  # vanishingly low collision probability


def test_bind_request_context_with_explicit_id() -> None:
    _reset()
    bind_request_context(request_id="abc123")
    assert request_id_var.get() == "abc123"
    assert _request_context_var.get()["request_id"] == "abc123"


def test_bind_request_context_auto_generates_id() -> None:
    _reset()
    bind_request_context()
    rid = request_id_var.get()
    assert rid is not None
    assert len(rid) == 32


def test_bind_request_context_preserves_existing_id() -> None:
    """Second call without an id reuses the one set by the first call.
    Without this, every nested middleware/handler would mint a new id
    and the forensic spine breaks."""
    _reset()
    bind_request_context(request_id="abc")
    bind_request_context(intent="hours")
    assert request_id_var.get() == "abc"
    ctx = _request_context_var.get()
    assert ctx["request_id"] == "abc"
    assert ctx["intent"] == "hours"


def test_bind_request_context_merges_fields() -> None:
    _reset()
    bind_request_context(request_id="r1", intent="hours")
    bind_request_context(scope_campus="oxford")
    bind_request_context(model_used="gpt-5.4-mini")
    ctx = _request_context_var.get()
    assert ctx["request_id"] == "r1"
    assert ctx["intent"] == "hours"
    assert ctx["scope_campus"] == "oxford"
    assert ctx["model_used"] == "gpt-5.4-mini"


def test_context_isolated_across_asyncio_tasks() -> None:
    """ContextVar is per-task by default in asyncio. Two concurrent
    requests must NOT see each other's ids -- without this, log lines
    from request A could carry request B's id."""
    _reset()

    async def worker(rid: str) -> str | None:
        bind_request_context(request_id=rid)
        # Yield to scheduler so other task interleaves.
        await asyncio.sleep(0)
        # After the yield, our id must still be ours, not the other task's.
        return request_id_var.get()

    async def main() -> tuple[str | None, str | None]:
        return await asyncio.gather(worker("alpha"), worker("beta"))

    a, b = asyncio.run(main())
    assert a == "alpha"
    assert b == "beta"


def main() -> int:
    tests = [
        test_new_request_id_shape,
        test_new_request_id_uniqueness,
        test_bind_request_context_with_explicit_id,
        test_bind_request_context_auto_generates_id,
        test_bind_request_context_preserves_existing_id,
        test_bind_request_context_merges_fields,
        test_context_isolated_across_asyncio_tasks,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
