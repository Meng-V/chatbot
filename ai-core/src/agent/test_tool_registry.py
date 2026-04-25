"""
Unit tests for the tool registry + dispatcher.

Run: `python -m src.agent.test_tool_registry` from ai-core/.

ToolRegistry sits between the LLM and every external system the bot
touches. A bug in dispatch silently swallows errors or surfaces stack
traces to the model -- the latter regularly causes the model to
hallucinate "I'll try a different approach" responses that turn into
junk answers.

Tests:
  1. register accepts a tool; get returns it; duplicate name raises.
  2. as_openai_tools returns the [{type, function:{name,description,parameters}}] shape.
  3. dispatch with unknown name returns error result (not raise).
  4. dispatch with successful handler returns data + non-zero latency.
  5. ToolError -> structured error result, latency recorded, no stack trace leak.
  6. Other exceptions PROPAGATE (agent loop captures at outer level).
  7. is_read_only defaults to True; can be overridden False.
  8. Tool dataclass fields all set correctly.
  9. Empty registry's as_openai_tools returns [].
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.agent.test_tool_registry`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.tool_registry import (  # noqa: E402
    Tool,
    ToolCall,
    ToolError,
    ToolRegistry,
    ToolResult,
)


def _basic_tool(name: str = "echo") -> Tool:
    return Tool(
        name=name,
        description=f"Echo {name}.",
        parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
        handler=lambda args: {"echoed": args.get("msg", "")},
    )


# --- register / get / duplicate ---


def test_register_and_get() -> None:
    reg = ToolRegistry()
    t = _basic_tool()
    reg.register(t)
    assert reg.get("echo") is t
    assert reg.get("nonexistent") is None


def test_register_duplicate_raises() -> None:
    reg = ToolRegistry()
    reg.register(_basic_tool("echo"))
    try:
        reg.register(_basic_tool("echo"))
    except ValueError as e:
        assert "already registered" in str(e)
        return
    raise AssertionError("expected ValueError on duplicate")


# --- as_openai_tools ---


def test_as_openai_tools_shape() -> None:
    reg = ToolRegistry()
    reg.register(_basic_tool("a"))
    reg.register(_basic_tool("b"))
    schema = reg.as_openai_tools()
    assert len(schema) == 2
    for entry in schema:
        assert entry["type"] == "function"
        assert "name" in entry["function"]
        assert "description" in entry["function"]
        assert "parameters" in entry["function"]


def test_as_openai_tools_empty_registry() -> None:
    assert ToolRegistry().as_openai_tools() == []


def test_as_responses_tools_shape() -> None:
    """Responses-API tools are internally-tagged: name/description/
    parameters at the top level, no `function` wrapper, strict=True
    by default per the migration guide."""
    reg = ToolRegistry()
    reg.register(_basic_tool("a"))
    reg.register(_basic_tool("b"))
    schema = reg.as_responses_tools()
    assert len(schema) == 2
    for entry in schema:
        assert entry["type"] == "function"
        # No nested wrapper.
        assert "function" not in entry
        # Top-level keys (the Responses-API contract).
        assert entry["name"] in {"a", "b"}
        assert "description" in entry
        assert "parameters" in entry
        # Strict by default per the Responses migration guide.
        assert entry["strict"] is True


def test_as_responses_tools_empty_registry() -> None:
    assert ToolRegistry().as_responses_tools() == []


# --- dispatch: success / errors ---


def test_dispatch_unknown_tool_returns_error_result() -> None:
    reg = ToolRegistry()
    result = reg.dispatch(ToolCall(id="t1", name="missing", arguments={}))
    assert result.is_error
    assert "Unknown tool" in result.error
    assert result.call_id == "t1"


def test_dispatch_success_returns_data_and_latency() -> None:
    reg = ToolRegistry()
    reg.register(_basic_tool())
    result = reg.dispatch(ToolCall(id="t1", name="echo", arguments={"msg": "hi"}))
    assert not result.is_error
    assert result.data == {"echoed": "hi"}
    assert result.latency_ms >= 0  # may be 0 for very fast handlers


def test_dispatch_tool_error_returns_structured_error() -> None:
    """ToolError -> error result with the message, NO stack trace
    leaked. The LLM reads this back; a stack trace would derail it."""
    reg = ToolRegistry()
    reg.register(Tool(
        name="boom",
        description="Always fails.",
        parameters={"type": "object"},
        handler=lambda _: (_ for _ in ()).throw(ToolError("LibCal returned 503")),
    ))
    result = reg.dispatch(ToolCall(id="t1", name="boom", arguments={}))
    assert result.is_error
    assert result.error == "LibCal returned 503"
    assert "Traceback" not in result.error
    # Latency still recorded so we can chart slow-failure tools.
    assert result.latency_ms >= 0


def test_dispatch_unexpected_exception_propagates() -> None:
    """Non-ToolError exceptions PROPAGATE so the agent loop's outer
    try/except captures them as turn-level failures (vs tool-level).
    Distinction matters for telemetry: a KeyError in a tool handler is
    a code bug, not a 'LibCal is down'."""
    def crashing(_):
        raise ValueError("wrong arg shape")

    reg = ToolRegistry()
    reg.register(Tool(
        name="crash", description="Crashes.",
        parameters={"type": "object"}, handler=crashing,
    ))
    try:
        reg.dispatch(ToolCall(id="t1", name="crash", arguments={}))
    except ValueError as e:
        assert "wrong arg shape" in str(e)
        return
    raise AssertionError("expected ValueError to propagate")


# --- Tool dataclass fields ---


def test_tool_is_read_only_defaults_true() -> None:
    t = _basic_tool()
    assert t.is_read_only is True


def test_tool_is_read_only_overridable() -> None:
    t = Tool(
        name="book", description="Action tool.",
        parameters={"type": "object"},
        handler=lambda _: {},
        is_read_only=False,
    )
    assert t.is_read_only is False


def test_tool_result_is_error_property() -> None:
    ok = ToolResult(call_id="t1", name="x", data={"a": 1})
    err = ToolResult(call_id="t1", name="x", error="boom")
    assert not ok.is_error
    assert err.is_error


def main() -> int:
    tests = [
        test_register_and_get,
        test_register_duplicate_raises,
        test_as_openai_tools_shape,
        test_as_openai_tools_empty_registry,
        test_as_responses_tools_shape,
        test_as_responses_tools_empty_registry,
        test_dispatch_unknown_tool_returns_error_result,
        test_dispatch_success_returns_data_and_latency,
        test_dispatch_tool_error_returns_structured_error,
        test_dispatch_unexpected_exception_propagates,
        test_tool_is_read_only_defaults_true,
        test_tool_is_read_only_overridable,
        test_tool_result_is_error_property,
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
