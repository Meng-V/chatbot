# Legacy v3.1 serving path — removed from production 2026-07-17

The LangGraph-based v3.1 orchestrator (orchestrator.py, rag_router.py,
intent_normalizer.py) and its test scripts, retired when the operator
went all-in on the v2 rebuild (src/graph/new_orchestrator.py).
Kept for reference; not importable from src/ anymore.
