"""
Tests for the v2 stack smoke harness.

Run: `python -m src.eval.test_smoke_e2e` from ai-core/.

Two layers:
  1. The path-classifier function (pure)
  2. The fixture set itself: each one runs, takes its expected path,
     and produces a response shape the UI can render.

If the smoke harness ever falsely passes (says ok when the orchestrator
silently regressed), the team loses its end-to-end safety net. Tests
make that hard.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m src.eval.test_smoke_e2e` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.smoke_e2e import (  # noqa: E402
    SmokeFixture,
    SmokeResult,
    _FIXTURES,
    _build_deps,
    classify_response_path,
    run_smoke,
)
from src.graph.new_orchestrator import TurnResponse  # noqa: E402


def _resp(
    *, agent_stopped_reason: str = "clean", is_refusal: bool = False,
) -> TurnResponse:
    return TurnResponse(
        answer="x",
        is_refusal=is_refusal,
        refusal_trigger=None,
        citations=[],
        confidence="high",
        intent="hours",
        scope={"campus": "oxford", "library": None, "source": "default"},
        model_used="(stub)",
        tokens={"input": 0, "cached_input": 0, "output": 0},
        fired_corrections=[],
        agent_stopped_reason=agent_stopped_reason,
        latency_ms=0,
        cited_chunk_ids=[],
    )


# --- classify_response_path (pure) ---


def test_classify_path_clarify() -> None:
    assert classify_response_path(_resp(agent_stopped_reason="clarify")) == "clarify"


def test_classify_path_point_to_url() -> None:
    assert classify_response_path(_resp(agent_stopped_reason="point_to_url")) == "point_to_url"


def test_classify_path_refuse() -> None:
    assert classify_response_path(_resp(agent_stopped_reason="refuse", is_refusal=True)) == "refuse"


def test_classify_path_agent_then_answer() -> None:
    assert (
        classify_response_path(_resp(agent_stopped_reason="clean", is_refusal=False))
        == "agent_then_answer"
    )


def test_classify_path_agent_then_refusal_after_clean_run() -> None:
    """The agent ran cleanly but the synthesizer / post-processor
    refused. agent_stopped_reason='clean' but is_refusal=True."""
    assert (
        classify_response_path(_resp(agent_stopped_reason="clean", is_refusal=True))
        == "agent_then_refusal"
    )


def test_classify_path_agent_then_refusal_after_max_iters() -> None:
    """Different agent stop reason, same outcome: refused."""
    assert (
        classify_response_path(_resp(agent_stopped_reason="max_iters", is_refusal=True))
        == "agent_then_refusal"
    )


# --- Fixture-set integrity ---


def test_every_fixture_has_distinct_name() -> None:
    """Names are used as conversation_ids; duplicates would confuse
    log analysis."""
    names = [f.name for f in _FIXTURES]
    assert len(names) == len(set(names)), f"duplicate fixture names: {names}"


def test_fixtures_cover_all_six_paths() -> None:
    """Lock-in: the six documented orchestrator paths are all
    represented. A new orchestrator path (added in a future PR)
    should add a fixture; this test fails loud if not."""
    expected = {
        "clarify",
        "point_to_url",
        "refuse",
        "agent_then_answer",
        "agent_then_refusal",
    }
    actual = {f.expected_path for f in _FIXTURES}
    missing = expected - actual
    assert not missing, f"smoke fixtures don't cover paths: {missing}"


def test_run_smoke_returns_one_result_per_fixture() -> None:
    results = run_smoke()
    assert len(results) == len(_FIXTURES)


def test_run_smoke_all_fixtures_pass() -> None:
    """The headline gate: every documented fixture runs through the
    real v2 stack (with stubbed LLM/Weaviate) and takes its
    declared expected path."""
    results = run_smoke()
    failures = [r for r in results if not r.ok]
    assert not failures, "\n".join(
        f"  {r.fixture.name}: expected={r.fixture.expected_path}, got={r.actual_path}"
        for r in failures
    )


def test_run_smoke_subset() -> None:
    """Caller can pass a custom fixture list -- useful for debugging
    one path."""
    one_fixture = [f for f in _FIXTURES if f.expected_path == "clarify"][:1]
    results = run_smoke(one_fixture)
    assert len(results) == 1
    assert results[0].fixture.expected_path == "clarify"


def test_run_smoke_all_under_one_second_each() -> None:
    """The smoke is meant to be a CI gate; if any fixture takes >1s
    something is wrong (real network call leaked in?). Cap is generous."""
    results = run_smoke()
    for r in results:
        assert r.duration_ms < 1000, f"{r.fixture.name} took {r.duration_ms}ms"


def test_smoke_result_status_line_format() -> None:
    fix = _FIXTURES[0]
    deps = _build_deps(fix)
    # Don't actually run; just construct a SmokeResult and check shape.
    r = SmokeResult(
        fixture=fix,
        actual_path="clarify",
        response=_resp(agent_stopped_reason="clarify"),
        duration_ms=42,
        ok=True,
    )
    line = r.status_line
    assert "PASS" in line
    assert fix.name in line
    assert "clarify" in line
    assert "42ms" in line


def test_smoke_result_failed_status_line() -> None:
    fix = _FIXTURES[0]
    r = SmokeResult(
        fixture=fix,
        actual_path="agent_then_answer",  # mismatch
        response=_resp(),
        duration_ms=5,
        ok=False,
    )
    assert "FAIL" in r.status_line


# --- Path-specific assertions on the response ---


def test_databases_path_response_has_a_z_url() -> None:
    """Lock the wire shape: the databases short-circuit must surface
    the A-Z URL as a citation so the UI's chip renders."""
    fix = next(f for f in _FIXTURES if f.name == "databases_jstor")
    deps = _build_deps(fix)
    from src.graph.new_orchestrator import TurnRequest, run_turn  # noqa: E402
    resp = run_turn(
        TurnRequest(user_message=fix.user_message, conversation_id="x"),
        deps,
    )
    assert any("az/databases" in c["url"] for c in resp.citations)


def test_account_path_response_is_refusal_with_myaccount_link() -> None:
    fix = next(f for f in _FIXTURES if f.name == "account_balance")
    deps = _build_deps(fix)
    from src.graph.new_orchestrator import TurnRequest, run_turn  # noqa: E402
    resp = run_turn(
        TurnRequest(user_message=fix.user_message, conversation_id="x"),
        deps,
    )
    assert resp.is_refusal
    assert resp.refusal_trigger == "account_privacy"
    assert "MyAccount" in resp.answer


def test_makerspace_hamilton_path_refuses_with_service_not_at_building() -> None:
    fix = next(f for f in _FIXTURES if f.name == "makerspace_hamilton")
    deps = _build_deps(fix)
    from src.graph.new_orchestrator import TurnRequest, run_turn  # noqa: E402
    resp = run_turn(
        TurnRequest(user_message=fix.user_message, conversation_id="x"),
        deps,
    )
    assert resp.is_refusal
    # Either SERVICE_NOT_AT_BUILDING (from the post-processor short-
    # circuit) or any other refusal trigger that surfaces the service
    # context. In the current wiring it's SERVICE_NOT_AT_BUILDING.
    assert resp.refusal_trigger == "service_not_at_building"
    assert "MakerSpace" in resp.answer


def test_king_hours_path_returns_answer_with_citations() -> None:
    fix = next(f for f in _FIXTURES if f.name == "king_hours")
    deps = _build_deps(fix)
    from src.graph.new_orchestrator import TurnRequest, run_turn  # noqa: E402
    resp = run_turn(
        TurnRequest(user_message=fix.user_message, conversation_id="x"),
        deps,
    )
    assert not resp.is_refusal
    assert len(resp.citations) >= 1
    assert resp.tokens["input"] > 0  # agent + synth ran


# --- Run ---


def main() -> int:
    tests = [
        test_classify_path_clarify,
        test_classify_path_point_to_url,
        test_classify_path_refuse,
        test_classify_path_agent_then_answer,
        test_classify_path_agent_then_refusal_after_clean_run,
        test_classify_path_agent_then_refusal_after_max_iters,
        test_every_fixture_has_distinct_name,
        test_fixtures_cover_all_six_paths,
        test_run_smoke_returns_one_result_per_fixture,
        test_run_smoke_all_fixtures_pass,
        test_run_smoke_subset,
        test_run_smoke_all_under_one_second_each,
        test_smoke_result_status_line_format,
        test_smoke_result_failed_status_line,
        test_databases_path_response_has_a_z_url,
        test_account_path_response_is_refusal_with_myaccount_link,
        test_makerspace_hamilton_path_refuses_with_service_not_at_building,
        test_king_hours_path_returns_answer_with_citations,
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
