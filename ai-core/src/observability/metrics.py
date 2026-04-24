"""
Prometheus metrics. Lazy-loaded so environments without
prometheus_client installed (dev / tests) still import this module.

Recording API: `record_request()`, `record_tool_call()`,
`record_llm_call()`. Each no-ops when prometheus_client isn't
available. Prod has the lib; dev doesn't need to.

The metrics themselves match the plan's Op 3 list:
  - Per HTTP endpoint: latency p50/p95/p99, error rate
  - Per LLM model: calls, latency, input / cached / output tokens, errors
  - Per tool: calls, latency, errors
  - Per dependency: latency + success rate
  - Cache hit rate (derived from token counters)
  - Refusal rate, citation-invalid rate

See plan: Operations -> Op 3 -> "Metrics".
"""

from __future__ import annotations

from typing import Optional


# --- Lazy lib detection ---------------------------------------------------

_prom_available: Optional[bool] = None
_metrics: dict = {}


def _ensure_metrics() -> bool:
    """Import prometheus_client on first use; cache result.

    Returns True if the lib is available and metrics are defined, False
    otherwise (in which case all record_* calls are no-ops).
    """
    global _prom_available
    if _prom_available is not None:
        return _prom_available

    try:
        from prometheus_client import Counter, Histogram  # type: ignore

        _metrics["request_count"] = Counter(
            "chatbot_request_count",
            "Total chatbot requests",
            ["endpoint", "status"],
        )
        _metrics["request_latency"] = Histogram(
            "chatbot_request_latency_seconds",
            "Request latency (seconds)",
            ["endpoint"],
        )
        _metrics["tool_call_count"] = Counter(
            "chatbot_tool_call_count",
            "Tool invocations",
            ["tool", "status"],
        )
        _metrics["tool_latency"] = Histogram(
            "chatbot_tool_latency_seconds",
            "Tool call latency (seconds)",
            ["tool"],
        )
        _metrics["llm_call_count"] = Counter(
            "chatbot_llm_call_count",
            "LLM API calls",
            ["model", "call_site", "status"],
        )
        _metrics["llm_latency"] = Histogram(
            "chatbot_llm_latency_seconds",
            "LLM call latency (seconds)",
            ["model", "call_site"],
        )
        _metrics["llm_input_tokens"] = Counter(
            "chatbot_llm_input_tokens",
            "Input tokens sent to the LLM",
            ["model", "call_site"],
        )
        _metrics["llm_cached_input_tokens"] = Counter(
            "chatbot_llm_cached_input_tokens",
            "Input tokens served from the prompt cache",
            ["model", "call_site"],
        )
        _metrics["llm_output_tokens"] = Counter(
            "chatbot_llm_output_tokens",
            "Output tokens produced by the LLM",
            ["model", "call_site"],
        )
        _metrics["refusal_count"] = Counter(
            "chatbot_refusal_count",
            "Refusal responses, by trigger",
            ["trigger"],
        )
        _prom_available = True
    except ImportError:
        _prom_available = False

    return _prom_available


# --- Recording helpers ----------------------------------------------------


def record_request(
    *, endpoint: str, status: str, latency_s: float
) -> None:
    """Record one HTTP request."""
    if not _ensure_metrics():
        return
    _metrics["request_count"].labels(endpoint=endpoint, status=status).inc()
    _metrics["request_latency"].labels(endpoint=endpoint).observe(latency_s)


def record_tool_call(*, tool: str, status: str, latency_s: float) -> None:
    """Record one tool invocation."""
    if not _ensure_metrics():
        return
    _metrics["tool_call_count"].labels(tool=tool, status=status).inc()
    _metrics["tool_latency"].labels(tool=tool).observe(latency_s)


def record_llm_call(
    *,
    model: str,
    call_site: str,
    status: str,
    latency_s: float,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Record one LLM API call.

    `call_site` is a short label: `agent`, `synthesizer`, `clarifier`,
    `judge`, `embed`. Used for the plan's per-call-site cache-hit-rate
    check (>= 0.5 at every site).
    """
    if not _ensure_metrics():
        return
    _metrics["llm_call_count"].labels(
        model=model, call_site=call_site, status=status
    ).inc()
    _metrics["llm_latency"].labels(
        model=model, call_site=call_site
    ).observe(latency_s)
    if input_tokens:
        _metrics["llm_input_tokens"].labels(
            model=model, call_site=call_site
        ).inc(input_tokens)
    if cached_input_tokens:
        _metrics["llm_cached_input_tokens"].labels(
            model=model, call_site=call_site
        ).inc(cached_input_tokens)
    if output_tokens:
        _metrics["llm_output_tokens"].labels(
            model=model, call_site=call_site
        ).inc(output_tokens)


def record_refusal(*, trigger: str) -> None:
    """Record one refusal. `trigger` is the RefusalTrigger value."""
    if not _ensure_metrics():
        return
    _metrics["refusal_count"].labels(trigger=trigger).inc()


__all__ = [
    "record_llm_call",
    "record_refusal",
    "record_request",
    "record_tool_call",
]
