"""
Unit tests for src/llm/client.py — the OpenAI Responses-API wrapper.

Run: `python -m src.llm.test_client` from ai-core/.

Strategy: monkeypatch `_get_client()` to return a stub that records
the kwargs the wrapper sent to `responses.create` and returns canned
output items. We verify both directions:
  - Inbound (request shape): instructions=registered prefix, input
    matches what the caller passed, store=False, structured-output
    schema in text.format, tools in internally-tagged shape.
  - Outbound (response parsing): output_text is returned for plain
    completions, JSON is parsed for structured_completion, function_call
    items are decoded into ToolCall(id, name, arguments=dict), usage
    is pulled off response.usage including cached_tokens.

Tests:
  1. embed: shape passes through SDK correctly.
  2. completion: instructions=prefix, input=suffix, store=False, no
     text.format, returns output_text + usage.
  3. structured_completion: text.format set with json_schema strict,
     output_text JSON parsed into dict.
  4. structured_completion: invalid JSON returns empty dict (caller's
     post-processor fires model_self_flagged refusal).
  5. completion_with_tools: tools passed through, function_call items
     parsed into ToolCall objects with decoded arguments dict.
  6. completion_with_tools: assistant_message wrapper preserves the
     raw output items list under _response_output_items.
  7. _resolve_prefix: unknown id raises PromptBuildError.
  8. Usage parsing: cached_tokens read from input_tokens_details.
  9. Usage parsing: missing usage block returns zeros (defensive).
 10. _item_attr handles both dict items and pydantic-ish objects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Allow running from ai-core/ as `python -m src.llm.test_client`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.tool_registry import ToolCall  # noqa: E402
from src.llm import client as client_module  # noqa: E402
from src.llm.client import (  # noqa: E402
    LLMUsage,
    _item_attr,
    _resolve_prefix,
    _usage_from_response,
    completion,
    completion_with_tools,
    embed,
    structured_completion,
)
from src.prompts.builder import PromptBuildError, register_prefix  # noqa: E402


# --- Stubs ---------------------------------------------------------------


class StubResponses:
    """Stub for client.responses.create."""

    def __init__(self, return_value: Any):
        self.return_value = return_value
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.return_value


class StubEmbeddings:
    def __init__(self, vec: list[float]):
        self.vec = vec
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vec)])


class StubClient:
    def __init__(self, responses_return: Any = None, embeddings_vec: list[float] = None):
        self.responses = StubResponses(responses_return)
        self.embeddings = StubEmbeddings(embeddings_vec or [])


def _install_stub(stub: StubClient) -> None:
    """Replace the cached _client with our stub."""
    client_module._client = stub


def _make_response(
    *,
    output_text: str = "",
    output_items: list = None,
    usage: dict = None,
) -> Any:
    """Build a SimpleNamespace that mimics a Responses-API response."""
    usage_ns = None
    if usage:
        details = None
        if "cached_tokens" in usage:
            details = SimpleNamespace(cached_tokens=usage["cached_tokens"])
        usage_ns = SimpleNamespace(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            input_tokens_details=details,
        )
    return SimpleNamespace(
        output_text=output_text,
        output=output_items or [],
        usage=usage_ns,
    )


def _ensure_test_prefix() -> None:
    """Register a test prefix so _resolve_prefix has something to find."""
    try:
        register_prefix("test_client_prefix_v1", "STABLE TEST PREFIX " * 50)
    except PromptBuildError:
        pass  # already registered


# --- Tests --------------------------------------------------------------


def test_embed_passes_text_and_returns_vector() -> None:
    stub = StubClient(embeddings_vec=[0.1, 0.2, 0.3])
    _install_stub(stub)
    result = embed("hello", model="text-embedding-3-large")
    assert result == [0.1, 0.2, 0.3]
    assert stub.embeddings.calls[0] == {
        "model": "text-embedding-3-large",
        "input": "hello",
    }


def test_completion_request_shape() -> None:
    _ensure_test_prefix()
    stub = StubClient(responses_return=_make_response(
        output_text="hi back",
        usage={"input_tokens": 100, "cached_tokens": 80, "output_tokens": 20},
    ))
    _install_stub(stub)
    text, usage = completion(
        prefix_id="test_client_prefix_v1",
        dynamic_suffix="hello",
        model="gpt-5.4-mini",
    )
    assert text == "hi back"
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 80
    assert usage.output_tokens == 20

    call = stub.responses.calls[0]
    # Instructions = the registered stable prefix; not empty.
    assert call["instructions"].startswith("STABLE TEST PREFIX")
    # Dynamic suffix passes through verbatim.
    assert call["input"] == "hello"
    # store=False (ZDR-friendly default).
    assert call["store"] is False
    # No text.format on plain completion.
    assert "text" not in call


def test_structured_completion_sets_text_format_and_parses_json() -> None:
    _ensure_test_prefix()
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    canned = json.dumps({"x": 42})
    stub = StubClient(responses_return=_make_response(
        output_text=canned,
        usage={"input_tokens": 200, "cached_tokens": 150, "output_tokens": 5},
    ))
    _install_stub(stub)
    parsed, usage = structured_completion(
        prefix_id="test_client_prefix_v1",
        dynamic_suffix="extract this",
        response_schema=schema,
        schema_name="my_schema",
    )
    assert parsed == {"x": 42}
    assert usage.cached_input_tokens == 150

    call = stub.responses.calls[0]
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["name"] == "my_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["text"]["format"]["schema"] == schema


def test_structured_completion_handles_invalid_json() -> None:
    """If the model somehow returns non-JSON despite strict mode, we
    return {} so the synthesizer's post_processor fires a refusal
    rather than crashing the request."""
    _ensure_test_prefix()
    stub = StubClient(responses_return=_make_response(output_text="not json {"))
    _install_stub(stub)
    parsed, _ = structured_completion(
        prefix_id="test_client_prefix_v1",
        dynamic_suffix="x",
        response_schema={},
    )
    assert parsed == {}


def test_completion_with_tools_parses_function_calls() -> None:
    _ensure_test_prefix()
    output_items = [
        {
            "type": "function_call",
            "call_id": "call_123",
            "name": "search_kb",
            "arguments": json.dumps({"query": "King hours", "scope": "oxford"}),
        },
    ]
    stub = StubClient(responses_return=_make_response(
        output_text="",  # no text portion when only function_call returned
        output_items=output_items,
        usage={"input_tokens": 500, "cached_tokens": 400, "output_tokens": 30},
    ))
    _install_stub(stub)
    tools = [{"type": "function", "name": "search_kb", "description": "...",
              "parameters": {"type": "object"}, "strict": True}]
    msg, calls, usage = completion_with_tools(
        prefix_id="test_client_prefix_v1",
        input_items=[{"role": "user", "content": "King hours?"}],
        tools=tools,
        model="gpt-5.4-mini",
    )
    assert len(calls) == 1
    assert calls[0].id == "call_123"
    assert calls[0].name == "search_kb"
    # Arguments decoded from JSON string into dict.
    assert calls[0].arguments == {"query": "King hours", "scope": "oxford"}
    # Token usage parsed.
    assert usage.input_tokens == 500
    assert usage.cached_input_tokens == 400
    # Assistant message wrapper preserves raw output items for
    # round-tripping into the next agent-loop input.
    assert msg["_response_output_items"] == output_items


def test_completion_with_tools_no_tool_calls_terminal() -> None:
    _ensure_test_prefix()
    stub = StubClient(responses_return=_make_response(
        output_text="Final answer: 7am to 2am.",
        output_items=[],
        usage={"input_tokens": 300, "output_tokens": 15},
    ))
    _install_stub(stub)
    msg, calls, usage = completion_with_tools(
        prefix_id="test_client_prefix_v1",
        input_items=[{"role": "user", "content": "King hours?"}],
        tools=[],
        model="gpt-5.4-mini",
    )
    assert calls == []
    assert msg["content"] == "Final answer: 7am to 2am."
    assert usage.output_tokens == 15


def test_resolve_prefix_unknown_id_raises() -> None:
    try:
        _resolve_prefix("nonexistent_prefix_v999")
    except PromptBuildError as e:
        assert "nonexistent_prefix_v999" in str(e)
        return
    raise AssertionError("expected PromptBuildError for unknown prefix")


def test_usage_parsing_with_cached_tokens() -> None:
    response = _make_response(
        usage={"input_tokens": 1000, "cached_tokens": 800, "output_tokens": 50},
    )
    usage = _usage_from_response(response)
    assert usage.input_tokens == 1000
    assert usage.cached_input_tokens == 800
    assert usage.output_tokens == 50
    assert usage.cache_hit_rate == 0.8


def test_usage_parsing_no_usage_block_returns_zeros() -> None:
    """Defensive: a response missing the usage block (rare but possible
    on streaming or error edge cases) shouldn't crash the wrapper."""
    response = SimpleNamespace(output_text="", output=[])
    usage = _usage_from_response(response)
    assert usage.input_tokens == 0
    assert usage.cached_input_tokens == 0
    assert usage.output_tokens == 0


def test_usage_parsing_no_input_tokens_details() -> None:
    """Some models / SDK versions don't expose input_tokens_details.
    Cached count defaults to 0 (worst-case overcount of billable
    tokens, which is the safe direction)."""
    response = SimpleNamespace(
        output_text="",
        output=[],
        usage=SimpleNamespace(input_tokens=100, output_tokens=10, input_tokens_details=None),
    )
    usage = _usage_from_response(response)
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 0
    assert usage.output_tokens == 10


def test_item_attr_handles_dict_and_object() -> None:
    """Output items can be either dicts (test stubs) or pydantic-ish
    objects (real SDK). _item_attr abstracts the difference."""
    assert _item_attr({"name": "x"}, "name") == "x"
    assert _item_attr({"name": "x"}, "missing") is None
    obj = SimpleNamespace(name="y")
    assert _item_attr(obj, "name") == "y"
    assert _item_attr(obj, "missing") is None


def main() -> int:
    tests = [
        test_embed_passes_text_and_returns_vector,
        test_completion_request_shape,
        test_structured_completion_sets_text_format_and_parses_json,
        test_structured_completion_handles_invalid_json,
        test_completion_with_tools_parses_function_calls,
        test_completion_with_tools_no_tool_calls_terminal,
        test_resolve_prefix_unknown_id_raises,
        test_usage_parsing_with_cached_tokens,
        test_usage_parsing_no_usage_block_returns_zeros,
        test_usage_parsing_no_input_tokens_details,
        test_item_attr_handles_dict_and_object,
    ]
    failed = 0
    for t in tests:
        try:
            # Reset client between tests so stubs don't bleed.
            client_module._client = None
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
