"""
Single source of truth for OpenAI model identifiers.

Every LLM call in the codebase imports from here. Updating a model name
(or call-shape) happens in exactly one place after consulting the latest
OpenAI docs.

================================================================================
MODEL & API FRESHNESS RULE
================================================================================

Whenever an AI assistant (Claude Code, Copilot, etc.) is helping with code
changes that touch the OpenAI client -- model parameters, structured outputs,
prompt caching headers, tool/function calling, streaming, or the Python `openai`
SDK call shape -- it MUST first fetch the latest OpenAI API docs
(https://platform.openai.com/docs) for the model IDs below to confirm:

    1. The exact model identifier string
    2. Supported parameters (some models drop `temperature`, change
       `max_tokens` semantics, etc.)
    3. Current structured-output / response-format syntax
    4. Prompt-cache prefix length and headers
    5. Tool/function-calling schema shape

DO NOT rely on training-data memory of older OpenAI APIs -- model families
change call shapes frequently. If the docs cannot be reached, STOP and ask
before writing code.

================================================================================
MODEL ROUTING POLICY (see plan: Layer 4 -- Prompts and synthesis)
================================================================================

- BASIC_MODEL: agent loop default, LLM-as-judge in eval, light extraction.
- REASONING_MODEL: synthesis when retrieval is ambiguous, tool-calling on
  multi-step queries, clarification generation. Promote from BASIC_MODEL when:
    (a) retrieval returned >5 chunks across multiple `topic` tags (multi-hop)
    (b) classifier confidence was in the clarification band but user opted to
        proceed anyway
    (c) the question contains comparative / multi-step phrasing
- EMBEDDING_MODEL: intent kNN classifier exemplars + document chunks. Single
  embedding model across all use cases so the vector spaces align.

================================================================================
PROMPT CACHE NOTES
================================================================================

OpenAI automatic prompt caching kicks in at >=1024 identical prefix tokens
(verify against current docs at code-change time). Different model IDs have
SEPARATE caches -- switching from BASIC_MODEL to REASONING_MODEL mid-conversation
forfeits the cache for that turn. Factor this into the model-routing decision.
"""

import os
from typing import Literal


# --- Model identifiers (env-driven; one place; .env-managed) -----------------
#
# Operator preference (2026-05-19): 3 tiers, switchable in .env without
# code edits. Defaults are the gpt-5.4 family, VERIFIED 2026-05-19
# against the operator's OpenAI dashboard + developers.openai.com
# (guides/reasoning, /text, /migrate-to-responses):
#
#   id              reasoning  ctx      $/1M in / cached / out
#   gpt-5.4         5/5        1.05M    2.50 / 0.25 / 15.00
#   gpt-5.4-mini    4/5        400K     0.75 / 0.08 /  4.50
#   gpt-5.4-nano    3/5        400K     0.20 / 0.02 /  1.25
#
# All three are REASONING models (reasoning-token support), expose both
# /v1/chat/completions and /v1/responses, 128K max output, cutoff
# 2025-08-31. Responses API: `input` (user), `instructions` (system),
# `max_output_tokens` (NOT max_tokens), structured output via
# `text.format`:{type:json_schema}, effort via `reasoning.effort`.

BASIC_MODEL: str = os.getenv("LLM_MODEL_BASIC", "gpt-5.4-mini").strip()
"""Easy / surface questions: agent loop default, light extraction.
Env: LLM_MODEL_BASIC."""

REASONING_MODEL: str = os.getenv("LLM_MODEL_REASONING", "gpt-5.4").strip()
"""Hard / sophisticated questions: ambiguous synthesis, multi-step
tool calls, clarification. Env: LLM_MODEL_REASONING."""

CHEAP_MODEL: str = os.getenv("LLM_MODEL_CHEAP", "gpt-5.4-nano").strip()
"""High-volume MECHANICAL calls where weak instruction-following is
low-risk: LLM-as-judge in eval, classifier-fallback, light
extraction/normalization. ~3.7x cheaper than basic, ~12x vs reasoning.
NEVER route the grounded synthesizer or the tool-calling agent here --
that reintroduces the hallucination/citation failures the rebuild
exists to kill. Env: LLM_MODEL_CHEAP."""

EMBEDDING_MODEL: str = os.getenv(
    "LLM_MODEL_EMBEDDING", "text-embedding-3-large"
).strip()
"""Embedding model for kNN classifier exemplars AND document chunks.
ONE embedding model across all use cases so the vector spaces align
(changing it invalidates the whole index -- re-embed required).
Env: LLM_MODEL_EMBEDDING."""


# --- Call-shape gate (the load-bearing correctness helper) -------------------

def is_reasoning_model(model_id: str) -> bool:
    """True if `model_id` is a REASONING model -> the OpenAI client must
    NOT send `temperature` (reasoning models reject/ignore it; control
    is via `reasoning.effort`). Sending temperature to a reasoning model
    risks a 400.

    Basis (NOT a guess -- verified 2026-05-19): the o-series (o1/o3/o4
    ...) and the entire gpt-5.x family (5.2, 5.4, 5.4-mini, 5.4-nano)
    are reasoning models. Older gpt-4*/gpt-3* are not. Omitting
    temperature is superset-safe: correct for reasoning models AND
    harmless for non-reasoning ones (they use their default). The 3
    OpenAI guides were silent on temperature for 5.4 specifically, so
    we deliberately take the can't-break direction.

    Replaces the legacy `OPENAI_MODEL.startswith("o")` check, which
    missed the gpt-5.x reasoning family and would 400 the live bot
    once the default moved to gpt-5.4.
    """
    m = (model_id or "").strip().lower()
    return m.startswith("o") or m.startswith("gpt-5")


# --- Type aliases for routing decisions --------------------------------------

ModelTier = Literal["basic", "reasoning", "cheap"]
"""Logical tier consumers pass when they don't care about the exact
model ID -- lets us swap underlying models via .env without touching
call sites."""


def resolve_model(tier: ModelTier) -> str:
    """Resolve a logical tier to the current concrete model ID.

    Always prefer this over hard-coding the constants at call sites.

    Args:
        tier: "basic" (easy/surface), "reasoning" (hard/sophisticated),
            or "cheap" (high-volume mechanical: judge / classifier
            fallback / extraction).

    Returns:
        The current concrete model identifier string.

    Raises:
        ValueError: If `tier` is not a recognized tier.
    """
    if tier == "basic":
        return BASIC_MODEL
    if tier == "reasoning":
        return REASONING_MODEL
    if tier == "cheap":
        return CHEAP_MODEL
    raise ValueError(
        f"Unknown model tier: {tier!r}. Expected 'basic', 'reasoning', "
        f"or 'cheap'."
    )


# --- Cache threshold constant -----------------------------------------------

PROMPT_CACHE_PREFIX_THRESHOLD_TOKENS: int = 1024
"""Minimum identical prefix length (tokens) for OpenAI's automatic prompt
cache to engage. Used by `prompts/builder.py` to assert stable prefixes
clear the threshold. VERIFY against live OpenAI docs at code-change time
-- this constant has changed across model generations."""
