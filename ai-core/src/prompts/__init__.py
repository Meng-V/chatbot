"""
Prompt registry + cache-aware prompt builder.

Every LLM call in the rebuilt chatbot composes its prompt as
    [STABLE PREFIX (cached)] + [DYNAMIC SUFFIX (not cached)]
through `prompts.builder.build_prompt()`. The stable prefix lives in a
versioned constants file (e.g. agent_v1.py) and is byte-stable across
calls; the builder asserts this with a hash check on every invocation
so a careless edit can't silently kill the cache hit rate.

See plan: Layer 4 (prompt shrinkage and LLM caching strategy).
"""

from src.prompts.builder import (
    PromptBuildError,
    build_prompt,
    register_prefix,
    registered_prefix_ids,
)

__all__ = [
    "PromptBuildError",
    "build_prompt",
    "register_prefix",
    "registered_prefix_ids",
]
