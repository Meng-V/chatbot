"""
Typed tool registry for the single agent.

The agent needs a list of tools with (a) name the LLM emits in its
tool_call, (b) JSON schema the LLM fills in, (c) a Python callable the
agent invokes. The registry is the handoff between "how the LLM
describes a tool" and "how Python runs it".

Design goals:
  - A tool author writes ONE function + schema + registration, nothing
    else. No base class, no ABCs, no inheritance.
  - The registry is injectable into the agent loop. Tests register
    only the tools they need; prod registers all of them.
  - Tool failures are typed (ToolError) rather than raw exceptions, so
    the agent loop can distinguish "the tool handler crashed" from
    "the tool ran fine and the result says no". The LLM sees a
    structured error message, not a stack trace.

See plan: Layer 3 -> "tool-calling agent" and Critical files ->
tool list (search_kb, lookup_librarian, get_hours, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --- Public types ---------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    """One tool definition.

    Attributes:
        name: Unique identifier the LLM emits. Keep it lowercase
            snake_case, verb-first (`search_kb`, `book_room`).
        description: Short human-readable description used by the LLM
            to decide WHEN to call this tool. Under 200 tokens is the
            rule -- longer descriptions bloat the system prompt.
        parameters: JSON schema describing the tool arguments. Used
            verbatim in the OpenAI tools= array on each agent call.
        handler: The Python callable. Signature: `(args: dict) -> Any`.
            Raise ToolError for expected failure modes ("no results
            found"); let other exceptions propagate so the agent loop
            records them as a crash.
        is_read_only: True for search / lookup tools. False for write
            tools (book_room, create_ticket) -- the agent loop may
            require explicit user confirmation before calling a non-
            read-only tool. See plan §"Action vs guidance distinction".
    """

    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], Any]
    is_read_only: bool = True


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation the LLM asked for."""

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolResult:
    """One tool invocation outcome. Either `data` or `error` is set."""

    call_id: str
    name: str
    data: Optional[Any] = None
    error: Optional[str] = None
    """Structured error string -- NOT a stack trace. The LLM reads this
    back to decide whether to retry, try a different tool, or give up."""

    latency_ms: int = 0

    @property
    def is_error(self) -> bool:
        return self.error is not None


class ToolError(Exception):
    """An expected tool failure, shown back to the LLM as a structured
    error message rather than a stack trace.

    Examples: "LibCal returned 503", "No librarian matches that
    subject", "URL not in allowlist". Contrast with bugs (unexpected
    exceptions) which the agent loop captures separately and treats
    as a hard turn-level failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# --- Registry -------------------------------------------------------------


@dataclass
class ToolRegistry:
    """Holds the set of tools available to the agent for one request.

    The same ToolRegistry is serialized into the system prompt (for
    the LLM) AND used to dispatch tool calls. Keeping both uses in one
    object means they cannot drift.
    """

    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        """Add a tool. Raises ValueError on duplicate names -- duplicate
        registration is always a bug (two modules registering the
        same tool), never something to silently tolerate."""
        if tool.name in self.tools:
            raise ValueError(f"Tool already registered: {tool.name!r}")
        self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)

    def as_openai_tools(self) -> list[dict]:
        """Serialize the registry as the shape OpenAI's tools= param
        expects: `[{"type": "function", "function": {...}}, ...]`.

        Kept here rather than inline in the agent loop so a future
        schema bump (e.g. OpenAI renames `function` to something
        else) is one change in one place.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self.tools.values()
        ]

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Run one tool call and return a structured result.

        Timing: wall-clock latency is recorded in the result so the
        observability layer can chart per-tool p95. ToolErrors are
        turned into error results. Other exceptions PROPAGATE -- the
        agent loop catches them at the outer level and records a
        turn-level failure (not a tool-level one).
        """
        import time

        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=f"Unknown tool: {call.name!r}",
            )

        start = time.monotonic()
        try:
            data = tool.handler(call.arguments)
            return ToolResult(
                call_id=call.id,
                name=call.name,
                data=data,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except ToolError as e:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=e.message,
                latency_ms=int((time.monotonic() - start) * 1000),
            )


__all__ = [
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
]
