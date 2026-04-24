"""
The load-bearing citation / URL / scope validator.

Every synthesizer output goes through `process_synthesizer_output()`
before it leaves the backend. If ANY check fails, the output is
DOWNGRADED to a refusal -- we never silently drop an invalid citation
and ship the remaining text. The whole point of this module is that the
LLM is not trusted as the last line of defense on citations; this is.

Four independent checks, in order:

  1. Confidence gate. The synthesizer returns
     `confidence in {"low", "medium", "high"}`. `low` is a refusal.
     (Also: the literal token "REFUSAL" anywhere in the answer is
     treated as a self-flag; the synthesizer prompt instructs the model
     to emit it when the answer isn't in the sources.)

  2. Citation match. Every `[n]` that appears in the answer text must
     resolve to an entry in `citations[]`. Bare `[1]` with no matching
     citation entry is a fabricated reference.

  3. URL validation. Every URL mentioned in the answer must appear
     either (a) in `citations[n].url` for some cited n, or (b) in the
     allowlist of known-live URLs (UrlSeen table, passed in as a set).
     URLs in the answer but not in the allowlist are fabricated and
     fail the check.

  4. Cross-campus citation check. Every cited chunk's provenance
     metadata must have `campus == scope.campus` OR `campus == "all"`.
     Prevents the King-hours-for-Hamilton-question failure mode. Also
     the service-not-at-this-building check: if any evidence-bundle
     metadata flags the service as unavailable at scope.campus, we
     refuse with SERVICE_NOT_AT_BUILDING.

Ordering matters. Confidence is checked first because a low-confidence
answer is refused regardless of citation quality -- no point running
URL regexes against text the bot itself admitted it wasn't sure about.
Cross-campus is last because it's the most context-dependent and
produces the most specific refusal copy.

See plan:
  - Citation and refusal contract -> "Why force structured citations
    rather than asking the model nicely"
  - Data preparation playbook §8 -> cross-campus refusal guard

NOTE: This module is deliberately pure logic. It imports no LLM client,
no HTTP, no DB. It takes inputs, returns outputs, and is fully unit-
testable against fixtures. All I/O (UrlSeen lookup, chunk provenance
join) happens in the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from src.synthesis.refusal_templates import (
    RefusalContext,
    RefusalTrigger,
    render_refusal,
)


# --- Public shapes ---------------------------------------------------------

Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Citation:
    """One citation in the synthesizer's structured output.

    `n` is the citation number the model wrote (1-indexed). `chunk_id`
    is the id of the evidence-bundle row the model was pointing at (the
    synthesizer knows the chunk ids because retrieval returns them).
    The caller provides the `campus` and `library` fields by joining
    chunk_id -> ChunkProvenance before running validation.
    """

    n: int
    url: str
    snippet: str
    chunk_id: Optional[str] = None
    campus: Optional[str] = None
    library: Optional[str] = None


@dataclass(frozen=True)
class SynthesizerOutput:
    """Structured output from the synthesizer LLM call.

    Shape mirrors what OpenAI structured-outputs returns. The post-
    processor treats this as authoritative input; validation happens
    on its fields, not on the raw text.
    """

    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: Confidence = "medium"


@dataclass(frozen=True)
class ValidationFailure:
    """One failed check. Zero or more of these feed into the decision
    to downgrade. A list of failures is still logged even when the
    downgrade already fired on the first one -- useful for debugging
    prompt / retrieval regressions."""

    trigger: RefusalTrigger
    detail: str
    """Human-readable reason; goes to debug logs and the eval report,
    NEVER to the user (the refusal template handles user-facing copy)."""


@dataclass(frozen=True)
class Refusal:
    """A post-processor refusal decision. `message` is the templated
    user-facing text; `trigger` is the enum value that caused it; the
    full failure list is preserved for logging."""

    trigger: RefusalTrigger
    message: str
    failures: list[ValidationFailure] = field(default_factory=list)


@dataclass(frozen=True)
class PostProcessorResult:
    """What `process_synthesizer_output()` returns.

    Exactly one of `answer` / `refusal` is set. Caller renders on the
    one that's populated; UI never has to check both.
    """

    answer: Optional[SynthesizerOutput] = None
    refusal: Optional[Refusal] = None

    @property
    def is_refusal(self) -> bool:
        return self.refusal is not None


# --- Citation-reference pattern --------------------------------------------

_CITATION_REF_RE = re.compile(r"\[(\d+)\]")
"""Matches `[1]`, `[23]`, etc. Any [n] in answer text is a citation
reference and must resolve to a citations[] entry."""

_URL_RE = re.compile(
    r"https?://[^\s<>\"'\])}]+",
    re.IGNORECASE,
)
"""Matches bare URLs. Deliberately conservative: stops at whitespace,
angle-bracket, or closing punctuation so we don't greedy-match into
Markdown syntax. URLs in Markdown links `[text](url)` still match the
url portion."""


# --- The main entry point --------------------------------------------------

def process_synthesizer_output(
    output: SynthesizerOutput,
    *,
    scope_campus: str,
    url_allowlist: set[str],
    service_unavailable_trigger: Optional[RefusalContext] = None,
) -> PostProcessorResult:
    """Validate the synthesizer's structured output. Downgrade to a
    refusal if any check fails.

    Args:
        output: Parsed synthesizer result (answer, citations, confidence).
        scope_campus: The resolved Scope.campus for this turn. Used in
            the cross-campus check and, if a refusal fires, to render
            campus-appropriate refusal copy.
        url_allowlist: Set of canonical URLs that are considered live
            (loaded from Postgres UrlSeen table by the caller). URLs
            in the answer must be a member of this set OR appear in
            one of the citations. A model URL that is in neither is
            fabricated.
        service_unavailable_trigger: If the caller has already
            determined (before synthesis) that the requested service
            isn't offered at scope.campus, passing the RefusalContext
            here will short-circuit to a SERVICE_NOT_AT_BUILDING
            refusal. None otherwise.

    Returns:
        A PostProcessorResult. Exactly one of `answer` / `refusal`
        is set.
    """
    # Short-circuit: if the caller pre-determined the service isn't
    # offered here, skip synthesis-level checks and refuse directly.
    if service_unavailable_trigger is not None:
        return PostProcessorResult(
            refusal=Refusal(
                trigger=RefusalTrigger.SERVICE_NOT_AT_BUILDING,
                message=render_refusal(
                    RefusalTrigger.SERVICE_NOT_AT_BUILDING,
                    service_unavailable_trigger,
                ),
                failures=[
                    ValidationFailure(
                        trigger=RefusalTrigger.SERVICE_NOT_AT_BUILDING,
                        detail=(
                            f"Service '{service_unavailable_trigger.service_name}' "
                            f"is not offered at {scope_campus}."
                        ),
                    )
                ],
            )
        )

    failures: list[ValidationFailure] = []

    # --- 1. Confidence gate ---
    if output.confidence == "low":
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.MODEL_SELF_FLAGGED,
                detail="Synthesizer returned confidence=low.",
            )
        )
    if "REFUSAL" in output.answer:
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.MODEL_SELF_FLAGGED,
                detail="Synthesizer emitted the literal REFUSAL token.",
            )
        )

    # --- 2. Citation match ---
    referenced_ns = {int(m.group(1)) for m in _CITATION_REF_RE.finditer(output.answer)}
    available_ns = {c.n for c in output.citations}
    missing_ns = referenced_ns - available_ns
    if missing_ns:
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.CITATION_INVALID,
                detail=(
                    f"Answer references citation numbers "
                    f"{sorted(missing_ns)} that don't exist in citations[]."
                ),
            )
        )

    # --- 3. URL validation ---
    urls_in_answer = {m.group(0).rstrip(".,);:") for m in _URL_RE.finditer(output.answer)}
    cited_urls = {c.url for c in output.citations}
    for url in urls_in_answer:
        if url in cited_urls:
            continue
        if url in url_allowlist:
            continue
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.CITATION_INVALID,
                detail=f"URL {url!r} in answer is neither cited nor in the allowlist.",
            )
        )

    # --- 4. Cross-campus citation check ---
    # Only citations that actually have provenance metadata loaded are
    # checkable. If the caller forgot to join campus metadata on, we
    # log a failure rather than silently pass (the check is load-
    # bearing; "I didn't have the data" is not a safe default).
    for c in output.citations:
        if c.campus is None:
            failures.append(
                ValidationFailure(
                    trigger=RefusalTrigger.CROSS_CAMPUS_MISMATCH,
                    detail=(
                        f"Citation [{c.n}] has no campus metadata -- "
                        "post-processor cannot verify scope."
                    ),
                )
            )
            continue
        if c.campus == scope_campus or c.campus == "all":
            continue
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.CROSS_CAMPUS_MISMATCH,
                detail=(
                    f"Citation [{c.n}] is from campus={c.campus!r} but "
                    f"scope.campus={scope_campus!r}."
                ),
            )
        )

    # --- Decide ---
    if not failures:
        return PostProcessorResult(answer=output)

    # Pick the highest-priority trigger for the user-facing message.
    # Order follows the logical severity: model self-flag first (the
    # model itself said no), then citation invalid (we caught a
    # fabrication), then cross-campus (scope violation). Further
    # failures are logged but the user sees one refusal paragraph.
    priority_order = [
        RefusalTrigger.MODEL_SELF_FLAGGED,
        RefusalTrigger.CITATION_INVALID,
        RefusalTrigger.CROSS_CAMPUS_MISMATCH,
    ]
    primary = next(
        (t for t in priority_order if any(f.trigger == t for f in failures)),
        failures[0].trigger,
    )

    context = _refusal_context_for(primary, scope_campus)
    return PostProcessorResult(
        refusal=Refusal(
            trigger=primary,
            message=render_refusal(primary, context),
            failures=failures,
        )
    )


# --- Helpers ---------------------------------------------------------------


def _refusal_context_for(
    trigger: RefusalTrigger, scope_campus: str
) -> Optional[RefusalContext]:
    """Build the minimal RefusalContext a given trigger needs.

    Cross-campus is the only post-processor-detected trigger that
    requires context (campus display + staff directory URL). The
    caller is expected to have a campus-display map; post_processor
    keeps its own tiny copy rather than importing from scope.aliases
    so the module has zero intra-package dependencies beyond
    refusal_templates (which is stateless).
    """
    if trigger != RefusalTrigger.CROSS_CAMPUS_MISMATCH:
        return None

    # Kept tiny here; the full map lives in scope/aliases.py. If this
    # ever drifts, the dup is fine because both derive from the same
    # source-of-truth: the six buildings in the plan §8 table.
    display = {
        "oxford": "Oxford",
        "hamilton": "Hamilton",
        "middletown": "Middletown",
    }.get(scope_campus, scope_campus.title())
    staff_url = {
        "oxford": "https://www.lib.miamioh.edu/about/organization/liaisons/",
        "hamilton": "https://www.lib.miamioh.edu/about/organization/liaisons/",
        "middletown": "https://www.lib.miamioh.edu/about/organization/liaisons/",
    }.get(scope_campus, "https://www.lib.miamioh.edu/")
    return RefusalContext(
        campus_display=display,
        staff_directory_url=staff_url,
    )


__all__ = [
    "Citation",
    "PostProcessorResult",
    "Refusal",
    "SynthesizerOutput",
    "ValidationFailure",
    "process_synthesizer_output",
]
