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

from typing import Literal


# --- Model identifiers -------------------------------------------------------

BASIC_MODEL: str = "gpt-5.4-mini"
"""Default model for agent loop, eval judge, and light extraction tasks."""

REASONING_MODEL: str = "gpt-5.2"
"""High-reasoning model for ambiguous synthesis, multi-step tool calls,
and clarification generation."""

EMBEDDING_MODEL: str = "text-embedding-3-large"
"""Embedding model for kNN classifier exemplars AND document chunks.
Higher cost than -small but gives meaningful accuracy lift on noun-heavy
library queries (e.g., 'Wertz', 'MakerSpace', 'ILL'). Corpus is small
enough (~580 URLs, single-digit thousands of chunks) that the cost
premium is negligible at our scale."""


# --- Type aliases for routing decisions --------------------------------------

ModelTier = Literal["basic", "reasoning"]
"""Logical tier consumers should pass when they don't care about the exact
model ID -- lets us swap underlying models without touching call sites."""


def resolve_model(tier: ModelTier) -> str:
    """Resolve a logical tier to the current concrete model ID.

    Always prefer this over hard-coding `BASIC_MODEL` / `REASONING_MODEL`
    at call sites that conditionally pick a tier (e.g., the synthesizer's
    routing logic).

    Args:
        tier: "basic" for high-throughput / cheap calls, "reasoning" for
            ambiguous-synthesis / multi-step / clarification calls.

    Returns:
        The current concrete model identifier string.

    Raises:
        ValueError: If `tier` is not a recognized tier.
    """
    if tier == "basic":
        return BASIC_MODEL
    if tier == "reasoning":
        return REASONING_MODEL
    raise ValueError(
        f"Unknown model tier: {tier!r}. Expected 'basic' or 'reasoning'."
    )


# --- Cache threshold constant -----------------------------------------------

PROMPT_CACHE_PREFIX_THRESHOLD_TOKENS: int = 1024
"""Minimum identical prefix length (tokens) for OpenAI's automatic prompt
cache to engage. Used by `prompts/builder.py` to assert stable prefixes
clear the threshold. VERIFY against live OpenAI docs at code-change time
-- this constant has changed across model generations."""
