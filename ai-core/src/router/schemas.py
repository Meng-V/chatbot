"""
Pydantic schemas for router responses
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class RouteCandidate(BaseModel):
    """A candidate agent/category from routing"""
    agent_id: str = Field(..., description="Agent identifier")
    score: float = Field(..., description="Confidence score (0-1)")
    text: str = Field(..., description="Prototype or example text that matched")


class ClarifyOption(BaseModel):
    """A clarification button option"""
    label: str = Field(..., description="User-facing button text")
    value: str = Field(..., description="Value to send back (agent_id or 'other')")
    description: Optional[str] = Field(None, description="Optional tooltip/description")


class ClarifyResponse(BaseModel):
    """Response when clarification is needed"""
    mode: Literal["clarify"] = "clarify"
    confidence: Literal["low"] = "low"
    clarifying_question: str = Field(..., description="Short question to ask user")
    options: List[ClarifyOption] = Field(..., description="Button options (always include 'other')")


class RouteResponse(BaseModel):
    """Response when route is determined"""
    mode: Literal["vector", "llm_judge", "heuristic"] = Field(..., description="How route was determined")
    agent_id: str = Field(..., description="Selected agent ID")
    confidence: Literal["high", "medium", "low"] = Field(..., description="Confidence level")
    reason: Optional[str] = Field(None, description="Why this route was chosen")
    candidates: Optional[List[RouteCandidate]] = Field(None, description="Top candidates considered")


class RouteRequest(BaseModel):
    """Request to route a query"""
    query: str = Field(..., description="User's question")
    user_context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    route_hint: Optional[str] = Field(None, description="Explicit route hint from clarification")
