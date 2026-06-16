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


# --- Strict-mode schema normalization -------------------------------------
#
# OpenAI's Responses API runs function tools with strict=True (set in
# as_responses_tools()). Strict mode constrains decoding to the JSON
# schema and imposes three rules the OpenAI docs spell out (verified
# against the function-calling guide + developer-community guidance,
# 2026-05 -- see the plan's model/API freshness rule):
#
#   1. EVERY key in `properties` must appear in `required`. (This is
#      the exact 400 the agent hit: "'required' ... must be an array
#      including every key in properties. Missing 'k'.")
#   2. A logically-optional parameter stays in `required`, but its
#      type becomes a union with "null" -- the model emits null to
#      mean "not supplied".
#   3. Every object must set `additionalProperties: false`.
#
# `default` is NOT honored under strict decoding, so a tool HANDLER
# must treat a null/absent value as the default itself.
#
# Tool authors write natural JSON Schema (optional params simply
# omitted from `required`). This transformer applies rules 1-3 at the
# serialization boundary so no tool author has to remember them and
# every tool is consistent. It is PURE -- returns new structures and
# never mutates the registry's stored Tool.parameters -- and
# DETERMINISTIC (`required` emitted in properties insertion order), so
# the serialized tool block stays byte-identical call-to-call, a hard
# requirement for OpenAI prompt caching.


def _make_nullable(prop_schema: dict) -> dict:
    """Copy `prop_schema` so its value space includes null. Lets a
    property be `required` (per strict mode) yet still 'optional' by
    the model emitting null."""
    out = dict(prop_schema)
    t = out.get("type")
    if isinstance(t, str):
        out["type"] = [t, "null"] if t != "null" else t
        return out
    if isinstance(t, list):
        out["type"] = list(t) + ([] if "null" in t else ["null"])
        return out
    if isinstance(out.get("anyOf"), list):
        has_null = any(
            isinstance(s, dict) and s.get("type") == "null"
            for s in out["anyOf"]
        )
        out["anyOf"] = list(out["anyOf"]) + (
            [] if has_null else [{"type": "null"}]
        )
        return out
    # No `type`/`anyOf` (enum-only, $ref, ...): wrap in anyOf-null.
    return {"anyOf": [out, {"type": "null"}]}


def _strictify_schema(schema: Any) -> Any:
    """Recursively rewrite a JSON Schema to satisfy OpenAI strict mode.

    Pure + deterministic (see the section comment above).
    """
    if not isinstance(schema, dict):
        return schema

    out = dict(schema)

    if "items" in out:  # array element schema
        out["items"] = _strictify_schema(out["items"])

    props = out.get("properties")
    if isinstance(props, dict):
        original_required = set(out.get("required") or [])
        new_props: dict = {}
        for key, sub in props.items():
            sub_strict = _strictify_schema(sub)
            if key not in original_required:
                sub_strict = _make_nullable(sub_strict)
            new_props[key] = sub_strict
        out["properties"] = new_props
        out["required"] = list(props.keys())  # insertion order = stable
        out["additionalProperties"] = False

    return out


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
        """Serialize the registry in the legacy Chat-Completions tools shape:
        `[{"type": "function", "function": {name, description, parameters}}, ...]`.

        Kept for the legacy code path. New code should use
        `as_responses_tools()` -- the Responses API uses an
        internally-tagged shape with no `function` wrapper.
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

    def as_responses_tools(self) -> list[dict]:
        """Serialize the registry in the Responses-API internally-tagged
        shape: `[{"type": "function", "name", "description", "parameters",
        "strict": True}, ...]`.

        Two differences from `as_openai_tools()`:
          - No nested `function` wrapper -- name/description/parameters
            sit at the top level of each tool item.
          - `strict: True` by default. Per the Responses migration
            guide: "In the Responses API, functions ARE strict by
            default" (vs Chat Completions where they're non-strict by
            default). Strict mode forces argument JSON to exactly
            match the schema -- the same enforcement as Structured
            Outputs and the only sane default for tools we'll
            actually dispatch.
        """
        return [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": _strictify_schema(t.parameters),
                "strict": True,
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

        def _meter(status: str, latency_s: float) -> None:
            # Per-tool Prometheus counters/histograms (no-op if
            # prometheus_client isn't installed). This is the single
            # dispatch chokepoint, so every tool call -- search_kb,
            # get_hours, book_room, lookup_librarian, ... -- is counted
            # and timed here rather than at each call site.
            try:
                from src.observability.metrics import record_tool_call
                record_tool_call(tool=call.name, status=status, latency_s=latency_s)
            except Exception:  # pragma: no cover -- metrics must never break a turn
                pass

        tool = self.tools.get(call.name)
        if tool is None:
            _meter("error", 0.0)
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=f"Unknown tool: {call.name!r}",
            )

        start = time.monotonic()
        try:
            data = tool.handler(call.arguments)
            _meter("ok", time.monotonic() - start)
            return ToolResult(
                call_id=call.id,
                name=call.name,
                data=data,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except ToolError as e:
            _meter("error", time.monotonic() - start)
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=e.message,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception:
            # Unexpected crash propagates to the agent loop's turn-level
            # handler, but record it as a tool error first so the metric
            # reflects reality.
            _meter("error", time.monotonic() - start)
            raise


__all__ = [
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
]
