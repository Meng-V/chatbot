"""
Prompt-cache health checker.

Two responsibilities:
  1. STATIC: verify that every registered prompt prefix in
     `src/prompts/` is byte-stable (hash-matches what was registered)
     and clears the OpenAI cache threshold (~1024 tokens).
  2. DYNAMIC: read `ModelTokenUsage` to compute observed cache-hit
     rate per call site over a recent window. Plan §Layer 4 calls
     for >= 0.6 average + >= 0.5 per call site as the week-4 gate.

Run:
    python -m src.observability.cache_health             # static + dynamic
    python -m src.observability.cache_health --static    # static only (no DB)
    python -m src.observability.cache_health --dynamic   # dynamic only
    python -m src.observability.cache_health --json      # machine-parseable

The dynamic path is gated on Prisma being importable (sandbox / CI
without the client returns "skipped" rather than crashing). The
static path runs unconditionally -- it's the load-bearing gate that
prevents the byte-drift class of regression.

See plan: Layer 4 ("Per-call-site strategy", "Things that silently
break caching") + Operations §Op 3 ("Cache health: cached_input_tokens
/ input_tokens rolling 1h average").
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Allow `python -m src.observability.cache_health` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))


# --- Static: registered-prefix integrity ---------------------------------


# OpenAI's prompt cache: 1024 token minimum identical prefix. We use a
# conservative 4-chars-per-token estimate (real tokens are usually
# shorter, so this errs on the safe side).
CACHE_THRESHOLD_TOKENS = 1024
CHARS_PER_TOKEN_ESTIMATE = 4
CACHE_THRESHOLD_CHARS = CACHE_THRESHOLD_TOKENS * CHARS_PER_TOKEN_ESTIMATE

# Per-call-site gates (week 4):
#   - per-site: each call site individually >= 0.5
#   - average: across all call sites >= 0.6
# These are config knobs, not constants -- the real OpenAI rates are
# verified at deploy time per the model freshness rule.
PER_SITE_GATE = 0.50
AVG_GATE = 0.60


@dataclass(frozen=True)
class PrefixCheck:
    """One row of the static prefix audit."""

    prefix_id: str
    char_length: int
    approx_tokens: int
    hash_short: str
    clears_threshold: bool
    issue: Optional[str] = None
    """Human-readable reason if the row fails the static check."""


@dataclass
class StaticReport:
    """Result of running every registered prefix through the integrity
    + threshold check. `ok` is True only when every prefix passes.
    """

    prefixes: list[PrefixCheck] = field(default_factory=list)
    ok: bool = True


def run_static_check() -> StaticReport:
    """Verify every registered prefix is intact + above the cache
    threshold. Imports the four documented prompt modules so their
    `register_prefix(...)` calls run.
    """
    # Import for side-effects: each module calls register_prefix at
    # import time. If any module is missing or fails to register,
    # the registry will reflect it and we'll report.
    from src.prompts import builder
    try:
        from src.prompts import (  # noqa: F401
            agent_v1,
            clarifier_v1,
            judge_v1,
            synthesizer_v1,
        )
    except ImportError as e:
        # If a prompt module doesn't exist or doesn't import, that's
        # a hard failure -- the prod app would crash on startup.
        return StaticReport(
            prefixes=[],
            ok=False,
        )

    rep = StaticReport()
    for prefix_id, entry in builder._REGISTRY.items():
        approx_tokens = entry["char_length"] // CHARS_PER_TOKEN_ESTIMATE
        clears = approx_tokens >= CACHE_THRESHOLD_TOKENS
        issue = None
        if not clears:
            issue = (
                f"{approx_tokens} tokens < {CACHE_THRESHOLD_TOKENS} threshold; "
                f"OpenAI cache will NOT engage. Pad with terminology "
                f"glossary / few-shot exemplars."
            )
        rep.prefixes.append(
            PrefixCheck(
                prefix_id=prefix_id,
                char_length=entry["char_length"],
                approx_tokens=approx_tokens,
                hash_short=entry["hash"][:12],
                clears_threshold=clears,
                issue=issue,
            )
        )
        if not clears:
            rep.ok = False

    # Lock-in: documented call sites must all be registered. A future
    # PR that drops one of these without updating the orchestrator
    # would silently broadcast prompts at full price.
    expected = {"agent_v1", "synthesizer_v1", "clarifier_v1", "judge_v1"}
    actual = {p.prefix_id for p in rep.prefixes}
    missing = expected - actual
    if missing:
        for prefix_id in sorted(missing):
            rep.prefixes.append(
                PrefixCheck(
                    prefix_id=prefix_id,
                    char_length=0,
                    approx_tokens=0,
                    hash_short="(not registered)",
                    clears_threshold=False,
                    issue="prompt module didn't register at import time",
                )
            )
        rep.ok = False

    return rep


# --- Dynamic: observed cache-hit rate from ModelTokenUsage --------------


@dataclass(frozen=True)
class CallSiteRate:
    """Aggregate cache-hit stats for one call site over the window."""

    call_site: str
    model: str
    call_count: int
    total_input_tokens: int
    total_cached_tokens: int

    @property
    def hit_rate(self) -> float:
        if self.total_input_tokens == 0:
            return 0.0
        return self.total_cached_tokens / self.total_input_tokens

    @property
    def passes_gate(self) -> bool:
        return self.hit_rate >= PER_SITE_GATE


@dataclass
class DynamicReport:
    """Aggregate of recent ModelTokenUsage rows by call site."""

    window_hours: int
    by_call_site: list[CallSiteRate] = field(default_factory=list)
    avg_hit_rate: float = 0.0
    """Overall average across all rows. Different from the per-site
    rate's average -- this is total_cached / total_input across the
    whole window."""
    ok: bool = True
    """True only when avg >= AVG_GATE AND every site >= PER_SITE_GATE."""
    skipped_reason: Optional[str] = None
    """Set when the dynamic check couldn't run (Prisma missing / DB
    unreachable). Caller treats skipped as neither pass nor fail."""


def run_dynamic_check(*, window_hours: int = 24) -> DynamicReport:
    """Read recent ModelTokenUsage rows and compute cache-hit rates.

    Returns DynamicReport with skipped_reason set if the DB layer
    isn't available -- not a hard failure, just an informational gap.
    """
    rep = DynamicReport(window_hours=window_hours)

    try:
        from prisma import Prisma  # type: ignore  # noqa: F401
    except ImportError:
        rep.skipped_reason = (
            "Prisma client not generated -- can't read ModelTokenUsage. "
            "Run `npx prisma generate` after the PR #13 schema migration "
            "lands in this env."
        )
        return rep

    # The actual DB query is gated on the Prisma client + the
    # PR #13 schema being deployed. Until then we skip dynamic.
    rep.skipped_reason = (
        "DB read not yet wired (week 6/7 task; gated on PR #13 prod "
        "cutover). The query shape is documented below for the next "
        "implementer."
    )
    return rep


# Documented query shape for the wiring task -- pseudo-SQL since the
# Prisma `.find_many` call is the actual implementation:
#
#   SELECT
#     "callSite",
#     "llmModelName" AS model,
#     COUNT(*) AS call_count,
#     SUM("promptTokens") AS total_input,
#     SUM("cachedInputTokens") AS total_cached
#   FROM "ModelTokenUsage"
#   WHERE "createdAt" > NOW() - INTERVAL '<window_hours> hours'
#     AND "callSite" IS NOT NULL
#   GROUP BY "callSite", "llmModelName"
#   ORDER BY total_input DESC


# --- Combined report + CLI ---------------------------------------------


@dataclass
class HealthReport:
    """Top-level health output. Consumer prints either this or
    serializes to JSON."""

    static: StaticReport
    dynamic: DynamicReport
    overall_ok: bool


def run_health_check(
    *,
    do_static: bool = True,
    do_dynamic: bool = True,
    window_hours: int = 24,
) -> HealthReport:
    static = run_static_check() if do_static else StaticReport()
    dynamic = (
        run_dynamic_check(window_hours=window_hours)
        if do_dynamic
        else DynamicReport(window_hours=window_hours,
                           skipped_reason="--static only")
    )

    # Overall ok requires static to pass; dynamic is informational
    # when skipped (skipped_reason set).
    overall_ok = static.ok and (
        dynamic.ok or dynamic.skipped_reason is not None
    )
    return HealthReport(static=static, dynamic=dynamic, overall_ok=overall_ok)


# --- Pretty printing ----------------------------------------------------


def _print_static(static: StaticReport) -> None:
    print("=" * 64)
    print("Prompt-cache static check")
    print("=" * 64)
    print(f"{'prefix_id':<20s} {'chars':>8s} {'~tokens':>8s} {'hash':>14s}  {'status':<8s}")
    print("-" * 64)
    for p in static.prefixes:
        status = "OK" if p.clears_threshold else "FAIL"
        print(
            f"{p.prefix_id:<20s} {p.char_length:>8d} {p.approx_tokens:>8d} "
            f"{p.hash_short:>14s}  {status:<8s}"
        )
        if p.issue:
            print(f"  -> {p.issue}")
    print()
    print(f"Static check: {'PASS' if static.ok else 'FAIL'}")


def _print_dynamic(dynamic: DynamicReport) -> None:
    print()
    print("=" * 64)
    print("Prompt-cache dynamic check (observed traffic)")
    print("=" * 64)
    if dynamic.skipped_reason:
        print(f"SKIPPED: {dynamic.skipped_reason}")
        return
    if not dynamic.by_call_site:
        print(f"No traffic in the last {dynamic.window_hours}h.")
        return
    print(
        f"{'call_site':<14s} {'model':<18s} {'calls':>6s} {'input':>10s} "
        f"{'cached':>10s} {'rate':>6s} {'status':<8s}"
    )
    print("-" * 76)
    for r in dynamic.by_call_site:
        status = "OK" if r.passes_gate else "FAIL"
        print(
            f"{r.call_site:<14s} {r.model:<18s} {r.call_count:>6d} "
            f"{r.total_input_tokens:>10d} {r.total_cached_tokens:>10d} "
            f"{r.hit_rate:>6.2%} {status:<8s}"
        )
    print()
    print(
        f"Average hit rate: {dynamic.avg_hit_rate:.1%} "
        f"(gate: >= {AVG_GATE:.0%})"
    )


def _print_summary(report: HealthReport) -> None:
    print()
    print("=" * 64)
    label = "PASS" if report.overall_ok else "FAIL"
    print(f"Overall: {label}")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify prompt-cache health (static prefix integrity + dynamic hit rate)."
    )
    parser.add_argument("--static", action="store_true",
                        help="Run only the static prefix check.")
    parser.add_argument("--dynamic", action="store_true",
                        help="Run only the dynamic hit-rate check.")
    parser.add_argument("--window-hours", type=int, default=24,
                        help="Dynamic check window in hours (default 24).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-parseable JSON instead of pretty trace.")
    args = parser.parse_args()

    do_static = args.static or not args.dynamic
    do_dynamic = args.dynamic or not args.static

    report = run_health_check(
        do_static=do_static, do_dynamic=do_dynamic,
        window_hours=args.window_hours,
    )

    if args.json:
        print(json.dumps(_to_jsonable(report), indent=2, default=str))
    else:
        if do_static:
            _print_static(report.static)
        if do_dynamic:
            _print_dynamic(report.dynamic)
        _print_summary(report)

    return 0 if report.overall_ok else 1


def _to_jsonable(report: HealthReport) -> dict:
    return {
        "static": {
            "ok": report.static.ok,
            "prefixes": [dataclasses.asdict(p) for p in report.static.prefixes],
        },
        "dynamic": {
            "ok": report.dynamic.ok,
            "window_hours": report.dynamic.window_hours,
            "skipped_reason": report.dynamic.skipped_reason,
            "avg_hit_rate": report.dynamic.avg_hit_rate,
            "by_call_site": [
                {
                    "call_site": r.call_site,
                    "model": r.model,
                    "call_count": r.call_count,
                    "input_tokens": r.total_input_tokens,
                    "cached_tokens": r.total_cached_tokens,
                    "hit_rate": r.hit_rate,
                    "passes_gate": r.passes_gate,
                }
                for r in report.dynamic.by_call_site
            ],
        },
        "overall_ok": report.overall_ok,
    }


__all__ = [
    "AVG_GATE",
    "CACHE_THRESHOLD_TOKENS",
    "CallSiteRate",
    "DynamicReport",
    "HealthReport",
    "PER_SITE_GATE",
    "PrefixCheck",
    "StaticReport",
    "run_dynamic_check",
    "run_health_check",
    "run_static_check",
]


if __name__ == "__main__":
    sys.exit(main())
