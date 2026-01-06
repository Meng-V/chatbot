"""
Router Module - Advanced Question Classification & Routing

This module provides a multi-stage routing system:
- Heuristic Gate: Fast pattern-based triage
- Weaviate Prototypes: Semantic similarity with high-quality prototypes
- Margin Decision: Confidence-based early stopping
- LLM Triage: o4-mini-based clarification/arbitration
"""

from .schemas import RouteResponse, ClarifyResponse, RouteCandidate
from .heuristics import HeuristicGate
from .weaviate_router import WeaviateRouter
from .margin import MarginDecision
from .llm_triage import LLMTriage

__all__ = [
    'RouteResponse',
    'ClarifyResponse',
    'RouteCandidate',
    'HeuristicGate',
    'WeaviateRouter',
    'MarginDecision',
    'LLMTriage',
]
