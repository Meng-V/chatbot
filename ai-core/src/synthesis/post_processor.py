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

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
"""Matches email addresses. Used for the trusted-evidence faithfulness
check: every email the model writes MUST appear verbatim in some
evidence item. Catches the directory-paraphrase bug
(bennethm@miamioh.edu -> bennett@miamioh.edu) and invented contacts.
Never false-positives on hours / "Closed" -- those aren't emails."""


# --- The main entry point --------------------------------------------------

def process_synthesizer_output(
    output: SynthesizerOutput,
    *,
    scope_campus: str,
    url_allowlist: set[str],
    service_unavailable_trigger: Optional[RefusalContext] = None,
    evidence: Optional[list] = None,
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

    # --- 0. Domain-typo normalizer (Miami University email domain) ---
    # The synth occasionally writes typo'd variants of the Miami domain
    # ("miamiohio.edu" instead of "miamioh.edu", "muohio.edu" — the old
    # pre-2013 domain — etc). Caught in R8 retest: bot told a student to
    # activate NYT with "your miamiohio.edu email". None of these typo
    # forms are valid; rewrite to the canonical "miamioh.edu" rather
    # than refuse — the answer is otherwise correct and a refusal here
    # would be worse for the user than a quiet correction.
    #
    # Cheap, deterministic, and structurally cannot break a legitimate
    # answer: no real string we'd want to keep contains "miamiohio.edu"
    # or "muohio.edu" (the old domain has been gone since 2013).
    _NORMALIZE_DOMAINS = {
        "miamiohio.edu": "miamioh.edu",
        "miamiohio.org": "miamioh.edu",
        "muohio.edu": "miamioh.edu",
    }
    import re as _re
    from dataclasses import replace as _dc_replace
    for typo, canonical in _NORMALIZE_DOMAINS.items():
        if typo in output.answer.lower():
            output = _dc_replace(
                output,
                answer=_re.sub(
                    _re.escape(typo),
                    canonical,
                    output.answer,
                    flags=_re.IGNORECASE,
                ),
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

    # --- 2b. Citation must be backed by retrieved evidence ---
    # A cited URL MUST be the source_url of a chunk the agent actually
    # retrieved. Without this, the synthesizer LLM can fabricate a citation
    # straight from its prompt's hard-coded reference-URL list even when
    # retrieval returned nothing -- the exact "made-up URL" failure the
    # citation contract exists to prevent (2026-06-08 Adobe-404 incident:
    # bot served `/use/technology/software/adobe/` with [1] while evidence
    # was empty). Empty evidence => every cited URL is unbacked => refuse,
    # which is the correct outcome for a no-sources turn. Normalize trailing
    # slash + case so a cosmetic mismatch isn't a spurious refusal.
    #
    # Only enforced when the caller passes `evidence` (None = legacy / unit
    # callers that don't supply it; an explicit [] = a real turn with zero
    # evidence, which SHOULD fail any citation). The production synthesizer
    # always passes the post-corrections bundle.
    if evidence is not None:
        def _norm_url(u: str) -> str:
            return (u or "").strip().rstrip("/").lower()

        evidence_urls = {
            _norm_url(getattr(c, "source_url", "")) for c in evidence
        }
        evidence_urls.discard("")
        for c in output.citations:
            if not c.url:
                continue
            if _norm_url(c.url) not in evidence_urls:
                failures.append(
                    ValidationFailure(
                        trigger=RefusalTrigger.CITATION_INVALID,
                        detail=(
                            f"Citation [{c.n}] URL {c.url!r} is not the "
                            f"source_url of any retrieved evidence chunk "
                            f"-- fabricated or pulled from the prompt's "
                            f"reference list rather than a real source."
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

    # --- 3b. Trusted-evidence email faithfulness ---
    # Every email the model emits MUST appear verbatim in some evidence
    # item. The whole point of wiring lookup_librarian was to surface
    # the EXACT directory address; a paraphrased/typo'd email
    # (bennethm@ -> bennett@) or an invented one is a fabrication. This
    # is deterministic, cheap, and structurally cannot false-positive
    # on hours / "Closed" / room text (none contain an "@"). Skipped
    # when the caller didn't pass evidence (older callers / unit tests).
    if evidence:
        evidence_blob = " ".join(getattr(c, "text", "") or "" for c in evidence)
        for em in {m.group(0) for m in _EMAIL_RE.finditer(output.answer)}:
            if em not in evidence_blob:
                failures.append(
                    ValidationFailure(
                        trigger=RefusalTrigger.CITATION_INVALID,
                        detail=(
                            f"Email {em!r} in answer is not present "
                            f"verbatim in any evidence item "
                            f"(fabricated or paraphrased contact)."
                        ),
                    )
                )

    # --- 3c. Staff-privacy roster guard ---
    # Operator rule (2026-05-16): the bot must NEVER proactively expose
    # staff contact lists. The demonstrated violation
    # (hh_chat_with_librarian) dumped 5 librarians' names for a generic
    # "can I chat with a librarian?". Deterministic, ~zero false
    # positive: a legitimate single-person lookup ("the history
    # librarian" -> Jenny Presnell) has exactly ONE individual email;
    # >=2 distinct INDIVIDUAL emails in one answer is a roster dump.
    #
    # IMPORTANT (2026-05-23): department inbox emails (archives@,
    # speccoll@, refdesk@, library@, ill@, etc.) are NOT individual
    # staff. They are public group inboxes documented on the website.
    # Treat them as zero-count for the roster check so questions like
    # "what's the archivist's email" can return both archives@ AND
    # speccoll@ without falsely tripping the privacy guard.
    #
    # Explicit allowlist rather than a regex because individual emails
    # like "bennethm@miamioh.edu" (lastname+initial) would otherwise
    # match a permissive regex. Department inboxes are a small, known
    # set documented on the library website.
    _DEPT_INBOX_LOCALPARTS = frozenset({
        "archives", "speccoll", "specialcollections", "library",
        "libraries", "refdesk", "reference", "circulation", "circ",
        "ill", "interlibraryloan", "reserves", "askus", "ask",
        "info", "contact", "feedback", "webmaster",
        "music", "wertz", "arts", "art", "king", "best",
        "rentschler", "gardnerharvey", "hamilton", "middletown",
        "makerspace", "digital", "digitalcollections",
    })
    distinct_emails = {m.group(0).lower() for m in _EMAIL_RE.finditer(output.answer)}
    individual_emails = {
        e for e in distinct_emails
        if e.split("@", 1)[0] not in _DEPT_INBOX_LOCALPARTS
    }
    if len(individual_emails) >= 2:
        failures.append(
            ValidationFailure(
                trigger=RefusalTrigger.STAFF_PRIVACY,
                detail=(
                    f"Answer exposes {len(individual_emails)} "
                    f"individual staff contacts "
                    f"({sorted(individual_emails)}) -- a roster "
                    f"dump. Bot must not volunteer staff lists; only "
                    f"a single specifically-requested person. "
                    f"(Total distinct emails: {len(distinct_emails)} "
                    f"of which {len(distinct_emails)-len(individual_emails)} "
                    f"are department inboxes, allowed.)"
                ),
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
        # Privacy first: a roster dump must surface as the privacy
        # refusal even if other failures co-occur (PII is the most
        # trust-damaging thing the bot can emit).
        RefusalTrigger.STAFF_PRIVACY,
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
