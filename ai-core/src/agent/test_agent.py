"""
Unit tests for the agent loop.

Run: `python -m src.agent.test_agent` from ai-core/.

The agent loop's job is to drive a deterministic, bounded interaction
between the LLM and the tool registry. Every guard rail (max_iters,
loop detection, tool-failure cap) is load-bearing -- without them, a
buggy LLM response can run up unbounded cost or burn through API
quota. Tests cover each rail independently.

Strategy: a stub LLM that returns canned (message, tool_calls, usage)
tuples per iteration so the loop's behavior is fully deterministic.

Tests:
  1. Clean stop: LLM emits no tool calls -> AgentOutcome(stopped_reason="clean").
  2. One tool round-trip then clean stop.
  3. Hits max_iterations -> stopped_reason="max_iters", terminal=None.
  4. Same tool+args twice -> stopped_reason="loop_detected".
  5. tool_failures >= max_tool_failures -> stopped_reason="tool_failures".
  6. Token usage accumulates across turns.
  7. Scope line composed correctly when scope_library set.
  8. Scope line composed correctly when scope_library is None.
  9. Conversation history is preserved + extended (not replaced).
 10. _canonical_args produces stable string for dict reorderings.
 11. _tool_result_message shape: role=tool, tool_call_id, name, content.
 12. _tool_result_message handles non-JSON-serializable data via repr.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Allow running from ai-core/ as `python -m src.agent.test_agent`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.agent import (  # noqa: E402
    AgentRequest,
    _canonical_args,
    _tool_result_message,
    run_agent,
)
from src.agent.tool_registry import (  # noqa: E402
    Tool,
    ToolCall,
    ToolError,
    ToolRegistry,
    ToolResult,
)


# --- Fixtures --------------------------------------------------------------


def _registry_with(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _echo_tool() -> Tool:
    return Tool(
        name="echo", description="Echo a string.",
        parameters={"type": "object"},
        handler=lambda args: {"echoed": args.get("msg", "")},
    )


def _failing_tool() -> Tool:
    return Tool(
        name="fail", description="Always fails.",
        parameters={"type": "object"},
        handler=lambda _: (_ for _ in ()).throw(ToolError("simulated failure")),
    )


class StubLLM:
    """LLM stub that returns canned (message, tool_calls, usage) per call.

    Construct with a list of return tuples; the i-th call returns
    responses[i]. Cycles back to the last response if exhausted (the
    test's max_iterations cap will kick in first).
    """

    def __init__(self, responses: list[tuple[dict, list[ToolCall], dict]]):
        self.responses = responses
        self.calls: list[dict] = []  # capture every call for inspection

    def __call__(self, *, prefix_id, messages, tools, model):
        self.calls.append({
            "prefix_id": prefix_id, "messages": list(messages),
            "tools": tools, "model": model,
        })
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]


def _request(scope_library: str | None = None) -> AgentRequest:
    return AgentRequest(
        user_message="hello", intent="hours",
        scope_campus="oxford", scope_library=scope_library,
    )


# --- Tests -----------------------------------------------------------------


def test_clean_stop_when_no_tool_calls() -> None:
    llm = StubLLM([
        ({"role": "assistant", "content": "Done"}, [], {"input_tokens": 10, "output_tokens": 5}),
    ])
    out = run_agent(_request(), _registry_with(), llm=llm)
    assert out.stopped_reason == "clean"
    assert out.terminal_message == {"role": "assistant", "content": "Done"}
    assert out.input_tokens == 10
    assert out.output_tokens == 5
    assert len(out.turns) == 1


def test_one_tool_round_trip_then_clean() -> None:
    llm = StubLLM([
        # iter 0: request a tool call
        (
            {"role": "assistant", "content": None, "tool_calls": [...]},
            [ToolCall(id="tc1", name="echo", arguments={"msg": "hi"})],
            {"input_tokens": 100, "output_tokens": 20},
        ),
        # iter 1: terminal
        (
            {"role": "assistant", "content": "Echoed."},
            [],
            {"input_tokens": 110, "output_tokens": 5},
        ),
    ])
    out = run_agent(_request(), _registry_with(_echo_tool()), llm=llm)
    assert out.stopped_reason == "clean"
    assert len(out.turns) == 2
    assert out.turns[0].tool_calls[0].name == "echo"
    assert out.turns[0].tool_results[0].data == {"echoed": "hi"}
    # Token usage accumulates.
    assert out.input_tokens == 210


def test_hits_max_iterations() -> None:
    """LLM keeps requesting tools forever -> loop bails at max_iters."""
    # Different tool args each call so loop_detected doesn't fire first.
    responses = [
        (
            {"role": "assistant", "content": None},
            [ToolCall(id=f"tc{i}", name="echo", arguments={"msg": f"call-{i}"})],
            {"input_tokens": 50, "output_tokens": 10},
        )
        for i in range(10)
    ]
    llm = StubLLM(responses)
    out = run_agent(_request(), _registry_with(_echo_tool()), llm=llm, max_iterations=3)
    assert out.stopped_reason == "max_iters"
    assert out.terminal_message is None
    assert len(out.turns) == 3


def test_loop_detected_on_repeated_tool_call() -> None:
    """Same tool name AND same args twice in a row -> loop_detected."""
    same = ToolCall(id="tc-x", name="echo", arguments={"msg": "stuck"})
    llm = StubLLM([
        ({"role": "assistant", "content": None}, [same], {"input_tokens": 50, "output_tokens": 10}),
        ({"role": "assistant", "content": None}, [same], {"input_tokens": 60, "output_tokens": 10}),
    ])
    out = run_agent(_request(), _registry_with(_echo_tool()), llm=llm)
    assert out.stopped_reason == "loop_detected"
    # Both turns logged.
    assert len(out.turns) == 2


def test_tool_failure_cap_breaks_loop() -> None:
    """Repeated tool failures bail before max_iters -- no point asking
    LibCal for hours 6 times when it's down."""
    responses = [
        (
            {"role": "assistant", "content": None},
            [ToolCall(id=f"tc{i}", name="fail", arguments={"i": i})],
            {"input_tokens": 50, "output_tokens": 10},
        )
        for i in range(10)
    ]
    llm = StubLLM(responses)
    out = run_agent(
        _request(), _registry_with(_failing_tool()),
        llm=llm, max_iterations=10, max_tool_failures=2,
    )
    assert out.stopped_reason == "tool_failures"
    # Loop bailed after 2nd failure (before doing 3rd iteration).
    assert len(out.turns) == 2


def test_token_usage_accumulates_across_turns() -> None:
    llm = StubLLM([
        (
            {"role": "assistant", "content": None},
            [ToolCall(id="tc1", name="echo", arguments={"msg": "a"})],
            {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10},
        ),
        (
            {"role": "assistant", "content": "done"},
            [],
            {"input_tokens": 200, "cached_input_tokens": 180, "output_tokens": 20},
        ),
    ])
    out = run_agent(_request(), _registry_with(_echo_tool()), llm=llm)
    assert out.input_tokens == 300
    assert out.cached_input_tokens == 260
    assert out.output_tokens == 30


def test_scope_line_includes_library_when_set() -> None:
    llm = StubLLM([({"role": "assistant", "content": "x"}, [], {})])
    run_agent(_request(scope_library="king"), _registry_with(), llm=llm)
    user_msg_content = llm.calls[0]["messages"][-1]["content"]
    assert "campus=oxford" in user_msg_content
    assert "library=king" in user_msg_content
    assert "intent=hours" in user_msg_content


def test_scope_line_omits_library_when_none() -> None:
    llm = StubLLM([({"role": "assistant", "content": "x"}, [], {})])
    run_agent(_request(scope_library=None), _registry_with(), llm=llm)
    user_msg = llm.calls[0]["messages"][-1]["content"]
    assert "campus=oxford" in user_msg
    assert "library=" not in user_msg


def test_conversation_history_preserved_and_extended() -> None:
    llm = StubLLM([
        (
            {"role": "assistant", "content": None},
            [ToolCall(id="tc1", name="echo", arguments={"msg": "a"})],
            {"input_tokens": 50, "output_tokens": 10},
        ),
        (
            {"role": "assistant", "content": "ok"}, [], {"input_tokens": 60, "output_tokens": 5},
        ),
    ])
    history = [
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous answer"},
    ]
    request = AgentRequest(
        user_message="follow-up", intent="hours",
        scope_campus="oxford", scope_library=None,
        conversation_history=history,
    )
    run_agent(request, _registry_with(_echo_tool()), llm=llm)
    # First call: history + the new user message at end.
    first_msgs = llm.calls[0]["messages"]
    assert first_msgs[0:2] == history
    assert first_msgs[-1]["role"] == "user"
    assert "follow-up" in first_msgs[-1]["content"]
    # Second call: includes the assistant + tool result messages.
    second_msgs = llm.calls[1]["messages"]
    assert len(second_msgs) > len(first_msgs)
    # Tool result message present (Responses-API function_call_output shape).
    assert any(m.get("type") == "function_call_output" for m in second_msgs)


# --- _canonical_args ---


def test_canonical_args_stable_across_dict_orderings() -> None:
    a = _canonical_args({"x": 1, "y": 2})
    b = _canonical_args({"y": 2, "x": 1})
    assert a == b


def test_canonical_args_handles_non_json_safe_values() -> None:
    """Set / object values fall back to repr; must not crash."""
    s = _canonical_args({"items": {1, 2, 3}})  # set isn't JSON-serializable
    assert isinstance(s, str)
    assert s  # non-empty


# --- _tool_result_message ---


def test_tool_result_message_success_shape() -> None:
    """Per Responses API: tool outputs are `function_call_output` items
    correlated with their function_call sibling by `call_id`."""
    r = ToolResult(call_id="tc1", name="echo", data={"echoed": "hi"})
    msg = _tool_result_message(r)
    assert msg["type"] == "function_call_output"
    assert msg["call_id"] == "tc1"
    # Output is JSON-stringified for the LLM.
    assert isinstance(msg["output"], str)
    assert "echoed" in msg["output"]


def test_tool_result_message_error_shape() -> None:
    r = ToolResult(call_id="tc1", name="echo", error="LibCal 503")
    msg = _tool_result_message(r)
    assert msg["type"] == "function_call_output"
    assert msg["call_id"] == "tc1"
    assert "error" in msg["output"]
    assert "LibCal 503" in msg["output"]


def test_tool_result_message_handles_non_json_safe_data() -> None:
    """If a tool returns a non-JSON-safe object (e.g. a dataclass
    instance), the wrapper must produce SOMETHING serializable rather
    than crash the loop. Defensive default=str path."""
    class Weird:
        def __repr__(self): return "<Weird>"

    r = ToolResult(call_id="tc1", name="x", data=Weird())
    msg = _tool_result_message(r)
    assert msg["type"] == "function_call_output"
    assert isinstance(msg["output"], str)


def main() -> int:
    tests = [
        test_clean_stop_when_no_tool_calls,
        test_one_tool_round_trip_then_clean,
        test_hits_max_iterations,
        test_loop_detected_on_repeated_tool_call,
        test_tool_failure_cap_breaks_loop,
        test_token_usage_accumulates_across_turns,
        test_scope_line_includes_library_when_set,
        test_scope_line_omits_library_when_none,
        test_conversation_history_preserved_and_extended,
        test_canonical_args_stable_across_dict_orderings,
        test_canonical_args_handles_non_json_safe_values,
        test_tool_result_message_success_shape,
        test_tool_result_message_error_shape,
        test_tool_result_message_handles_non_json_safe_data,
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
