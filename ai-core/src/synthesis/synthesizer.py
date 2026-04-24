"""
The synthesizer: turns a question + numbered evidence bundle into a
structured answer (or a refusal).

This is a SCAFFOLD. The actual OpenAI call is gated behind the model
freshness rule (must check live OpenAI docs at code-change time before
wiring the SDK call); see plan: "Model & API freshness rule". For now
this module:

  - Defines the Evidence -> Synthesizer prompt builder
  - Defines the call shape (`synthesize(question, evidence, scope)`)
  - Wires the corrections layer in front of synthesis
  - Wires the post-processor on the way out
  - Leaves the LLM call as a single replaceable function
    (`_call_synthesizer_llm`) that raises NotImplementedError until
    the LLM client wrapper exists in src/llm/client.py

The split exists so this module is unit-testable today against fixture
LLM outputs (just monkeypatch `_call_synthesizer_llm`), and so when
the live wiring lands it touches one function.

See plan:
  - Layer 4 -> "Grounded synthesis" (structured output JSON schema)
  - Citation and refusal contract -> data flow diagram
  - Operations Op 2 -> apply_corrections wired in here
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from src.synthesis.corrections import (
    CorrectionOutcome,
    EvidenceChunk,
    ManualCorrection,
    apply_corrections,
)
from src.synthesis.post_processor import (
    Citation,
    PostProcessorResult,
    SynthesizerOutput,
    process_synthesizer_output,
)
from src.synthesis.refusal_templates import RefusalContext


# --- Shapes ----------------------------------------------------------------


@dataclass(frozen=True)
class SynthesisRequest:
    """The full input to one synthesis call. All inputs are explicit
    so the call is pure -- no globals, no implicit DB reads."""

    question: str
    evidence: list[EvidenceChunk]
    scope_campus: str
    scope_library: Optional[str]
    corrections: list[ManualCorrection]
    url_allowlist: set[str]
    service_unavailable: Optional[RefusalContext] = None
    """If the orchestrator already determined (from LibrarySpace
    services_offered) that the requested service isn't at this
    building, pass the refusal context here -- post-processor short-
    circuits to SERVICE_NOT_AT_BUILDING without calling the LLM."""

    intent: Optional[str] = None
    """Optional intent label from the kNN classifier. Threaded through
    for telemetry; not currently used in prompt construction."""


@dataclass(frozen=True)
class SynthesisResult:
    """What the orchestrator gets back.

    `post_processor` carries the user-visible answer or refusal. The
    other fields are diagnostic -- logged per turn for the eval suite
    and the librarian-review surface.
    """

    post_processor: PostProcessorResult
    fired_corrections: list[int]
    model_used: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


# --- Prompt construction ---------------------------------------------------
#
# The stable prefix lives in src/prompts/synthesizer_v1.py and is
# composed via prompts/builder.py so it benefits from OpenAI prompt
# caching. The dynamic suffix is built here and is intentionally
# minimal: numbered evidence, the user question, and a one-line scope
# reminder.


def _format_evidence_block(evidence: list[EvidenceChunk]) -> str:
    """Render the evidence list in the numbered format the synthesizer
    prompt expects. Citation numbers are 1-indexed because that's what
    users read in the UI -- keep prompt and UI numbering aligned.
    """
    if not evidence:
        return "(no evidence)"

    lines: list[str] = []
    for i, chunk in enumerate(evidence, start=1):
        # Truncate snippet for the prompt; the full chunk text is in
        # the citation chip. 600 chars is roughly 150 tokens, plenty
        # for context, well under the per-chunk budget.
        snippet = chunk.text.strip().replace("\n", " ")
        if len(snippet) > 600:
            snippet = snippet[:597] + "..."
        meta = []
        if chunk.library:
            meta.append(f"library={chunk.library}")
        if chunk.campus:
            meta.append(f"campus={chunk.campus}")
        if chunk.topic:
            meta.append(f"topic={chunk.topic}")
        meta_str = f" [{', '.join(meta)}]" if meta else ""
        lines.append(
            f"[{i}]{meta_str} {chunk.source_url}\n    {snippet}"
        )
    return "\n\n".join(lines)


def _build_dynamic_suffix(
    question: str,
    evidence: list[EvidenceChunk],
    scope_campus: str,
    scope_library: Optional[str],
) -> str:
    """The non-cached portion of the synthesizer prompt: scope reminder,
    evidence block, and the user question. Order matters -- the
    question goes LAST so the model treats it as the most recent
    instruction."""
    scope_line = f"Scope: campus={scope_campus}"
    if scope_library:
        scope_line += f", library={scope_library}"

    return (
        f"{scope_line}\n\n"
        f"Sources:\n{_format_evidence_block(evidence)}\n\n"
        f"User question: {question}"
    )


# --- Citation parser -------------------------------------------------------
#
# OpenAI structured outputs returns the JSON-shaped output as a dict
# the SDK has already validated. This function adapts that dict into
# our SynthesizerOutput dataclass. Kept separate so a future schema
# bump (v2 fields) is a one-function change.


def parse_synthesizer_response(
    raw: dict,
    evidence: list[EvidenceChunk],
) -> SynthesizerOutput:
    """Turn the raw LLM JSON response into a SynthesizerOutput.

    Joins each citation's `n` back to the corresponding evidence chunk
    so post-processor cross-campus check has the campus/library
    metadata it needs. Citations whose `n` is out of range are kept
    with campus=None, which the post-processor flags as a failure --
    fail-loud rather than silently dropping.
    """
    citations: list[Citation] = []
    for c in raw.get("citations", []):
        n = int(c["n"])
        # Index back to the evidence chunk by position (1-indexed).
        chunk = evidence[n - 1] if 1 <= n <= len(evidence) else None
        citations.append(
            Citation(
                n=n,
                url=str(c.get("url", chunk.source_url if chunk else "")),
                snippet=str(c.get("snippet", "")),
                chunk_id=chunk.chunk_id if chunk else None,
                campus=chunk.campus if chunk else None,
                library=chunk.library if chunk else None,
            )
        )
    return SynthesizerOutput(
        answer=str(raw.get("answer", "")),
        citations=citations,
        confidence=raw.get("confidence", "medium"),
    )


# --- LLM call (replaceable seam) ------------------------------------------


class SynthesizerLLM(Protocol):
    """Minimal interface the synthesizer needs from an LLM client.

    Lets tests pass in a stub callable returning canned JSON, without
    the synthesizer module importing the real OpenAI client. Kept as
    a Protocol (structural) so neither side has to import the other.
    """

    def __call__(
        self,
        *,
        prefix_id: str,
        dynamic_suffix: str,
        model: str,
    ) -> tuple[dict, dict]:
        """Returns `(parsed_response_dict, usage_dict)`.

        `parsed_response_dict` is the JSON the model returned (matching
        the structured-output schema). `usage_dict` carries
        `{input_tokens, cached_input_tokens, output_tokens}`.
        """
        ...


def _default_llm_call(
    *,
    prefix_id: str,
    dynamic_suffix: str,
    model: str,
) -> tuple[dict, dict]:
    """Placeholder LLM call. Replaced when src/llm/client.py lands.

    Raises NotImplementedError deliberately so an accidentally-live
    synthesizer call surfaces immediately during development rather
    than silently shipping a stub answer. Tests pass a stub via the
    `llm` argument to `synthesize()` and never hit this.
    """
    raise NotImplementedError(
        "Synthesizer LLM client not yet wired. Wire src/llm/client.py "
        "(see plan: Model & API freshness rule -- check OpenAI docs "
        "before writing the call shape) and pass it as the `llm` "
        "argument to synthesize(), or monkeypatch _default_llm_call "
        "for tests."
    )


# --- Top-level orchestration ----------------------------------------------


def synthesize(
    request: SynthesisRequest,
    *,
    llm: Optional[SynthesizerLLM] = None,
    prefix_id: str = "synthesizer_v1",
    model: str = "gpt-5.4-mini",
) -> SynthesisResult:
    """Run synthesis end to end: corrections -> LLM -> post-processor.

    Args:
        request: Full input bundle.
        llm: Callable matching the SynthesizerLLM protocol. If None,
            uses _default_llm_call which raises NotImplementedError.
        prefix_id: Which stable prefix in src/prompts/ to use. Versioned
            so prompt revisions don't collide on the cache.
        model: OpenAI model id. Default `gpt-5.4-mini` per plan;
            orchestrator promotes to `gpt-5.2` when the
            multi-hop / comparative escalation conditions hit.

    Returns:
        SynthesisResult with post_processor decision and telemetry.
    """
    # Service-unavailable short-circuit. We do this BEFORE corrections
    # because if MakerSpace doesn't exist at Middletown, we don't want
    # to even consider replacement chunks for it -- the answer is
    # categorically "we don't have that here".
    if request.service_unavailable is not None:
        pp = process_synthesizer_output(
            SynthesizerOutput(answer="", citations=[], confidence="low"),
            scope_campus=request.scope_campus,
            url_allowlist=request.url_allowlist,
            service_unavailable_trigger=request.service_unavailable,
        )
        return SynthesisResult(
            post_processor=pp,
            fired_corrections=[],
            model_used="(none -- service-unavailable refusal)",
        )

    # 1. Apply librarian corrections to the evidence bundle.
    correction_outcome: CorrectionOutcome = apply_corrections(
        request.evidence, request.corrections, request.question
    )

    # 2. Build prompt (stable prefix loaded by builder; here we only
    #    construct the dynamic suffix).
    dynamic_suffix = _build_dynamic_suffix(
        request.question,
        correction_outcome.chunks,
        request.scope_campus,
        request.scope_library,
    )

    # 3. Call the LLM.
    call = llm if llm is not None else _default_llm_call
    raw_response, usage = call(
        prefix_id=prefix_id,
        dynamic_suffix=dynamic_suffix,
        model=model,
    )

    # 4. Parse and validate.
    parsed = parse_synthesizer_response(raw_response, correction_outcome.chunks)
    pp_result = process_synthesizer_output(
        parsed,
        scope_campus=request.scope_campus,
        url_allowlist=request.url_allowlist,
    )

    return SynthesisResult(
        post_processor=pp_result,
        fired_corrections=correction_outcome.fired,
        model_used=model,
        input_tokens=int(usage.get("input_tokens", 0)),
        cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )


__all__ = [
    "SynthesisRequest",
    "SynthesisResult",
    "SynthesizerLLM",
    "parse_synthesizer_response",
    "synthesize",
]
