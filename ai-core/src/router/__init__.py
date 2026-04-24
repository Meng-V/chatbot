"""
Router module.

Two classifier eras coexist here during the rebuild:

  - The legacy 4-stage router (heuristics -> Weaviate prototypes ->
    margin -> LLM triage). Scheduled for deletion in week 3 per plan
    §"Critical files to modify". These are guarded by a lazy import
    so environments that don't have the legacy deps (langchain,
    pydantic) can still import the new classifier.

  - The new embedding-kNN classifier in intent_knn.py. Zero external
    deps, unit-testable without OpenAI credentials, drop-in
    replacement.
"""

# New classifier -- always importable, zero heavy deps.
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

# Legacy router exports. Guarded so test / ETL environments that lack
# langchain / pydantic can import the new classifier without pulling
# the whole legacy stack in. In prod all deps are installed and the
# names are available.
try:
    from .schemas import RouteResponse, ClarifyResponse, RouteCandidate  # noqa: F401
    from .heuristics import HeuristicGate  # noqa: F401
    from .weaviate_router import WeaviateRouter  # noqa: F401
    from .margin import MarginDecision  # noqa: F401
    from .llm_triage import LLMTriage  # noqa: F401

    __all__ = [
        "Classification",
        "Embedder",
        "Exemplar",
        "INTENTS",
        "IntentKNN",
        "MARGIN_HIGH",
        "MARGIN_LOW",
        "build_classifier",
        "RouteResponse",
        "ClarifyResponse",
        "RouteCandidate",
        "HeuristicGate",
        "WeaviateRouter",
        "MarginDecision",
        "LLMTriage",
    ]
except ImportError:
    # Legacy deps not installed -- new classifier is still usable.
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
