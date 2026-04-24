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
FRESHNESS RULE -- READ BEFORE EDITING
================================================================================
Per plan ("Model & API freshness rule"):
  - Before adding / changing ANY of: model identifier strings,
    structured-output schema syntax, prompt-caching headers,
    tool/function calling shape, streaming, or the openai SDK call
    signature -- FETCH the live OpenAI docs at
    https://platform.openai.com/docs and confirm:
      (1) the exact model identifier string
      (2) supported parameters (some models drop temperature, change
          max_tokens semantics, etc.)
      (3) current structured-output / response-format syntax
      (4) prompt-cache prefix length and headers

  - Do NOT rely on training-data memory of older OpenAI APIs -- model
    families change call shapes frequently.
  - If the docs cannot be reached, STOP and ask before writing code.

The functions below intentionally raise NotImplementedError until that
verification is performed. Replace the bodies after consulting the
docs.
================================================================================

See plan:
  - "Model & API freshness rule"
  - Layer 4 -> "Prompt shrinkage and LLM caching strategy"
  - Critical files -> ai-core/src/llm/client.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


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


# --- Guard ---------------------------------------------------------------

_NOT_WIRED_MESSAGE = (
    "OpenAI client call not wired. Per the plan's freshness rule, fetch "
    "live OpenAI docs (https://platform.openai.com/docs) for the target "
    "model identifier ('gpt-5.4-mini' / 'gpt-5.2' / 'text-embedding-3-large') "
    "and confirm: (1) exact id string, (2) supported parameters, (3) "
    "structured-output / response-format syntax, (4) prompt-cache prefix "
    "length and headers. Then replace this function body. Do NOT rely on "
    "training-data memory of older OpenAI APIs."
)


def _ensure_wired() -> None:
    raise NotImplementedError(_NOT_WIRED_MESSAGE)


# --- Public helpers (each gated until verified) ---------------------------


def embed(text: str, *, model: str = "text-embedding-3-large") -> list[float]:
    """Embed one piece of text. Used by intent_knn and (future) by
    retrieval-time query embedding.

    Wiring TODO (after freshness check):
        client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding
    """
    _ensure_wired()
    return []  # unreachable; satisfies static type checkers


def completion(
    *,
    prefix_id: str,
    dynamic_suffix: str,
    model: str = "gpt-5.4-mini",
    max_output_tokens: int = 800,
) -> tuple[str, LLMUsage]:
    """Plain text completion. Goes through prompts/builder so the cache
    prefix is byte-stable.

    Wiring TODO (after freshness check):
        from src.prompts.builder import build_prompt
        messages = build_prompt(prefix_id, [{'role': 'user', 'content': dynamic_suffix}])
        resp = client.chat.completions.create(model=model, messages=messages, ...)
        usage = LLMUsage(
            input_tokens=resp.usage.prompt_tokens,
            cached_input_tokens=resp.usage.prompt_tokens_details.cached_tokens,
            output_tokens=resp.usage.completion_tokens,
        )
        return resp.choices[0].message.content, usage
    """
    _ensure_wired()
    return "", LLMUsage()


def structured_completion(
    *,
    prefix_id: str,
    dynamic_suffix: str,
    response_schema: dict,
    model: str = "gpt-5.4-mini",
) -> tuple[dict, LLMUsage]:
    """Completion that returns JSON matching `response_schema`. This is
    the call the synthesizer makes -- the schema is
    `{answer, citations, confidence}`.

    Wiring TODO (after freshness check): use the structured-output /
    json-schema response_format param per the docs. The exact param
    name and schema-version key changes across model generations --
    confirm at code-change time."""
    _ensure_wired()
    return {}, LLMUsage()


def completion_with_tools(
    *,
    prefix_id: str,
    messages: list[dict],
    tools: list[dict],
    model: str = "gpt-5.4-mini",
) -> tuple[dict, list[Any], LLMUsage]:
    """Tool-calling completion. This is the call the agent loop makes.

    Returns `(assistant_message, tool_calls, usage)`. `tool_calls` is
    a list of `ToolCall` objects (defined in src/agent/tool_registry).
    The mapping from raw OpenAI tool_calls to ToolCall happens here so
    the agent module doesn't have to know the SDK shape.

    Wiring TODO (after freshness check): tool-call response shape has
    changed across the gpt-4 / gpt-5 transition; confirm whether
    `tool_calls` lives on `message.tool_calls` or in a `function_call`
    field, and whether arguments are str-encoded JSON or pre-parsed."""
    _ensure_wired()
    return {}, [], LLMUsage()


__all__ = [
    "LLMUsage",
    "completion",
    "completion_with_tools",
    "embed",
    "structured_completion",
]
