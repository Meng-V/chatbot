"""
The single tool-calling agent loop.

Replaces the 6 specialized sub-agents with one LLM-driven loop. The
loop is small on purpose: the LLM picks the tool, the registry runs
it, the result is fed back, repeat until the LLM emits a terminal
response.

Loop shape:

    iter 0: prompt = [system_prefix, user_message]
    repeat (max N iterations):
        llm_response = call_llm(prompt, tools=registry)
        if llm_response.has_tool_calls:
            for each tool_call:
                result = registry.dispatch(tool_call)
                prompt.append(tool_result_message(result))
            continue
        else:
            return AgentOutcome(terminal=llm_response)

Guard-rails:
  - Hard cap on iterations (default 6) to bound cost per turn. In
    practice a well-scoped library question should finish in 1-3.
  - If the LLM repeats the same tool call with the same arguments
    twice in a row, the loop returns -- the model is stuck and
    further turns won't unstick it.
  - If more than `max_tool_failures` tool dispatches return errors,
    the loop returns early with a degraded outcome. Prevents runaway
    spend when a dependency (LibCal) is down.

The loop does NOT itself call the synthesizer. The synthesizer is a
separate step in the orchestrator; the agent's job is to produce the
evidence bundle + any tool outputs the synthesizer needs. Separation
means the synthesizer's strict grounding contract isn't mixed up with
the agent's more freewheeling tool-selection logic.

Status: SCAFFOLD. The LLM call is gated behind the freshness rule (see
src/llm/client.py, once it exists). This module exposes the control
flow and state so tests can drive it with a stub LLM that emits canned
tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from src.agent.tool_registry import ToolCall, ToolRegistry, ToolResult


# --- Public types ---------------------------------------------------------


@dataclass(frozen=True)
class AgentRequest:
    """One agent invocation's input. All state is explicit."""

    user_message: str
    intent: str
    """Label from the kNN classifier. Used for telemetry and -- in
    future -- for a per-intent system-prompt variant if needed."""

    scope_campus: str
    scope_library: Optional[str]
    """Resolved scope. Threaded through so tools like search_kb can
    filter retrieval by campus/library."""

    conversation_history: list[dict] = field(default_factory=list)
    """Prior turns in the conversation, OpenAI message format. Kept as
    dicts because this is exactly how the LLM client consumes them."""


@dataclass(frozen=True)
class AgentTurn:
    """One iteration of the agent loop -- what the LLM said, what
    tools it called, and what those tools returned. Logged per turn
    for the audit trail.
    """

    iteration: int
    llm_message: dict
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass(frozen=True)
class AgentOutcome:
    """Final result of the agent loop.

    `terminal_message` is the last LLM message when the loop ended
    cleanly (no more tool calls requested). `turns` is every step
    recorded, including tool dispatches, so the synthesizer and the
    logger can see the full trajectory.
    """

    terminal_message: Optional[dict]
    turns: list[AgentTurn]
    stopped_reason: str
    """One of: `clean` (LLM stopped requesting tools), `max_iters`
    (hit iteration cap), `loop_detected` (same tool call twice),
    `tool_failures` (too many tool errors)."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


# --- LLM seam -------------------------------------------------------------


class AgentLLM(Protocol):
    """Minimal interface the agent loop needs from an LLM client.

    Returns the next assistant message + any tool calls the model
    requested. `(msg, usage)` shape mirrors the synthesizer's LLM
    protocol so src/llm/client.py can implement both with one method.
    """

    def __call__(
        self,
        *,
        prefix_id: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
    ) -> tuple[dict, list[ToolCall], dict]:
        """Returns `(assistant_message, tool_calls, usage_dict)`."""
        ...


def _default_llm_call(
    *,
    prefix_id: str,
    messages: list[dict],
    tools: list[dict],
    model: str,
) -> tuple[dict, list[ToolCall], dict]:
    """Real LLM call via the Responses API (src/llm/client.py).

    The `messages` argument is the agent loop's running list of input
    items (user message, prior assistant messages, tool outputs).
    Per the Responses API contract, this list IS the `input=` payload
    -- it accepts message-shaped dicts plus `function_call_output`
    items keyed by `call_id`.

    `tools` must already be in the Responses-API internally-tagged
    shape (see ToolRegistry.as_responses_tools()).
    """
    # Lazy import: src.llm.client imports openai which requires a key;
    # tests pass their own `llm=` and never trigger this path.
    from src.llm.client import completion_with_tools

    assistant_message, tool_calls, usage = completion_with_tools(
        prefix_id=prefix_id,
        input_items=messages,
        tools=tools,
        model=model,
    )
    return assistant_message, tool_calls, usage.as_dict()


# --- Loop -----------------------------------------------------------------


def run_agent(
    request: AgentRequest,
    registry: ToolRegistry,
    *,
    llm: Optional[AgentLLM] = None,
    prefix_id: str = "agent_v1",
    model: str = "gpt-5.4-mini",
    max_iterations: int = 6,
    max_tool_failures: int = 3,
) -> AgentOutcome:
    """Run the tool-calling loop to completion or bounded failure.

    Returns an AgentOutcome with the full turn-by-turn trace. The
    caller is responsible for feeding evidence from tool results into
    the synthesizer.
    """
    call = llm if llm is not None else _default_llm_call

    # Build the initial messages array. The stable prefix lives at
    # `prefix_id`; the dynamic suffix is conversation history + the
    # current user message.
    scope_line = f"Scope: campus={request.scope_campus}"
    if request.scope_library:
        scope_line += f", library={request.scope_library}"
    scope_line += f" | intent={request.intent}"

    messages: list[dict] = list(request.conversation_history)
    messages.append(
        {
            "role": "user",
            "content": f"{scope_line}\n\n{request.user_message}",
        }
    )

    turns: list[AgentTurn] = []
    last_tool_call_key: Optional[tuple[str, str]] = None
    tool_failure_count = 0
    total_in = 0
    total_cached = 0
    total_out = 0
    # Responses API uses internally-tagged tool shape (no `function`
    # wrapper). `as_responses_tools()` also flips strict=true per the
    # Responses migration guide.
    tools_schema = registry.as_responses_tools()

    for i in range(max_iterations):
        llm_message, tool_calls, usage = call(
            prefix_id=prefix_id,
            messages=messages,
            tools=tools_schema,
            model=model,
        )
        total_in += int(usage.get("input_tokens", 0))
        total_cached += int(usage.get("cached_input_tokens", 0))
        total_out += int(usage.get("output_tokens", 0))

        # No tool calls => LLM is done. Return the terminal message.
        if not tool_calls:
            turns.append(
                AgentTurn(
                    iteration=i,
                    llm_message=llm_message,
                    tool_calls=[],
                    tool_results=[],
                )
            )
            return AgentOutcome(
                terminal_message=llm_message,
                turns=turns,
                stopped_reason="clean",
                input_tokens=total_in,
                cached_input_tokens=total_cached,
                output_tokens=total_out,
            )

        # Loop-detection: same tool name + args as the previous turn?
        # Model is stuck -- break out rather than keep paying.
        current_key = (
            tool_calls[0].name,
            _canonical_args(tool_calls[0].arguments),
        )
        if current_key == last_tool_call_key:
            turns.append(
                AgentTurn(
                    iteration=i,
                    llm_message=llm_message,
                    tool_calls=tool_calls,
                    tool_results=[],
                )
            )
            return AgentOutcome(
                terminal_message=llm_message,
                turns=turns,
                stopped_reason="loop_detected",
                input_tokens=total_in,
                cached_input_tokens=total_cached,
                output_tokens=total_out,
            )
        last_tool_call_key = current_key

        # Dispatch each tool call.
        results: list[ToolResult] = []
        for tc in tool_calls:
            result = registry.dispatch(tc)
            results.append(result)
            if result.is_error:
                tool_failure_count += 1

        turns.append(
            AgentTurn(
                iteration=i,
                llm_message=llm_message,
                tool_calls=tool_calls,
                tool_results=results,
            )
        )

        # Too many tool failures in one turn? Bail -- repeated retries
        # against a broken dependency burn budget and don't help.
        if tool_failure_count >= max_tool_failures:
            return AgentOutcome(
                terminal_message=None,
                turns=turns,
                stopped_reason="tool_failures",
                input_tokens=total_in,
                cached_input_tokens=total_cached,
                output_tokens=total_out,
            )

        # Feed results back into the input items for the next iteration.
        # Per the Responses API contract, append the FULL list of
        # output items the model returned (not just an "assistant
        # message" wrapper) so function_call items round-trip
        # correlated with their function_call_output siblings by
        # call_id. The wrapper dict our llm helper returns carries
        # the original output items in `_response_output_items`.
        prior_outputs = llm_message.get("_response_output_items")
        if isinstance(prior_outputs, list):
            messages.extend(prior_outputs)
        else:
            # Test stubs / non-Responses-shaped LLMs may return only
            # the consolidated message dict. Append it as-is so the
            # loop still progresses; tests that use stubs won't have
            # a real Responses replay either.
            messages.append(llm_message)
        for result in results:
            messages.append(_tool_result_message(result))

    # Hit iteration cap.
    return AgentOutcome(
        terminal_message=None,
        turns=turns,
        stopped_reason="max_iters",
        input_tokens=total_in,
        cached_input_tokens=total_cached,
        output_tokens=total_out,
    )


# --- Helpers --------------------------------------------------------------


def _canonical_args(args: dict) -> str:
    """Stable string for tool-arg comparison. JSON with sorted keys so
    dict ordering doesn't make two identical calls look different.
    """
    import json

    try:
        return json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(sorted(args.items()))


def _tool_result_message(result: ToolResult) -> dict:
    """Shape a ToolResult as a Responses-API `function_call_output`
    input item so the LLM sees it on the next turn.

    Per the Responses migration guide: "tool calls and their outputs
    are two distinct types of Items that are correlated using a
    `call_id`." The shape is:
        {"type": "function_call_output", "call_id": "...", "output": "..."}

    `output` is a string per the API contract (the LLM treats it as
    the tool's textual output). We JSON-stringify dict/list outputs;
    errors get a structured `{"error": "..."}` JSON string. Non-JSON-
    safe data falls back to repr to keep the loop running instead of
    crashing the request.
    """
    import json

    content: Any
    if result.is_error:
        content = {"error": result.error}
    else:
        try:
            content = result.data
            json.dumps(content, default=str)
        except (TypeError, ValueError):
            content = {"repr": repr(result.data)}

    return {
        "type": "function_call_output",
        "call_id": result.call_id,
        "output": json.dumps(content, default=str),
    }


__all__ = [
    "AgentLLM",
    "AgentOutcome",
    "AgentRequest",
    "AgentTurn",
    "run_agent",
]
