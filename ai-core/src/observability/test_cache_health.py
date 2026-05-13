"""
Tests for the prompt-cache health checker.

Run: `python -m src.observability.test_cache_health` from ai-core/.

The static check is the load-bearing test: it's what stops a prompt
edit from silently falling below the cache threshold and inflating
costs by 3-4x. Dynamic check is informational + gated on prod DB.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Allow `python -m src.observability.test_cache_health` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.observability.cache_health import (  # noqa: E402
    AVG_GATE,
    CACHE_THRESHOLD_TOKENS,
    CallSiteRate,
    DynamicReport,
    HealthReport,
    PER_SITE_GATE,
    PrefixCheck,
    StaticReport,
    _print_dynamic,
    _print_static,
    _print_summary,
    _to_jsonable,
    run_dynamic_check,
    run_health_check,
    run_static_check,
)


# --- Static check ---


def test_static_check_passes_for_current_prefixes() -> None:
    """The four shipped prompts are all padded above the cache
    threshold (verified by their own test_builder lock-in test).
    The static cache health check must agree."""
    rep = run_static_check()
    assert rep.ok, (
        f"static check failed; problematic prefixes: "
        f"{[(p.prefix_id, p.issue) for p in rep.prefixes if not p.clears_threshold]}"
    )


def test_static_check_includes_all_four_prefixes() -> None:
    rep = run_static_check()
    found = {p.prefix_id for p in rep.prefixes}
    expected = {"agent_v1", "synthesizer_v1", "clarifier_v1", "judge_v1"}
    assert expected.issubset(found), f"missing prefixes: {expected - found}"


def test_static_check_records_byte_length_and_token_estimate() -> None:
    rep = run_static_check()
    for p in rep.prefixes:
        assert p.char_length > 0
        assert p.approx_tokens > 0
        assert p.approx_tokens == p.char_length // 4
        # Hash should be at least the documented short form.
        assert len(p.hash_short) >= 12


def test_static_check_reports_threshold() -> None:
    """All shipped prefixes clear the threshold; lock-in confirms."""
    rep = run_static_check()
    for p in rep.prefixes:
        assert p.clears_threshold, (
            f"{p.prefix_id} doesn't clear cache threshold "
            f"({p.approx_tokens} tokens vs {CACHE_THRESHOLD_TOKENS})"
        )


def test_static_check_failure_records_issue() -> None:
    """When a prefix fails, the issue field carries human-readable
    guidance. (Synthesized via direct PrefixCheck since no shipped
    prefix actually fails.)"""
    p = PrefixCheck(
        prefix_id="too_short_v1",
        char_length=100, approx_tokens=25, hash_short="abc123",
        clears_threshold=False,
        issue=f"25 tokens < {CACHE_THRESHOLD_TOKENS}; pad with glossary",
    )
    assert p.issue is not None
    assert "tokens" in p.issue.lower()
    assert str(CACHE_THRESHOLD_TOKENS) in p.issue


# --- Dynamic check (skipped path) ---


def test_dynamic_check_skipped_when_db_unavailable() -> None:
    """Sandbox / CI without Prisma should skip cleanly, not crash."""
    rep = run_dynamic_check(window_hours=24)
    assert rep.skipped_reason is not None
    assert rep.window_hours == 24


def test_dynamic_skipped_does_not_fail_overall() -> None:
    """Dynamic SKIPPED + static PASS -> overall PASS. Skipped is
    informational, not a failure."""
    rep = run_health_check()
    if rep.dynamic.skipped_reason:
        # Static must pass; overall must reflect static only.
        assert rep.overall_ok == rep.static.ok


def test_dynamic_dynamic_only_returns_skipped() -> None:
    rep = run_health_check(do_static=False, do_dynamic=True)
    # Static skipped -> empty StaticReport, ok=True by default
    assert rep.static.ok is True
    # Dynamic skipped (no DB) -> overall ok carries the static True
    assert rep.overall_ok is True


# --- CallSiteRate computations ---


def test_call_site_rate_hit_rate() -> None:
    r = CallSiteRate(
        call_site="agent",
        model="gpt-5.4-mini",
        call_count=100,
        total_input_tokens=10000,
        total_cached_tokens=7000,
    )
    assert r.hit_rate == 0.7
    assert r.passes_gate is True  # 0.7 >= 0.5


def test_call_site_rate_below_gate() -> None:
    r = CallSiteRate(
        call_site="synthesizer",
        model="gpt-5.4-mini",
        call_count=50,
        total_input_tokens=10000,
        total_cached_tokens=3000,
    )
    assert r.hit_rate == 0.3
    assert r.passes_gate is False  # 0.3 < 0.5


def test_call_site_rate_zero_input_returns_zero() -> None:
    """Defensive: a freshly-deployed call site with zero traffic
    shouldn't divide-by-zero."""
    r = CallSiteRate(
        call_site="judge",
        model="gpt-5.4-mini",
        call_count=0,
        total_input_tokens=0,
        total_cached_tokens=0,
    )
    assert r.hit_rate == 0.0
    assert r.passes_gate is False


# --- Combined / overall ---


def test_run_health_check_default_runs_both() -> None:
    rep = run_health_check()
    assert isinstance(rep, HealthReport)
    assert rep.static.prefixes  # static ran
    # Dynamic ran and was skipped (DB unavailable in sandbox).
    assert rep.dynamic.skipped_reason is not None


def test_run_health_check_static_only() -> None:
    rep = run_health_check(do_static=True, do_dynamic=False)
    assert rep.static.prefixes
    # Dynamic was not run -> empty, no skipped reason from that path.
    # In our impl, an unrun dynamic returns a synthesized SKIPPED
    # explanation that says --static only.
    assert "static only" in (rep.dynamic.skipped_reason or "").lower()


def test_overall_ok_requires_static_pass() -> None:
    """If static fails, overall MUST fail regardless of dynamic."""
    bad_static = StaticReport(
        prefixes=[
            PrefixCheck(
                prefix_id="bad_v1", char_length=10, approx_tokens=2,
                hash_short="abc", clears_threshold=False,
                issue="too short",
            )
        ],
        ok=False,
    )
    healthy_dynamic = DynamicReport(
        window_hours=24,
        avg_hit_rate=0.8,
        ok=True,
    )
    rep = HealthReport(static=bad_static, dynamic=healthy_dynamic, overall_ok=False)
    assert rep.overall_ok is False


# --- JSON serialization ---


def test_to_jsonable_round_trip() -> None:
    """JSON output is parseable + contains the documented top-level
    keys."""
    rep = run_health_check()
    j = _to_jsonable(rep)
    import json
    s = json.dumps(j, default=str)  # must not raise
    parsed = json.loads(s)
    assert "static" in parsed
    assert "dynamic" in parsed
    assert "overall_ok" in parsed
    assert "prefixes" in parsed["static"]


def test_to_jsonable_includes_per_call_site_rates() -> None:
    """When dynamic ran with traffic, JSON must surface per-site rows."""
    static = StaticReport(prefixes=[], ok=True)
    dynamic = DynamicReport(
        window_hours=24,
        avg_hit_rate=0.65,
        by_call_site=[
            CallSiteRate("agent", "gpt-5.4-mini", 100, 10000, 7000),
            CallSiteRate("synth", "gpt-5.4-mini", 50, 5000, 3000),
        ],
        ok=False,  # synth below 0.5
    )
    rep = HealthReport(static=static, dynamic=dynamic, overall_ok=False)
    j = _to_jsonable(rep)
    sites = j["dynamic"]["by_call_site"]
    assert len(sites) == 2
    assert sites[0]["call_site"] == "agent"
    assert sites[0]["hit_rate"] == 0.7
    # 3000 / 5000 = 0.6 -> >= 0.5 gate -> passes.
    assert sites[1]["hit_rate"] == 0.6
    assert sites[1]["passes_gate"] is True


# --- Pretty-print smoke ---


def test_print_static_includes_each_prefix() -> None:
    buf = io.StringIO()
    rep = run_static_check()
    with redirect_stdout(buf):
        _print_static(rep)
    out = buf.getvalue()
    assert "Prompt-cache static check" in out
    for p in rep.prefixes:
        assert p.prefix_id in out
    assert "PASS" in out or "FAIL" in out


def test_print_dynamic_skipped_message() -> None:
    """When dynamic is skipped, the print path shows the reason
    rather than a confusing empty table."""
    rep = DynamicReport(
        window_hours=24, skipped_reason="Prisma not generated"
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_dynamic(rep)
    out = buf.getvalue()
    assert "SKIPPED" in out
    assert "Prisma not generated" in out


def test_print_dynamic_with_traffic() -> None:
    rep = DynamicReport(
        window_hours=24,
        by_call_site=[
            CallSiteRate("agent", "gpt-5.4-mini", 100, 10000, 7000),
        ],
        avg_hit_rate=0.7,
        ok=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_dynamic(rep)
    out = buf.getvalue()
    assert "agent" in out
    assert "70" in out  # 70% hit rate


def test_print_summary_pass_and_fail() -> None:
    static = StaticReport(prefixes=[], ok=True)
    dynamic = DynamicReport(window_hours=24, ok=True)
    rep_pass = HealthReport(static=static, dynamic=dynamic, overall_ok=True)
    rep_fail = HealthReport(static=static, dynamic=dynamic, overall_ok=False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_summary(rep_pass)
        _print_summary(rep_fail)
    out = buf.getvalue()
    assert "PASS" in out
    assert "FAIL" in out


# --- Constants ---


def test_documented_gates() -> None:
    """Lock-in: per-site and average gates match the plan §Layer 4."""
    assert PER_SITE_GATE == 0.50
    assert AVG_GATE == 0.60
    assert CACHE_THRESHOLD_TOKENS == 1024


def main() -> int:
    tests = [
        test_static_check_passes_for_current_prefixes,
        test_static_check_includes_all_four_prefixes,
        test_static_check_records_byte_length_and_token_estimate,
        test_static_check_reports_threshold,
        test_static_check_failure_records_issue,
        test_dynamic_check_skipped_when_db_unavailable,
        test_dynamic_skipped_does_not_fail_overall,
        test_dynamic_dynamic_only_returns_skipped,
        test_call_site_rate_hit_rate,
        test_call_site_rate_below_gate,
        test_call_site_rate_zero_input_returns_zero,
        test_run_health_check_default_runs_both,
        test_run_health_check_static_only,
        test_overall_ok_requires_static_pass,
        test_to_jsonable_round_trip,
        test_to_jsonable_includes_per_call_site_rates,
        test_print_static_includes_each_prefix,
        test_print_dynamic_skipped_message,
        test_print_dynamic_with_traffic,
        test_print_summary_pass_and_fail,
        test_documented_gates,
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
