"""
Unit tests for the Prometheus metrics recording layer.

Run: `python -m src.observability.test_metrics` from ai-core/.

The metrics module is lazy-loaded: when `prometheus_client` isn't
installed (dev / sandbox / tests), every record_* call must be a
silent no-op. Prod has the lib; test env doesn't. Either way, the
calling code (orchestrator, agent loop) must not see exceptions.

A bug here could either:
  - Crash the request path on dev when someone calls record_*
    without realizing prometheus is optional (forces every dev to
    install the lib).
  - Silently fail to record in prod (no metrics, no alerts -- the
    invisible failure mode).

Tests cover both branches: simulating "prom unavailable" by inserting
None into sys.modules to short-circuit the import, and exercising the
"prom available" path only when the lib is actually installed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.observability.test_metrics`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))


def _fresh_metrics_module(prom_block: bool = True):
    """Reimport the metrics module so the global `_prom_available`
    cache is reset. Each test that touches the cache calls this first
    to avoid bleed-over from previous tests in the same run.

    Args:
        prom_block: If True, insert None into sys.modules to make
            `import prometheus_client` raise. If False, leave the real
            (or absent) lib alone.
    """
    if prom_block:
        # Setting to None makes `import prometheus_client` raise ImportError.
        sys.modules["prometheus_client"] = None  # type: ignore[assignment]
    else:
        # Drop any sentinel; let the real import attempt happen.
        if (
            "prometheus_client" in sys.modules
            and sys.modules["prometheus_client"] is None
        ):
            del sys.modules["prometheus_client"]
    import src.observability.metrics as m
    importlib.reload(m)
    return m


def _prom_installed() -> bool:
    """Probe whether the real prometheus_client is importable. Used to
    skip the available-path tests in environments without the lib."""
    if "prometheus_client" in sys.modules and sys.modules["prometheus_client"] is None:
        del sys.modules["prometheus_client"]
    try:
        import prometheus_client  # noqa: F401
        return True
    except ImportError:
        return False


# --- Unavailable path: must no-op silently -------------------------------


def test_record_request_no_op_when_prom_missing() -> None:
    m = _fresh_metrics_module(prom_block=True)
    # Should not raise.
    m.record_request(endpoint="/chat", status="ok", latency_s=0.123)


def test_record_tool_call_no_op_when_prom_missing() -> None:
    m = _fresh_metrics_module(prom_block=True)
    m.record_tool_call(tool="search_kb", status="ok", latency_s=0.05)
    m.record_tool_call(tool="get_hours", status="error", latency_s=0.5)


def test_record_llm_call_no_op_when_prom_missing() -> None:
    m = _fresh_metrics_module(prom_block=True)
    m.record_llm_call(
        model="gpt-5.4-mini", call_site="agent", status="ok",
        latency_s=0.4, input_tokens=100, cached_input_tokens=80, output_tokens=20,
    )


def test_record_refusal_no_op_when_prom_missing() -> None:
    m = _fresh_metrics_module(prom_block=True)
    m.record_refusal(trigger="citation_invalid")
    m.record_refusal(trigger="no_results")


def test_ensure_metrics_caches_unavailable_result() -> None:
    """Second call must NOT re-attempt the import. Verified by
    inspecting the cached _prom_available global."""
    m = _fresh_metrics_module(prom_block=True)
    assert m._ensure_metrics() is False
    assert m._prom_available is False
    # Second call returns same value.
    assert m._ensure_metrics() is False


def test_record_llm_call_zero_tokens_is_safe() -> None:
    """record_llm_call accepts default zero-token args without
    crashing. The conditional `if input_tokens:` guards against
    Counter.inc(0)."""
    m = _fresh_metrics_module(prom_block=True)
    m.record_llm_call(
        model="gpt-5.4-mini", call_site="agent", status="ok", latency_s=0.1,
    )


def test_public_api_surface() -> None:
    """Lock in the documented record_* surface so a future PR can't
    silently rename a function and leave callers broken."""
    m = _fresh_metrics_module(prom_block=True)
    expected = {
        "record_request", "record_tool_call",
        "record_llm_call", "record_refusal",
    }
    actual = set(getattr(m, "__all__", []))
    assert expected.issubset(actual), f"missing from __all__: {expected - actual}"


# --- Available path: only runs when prom is installed --------------------


def test_record_increments_counters_when_prom_available() -> None:
    """When prometheus_client IS installed (prod path), record_*
    actually increments labelled counters. Skipped in environments
    that don't have the lib (test sandbox)."""
    if not _prom_installed():
        print("  (skipped: prometheus_client not installed)")
        return
    m = _fresh_metrics_module(prom_block=False)
    assert m._ensure_metrics() is True
    m.record_request(endpoint="/chat", status="ok", latency_s=0.1)
    m.record_request(endpoint="/chat", status="ok", latency_s=0.2)
    counter = m._metrics["request_count"]
    val = counter.labels(endpoint="/chat", status="ok")._value.get()
    assert val >= 2.0


def test_ensure_metrics_caches_available_result() -> None:
    """When prom IS available, the cache should reflect that on the
    first call and short-circuit subsequent calls."""
    if not _prom_installed():
        print("  (skipped: prometheus_client not installed)")
        return
    m = _fresh_metrics_module(prom_block=False)
    assert m._ensure_metrics() is True
    assert m._prom_available is True
    # Second call returns same value without rebuilding the metrics dict.
    metrics_id = id(m._metrics)
    assert m._ensure_metrics() is True
    assert id(m._metrics) == metrics_id


def main() -> int:
    tests = [
        test_record_request_no_op_when_prom_missing,
        test_record_tool_call_no_op_when_prom_missing,
        test_record_llm_call_no_op_when_prom_missing,
        test_record_refusal_no_op_when_prom_missing,
        test_ensure_metrics_caches_unavailable_result,
        test_record_llm_call_zero_tokens_is_safe,
        test_public_api_surface,
        test_record_increments_counters_when_prom_available,
        test_ensure_metrics_caches_available_result,
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
