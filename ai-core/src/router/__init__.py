"""
Router module: the embedding-kNN intent classifier used by the v2
orchestrator, plus the intent-capability table and exemplar data.

The legacy 4-stage pipeline that used to live alongside it (schemas /
heuristics / weaviate_router / margin / llm_triage / router_subgraph)
was archived 2026-07-18 to `ai-core/archived/legacy_v31/` together with
the /route endpoint that was its only consumer.
"""

from .intent_knn import (
    Classification,
    Embedder,
    Exemplar,
    INTENTS,
    IntentKNN,
    MARGIN_HIGH,
    MARGIN_LOW,
    build_classifier,
)

__all__ = [
    "Classification",
    "Embedder",
    "Exemplar",
    "INTENTS",
    "IntentKNN",
    "MARGIN_HIGH",
    "MARGIN_LOW",
    "build_classifier",
]
