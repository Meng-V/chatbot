"""
The new agent's tool surface.

Replaces the per-agent tool collections from the legacy `src/agents/`
sub-agents (subject_librarian / libguide / libcal_comprehensive / etc.)
with a single flat tool registry the one tool-calling agent picks
from per turn.

Why a parallel module rather than mutating `src/tools/`:
    - The legacy tools in `src/tools/` are plug-compatible with the
      LangChain-shaped sub-agents; the plan keeps those agents alive
      behind the feature flag for instant rollback. We don't want to
      change their import surface.
    - The new tools target the new `src/agent/run_agent` loop and use
      our typed `Tool` / `ToolError` types. Different shape, different
      home.
    - When the rollout flag flips to 100% and the legacy path retires,
      we delete `src/tools/` and rename this to `src/tools/`. Until
      then both coexist.

The `ToolBackends` dataclass is the only seam: prod code passes a
`ToolBackends(...)` with real Weaviate / Postgres / LibCal clients
plumbed in; tests pass a `ToolBackends(...)` with stub callables. Adding
a new tool means: write the handler, declare the JSON schema, register
it in `build_tool_registry()` -- four lines in one file.
"""

from __future__ import annotations

from src.tools_v2.registry import (
    ToolBackends,
    build_tool_registry,
)


__all__ = [
    "ToolBackends",
    "build_tool_registry",
]
