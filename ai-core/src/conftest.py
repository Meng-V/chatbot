"""Shared pytest fixtures for the ai-core test suite."""
from __future__ import annotations

import pytest

from src.prompts import builder

# Ensure every SHIPPED prefix is registered, then snapshot that as the
# clean baseline. Importing the modules runs their module-level
# register_prefix() calls (idempotent).
from src.prompts import (  # noqa: E402,F401
    agent_v1,
    clarifier_v1,
    judge_v1,
    synthesizer_v1,
)

_BASELINE_REGISTRY = dict(builder._REGISTRY)


@pytest.fixture(autouse=True)
def _isolate_prefix_registry():
    """Reset the global prompt-prefix registry to the shipped-prefix
    baseline around EVERY test.

    The registry is a module-level global. Tests register throwaway
    prefixes (e.g. ``test_client_prefix_v1`` via _ensure_test_prefix) or
    clear it (test_builder), and the registry holds whatever was last
    written. Without isolation that leaked across modules and produced
    order-dependent failures under ``pytest src/`` that did NOT reproduce
    when a module ran alone -- the classic symptom being
    test_cache_health's "every registered prefix clears the 1024-token
    cache threshold" tripping over a leaked 237-token throwaway prefix,
    or "current prefixes registered" failing because an earlier test had
    cleared the registry.

    Resetting to the SHIPPED baseline (not just snapshot/restore) means
    every test starts from exactly the production set: no junk, all
    shipped prefixes present. Production is unaffected -- the running app
    registers prefixes once at import and never clears them; this is
    purely test hygiene that makes the suite order-independent.
    """
    builder._REGISTRY.clear()
    builder._REGISTRY.update(_BASELINE_REGISTRY)
    try:
        yield
    finally:
        builder._REGISTRY.clear()
        builder._REGISTRY.update(_BASELINE_REGISTRY)
