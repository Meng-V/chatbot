"""
The OpenAI client wrapper. ALL OpenAI calls in the bot go through here.

Why centralize:
  1. The plan's model-freshness rule has ONE module to enforce instead
     of being scattered across the codebase. Every call site imports
     from here; this module imports from `openai` and is the single
     audit point for "did we check the docs before changing this?"
  2. Prompt-cache discipline (stable prefix first, dynamic suffix
     last) is enforced by funneling every prompt through
     `src/prompts/builder.py`. The wrapper rejects raw `messages`
     that don't go through the builder.
  3. Token usage (input / cached / output) is logged in one place.
     `ModelTokenUsage.cached_input_tokens` is populated from the
     usage dict the SDK returns, not assembled by hand at every
     call site.
  4. The synthesizer / agent / classifier protocols (SynthesizerLLM,
     AgentLLM, Embedder) all bind here. Tests in those modules pass
     stubs; prod calls these helpers.

================================================================================
FRESHNESS RULE -- VERIFIED 2026-04-25 against the OpenAI Responses API
migration guide. This module is wired against the **Responses API**
(not legacy Chat Completions), per OpenAI's recommendation that
"Responses is recommended for all new projects".

Key differences from Chat Completions that this module embodies:
  - `client.responses.create(...)` not `client.chat.completions.create(...)`.
  - Stable system prefix goes in `instructions=` (top-level), dynamic
    portion in `input=`. This pairs cleanly with prompts/builder.py's
    [stable prefix] + [dynamic suffix] discipline -- the same prefix
    string is used as `instructions` on every call, maximizing the
    cache prefix.
  - Structured outputs use `text={"format": {...}}` not `response_format`.
  - Tools are internally-tagged: `{type: "function", name, description,
    parameters, strict}` -- NOT the Chat Completions outer wrapper
    `{type: "function", function: {...}}`.
  - Function calls come back as items in `response.output` with
    `type: "function_call"`, `call_id`, `name`, `arguments` (JSON-string).
  - Function-call results are passed back as input items of type
    `function_call_output` with the matching `call_id`.
  - Usage shape: `response.usage.input_tokens`,
    `response.usage.input_tokens_details.cached_tokens` (when present),
    `response.usage.output_tokens`.
  - We pass `store=False` everywhere -- the bot's persistence happens in
    Postgres (Conversation/Message), not in OpenAI's stateful storage.
    This keeps us ZDR-compatible by default.

If OpenAI changes any of the above, re-verify here before editing.
================================================================================

See plan:
  - "Model & API freshness rule"
  - Layer 4 -> "Prompt shrinkage and LLM caching strategy"
  - Critical files -> ai-core/src/llm/client.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.agent.tool_registry import ToolCall

logger = logging.getLogger(__name__)


# --- Shared shapes --------------------------------------------------------


@dataclass(frozen=True)
class LLMUsage:
    """Token usage for one LLM call. Populated from the SDK response.

    `cached_input_tokens` is the cache-hit portion of `input_tokens`.
    Logged into ModelTokenUsage.cached_input_tokens for the
    cache-hit-rate gate (>= 0.6 across the eval suite, per plan).
    """

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        if self.input_tokens == 0:
            return 0.0
        return self.cached_input_tokens / self.input_tokens

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
        }


# --- SDK client (lazy) ----------------------------------------------------

_client: Any = None


def _get_client() -> Any:
    """Return a memoized OpenAI client. Imported lazily so test envs
    without OPENAI_API_KEY can still import this module."""
    global _client
    if _client is None:
        from openai import OpenAI  # type: ignore[import-not-found]

        _client = OpenAI()
    return _client


# --- Usage parsing --------------------------------------------------------


def _usage_from_response(response: Any) -> LLMUsage:
    """Pull token counts off the Responses-API response.

    Defensive about field presence: not every SDK version exposes
    `input_tokens_details` on every model. Missing cached count is
    treated as zero (worst-case overcount of billable tokens, which
    is the safe direction).
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return LLMUsage()

    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

    cached = 0
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        cached = int(getattr(details, "cached_tokens", 0) or 0)

    return LLMUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
    )


# --- Prefix lookup --------------------------------------------------------


def _resolve_prefix(prefix_id: str) -> str:
    """Look up a registered prompt prefix by id.

    The prompts/builder registry is the source of truth -- this module
    pulls the stable text from there so the byte-stability assertions
    apply to every Responses API call too. The prefix is passed as the
    Responses API's top-level `instructions=` field, where it serves
    as the cached system prefix.
    """
    from src.prompts.builder import _REGISTRY, PromptBuildError

    entry = _REGISTRY.get(prefix_id)
    if entry is None:
        raise PromptBuildError(
            f"unknown prefix_id {prefix_id!r}. Did you forget to import "
            f"the prompt module so its register_prefix() call runs?"
        )
    return entry["content"]


# --- Public helpers -------------------------------------------------------


def embed(text: str, *, model: str = "text-embedding-3-large") -> list[float]:
    """Embed one piece of text. Used by intent_knn and (future) by
    retrieval-time query embedding.

    Embeddings API call shape is stable across openai SDK versions and
    independent of the Responses-vs-Chat-Completions split.
    """
    resp = _get_client().embeddings.create(model=model, input=text)
    return list(resp.data[0].embedding)


def completion(
    *,
    prefix_id: str,
    dynamic_suffix: str,
    model: str = "gpt-5.4-mini",
    max_output_tokens: int = 800,
) -> tuple[str, LLMUsage]:
    """Plain text completion via the Responses API.

    The cached prefix lives in `instructions=`; the dynamic portion
    becomes `input=`. This split is what makes prompt caching work --
    `instructions` is byte-stable across calls (registered at module
    import via prompts/builder.register_prefix), `input` is what
    changes per turn.
    """
    instructions = _resolve_prefix(prefix_id)
    response = _get_client().responses.create(
        model=model,
        instructions=instructions,
        input=dynamic_suffix,
        max_output_tokens=max_output_tokens,
        store=False,
    )
    text = getattr(response, "output_text", "") or ""
    return text, _usage_from_response(response)


def structured_completion(
    *,
    prefix_id: str,
    dynamic_suffix: str,
    response_schema: dict,
    schema_name: str = "structured_output",
    model: str = "gpt-5.4-mini",
) -> tuple[dict, LLMUsage]:
    """Completion that returns JSON matching `response_schema`. This is
    the call the synthesizer makes -- the schema is
    `{answer, citations, confidence}`.

    Per the Responses API, structured outputs go in
    `text={"format": {"type": "json_schema", "name": ..., "strict": True,
    "schema": ...}}`. `output_text` returns the JSON string, which we
    parse here so the caller gets a dict.
    """
    instructions = _resolve_prefix(prefix_id)
    response = _get_client().responses.create(
        model=model,
        instructions=instructions,
        input=dynamic_suffix,
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": response_schema,
            }
        },
        store=False,
    )
    raw_text = getattr(response, "output_text", "") or ""
    try:
        parsed = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError as e:
        # With strict json_schema this should be impossible. If it
        # happens, the synthesizer's downstream post-processor will
        # see an empty answer and refuse with model_self_flagged --
        # log loudly so it's debuggable.
        logger.error(
            "structured_completion: json decode failed",
            extra={"error": str(e), "raw_text_preview": raw_text[:200]},
        )
        parsed = {}
    return parsed, _usage_from_response(response)


def completion_with_tools(
    *,
    prefix_id: str,
    input_items: list[dict],
    tools: list[dict],
    model: str = "gpt-5.4-mini",
) -> tuple[dict, list[ToolCall], LLMUsage]:
    """Tool-calling completion via the Responses API.

    `input_items` is a list of Items in the Responses-API shape:
    user/assistant message dicts and prior `function_call_output`
    items from earlier turns of the agent loop. The agent loop
    appends to this list across iterations.

    `tools` must be in the Responses-API internally-tagged shape:
        {"type": "function", "name": ..., "description": ...,
         "parameters": ..., "strict": True}
    Use `ToolRegistry.as_responses_tools()` to get them in this shape.

    Returns `(assistant_message, tool_calls, usage)`. `assistant_message`
    is a single dict suitable to append to `input_items` for the next
    turn (we re-shape Responses output items into one consolidated
    "assistant message" record for the agent loop's bookkeeping).
    `tool_calls` is the parsed list of ToolCall objects -- the agent
    module doesn't have to know the Responses-API SDK shape.
    """
    instructions = _resolve_prefix(prefix_id)
    response = _get_client().responses.create(
        model=model,
        instructions=instructions,
        input=input_items,
        tools=tools,
        store=False,
    )

    output_items: list[Any] = list(getattr(response, "output", []) or [])

    # Parse function_call items into ToolCall objects. Arguments come
    # back as a JSON-encoded string per the Responses API contract; we
    # decode them here so the agent module receives a plain dict.
    tool_calls: list[ToolCall] = []
    for item in output_items:
        item_type = _item_attr(item, "type")
        if item_type != "function_call":
            continue
        call_id = _item_attr(item, "call_id") or _item_attr(item, "id") or ""
        name = _item_attr(item, "name") or ""
        raw_args = _item_attr(item, "arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            args = {"_raw": raw_args}
        tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))

    # Build a single dict to represent "what the LLM said" for the
    # agent loop's `last_tool_call_key` bookkeeping and conversation
    # extension. We preserve the raw output items list so callers can
    # round-trip them back into the next request's input.
    text_output = getattr(response, "output_text", "") or ""
    assistant_message = {
        "role": "assistant",
        "content": text_output,
        "_response_output_items": output_items,
    }

    return assistant_message, tool_calls, _usage_from_response(response)


def _item_attr(item: Any, name: str) -> Any:
    """Read an attribute from a Responses-API output item that may be
    an SDK pydantic object OR a plain dict (test stubs)."""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


__all__ = [
    "LLMUsage",
    "completion",
    "completion_with_tools",
    "embed",
    "structured_completion",
]
