"""
The cross-campus "service-not-at-this-building" guard (plan §8/§9).

`build_service_guard()` returns the `lookup_service_availability`
callable the orchestrator expects:

    (intent: str, scope_campus: str) -> Optional[RefusalContext]

It is the load-bearing DETERMINISTIC defense against the
"MakerSpace at Hamilton" hallucination class: if the classified
intent maps to a campus-restricted featured service and NO building
on `scope_campus` offers it, the orchestrator short-circuits to a
SERVICE_NOT_AT_BUILDING refusal BEFORE the agent/synthesizer can
invent a "yes".

WHY read the seed's `SPACES` constant instead of the DB:
`scripts/seed_library_spaces_v2.py::SPACES` is the *authoritative*
source (its own docstring: "This module's SPACES constant is the
authoritative source ... Adding a new building or service is a
one-edit append plus re-run"). The `LibrarySpace_v2` table is a
projection of it (seeded FROM it; verified identical). Reading SPACES
directly makes the guard pure/sync/offline-testable and means it
CANNOT be silently disabled by the DB being unreachable -- the right
property for a load-bearing safety guard. (`run_turn` calls this
synchronously; a per-request async DB hit would be the wrong shape.)

CONSERVATIVE BY DESIGN: only intents for services the plan §7 marks
campus-restricted (MakerSpace, Special Collections) are gated.
University-wide services (Adobe, ILL, newspapers, digital
collections, printing) are NEVER gated -- they exist on every
campus, so gating them would cause FALSE refusals (worse-not-better;
plan §9 requires <10% refusal on legitimate questions). An unknown /
ungated intent always returns None (no refusal).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from src.synthesis.refusal_templates import RefusalContext

logger = logging.getLogger(__name__)

# intent -> (required service token(s), user-facing service name).
# A campus "has" the service if ANY of its buildings lists ANY of the
# required tokens in services_offered. Keep this MINIMAL: only the
# plan §7 campus-restricted featured services. Adding an entry here
# makes the guard refuse that intent on campuses lacking the service,
# so it must be a service that genuinely doesn't exist parity-wide.
_GATED_INTENTS: dict[str, tuple[frozenset[str], str]] = {
    "makerspace_3d": (frozenset({"makerspace"}), "the MakerSpace"),
    "special_collections": (
        frozenset({"rare_books_access", "archival_research"}),
        "Special Collections & University Archives",
    ),
}

_CAMPUS_DISPLAY = {
    "oxford": "Oxford",
    "hamilton": "Hamilton",
    "middletown": "Middletown",
}


def _load_spaces():
    """The canonical truth table (seed SPACES). Defensive: any import
    failure -> empty, which makes the guard a no-op (safe degradation:
    a guard that can't load must NOT start refusing legitimate
    questions; absence of data is not evidence of absence of service)."""
    try:
        from scripts.seed_library_spaces_v2 import SPACES  # type: ignore

        return list(SPACES)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "service guard: could not load SPACES (%s); guard DISABLED "
            "(returns None for all intents).", e,
        )
        return []


def build_service_guard(
    spaces: Optional[list] = None,
) -> Callable[[str, str], Optional[RefusalContext]]:
    """Build the `(intent, scope_campus) -> Optional[RefusalContext]`
    guard, closing over an in-memory copy of the truth table.

    `spaces` is injectable for tests (a list of objects/rows with
    `.campus`, `.library`, `.name`, `.services_offered`). Production
    passes nothing -> the canonical seed SPACES.
    """
    rows = spaces if spaces is not None else _load_spaces()

    # campus -> union of all services offered by any building there.
    campus_services: dict[str, set[str]] = {}
    # required-token -> a human phrase for where it DOES exist.
    for r in rows:
        campus = (getattr(r, "campus", "") or "").lower()
        svcs = set(getattr(r, "services_offered", []) or [])
        campus_services.setdefault(campus, set()).update(svcs)

    def _where_phrase(required: frozenset[str]) -> Optional[str]:
        for r in rows:
            svcs = set(getattr(r, "services_offered", []) or [])
            if required & svcs:
                name = getattr(r, "name", None) or getattr(r, "library", "")
                camp = _CAMPUS_DISPLAY.get(
                    (getattr(r, "campus", "") or "").lower(),
                    (getattr(r, "campus", "") or "").title(),
                )
                return f"{name} on the {camp} campus"
        return None

    def guard(intent: str, scope_campus: str) -> Optional[RefusalContext]:
        if not rows:
            # Truth table unavailable (import failed / injected empty).
            # SAFE DEGRADATION: absence of data is NOT evidence of
            # absence of service -- a guard that can't load its table
            # must NOT start false-refusing legitimate questions.
            return None
        spec = _GATED_INTENTS.get(intent or "")
        if spec is None:
            return None  # ungated/unknown intent -> never refuse
        required, label = spec
        campus = (scope_campus or "oxford").lower()
        if required & campus_services.get(campus, set()):
            return None  # the service IS offered on this campus -> proceed
        # Service is genuinely not on this campus -> refuse, and say
        # where it DOES exist so the refusal is actionable.
        return RefusalContext(
            service_name=label,
            campus_display=_CAMPUS_DISPLAY.get(campus, campus.title()),
            service_available_at=_where_phrase(required),
        )

    return guard


__all__ = ["build_service_guard"]
