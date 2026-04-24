"""
LLM client wrapper.

Centralizes every OpenAI call site in the codebase behind one set of
helpers, so:

  - The freshness rule (must consult OpenAI docs before changing
    call shape) has ONE module to gatekeep.
  - Token usage logging (input / cached / output) happens in one
    place.
  - The prompt-cache prefix discipline is enforced by funneling
    every call through src/prompts/builder.py.

See plan: "Model & API freshness rule".
"""

from src.llm.client import (
    LLMUsage,
    completion,
    completion_with_tools,
    embed,
    structured_completion,
)

__all__ = [
    "LLMUsage",
    "completion",
    "completion_with_tools",
    "embed",
    "structured_completion",
]
