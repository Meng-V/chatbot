"""
Synthetic monitoring: run a canned question end to end, assert the
response has a citation, is not a refusal, and came back within the
latency bound.

Catches the class of outages where every individual component reports
healthy but the chain is broken (an API key rotated, an env var
missing, a schema mismatch between synthesizer and post-processor).
An external pinger (UptimeRobot / BetterStack free tier) hits
`/smoketest` every 5 minutes; if the synthetic fails, alert.

See plan: Operations -> Op 3 -> "Synthetic monitoring".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class SmoketestResult:
    """Outcome of one smoketest run."""

    passed: bool
    reason: str
    """Human-readable explanation. Empty string when passed=True."""

    latency_ms: int = 0
    answer_preview: str = ""
    """First ~200 chars of the bot's answer, for eyeballing in the
    monitoring UI."""

    checks: dict = field(default_factory=dict)
    """Per-check outcome dict (has_citation / is_answer / under_latency).
    Fine-grained so the alert message can say WHICH check failed."""


# Default canned question -- picked because it's answerable from a
# single high-traffic page (King Library locations), touches live hours
# via a tool, and has a stable expected shape (answer + one citation).
DEFAULT_QUESTION = "What are King Library's hours today?"
DEFAULT_LATENCY_BUDGET_MS = 8000


def run_smoketest(
    *,
    ask_bot: Callable[[str], dict],
    question: str = DEFAULT_QUESTION,
    latency_budget_ms: int = DEFAULT_LATENCY_BUDGET_MS,
) -> SmoketestResult:
    """Run the canned question through the bot and validate the shape.

    Args:
        ask_bot: Callable `(question: str) -> dict` that runs a full
            orchestrator turn. Injected rather than imported so this
            module stays dependency-free -- the caller wires the real
            orchestrator in at /smoketest endpoint time.
        question: The canned question.
        latency_budget_ms: Fail if the full turn takes longer.

    Returns:
        SmoketestResult. Pass means all three checks hit: (a) there's
        at least one citation, (b) it's not a refusal, (c) latency is
        under budget.
    """
    checks: dict = {}
    start = time.monotonic()

    try:
        response = ask_bot(question)
    except Exception as e:
        return SmoketestResult(
            passed=False,
            reason=f"ask_bot raised: {type(e).__name__}: {e}",
            latency_ms=int((time.monotonic() - start) * 1000),
            checks={"reachable": False},
        )

    latency_ms = int((time.monotonic() - start) * 1000)

    # Check 1: not a refusal
    is_refusal = bool(response.get("is_refusal", False))
    checks["is_answer"] = not is_refusal

    # Check 2: has at least one citation
    citations = response.get("citations") or []
    checks["has_citation"] = len(citations) > 0

    # Check 3: under latency budget
    checks["under_latency"] = latency_ms <= latency_budget_ms

    passed = all(checks.values())
    reason = "" if passed else _explain_failure(checks, latency_ms, latency_budget_ms)
    answer = response.get("answer", "") or ""
    preview = answer[:200]

    return SmoketestResult(
        passed=passed,
        reason=reason,
        latency_ms=latency_ms,
        answer_preview=preview,
        checks=checks,
    )


def _explain_failure(
    checks: dict, latency_ms: int, budget_ms: int
) -> str:
    bits = []
    if checks.get("reachable") is False:
        bits.append("backend unreachable")
    if not checks.get("is_answer", False):
        bits.append("response was a refusal")
    if not checks.get("has_citation", False):
        bits.append("no citations")
    if not checks.get("under_latency", False):
        bits.append(f"latency {latency_ms}ms > budget {budget_ms}ms")
    return "; ".join(bits) if bits else "unknown failure"


__all__ = [
    "DEFAULT_QUESTION",
    "DEFAULT_LATENCY_BUDGET_MS",
    "SmoketestResult",
    "run_smoketest",
]
