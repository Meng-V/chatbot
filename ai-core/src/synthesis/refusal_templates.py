"""
Templated refusal copy, keyed by `RefusalTrigger`.

Refusals are templated (not LLM-generated) for three reasons:
  1. Predictability -- a refusal should read the same way every time
     so the user learns to trust the handoff affordance.
  2. No second model call -- we already decided to refuse; paying for
     another round-trip to write "I don't know" would be wasteful.
  3. Scope-awareness -- the copy mentions the resolved campus / library
     by display name ("the Hamilton campus", "Rentschler Library"),
     which comes from the Scope object, not from the model.

See plan:
  - Citation and refusal contract -> Refusal triggers (nine cases)
  - Data preparation playbook §8 -> scope-specific refusal copy for
    cross-campus and service-not-at-this-building
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RefusalTrigger(str, Enum):
    """The nine reasons a turn can downgrade to a refusal.

    String-valued so the enum is JSON-serializable for logging and
    eval-suite reporting without a custom encoder.
    """

    # Retrieval side
    NO_RESULTS = "no_results"
    """search_kb returned 0 chunks above the relevance threshold."""

    LOW_CONFIDENCE = "low_confidence"
    """Top score below threshold, or top-1/top-2 margin below 0.05."""

    # Intent / capability side
    OUT_OF_SCOPE = "out_of_scope"
    """kNN classifier picked `out_of_scope` (e.g. catalog searches,
    sports scores, homework help)."""

    CAPABILITY_LIMIT = "capability_limit"
    """capability_scope.py flagged this as a thing the bot cannot do
    (account ops, ILL submission, renewals)."""

    LIVE_DATA_DOWN = "live_data_down"
    """LibCal / LibAnswers tool call failed or timed out. The bot
    refuses with this trigger instead of guessing stale hours."""

    # Synthesizer side
    MODEL_SELF_FLAGGED = "model_self_flagged"
    """The synthesizer returned `confidence: low` or the literal
    REFUSAL token. The model itself admitted it can't answer."""

    CITATION_INVALID = "citation_invalid"
    """Post-processor caught a fabricated URL or a [n] citation that
    points to a non-existent source in the evidence bundle."""

    # Scope-discipline side (the load-bearing cross-campus guard)
    CROSS_CAMPUS_MISMATCH = "cross_campus_mismatch"
    """Synthesizer cited a chunk whose campus differs from
    scope.campus (and isn't `all`). Prevents King hours being served
    as Hamilton hours."""

    SERVICE_NOT_AT_BUILDING = "service_not_at_building"
    """User asked about a service at a building/campus that
    LibrarySpace.services_offered doesn't list (e.g. MakerSpace at
    Middletown). Refusal names the service, names the campus, points
    to where the service DOES exist."""


@dataclass(frozen=True)
class RefusalContext:
    """Everything the template renderer may need to fill placeholders.

    Kept as a single dataclass rather than **kwargs so it's type-
    checkable at the call site and so forgetting a field for a
    scope-specific refusal fails loud instead of producing
    "I don't know about {campus_display}" in production.
    """

    campus_display: Optional[str] = None
    library_display: Optional[str] = None
    service_name: Optional[str] = None
    """For SERVICE_NOT_AT_BUILDING: user-facing service name
    (e.g. `MakerSpace`, `Special Collections`)."""

    service_available_at: Optional[str] = None
    """For SERVICE_NOT_AT_BUILDING: where the service DOES exist,
    phrased for the template (e.g. `King Library on the Oxford campus`)."""

    staff_directory_url: Optional[str] = None
    """For CROSS_CAMPUS_MISMATCH: the campus-appropriate staff
    directory to link to ("try the Rentschler staff directory")."""


# --- Templates -------------------------------------------------------------
#
# Keep these short, plain-spoken, and end with a concrete next step.
# Each is a string.format() template -- placeholders must match fields on
# RefusalContext. Unknown placeholders raise KeyError at render time,
# which is intentional: a missing field should crash the test run, not
# ship "{campus_display}" to a user.

_TEMPLATES: dict[RefusalTrigger, str] = {
    RefusalTrigger.NO_RESULTS: (
        "I couldn't find anything in the library's pages that answers that. "
        "You can ask a librarian directly via Ask Us, or try rephrasing the "
        "question with a more specific term."
    ),
    RefusalTrigger.LOW_CONFIDENCE: (
        "I'm not confident I have the right answer here. Rather than guess, "
        "I'd recommend asking a librarian -- Ask Us will reach someone who "
        "can help."
    ),
    RefusalTrigger.OUT_OF_SCOPE: (
        "That's outside what I can help with. If this is a library question "
        "I'm misreading, try rephrasing it. For research help, Ask Us will "
        "connect you to a librarian."
    ),
    RefusalTrigger.CAPABILITY_LIMIT: (
        "I can point you to the right page, but I can't do that action "
        "myself. A librarian can help -- try Ask Us."
    ),
    RefusalTrigger.LIVE_DATA_DOWN: (
        "I can't check live information right now (hours / room "
        "availability). Please try again in a few minutes, or check the "
        "library website directly."
    ),
    RefusalTrigger.MODEL_SELF_FLAGGED: (
        "I don't have a reliable answer to that. You can ask a librarian "
        "directly through Ask Us."
    ),
    RefusalTrigger.CITATION_INVALID: (
        "I started to answer but couldn't verify my sources. Rather than "
        "send you something I can't back up, please ask a librarian through "
        "Ask Us."
    ),
    RefusalTrigger.CROSS_CAMPUS_MISMATCH: (
        "I don't have information about that for the {campus_display} "
        "campus. Try asking the {campus_display} library staff directly -- "
        "their directory is at {staff_directory_url}."
    ),
    RefusalTrigger.SERVICE_NOT_AT_BUILDING: (
        "There isn't a {service_name} at the {campus_display} campus "
        "library. {service_name} is at {service_available_at}. For help "
        "at {campus_display}, ask the library staff through Ask Us."
    ),
}


def render_refusal(
    trigger: RefusalTrigger,
    context: Optional[RefusalContext] = None,
) -> str:
    """Render the templated refusal copy for `trigger`.

    Args:
        trigger: Which refusal variant to render.
        context: Fields to fill into the template. Required for
            CROSS_CAMPUS_MISMATCH and SERVICE_NOT_AT_BUILDING; ignored
            for others (which have no placeholders).

    Returns:
        A single-paragraph plain-text string ready to render in the UI.
        The UI is responsible for appending the human-handoff affordance
        (a button, not text), so the copy never includes "click here".

    Raises:
        KeyError: if the template references a RefusalContext field that
            is None. This is deliberate -- a scope-specific refusal
            without a scope is a bug, not a degraded output.
    """
    template = _TEMPLATES[trigger]
    if context is None:
        # No placeholders for the scope-free templates; format() with
        # an empty dict is a no-op unless the template *did* have a
        # placeholder, in which case KeyError fires as designed.
        return template.format()

    # Only pass non-None fields so the KeyError above actually fires
    # for missing fields rather than being masked by `None` values.
    kwargs = {
        k: v for k, v in context.__dict__.items() if v is not None
    }
    return template.format(**kwargs)


__all__ = [
    "RefusalContext",
    "RefusalTrigger",
    "render_refusal",
]
