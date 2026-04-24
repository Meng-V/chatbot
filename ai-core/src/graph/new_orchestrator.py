"""
The rebuilt orchestrator: `classify -> run_agent -> synthesize`.

Replaces the LangGraph-shaped orchestrator in `orchestrator.py` with
a straight-line pipeline. The old orchestrator stays wired to today's
traffic; this one runs behind the v2 feature flag during the 8-week
rollout, then takes over.

One turn, five steps:

    1. resolve_scope(user_message, session_origin)   -> Scope
    2. classify(user_message)                        -> Classification
    3. check_service_availability(intent, scope)     -> optional refusal short-circuit
    4. run_agent(request, tool_registry)             -> evidence + tool trail
    5. synthesize(request)                           -> answer | refusal

The orchestrator owns:
  - Binding request-context fields into the observability logger
  - Composing the SynthesisRequest from agent outputs
  - Promoting the LLM to gpt-5.2 when escalation conditions hit
  - Logging per-turn telemetry (intent, scope, model, tokens, latency,
    fired corrections, refusal trigger) into the existing
    conversation store

The orchestrator does NOT own:
  - How tools work (tool_registry)
  - What the system prompts look like (src/prompts/)
  - How citations are validated (synthesis/post_processor)

Those are separate modules with their own tests. The orchestrator is
the integration point; each step is already unit-testable in isolation.

See plan:
  - Architecture -> "Layer overview"
  - Critical files -> ai-core/src/graph/orchestrator.py
  - Layer 4 -> "Model routing" (when to escalate to gpt-5.2)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.agent.agent import AgentLLM, AgentOutcome, AgentRequest, run_agent
from src.agent.tool_registry import ToolRegistry
from src.observability.logging import bind_request_context, get_logger
from src.observability.metrics import (
    record_llm_call,
    record_refusal,
    record_request,
)
from src.router.intent_knn import Classification, IntentKNN, MARGIN_HIGH, MARGIN_LOW
from src.scope.resolver import Scope, resolve_scope, resolve_session_origin
from src.synthesis.corrections import EvidenceChunk, ManualCorrection
from src.synthesis.post_processor import PostProcessorResult
from src.synthesis.refusal_templates import RefusalContext, RefusalTrigger
from src.synthesis.synthesizer import (
    SynthesisRequest,
    SynthesisResult,
    SynthesizerLLM,
    synthesize,
)


log = get_logger("orchestrator")


# --- Turn I/O shapes ------------------------------------------------------


@dataclass(frozen=True)
class TurnRequest:
    """One incoming user turn. Socket.IO / HTTP layer builds this from
    the wire payload and hands it to `run_turn`."""

    user_message: str
    conversation_id: str
    """Existing conversation key so we can load history + log results."""

    session_origin_url: Optional[str] = None
    """The referrer/origin from the chat widget. Oxford default unless
    this points at ham.miamioh.edu or mid.miamioh.edu."""

    conversation_history: list[dict] = field(default_factory=list)
    """Prior messages, OpenAI message format."""


@dataclass(frozen=True)
class TurnResponse:
    """One outgoing turn. UI renders on this shape; the existing React
    components care about answer + citations + is_refusal."""

    answer: str
    is_refusal: bool
    refusal_trigger: Optional[str]
    citations: list[dict]
    """UI-ready list: `[{"n": 1, "url": "...", "snippet": "..."}, ...]`."""

    confidence: str
    intent: str
    scope: dict
    model_used: str
    tokens: dict
    """`{input, cached_input, output}` per turn for logging into
    ModelTokenUsage."""

    fired_corrections: list[int]
    agent_stopped_reason: str
    latency_ms: int
    cited_chunk_ids: list[str]
    """For the Message.cited_chunk_ids column so librarian review can
    join back to ChunkProvenance."""


# --- Dependency bundle ---------------------------------------------------


@dataclass
class OrchestratorDeps:
    """Everything the orchestrator needs injected. Tests pass stubs;
    prod passes real implementations built at FastAPI startup.

    Kept as a single dataclass (not per-call kwargs) so the wiring
    happens in one place at app boot.
    """

    classifier: IntentKNN
    tool_registry: ToolRegistry
    agent_llm: AgentLLM
    synthesizer_llm: SynthesizerLLM
    load_corrections: Callable[[], list[ManualCorrection]]
    """Returns active ManualCorrection rows. Caller filters by
    active=true AND expires_at > now(); orchestrator treats the list
    as-is."""

    load_url_allowlist: Callable[[], set[str]]
    """Returns the current set of live URLs (from UrlSeen where
    is_active=true AND is_blacklisted=false). Cached at the call site
    with a short TTL -- reading every turn is wasteful."""

    lookup_service_availability: Callable[
        [str, str], Optional[RefusalContext]
    ]
    """`(intent, scope_campus) -> Optional[RefusalContext]`. Returns
    the refusal context if the service isn't offered at this campus
    (pre-synthesis short-circuit), else None.

    Queries LibrarySpace.services_offered. See plan §8.
    """

    log_turn: Callable[[dict], None] = lambda _payload: None
    """Persists the per-turn log row into the conversation store.
    Default no-op so tests don't need a DB; prod passes the real
    persistence function."""


# --- The main entry point ------------------------------------------------


def run_turn(
    request: TurnRequest,
    deps: OrchestratorDeps,
    *,
    model_basic: str = "gpt-5.4-mini",
    model_reasoning: str = "gpt-5.2",
) -> TurnResponse:
    """Run one turn end to end.

    Returns a TurnResponse either way -- refusals and answers both use
    the same shape, so the UI doesn't have to branch. `is_refusal`
    tells the UI whether to render the handoff button.
    """
    turn_start = time.monotonic()

    # --- 1. Resolve scope ---
    origin_campus = resolve_session_origin(request.session_origin_url)
    scope: Scope = resolve_scope(request.user_message, origin_campus)

    bind_request_context(
        conversation_id=request.conversation_id,
        scope_campus=scope.campus,
        scope_library=scope.library or "",
        scope_source=scope.source,
    )

    # --- 2. Classify intent ---
    classification: Classification = deps.classifier.classify(request.user_message)
    bind_request_context(intent=classification.intent, margin=classification.margin)

    # Clarification short-circuit: if the kNN is too uncertain, hand
    # back a structured "please pick one" response before burning
    # agent + synthesizer budget. The UI has an existing
    # ClarificationChoices component that renders `clarify_options`.
    if classification.needs_clarification:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="clarify", latency_s=latency_ms / 1000)
        return _clarify_response(classification, scope, latency_ms)

    # --- 3. Service-availability pre-check ---
    # If the user asked about MakerSpace at Middletown (say), skip
    # agent + synthesizer entirely. LibrarySpace.services_offered is
    # the truth table. Plan §8 load-bearing guard.
    service_refusal: Optional[RefusalContext] = deps.lookup_service_availability(
        classification.intent, scope.campus
    )

    # --- 4. Run the agent ---
    # Model selection: basic by default, reasoning on comparative /
    # cross-campus / multi-hop intents. Plan: "Synthesizer defaults to
    # gpt-5.4-mini. Promote to gpt-5.2 when: (a) retrieval returned
    # >5 chunks across multiple topic tags (multi-hop), (b) classifier
    # confidence was in the clarification band, (c) comparative /
    # multi-step phrasing." We evaluate (c) here; (a) and (b) are
    # evaluated after agent run.
    model = (
        model_reasoning
        if _is_reasoning_intent(classification.intent)
        else model_basic
    )

    agent_req = AgentRequest(
        user_message=request.user_message,
        intent=classification.intent,
        scope_campus=scope.campus,
        scope_library=scope.library,
        conversation_history=request.conversation_history,
    )
    agent_start = time.monotonic()
    agent_outcome: AgentOutcome = run_agent(
        agent_req,
        deps.tool_registry,
        llm=deps.agent_llm,
        model=model,
    )
    agent_latency_s = time.monotonic() - agent_start
    record_llm_call(
        model=model,
        call_site="agent",
        status="ok" if agent_outcome.stopped_reason == "clean" else "degraded",
        latency_s=agent_latency_s,
        input_tokens=agent_outcome.input_tokens,
        cached_input_tokens=agent_outcome.cached_input_tokens,
        output_tokens=agent_outcome.output_tokens,
    )

    # --- 5. Assemble evidence and run synthesizer ---
    evidence = _extract_evidence(agent_outcome)

    # Promote to reasoning model when evidence is multi-hop: >5 chunks
    # across multiple topics.
    if len(evidence) > 5 and len({c.topic for c in evidence if c.topic}) > 1:
        model = model_reasoning

    synthesis_req = SynthesisRequest(
        question=request.user_message,
        evidence=evidence,
        scope_campus=scope.campus,
        scope_library=scope.library,
        corrections=deps.load_corrections(),
        url_allowlist=deps.load_url_allowlist(),
        service_unavailable=service_refusal,
        intent=classification.intent,
    )
    synth_start = time.monotonic()
    synth_result: SynthesisResult = synthesize(
        synthesis_req,
        llm=deps.synthesizer_llm,
        model=model,
    )
    synth_latency_s = time.monotonic() - synth_start
    record_llm_call(
        model=synth_result.model_used,
        call_site="synthesizer",
        status="refusal" if synth_result.post_processor.is_refusal else "ok",
        latency_s=synth_latency_s,
        input_tokens=synth_result.input_tokens,
        cached_input_tokens=synth_result.cached_input_tokens,
        output_tokens=synth_result.output_tokens,
    )

    # --- 6. Shape response + log ---
    total_latency_ms = int((time.monotonic() - turn_start) * 1000)
    response = _shape_response(
        synth_result=synth_result,
        classification=classification,
        scope=scope,
        agent_outcome=agent_outcome,
        total_latency_ms=total_latency_ms,
    )

    if response.is_refusal and response.refusal_trigger:
        record_refusal(trigger=response.refusal_trigger)
    record_request(
        endpoint="/chat",
        status="refusal" if response.is_refusal else "ok",
        latency_s=total_latency_ms / 1000,
    )

    deps.log_turn(
        {
            "conversation_id": request.conversation_id,
            "intent": classification.intent,
            "scope": scope.as_filter(),
            "model_used": response.model_used,
            "tokens": response.tokens,
            "confidence": response.confidence,
            "was_refusal": response.is_refusal,
            "refusal_trigger": response.refusal_trigger,
            "cited_chunk_ids": response.cited_chunk_ids,
            "fired_corrections": response.fired_corrections,
            "agent_stopped_reason": response.agent_stopped_reason,
            "latency_ms": response.latency_ms,
        }
    )

    return response


# --- Helpers -------------------------------------------------------------


_REASONING_INTENTS = frozenset(
    {"cross_campus_comparison", "policy_question"}
)
"""Intents that get `gpt-5.2` by default. Comparative / policy questions
benefit from the reasoning tier; quick lookups don't."""


def _is_reasoning_intent(intent: str) -> bool:
    return intent in _REASONING_INTENTS


def _extract_evidence(agent_outcome: AgentOutcome) -> list[EvidenceChunk]:
    """Walk the agent's tool-call trail and collect evidence chunks.

    Each `search_kb` tool result is expected to return
    `{"chunks": [...]}` where each chunk is a dict that maps onto
    EvidenceChunk fields. Other tool results (hours, room availability)
    aren't retrieval evidence and don't feed the synthesizer's
    citation bundle -- they go into the conversation as tool messages
    and the LLM can quote them from context.
    """
    evidence: list[EvidenceChunk] = []
    for turn in agent_outcome.turns:
        for result in turn.tool_results:
            if result.is_error or result.name != "search_kb":
                continue
            raw_chunks = (result.data or {}).get("chunks", [])
            for raw in raw_chunks:
                evidence.append(
                    EvidenceChunk(
                        chunk_id=str(raw.get("chunk_id", "")),
                        source_url=str(raw.get("source_url", raw.get("url", ""))),
                        text=str(raw.get("text", "")),
                        campus=raw.get("campus"),
                        library=raw.get("library"),
                        topic=raw.get("topic"),
                        featured_service=raw.get("featured_service"),
                        score=float(raw.get("score", 0.0)),
                    )
                )
    return evidence


def _shape_response(
    *,
    synth_result: SynthesisResult,
    classification: Classification,
    scope: Scope,
    agent_outcome: AgentOutcome,
    total_latency_ms: int,
) -> TurnResponse:
    """Turn the synthesis result + agent outcome into the wire shape."""
    pp: PostProcessorResult = synth_result.post_processor
    if pp.is_refusal and pp.refusal:
        return TurnResponse(
            answer=pp.refusal.message,
            is_refusal=True,
            refusal_trigger=pp.refusal.trigger.value,
            citations=[],
            confidence="low",
            intent=classification.intent,
            scope=scope.as_filter(),
            model_used=synth_result.model_used,
            tokens={
                "input": synth_result.input_tokens
                + agent_outcome.input_tokens,
                "cached_input": synth_result.cached_input_tokens
                + agent_outcome.cached_input_tokens,
                "output": synth_result.output_tokens
                + agent_outcome.output_tokens,
            },
            fired_corrections=synth_result.fired_corrections,
            agent_stopped_reason=agent_outcome.stopped_reason,
            latency_ms=total_latency_ms,
            cited_chunk_ids=[],
        )

    assert pp.answer is not None  # implied by `not is_refusal`
    citations_wire = [
        {"n": c.n, "url": c.url, "snippet": c.snippet}
        for c in pp.answer.citations
    ]
    cited_chunk_ids = [
        c.chunk_id for c in pp.answer.citations if c.chunk_id is not None
    ]
    return TurnResponse(
        answer=pp.answer.answer,
        is_refusal=False,
        refusal_trigger=None,
        citations=citations_wire,
        confidence=pp.answer.confidence,
        intent=classification.intent,
        scope=scope.as_filter(),
        model_used=synth_result.model_used,
        tokens={
            "input": synth_result.input_tokens + agent_outcome.input_tokens,
            "cached_input": synth_result.cached_input_tokens
            + agent_outcome.cached_input_tokens,
            "output": synth_result.output_tokens + agent_outcome.output_tokens,
        },
        fired_corrections=synth_result.fired_corrections,
        agent_stopped_reason=agent_outcome.stopped_reason,
        latency_ms=total_latency_ms,
        cited_chunk_ids=cited_chunk_ids,
    )


def _clarify_response(
    classification: Classification,
    scope: Scope,
    latency_ms: int,
) -> TurnResponse:
    """Structured 'pick one' response for low-margin classifications.

    The UI's existing ClarificationChoices component renders the top-2
    candidate intents as buttons; clicking one re-runs the turn with
    that intent forced.
    """
    top_two = [
        {"intent": intent, "score": score}
        for intent, score in classification.candidates[:2]
    ]
    return TurnResponse(
        answer=(
            "I'm not sure which of these you meant. Can you pick one?"
            + "\n\nOptions: "
            + ", ".join(
                opt["intent"].replace("_", " ") for opt in top_two
            )
        ),
        is_refusal=False,
        refusal_trigger=None,
        citations=[],
        confidence="low",
        intent=classification.intent,
        scope=scope.as_filter(),
        model_used="(none -- kNN only)",
        tokens={"input": 0, "cached_input": 0, "output": 0},
        fired_corrections=[],
        agent_stopped_reason="clarify",
        latency_ms=latency_ms,
        cited_chunk_ids=[],
    )


__all__ = [
    "OrchestratorDeps",
    "TurnRequest",
    "TurnResponse",
    "run_turn",
]
