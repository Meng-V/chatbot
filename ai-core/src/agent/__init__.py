"""
Single tool-calling agent.

Replaces the 6 specialized sub-agents with one LLM-driven agent that
picks tools per turn. The pattern already works internally in
LibCalComprehensiveAgent -- this module applies it to the whole bot.

Two pieces:
  - tool_registry.py -- a typed registry for tool definitions (name,
                         JSON schema, callable). Tools plug in without
                         touching the agent loop.
  - agent.py         -- the loop: classify -> plan -> call tool -> observe
                         -> synthesize. Bounded iterations, bounded
                         cost, structured output.

See plan: Layer 3 (classification+routing), Critical files section.
"""

from src.agent.agent import (
    AgentOutcome,
    AgentRequest,
    AgentTurn,
    run_agent,
)
from src.agent.tool_registry import (
    Tool,
    ToolCall,
    ToolError,
    ToolRegistry,
    ToolResult,
)

__all__ = [
    "AgentOutcome",
    "AgentRequest",
    "AgentTurn",
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "run_agent",
]
