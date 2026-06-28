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

import re
import time
from dataclasses import dataclass, field, replace as _dc_replace
from typing import Any, Callable, Optional

from src.agent.agent import AgentLLM, AgentOutcome, AgentRequest, run_agent
from src.agent.tool_registry import ToolRegistry
from src.observability.logging import bind_request_context, get_logger
from src.observability.metrics import (
    record_llm_call,
    record_refusal,
    record_request,
)
from src.router.intent_capabilities import (
    CapabilityTier,
    IntentCapability,
    get_intent_capability,
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
    # Anaphoric follow-ups ("what about tomorrow?") carry no standalone library
    # signal; prepend the prior user question to the CLASSIFIER input only so
    # the intent is right. The agent still gets the real message + history and
    # resolves the reference. See _is_bare_followup.
    classify_input = request.user_message
    if _is_bare_followup(request.user_message):
        _prev_q = _last_user_question(request.conversation_history)
        if _prev_q:
            classify_input = f"{_prev_q} {request.user_message}"
    classification: Classification = deps.classifier.classify(classify_input)
    bind_request_context(intent=classification.intent, margin=classification.margin)

    # --- 2.0. Booking-flow continuation override ---
    # A mid-flow booking message ("my name is Meng Qu, email qum@...",
    # "confirm") carries no library vocabulary, so the stateless kNN
    # classifies it as out_of_scope / clarify and the flow dies (live
    # repro 2026-06-10: turn 2 of a booking got clarification chips,
    # turn 3's "confirm" got the OOS refusal). If the PREVIOUS assistant
    # message is one of OUR booking-flow texts (delivered verbatim by
    # the transactional short-circuit below, so the markers are
    # byte-stable), this turn belongs to the booking conversation:
    # force intent=room_booking, skip clarify and the
    # limitation/capability gates, and let the agent -- which sees the
    # full history -- call book_room with the accumulated slots.
    booking_flow = _booking_flow_active(request.conversation_history)
    if booking_flow:
        classification = _dc_replace(
            classification, intent="room_booking", needs_clarification=False
        )
        bind_request_context(intent="room_booking", margin=classification.margin)

    # --- 2.05. Greeting short-circuit ---
    # A bare "hi"/"hello" has no library signal, so the kNN sends it to
    # out_of_scope and the user gets a refusal for saying hello. Greet
    # back deterministically instead. Skipped mid-booking-flow so a
    # slot-fill that happens to look like a greeting still reaches the
    # agent.
    _greet_text = None if booking_flow else _greeting_answer(request.user_message)
    if _greet_text:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="greeting",
                       latency_s=latency_ms / 1000)
        return TurnResponse(
            answer=_greet_text, is_refusal=False, refusal_trigger=None,
            citations=[], confidence="high", intent="greeting",
            scope=scope.as_filter(), model_used=model_basic,
            tokens={"input": 0, "cached_input": 0, "output": 0},
            fired_corrections=[], agent_stopped_reason="greeting_short_circuit",
            latency_ms=latency_ms, cited_chunk_ids=[],
        )

    # --- 2.06. Facilities/conduct policy short-circuit ---
    # Food/drink/alcohol/sleeping/noise/pets/smoking/bikes/... policies live
    # in the operator's Facilities & Events Policies Google Doc, not the
    # indexed site. Placed EARLY (before clarify / OOS-refuse) because these
    # questions often classify as out_of_scope or low-margin clarify -- a
    # deterministic message match must win so they reach the doc, not a
    # refusal. Skipped mid-booking-flow.
    if not booking_flow:
        _fac = _facilities_policy_answer(request.user_message)
        if _fac is not None:
            _ans, _cites = _fac
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="facilities_policy",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="facilities_policy_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.07. Closed-library short-circuit ---
    # B.E.S.T. and Amos Music Library have permanently closed. Answer the
    # closure deterministically (these otherwise confuse/refuse). Early,
    # before clarify/OOS, same as the facilities pointer.
    if not booking_flow:
        _closed = _closed_library_answer(request.user_message)
        if _closed is not None:
            _ans, _cites = _closed
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="closed_library",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="closed_library_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.08. MakerSpace staff/contact short-circuit ---
    # "who is the makerspace librarian" / "I need help with the makerspace"
    # had no authoritative staff chunk in Weaviate, so the bot either refused
    # or fabricated a wrong contact (a random subject liaison -- prod
    # 2026-06-25). Answer deterministically from the MakerSpace staff page.
    if not booking_flow:
        _ms = _makerspace_staff_answer(request.user_message)
        if _ms is not None:
            _ans, _cites = _ms
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="makerspace_staff",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="makerspace_staff_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.09. Scholarly-communication / open-access contact short-circuit ---
    # No scholarly-comm chunk in the index, so the bot named the wrong liaison
    # (the Business librarian) for open access -- same fabrication as MakerSpace
    # (contacts probe 2026-06-25). Answer with the real coordinator.
    if not booking_flow:
        _sc = _scholarly_comm_answer(request.user_message)
        if _sc is not None:
            _ans, _cites = _sc
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="scholarly_comm",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="scholarly_comm_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.10. MakerSpace 3D-printing / usage short-circuit ---
    # "3d printing in King" misroutes to printing_wifi (the "printing" token),
    # where the agent loops and refuses/answers weakly. Answer the Oxford/King
    # case deterministically; cross-campus + regional buildings fall through.
    if not booking_flow:
        _ms3d = _makerspace_3d_answer(request.user_message, scope)
        if _ms3d is not None:
            _ans, _cites = _ms3d
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="makerspace_3d",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="makerspace_3d_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.11. Cancel-reservation short-circuit ---
    # Cancel was never wired into v2 (no cancel tool), so "cancel my booking
    # <code>" used to loop/error. Handle it deterministically + gracefully.
    # Skipped mid-booking-flow (there, "cancel" means abort the new booking).
    if not booking_flow:
        _cx = _cancel_reservation_answer(request.user_message)
        if _cx is not None:
            _ans, _cites = _cx
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="cancel_reservation",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model_basic,
                tokens={"input": 0, "cached_input": 0, "output": 0},
                fired_corrections=[],
                agent_stopped_reason="cancel_reservation_short_circuit",
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    # --- 2.1. Long-period hours short-circuit (operator rule B) ---
    # LibCal's API only covers a limited date window, so a "summer
    # hours / winter break / this semester" question can't be answered
    # from it. ALWAYS point the user to the campus hours PAGE instead.
    # Placed BEFORE the clarify short-circuit so a low-margin
    # long-period hours question (e.g. "Is Rentschler open during
    # winter break?") points to the page rather than asking the user
    # to disambiguate. Deterministic -> reliable, unlike a prompt rule.
    if classification.intent == "hours" and _is_long_period_hours(
        request.user_message
    ):
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="point_to_url",
                       latency_s=latency_ms / 1000)
        return _long_period_hours_response(classification, scope, latency_ms)

    # Clarification short-circuit: if the kNN is too uncertain, hand
    # back a structured "please pick one" response before burning
    # agent + synthesizer budget. The UI has an existing
    # ClarificationChoices component that renders `clarify_options`.
    if classification.needs_clarification:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="clarify", latency_s=latency_ms / 1000)
        return _clarify_response(classification, scope, latency_ms)

    # --- 2.4. Per-PATTERN limitation pre-check (capability_scope) ---
    # Some user messages match an ACTION the bot cannot perform
    # regardless of the kNN-routed intent — "renew my book", "submit
    # an ILL request for me", "pay my fine". The bot must explicitly
    # say "I can't do that" with a redirect URL. Without this short-
    # circuit, the agent answers helpfully ("here's how to renew") but
    # omits the refusal preamble, which the eval (and a real user
    # whose item is overdue) reads as the bot saying it WILL do it.
    # See `src/config/capability_scope.py` LIMITATIONS table.
    #
    # Wired 2026-05-23 after eval failure analysis showed cap_renew_book
    # and fs_ill_no_submit failing on this exact missing-preamble issue
    # (PR-TBD). Placed BEFORE the intent-capability check so a regex
    # match always wins — the LIMITATIONS table is the operator's
    # explicit "do not roleplay this action" list.
    from src.config.capability_scope import (
        detect_limitation_request,
        get_limitation_response,
    )
    # Mid-booking-flow messages skip the limitation regexes: a slot-fill
    # like "yes please book it" must reach the agent, not a template.
    limitation = (
        {} if booking_flow
        else detect_limitation_request(request.user_message)
    )
    if limitation.get("is_limitation"):
        ltype = limitation["limitation_type"]
        response_text = get_limitation_response(ltype)
        # Pull the redirect URL out of the response text so we render
        # a citation chip (UI relies on `citations[0].url`).
        import re as _re
        url_match = _re.search(r"(https?://[^\s)\"]+)", response_text)
        cite_url = url_match.group(1) if url_match else ""
        citations = [{"n": 1, "url": cite_url, "snippet": ""}] if cite_url else []
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="refusal",
                       latency_s=latency_ms / 1000)
        record_refusal(trigger=f"capability_limitation:{ltype}")
        return TurnResponse(
            answer=response_text,
            is_refusal=True,
            refusal_trigger=f"capability_limitation:{ltype}",
            citations=citations,
            confidence="high",
            intent=classification.intent,
            scope=scope.as_filter(),
            model_used="(none — capability_scope limitation)",
            tokens={"input": 0, "cached_input": 0, "output": 0},
            fired_corrections=[],
            agent_stopped_reason="capability_limitation",
            latency_ms=latency_ms,
            cited_chunk_ids=[],
        )

    # --- 2.5. Per-intent capability check ---
    # Some intents (account, events_news, find_resource, databases) are
    # deliberately not LLM-answerable: the answer is an authoritative
    # URL or a privacy refusal. Skip agent + synth entirely and return
    # the templated response. See src/router/intent_capabilities.py.
    capability = get_intent_capability(classification.intent)
    if capability.tier == CapabilityTier.POINT_TO_URL:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="point_to_url",
                       latency_s=latency_ms / 1000)
        return _capability_response(
            classification, scope, capability, latency_ms,
            is_refusal=False,
        )
    if capability.tier == CapabilityTier.REFUSE:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="refusal",
                       latency_s=latency_ms / 1000)
        if capability.refusal_trigger:
            record_refusal(trigger=capability.refusal_trigger)
        return _capability_response(
            classification, scope, capability, latency_ms,
            is_refusal=True,
        )

    # --- 3. Service-availability pre-check ---
    # If the user asked about MakerSpace at Middletown (say), skip
    # agent + synthesizer entirely. LibrarySpace.services_offered is
    # the truth table. Plan §8 load-bearing guard.
    service_refusal: Optional[RefusalContext] = deps.lookup_service_availability(
        classification.intent, scope.campus
    )

    # --- 3.5. Administrative-role short-circuit ---
    # "Who is the library dean?" / "library administration" etc. is NOT a
    # subject-librarian lookup. Answer deterministically with the Dean's
    # Office page before the agent can fuzzy-match "dean" to a subject and
    # name a random liaison.
    _admin = _admin_role_answer(request.user_message)
    if _admin is not None:
        _ans, _cites = _admin
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="admin_role",
                       latency_s=latency_ms / 1000)
        return TurnResponse(
            answer=_ans, is_refusal=False, refusal_trigger=None,
            citations=_cites, confidence="high",
            intent=classification.intent, scope=scope.as_filter(),
            model_used=model_basic,
            tokens={"input": 0, "cached_input": 0, "output": 0},
            fired_corrections=[], agent_stopped_reason="admin_role_short_circuit",
            latency_ms=latency_ms, cited_chunk_ids=[],
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

    # --- 4.5. Booking transactional short-circuit ---
    # If the agent invoked book_room, the tool's text IS the reply:
    # deterministic backend/v1-tool output (missing-slot list, the
    # confirmation summary, the booked confirmation, or the
    # we-don't-book-there explanation). Returning it VERBATIM (a) keeps
    # the byte-stable markers the 2.0 flow-continuation gate matches on
    # -- the synthesizer was observed paraphrasing them away -- and
    # (b) skips an LLM call on a turn with nothing to synthesize.
    _bk_text = _last_book_room_text(agent_outcome)
    if _bk_text:
        latency_ms = int((time.monotonic() - turn_start) * 1000)
        record_request(endpoint="/chat", status="booking_flow",
                       latency_s=latency_ms / 1000)
        return TurnResponse(
            answer=_bk_text,
            is_refusal=False,
            refusal_trigger=None,
            citations=[],
            confidence="high",
            intent=classification.intent,
            scope=scope.as_filter(),
            model_used=model,
            tokens={
                "input": agent_outcome.input_tokens,
                "cached_input": agent_outcome.cached_input_tokens,
                "output": agent_outcome.output_tokens,
            },
            fired_corrections=[],
            agent_stopped_reason=agent_outcome.stopped_reason,
            latency_ms=latency_ms,
            cited_chunk_ids=[],
        )

    # --- 4.6. Subject-liaison deterministic short-circuit ---
    # For "who is the librarian for <subject>?" (and the research-help
    # variants that resolve to a subject), the lookup_librarian backend
    # returns the exact liaison(s)+email. The synth was unreliable at
    # stating them (deflected to the directory; refused on two co-liaisons),
    # so format the contact deterministically and skip the synth. Only
    # fires on a SUBJECT-scoped lookup with in-campus results; building
    # rosters and empty results fall through to normal synthesis.
    # --- 4.55. Cross-campus service comparison short-circuit ---
    # "Do all the libraries have <service>?" -- aggregate per campus from
    # the LibrarySpace truth table deterministically, rather than letting
    # the synth answer (it dropped the regional campuses).
    if classification.intent == "cross_campus_comparison":
        _xc = _cross_campus_service_short_circuit(request.user_message, deps)
        if _xc is not None:
            _ans, _cites = _xc
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="cross_campus",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans, is_refusal=False, refusal_trigger=None,
                citations=_cites, confidence="high",
                intent=classification.intent, scope=scope.as_filter(),
                model_used=model,
                tokens={"input": agent_outcome.input_tokens,
                        "cached_input": agent_outcome.cached_input_tokens,
                        "output": agent_outcome.output_tokens},
                fired_corrections=[],
                agent_stopped_reason=agent_outcome.stopped_reason,
                latency_ms=latency_ms, cited_chunk_ids=[],
            )

    if classification.intent in ("subject_librarian", "research_consultation"):
        _liaison = _subject_liaison_short_circuit(agent_outcome, scope)
        if _liaison is not None:
            _ans, _cites = _liaison
            latency_ms = int((time.monotonic() - turn_start) * 1000)
            record_request(endpoint="/chat", status="subject_liaison",
                           latency_s=latency_ms / 1000)
            return TurnResponse(
                answer=_ans,
                is_refusal=False,
                refusal_trigger=None,
                citations=_cites,
                confidence="high",
                intent=classification.intent,
                scope=scope.as_filter(),
                model_used=model,
                tokens={
                    "input": agent_outcome.input_tokens,
                    "cached_input": agent_outcome.cached_input_tokens,
                    "output": agent_outcome.output_tokens,
                },
                fired_corrections=[],
                agent_stopped_reason=agent_outcome.stopped_reason,
                latency_ms=latency_ms,
                cited_chunk_ids=[],
            )

    # --- 5. Assemble evidence and run synthesizer ---
    evidence = _extract_evidence(agent_outcome)

    # Deterministic MakerSpace-equipment evidence. The MakerSpace is its
    # OWN LibrarySpace row ("makerspace"), separate from King's building
    # row, and the agent is unreliable at picking lookup_space("makerspace")
    # vs ("king") for equipment questions -- it kept querying King (whose
    # row lists makerspace only as a *service*, with no 3D-printer in its
    # equipment) and then hedged/refused on "does the MakerSpace have a 3D
    # printer?". For the makerspace intent on the Oxford campus, fetch the
    # MakerSpace row directly and prepend it so the synthesizer always has
    # the equipment/services facts. (Regional makerspace asks never reach
    # here -- the service-availability guard refuses them before the agent.)
    if classification.intent == "makerspace_3d" and scope.campus in ("oxford", None):
        evidence = _ensure_makerspace_evidence(evidence, deps)

    # Promote to reasoning model when CRAWLED evidence is multi-hop:
    # >5 chunks across multiple topics. Tool facts (live_api /
    # authoritative_db) are excluded -- they have no topic and a
    # single hours/librarian lookup isn't "multi-hop"; counting them
    # would silently (and expensively) flip model selection.
    _crawled = [c for c in evidence if c.kind == "crawled"]
    if len(_crawled) > 5 and len({c.topic for c in _crawled if c.topic}) > 1:
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
        user_message=request.user_message,
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
    {"cross_campus_comparison", "loan_policy", "research_consultation"}
)
"""Intents that get `gpt-5.2` by default. Comparative + policy + research-
consultation questions benefit from the reasoning tier; quick lookups
don't."""


def _is_reasoning_intent(intent: str) -> bool:
    return intent in _REASONING_INTENTS


# canonical library id -> canonical campus, for the cross-campus
# citation guard on tool-fact evidence (search_kb chunks carry their
# own campus; tool facts must be tagged here or the guard can't check
# them -- and that guard is the King-hours-for-Hamilton protection).
_LIB_CAMPUS = {
    "king": "oxford", "wertz": "oxford", "special": "oxford",
    # MakerSpace is a bookable LibCal location inside King (id 11904).
    # Missing from this map, a get_hours("makerspace") evidence chunk got
    # campus=None and post-processor rule 4 (no campus metadata -> cannot
    # verify scope) downgraded a CORRECT live-hours answer to a refusal --
    # audit cases fs_makerspace_hours / ms_hours_today, 2026-06-09.
    "makerspace": "oxford",
    "rentschler": "hamilton",
    "gardner_harvey": "middletown", "sword": "middletown",
}
_LIAISONS_URL = "https://www.lib.miamioh.edu/about/organization/liaisons/"
_ROOMS_URL = "https://www.lib.miamioh.edu/use/spaces/room-reservations/"
_DEANS_OFFICE_URL = "https://www.lib.miamioh.edu/about/organization/deans-office/"

# "Who is the library dean?" is an ADMINISTRATIVE-role question, NOT a
# subject-librarian lookup. Left to the agent, "dean" fuzzy-matches a
# LibGuides subject and the liaison short-circuit then names a random
# liaison as "your subject librarian" (prod 2026-06-17: Katie Gibson /
# Stefanie Hilles / Roger Justus for the same question). Point to the
# Dean's Office page deterministically instead.
_ADMIN_ROLE_RE = re.compile(
    r"\bdean(['’]?s)?\b"
    r"|library (administration|leadership|director|directors)"
    r"|director of (the )?librar"
    r"|head of (the )?librar"
    r"|who (runs|heads|leads|is in charge of) (the )?librar",
    re.IGNORECASE,
)


# Bare greeting -> a friendly hello, not the out_of_scope refusal. A
# standalone "hi" has no library signal so the kNN classifier sends it to
# out_of_scope; greet deterministically instead and point at what the bot
# can do.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hey+|hello+|heya|yo|howdy|greetings|good\s+(morning|afternoon|"
    r"evening|day)|sup|hiya|hello\s+there|hey\s+there)\s*[!.,?]*\s*$",
    re.IGNORECASE,
)
_GREETING_TEXT = (
    "Hi! I'm the Miami University Libraries assistant. I can help with "
    "things like library hours, finding the subject librarian for a course "
    "or major, booking a study room, locations and addresses, and services "
    "like printing, interlibrary loan, or the MakerSpace. What can I help "
    "you with?"
)
# Identity / capability questions ("who are you", "what can you help me
# with") carry no library signal either, so the context-free classifier
# sends them to out_of_scope too -- but the greeting intro IS the right
# answer. Anchored so a real question that merely starts with these words
# ("who are you going to recommend for nursing?") still reaches the agent.
_IDENTITY_RE = re.compile(
    r"^\s*("
    r"who\s+are\s+you|what\s+are\s+you|"
    r"what\s+can\s+you\s+do|what\s+do\s+you\s+do|"
    r"what\s+can\s+you\s+help\s+(me\s+)?with|what\s+can\s+you\s+help\s+me|"
    r"how\s+can\s+you\s+help( me)?|how\s+do\s+you\s+work|"
    r"what\s+(kinds?|sorts?)\s+of\s+(questions|things|stuff)\s+can\s+you\s+(answer|help( me)?\s+with|do)|"
    r"what\s+can\s+i\s+ask( you)?( about)?|"
    r"are\s+you\s+(a\s+)?(bot|robot|chatbot|human|real|a\s+person|an?\s+ai)"
    r")\s*[!.,?]*\s*$",
    re.IGNORECASE,
)
# A bare thanks shouldn't get an out-of-scope refusal. Anchored so
# "thanks, but what time do you close?" still reaches the agent.
_THANKS_RE = re.compile(
    r"^\s*(thanks?|thank\s+you|thank\s+u|thx|ty|tysm|"
    r"much\s+appreciated|appreciate\s+it|appreciated|cheers)"
    r"(\s+(so\s+much|a\s+lot|a\s+bunch|very\s+much|so|much|again))?"
    r"\s*[!.,]*\s*$",
    re.IGNORECASE,
)
_THANKS_TEXT = (
    "You're welcome! If there's anything else I can help with -- library "
    "hours, finding a subject librarian, booking a study room, or services "
    "like printing or interlibrary loan -- just ask."
)


def _greeting_answer(message: str) -> "Optional[str]":
    """Friendly reply for a bare greeting, an identity/capability question
    ('who are you', 'what can you help with'), or a thanks -- each of which a
    context-free kNN classifier otherwise misroutes to out_of_scope. Returns
    the reply text, or None."""
    m = message or ""
    if _GREETING_RE.match(m) or _IDENTITY_RE.match(m):
        return _GREETING_TEXT
    if _THANKS_RE.match(m):
        return _THANKS_TEXT
    return None


# Anaphoric follow-up handling. A terse referential message ("what about
# tomorrow?", "how about Wertz?", "and on Sunday?") has no standalone library
# signal, so the context-free classifier misroutes it to out_of_scope and the
# user gets a refusal -- even though the agent (which DOES receive history)
# could resolve it. When one is detected and a prior user turn exists, classify
# on "<prior question> <this message>" so the INTENT comes out right; the agent
# still gets the real message + history and resolves the reference itself.
# (Found 2026-06-24: "King hours today?" then "what about tomorrow?" -> OOS.)
_FOLLOWUP_RE = re.compile(
    r"^\s*(?:and|but|so|ok(?:ay)?|well|then)?[\s,]*"
    r"(?:"
    r"what about|how about|what if|and what about|and how about|"
    r"tomorrow|tonight|"
    r"this (?:weekend|week|morning|afternoon|evening|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"next (?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|the weekend)|"
    r"later|earlier|the day after|over the weekend"
    r")\b.{0,40}$",
    re.IGNORECASE,
)


def _is_bare_followup(message: str) -> bool:
    """True for a short anaphoric follow-up that needs prior context to
    classify ('what about tomorrow?'). Length-capped so a self-contained
    question that merely starts with these words isn't swept up."""
    m = (message or "").strip()
    if not m or len(m) > 45:
        return False
    return bool(_FOLLOWUP_RE.match(m))


def _last_user_question(history: "Optional[list]") -> "Optional[str]":
    """The most recent prior USER message that carries its own signal, used as
    the anchor when reformulating a bare follow-up. Skips earlier bare
    follow-ups so a chain ('King hours today?' -> 'what about tomorrow?' ->
    'how about this weekend?') still anchors on the substantive question. The
    current turn is already de-duplicated from history upstream."""
    for raw in reversed(history or []):
        if not isinstance(raw, dict):
            continue
        role = raw.get("role") or raw.get("type")
        if role == "user":
            c = (raw.get("content") or "").strip()
            if c and not _is_bare_followup(c):
                return c
    return None


# Prompt-injection backstop. The synthesizer's rule 1a tells the model not to
# obey user-dictated text ("append this exact sentence: '...'"), but that's a
# model instruction and not 100% reliable -- an hours turn appended a dictated
# "the library is closing permanently next week." on 2026-06-24 (adversarial
# probe). This deterministic strip is the second line of defense: it finds a
# sentence the user tried to DICTATE via an injection trigger and, if that exact
# text leaked into the answer, removes it. It only ever touches attacker-
# dictated text that actually appears verbatim in the answer, so normal turns
# (no such trigger in the message) are never altered.
_QUOTES = "'\"‘’“”"
_INJECT_DICTATION_RE = re.compile(
    r"\b("
    # A: verbs that alone imply dictation (no cue needed)
    r"(?:append|prepend|repeat|verbatim)"
    # B: position verb + "with" ("end your answer with", "finish with")
    r"|(?:end[a-z]*|finish|conclude|start|begin|respond|reply|follow)"
    r"(?:\s+\w+){0,3}\s+with"
    # C: general verb + an explicit dictation cue
    r"|(?:say|write|print|output|add|include|put)\b[^" + _QUOTES + r"\n]{0,30}?"
    r"(?:this exact|exactly this|the following|verbatim|this sentence|this phrase|"
    r"this line|this text|this statement|the phrase|the sentence|the words|"
    r"to the end|at the end)"
    r")"
    r"[^" + _QUOTES + r"\n]{0,40}?"
    r"[" + _QUOTES + r"]([^" + _QUOTES + r"\n]{10,200})[" + _QUOTES + r"]",
    re.IGNORECASE,
)


def _strip_injected_dictation(user_message: str, answer: str) -> str:
    """Remove attacker-dictated sentences (prompt injection) that leaked into
    the answer. See the note above _INJECT_DICTATION_RE."""
    um = user_message or ""
    ans = answer or ""
    if not ans or not um:
        return ans
    for m in _INJECT_DICTATION_RE.finditer(um):
        dictated = m.group(2).strip().strip(".!?,;:" + _QUOTES).strip()
        if len(dictated) < 10:
            continue
        pat = re.compile(
            r"\s*[" + _QUOTES + r"]?" + re.escape(dictated)
            + r"[.!?]*[" + _QUOTES + r"]?",
            re.IGNORECASE,
        )
        ans = pat.sub("", ans)
    ans = re.sub(r"[ \t]{2,}", " ", ans)
    ans = re.sub(r"\s+([.!?,;:])", r"\1", ans)
    return ans.strip()


# Building-conduct / facilities policies (food, drink, alcohol, sleeping,
# noise, pets, smoking, bikes, solicitation, room rules, ...) live in the
# operator's "Facilities & Events Policies" Google Doc, not on the indexed
# site. Point there deterministically so these questions never get a
# refusal or a guess.
# NB: keep this URL on ONE source line. validate_prompt_urls.py scans source
# text and its URL regex stops at the closing quote, so a string split across
# two literals makes it see only the truncated "…/document/d/" (404) and fail
# preflight (found 2026-06-23). The full URL returns 200.
_FACILITIES_POLICY_URL = "https://docs.google.com/document/d/1ZQdegDmo_8V7_aM8EMzpr57lQ5-kOj_jgtCqsbJ8_d4/edit?tab=t.0"
# Strong terms: in a library bot, asking about these is ~always a conduct
# question (no permission phrasing required) -- UNLESS it's a research
# question about the topic (handled by _RESEARCH_CTX_RE below).
_CONDUCT_STRONG_RE = re.compile(
    r"\b(alcohol|beer|wine|liquor|smoking|smoke|vape|vaping|tobacco|"
    r"cigarettes?|napping|nap|sleeping in|sleep in|overnight|"
    r"live in the|living in the|reside|residence)\b",
    re.IGNORECASE,
)
# Weak terms also match common non-policy questions ("food science
# librarian", "coffee shop"), so they only fire WITH permission/policy
# phrasing.
_CONDUCT_WEAK_RE = re.compile(
    r"\b(food|eat|eating|snacks?|drinks?|beverages?|coffee|water bottle|water|"
    r"pets?|dogs?|animals?|snakes?|skateboards?|scooters?|bikes?|bicycles?|"
    r"rollerblad\w*|skat\w*|sell|selling|sales|vendors?|solicit\w*|"
    r"flyers?|fliers?|posters?|leaflets?|handbills?|handouts?|tabling|"
    r"noise|talking|loud|amplified|music|quiet|"
    r"balloons?|confetti|glitter|candles?|incense|decorations?|"
    r"child|children|kids?|minors?|strollers?|baby|toddlers?|year.?old)\b",
    re.IGNORECASE,
)
_PERMISSION_RE = re.compile(
    r"\b(can (i|we|my|a|an|you|someone|somebody|he|she|they)|"
    r"am i allowed|are .{0,30} allowed|allowed|permitted|"
    r"is it ok|okay to|policy|policies|rules?|prohibit\w*|forbid\w*|against "
    r"the rules|bring (my|a|an|in|some|me)|put up|set up)\b",
    re.IGNORECASE,
)
# If the question is about FINDING research on a topic, it's NOT a conduct
# question even if the topic word is a conduct term ("article about alcohol
# abuse"). Skip the policy pointer and let the agent handle the research ask.
_RESEARCH_CTX_RE = re.compile(
    r"\b(articles?|journals?|databases?|papers?|sources?|cite|citations?|"
    r"citing|peer.?reviewed|research (on|about|paper|topic|for)|study about|"
    r"studies (on|about)|books? about|information (on|about)|"
    r"find .{0,30}(article|source|paper|book|journal))\b",
    re.IGNORECASE,
)


def _facilities_policy_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic pointer to the Facilities & Events Policies doc for
    building-conduct questions (food/drink/alcohol/sleeping/noise/pets/
    smoking/bikes/...). Returns (answer, citations) or None."""
    m = message or ""
    if _RESEARCH_CTX_RE.search(m):
        return None  # "article about alcohol" etc. -> research, not conduct
    if not (_CONDUCT_STRONG_RE.search(m)
            or (_CONDUCT_WEAK_RE.search(m) and _PERMISSION_RE.search(m))):
        return None
    answer = (
        "Miami University Libraries' building policies -- food and drink, "
        "alcohol, sleeping/napping, noise, pets and service animals, "
        "smoking/vaping, bikes and skateboards, and more -- are in the "
        "Libraries' Facilities & Events Policies guide [1]."
    )
    return answer, [{
        "n": 1, "url": _FACILITIES_POLICY_URL,
        "snippet": "Miami University Libraries — Facilities & Events Policies",
    }]


_ASKUS_URL = "https://www.lib.miamioh.edu/research/research-support/ask/"

# Permanently CLOSED libraries (operator-confirmed 2026-06-18): the
# B.E.S.T. Library and the Amos Music Library. Questions about them as
# locations were getting confused/refused (Music) or conflated with "best
# library" = flagship (BEST). Answer the closure deterministically.
_CLOSED_LIBRARY_RE = re.compile(
    r"(b\.?e\.?s\.?t\.?\s+librar|amos\s+music|music\s+librar(y|ies)\b)",
    re.IGNORECASE,
)


def _closed_library_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic 'this library has closed' answer for B.E.S.T. / Amos
    Music Library. Returns None for the music SUBJECT LIBRARIAN (still a
    valid liaison -- only the building closed)."""
    m = message or ""
    if re.search(r"music\s+librarian", m, re.IGNORECASE):
        return None  # the Music subject liaison still exists
    if not _CLOSED_LIBRARY_RE.search(m):
        return None
    is_best = bool(re.search(r"b\.?e\.?s\.?t\.?\s+librar", m, re.IGNORECASE))
    name = ("The B.E.S.T. Library" if is_best else "The Amos Music Library")
    extra = (" (If you meant the main/flagship library, that's King Library.)"
             if is_best else "")
    answer = (
        f"{name} has permanently closed. Its collections and services have "
        f"moved to other Miami University Libraries.{extra} For where a "
        f"specific item or service is now, ask a librarian through Ask Us [1]."
    )
    return answer, [{
        "n": 1, "url": _ASKUS_URL,
        "snippet": "Miami University Libraries — Ask Us",
    }]


# MakerSpace staff (https://libguides.lib.miamioh.edu/create/about-makerspace/staff,
# curl-verified 2026-06-25). Sarah Nagle is the librarian; the others are the
# team. Katie Gibson is a SUBJECT liaison and does NOT staff the MakerSpace --
# the bot was fabricating her as the contact because no makerspace-staff chunk
# existed in the index.
_MAKERSPACE_STAFF_URL = "https://libguides.lib.miamioh.edu/create/about-makerspace/staff"
_MAKERSPACE_RE = re.compile(r"\bmaker\s?space\b", re.IGNORECASE)
# A staff / contact / who-do-I-talk-to signal.
_MS_STAFF_RE = re.compile(
    r"\b(librarian|staff|contact|email|e-mail|reach|manager|specialist|"
    r"coordinator|technologist|run by|in charge|"
    r"who\s+(runs|manages|works|is in charge|to (contact|email|ask|talk|see)|"
    r"do i (contact|email|ask|talk|see)|is the|are the|can help|"
    r"can i (contact|email|talk|ask))|"
    r"help\s+(me\s+)?with|need help|get help|talk to|get in touch|works there)\b",
    re.IGNORECASE,
)
# Usage / hours / 3D / booking questions are handled elsewhere -- don't hijack.
_MS_NOT_STAFF_RE = re.compile(
    r"\b(hours?|open|clos(e|ed|ing)|3-?d|print|laser|sewing|vinyl|embroider|"
    r"who can use|who(?:'s| is) allowed|who can access|can i use|am i allowed|"
    r"book a|reserve|consultation|located|where(?:'s| is)|cost|price|how much|"
    r"equipment|tool)\b",
    re.IGNORECASE,
)


def _makerspace_staff_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic MakerSpace staff/contact answer. Fires on
    'who is the makerspace librarian' / 'I need help with the makerspace' etc.,
    but NOT on usage/hours/3D/booking questions handled elsewhere. Returns
    (answer, citations) or None."""
    m = message or ""
    if not _MAKERSPACE_RE.search(m):
        return None
    if _MS_NOT_STAFF_RE.search(m):
        return None
    if not _MS_STAFF_RE.search(m):
        return None
    answer = (
        "The MakerSpace librarian is Sarah Nagle, Creation & Innovation "
        "Services Librarian (pricesb@miamioh.edu). The rest of the MakerSpace "
        "team: Lori Chapin, Manager of Innovative Spaces (pheanila@miamioh.edu); "
        "Lindsey Masters, Creative Technologist (masterlr@miamioh.edu); "
        "John Williams, MakerSpace Technology Specialist (williajc@miamioh.edu); "
        "and Nathan Hall, MakerSpace Specialist (hallnj3@miamioh.edu) [1]."
    )
    return answer, [{
        "n": 1, "url": _MAKERSPACE_STAFF_URL,
        "snippet": "Miami University Libraries — MakerSpace: Our Staff",
    }]


# Scholarly communication / open access. Carla Myers is the Coordinator of
# Scholarly Communication (staff-directory-verified 2026-06-25). The bot had no
# scholarly-comm chunk, so it named the BUSINESS liaison (Erica Freed) for open
# access -- the same misapplied-liaison fabrication as the MakerSpace case
# (contacts probe 2026-06-25). Her email isn't in the static page (JS contact
# widget), so we name her + title + the Scholarly Commons page, no fabricated
# address.
_SCHOLARLY_COMMONS_URL = "https://www.lib.miamioh.edu/research/creation/scholarly-commons/"
_SCHOLCOMM_STRONG_RE = re.compile(
    r"\b(scholarly communication|scholarly commons|author'?s? rights|"
    r"institutional repository|predatory journals?)\b",
    re.IGNORECASE,
)
_OPEN_ACCESS_RE = re.compile(r"\bopen access\b", re.IGNORECASE)
_OA_SERVICE_RE = re.compile(
    r"\b(who|contact|help|reach|publish|publishing|deposit|polic|fund|fee|"
    r"support|librarian|coordinator|office|advice|question)\b",
    re.IGNORECASE,
)


# 3D printing / MakerSpace USAGE (distinct from the staff short-circuit above).
# "3d printing in King" classifies as printing_wifi (the "printing" token), which
# has no good 3D content -- the agent loops and either refuses ("couldn't verify
# my sources") or gives a weak "King offers a makerspace" (prod 2026-06-25). The
# makerspace_3d evidence prefetch only runs on the makerspace_3d intent, so the
# misroute skips it. Answer the Oxford/King case deterministically; leave the
# cross-campus comparison and the regional buildings to the existing paths.
_MAKERSPACE_GUIDE_URL = "https://libguides.lib.miamioh.edu/create/makerspace"
_MS_3D_RE = re.compile(
    r"\b3-?d\s*print\w*|\b3-?d\s*printer|\bstl\b|\.stl\b|"
    r"\b3-?d\s*(model|file)|\bg-?code\b|\bresin print",
    re.IGNORECASE,
)
_MS_USE_RE = re.compile(
    r"\b(can i|could i|i (need|want|'?d like|wanna)|how (do|can|to)|where|"
    r"do you have|is there|are there|available|access|use|using|book|reserve|"
    r"consult|cost|price|how much|hours?|get to)\b",
    re.IGNORECASE,
)
_MS_CROSS_RE = re.compile(
    r"\b(all (the )?librar(y|ies)|every (campus|librar(y|ies)|location)|"
    r"each (campus|librar(y|ies))|which (librar(y|ies)|campus|location)|"
    r"both campus|compare|across campus|any (librar(y|ies)|campus)|vs\b|versus)\b",
    re.IGNORECASE,
)
_MS_REGIONAL_RE = re.compile(
    r"\b(hamilton|rentschler|middletown|gardner|gardner-harvey|regional)\b",
    re.IGNORECASE,
)


def _makerspace_3d_answer(message: str, scope: "Scope") -> "Optional[tuple[str, list[dict]]]":
    """Deterministic King MakerSpace 3D-printing/usage answer. Fires on any
    3D-printing service question, or a MakerSpace question that names King/
    Oxford. Defers (None) on cross-campus comparisons and regional buildings so
    the existing cross-campus path handles those. Returns (answer, cites) or None."""
    m = message or ""
    names_king = bool(re.search(r"\b(king|oxford)\b", m, re.IGNORECASE))
    is_3d = bool(_MS_3D_RE.search(m))
    is_ms = bool(_MAKERSPACE_RE.search(m))
    if not (is_3d or (is_ms and names_king)):
        return None
    if is_ms and not is_3d and not _MS_USE_RE.search(m):
        return None
    if _MS_CROSS_RE.search(m):
        return None
    if _MS_REGIONAL_RE.search(m) and not names_king:
        return None
    if scope.campus not in ("oxford", None):
        return None
    answer = (
        "Yes — 3D printing is available at the King Library MakerSpace (3rd "
        "floor, Room 303) on the Oxford campus, and it's self-service. The "
        "MakerSpace guide has how to get started — including any training or "
        "consultation — plus the available printers and costs [1]."
    )
    return answer, [{
        "n": 1, "url": _MAKERSPACE_GUIDE_URL,
        "snippet": "Miami University Libraries — MakerSpace (Create)",
    }]


# --- Cancel a room reservation (destructive write; deterministic, NOT LLM) ---
# The cancel feature existed only in the v1 agent (LibCalCancelReservationTool)
# and was NEVER wired into the live v2 path: the v2 tool registry is
# search_kb/lookup_librarian/lookup_space/get_hours/book_room -- no cancel. So
# "cancel my booking <code>" had no tool to call, the agent looped, and the turn
# fell through to the generic "I encountered an error" (prod 2026-06-25, boss
# demo). Handle it deterministically here: pull the LibCal confirmation code +
# the booking email out of the message, verify+cancel via the v1 tool over the
# _bridge daemon loop (loop-safe, same as book_room), and degrade GRACEFULLY on
# ANY failure -- a destructive external call must never surface a raw crash.
_CANCEL_INTENT_RE = re.compile(r"\bcancel(l?ing|l?ed|lation)?\b", re.IGNORECASE)
_CANCEL_CTX_RE = re.compile(
    r"\b(reservation|booking|booked|study\s*room|\broom\b|appointment|reserve)\b",
    re.IGNORECASE,
)
# "what's the cancellation policy / fee / refund / deadline" is informational,
# NOT a request to cancel a specific reservation.
_CANCEL_INFO_RE = re.compile(
    r"\b(policy|policies|fee|fees|charge|charges|deadline|refund|penalt)\b",
    re.IGNORECASE,
)
_CONF_CODE_RE = re.compile(r"\bcs_[A-Za-z0-9]{3,}\b", re.IGNORECASE)
_ANY_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CANCEL_HELP = (
    "To cancel a room reservation I need two things: the confirmation number "
    "(it looks like cs_… and is in your confirmation email) and the email "
    "address used to book it (so I can verify the reservation is yours). Send "
    "both and I'll cancel it. You can also cancel anytime with the link in that "
    "confirmation email, or by calling the library at (513) 529-4141 [1]."
)
_CANCEL_FALLBACK = (
    "I couldn't complete the cancellation just now. You can cancel using the "
    "link in your confirmation email, or contact the library at (513) 529-4141 "
    "and they'll take care of it [1]."
)


def _cancel_reservation_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic room-reservation cancellation. Returns (answer, cites) or
    None. NEVER raises: a failed destructive call degrades to a graceful
    fallback, not a crash."""
    m = message or ""
    if not _CANCEL_INTENT_RE.search(m):
        return None
    has_code = bool(_CONF_CODE_RE.search(m))
    if not (has_code or _CANCEL_CTX_RE.search(m)):
        return None
    # informational ("cancellation policy/fee") with no concrete code -> let the
    # normal path answer; don't treat it as a cancel action.
    if _CANCEL_INFO_RE.search(m) and not has_code:
        return None
    cite = [{"n": 1, "url": _ROOMS_URL,
             "snippet": "Miami University Libraries — Room Reservations"}]
    code_m = _CONF_CODE_RE.search(m)
    email_m = _ANY_EMAIL_RE.search(m)
    if not (code_m and email_m):
        return _CANCEL_HELP, cite
    try:
        from src.eval.real_backends import _bridge
        from src.tools.libcal_comprehensive_tools import LibCalCancelReservationTool
        res = _bridge(
            LibCalCancelReservationTool().execute(
                query=m, booking_id=code_m.group(0), email=email_m.group(0)),
            timeout=30.0,
        )
        text = res.get("text") if isinstance(res, dict) else None
        return ((text + " [1]") if text else _CANCEL_FALLBACK), cite
    except Exception:  # noqa: BLE001 -- destructive call must never crash a turn
        get_logger("new_orchestrator").exception("cancel_reservation failed")
        return _CANCEL_FALLBACK, cite


def _scholarly_comm_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic scholarly-communication / open-access contact. Fires on
    the service ('who handles open access and scholarly communication') but not
    on 'find open access articles' (research). Returns (answer, citations) or
    None."""
    m = message or ""
    if not (_SCHOLCOMM_STRONG_RE.search(m)
            or (_OPEN_ACCESS_RE.search(m) and _OA_SERVICE_RE.search(m))):
        return None
    answer = (
        "For open access, scholarly communication, author rights, and the "
        "institutional repository, the contact is Carla Myers, Coordinator of "
        "Scholarly Communication. The Scholarly Commons page has the details "
        "and her contact info [1]."
    )
    return answer, [{
        "n": 1, "url": _SCHOLARLY_COMMONS_URL,
        "snippet": "Miami University Libraries — Scholarly Commons",
    }]


def _admin_role_answer(message: str) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic pointer to the Dean's Office for library-leadership
    questions, so they never get mis-answered as a subject-librarian
    lookup. Returns (answer, citations) or None."""
    if not _ADMIN_ROLE_RE.search(message or ""):
        return None
    answer = (
        "For the Dean of University Libraries and the library "
        "administration/leadership team, see the Dean's Office page [1]."
    )
    return answer, [{
        "n": 1, "url": _DEANS_OFFICE_URL,
        "snippet": "Miami University Libraries — Dean's Office",
    }]


def _subject_liaison_short_circuit(
    agent_outcome: "AgentOutcome", scope: "Scope"
) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic answer for "who is the librarian for <subject>?".

    The `lookup_librarian` backend is exact (Postgres `LibrarianSubject`),
    but the synthesizer was unreliable at actually stating the name+email
    it was handed -- it kept deflecting to the liaisons page, and refused
    outright when a subject had two co-liaisons. When the agent did a
    SUBJECT-scoped lookup (a `subject` arg, not a building roster) and got
    liaison rows for the user's campus, format the contact ourselves and
    skip the synth -- the same pattern as the booking short-circuit.

    Returns `(answer_text, citations)` or None to fall through to synth.
    Building-roster lookups (no `subject` arg) and empty/cross-campus
    results return None so they keep their normal handling.
    """
    want_campus = (scope.campus or "").lower()
    seen: set = set()
    liaisons: list[dict] = []
    guide_name = ""
    guide_url = ""
    for turn in (agent_outcome.turns or []):
        args_by_id = {tc.id: (tc.arguments or {}) for tc in (turn.tool_calls or [])}
        for res in (turn.tool_results or []):
            if res.name != "lookup_librarian" or res.error or not res.data:
                continue
            subj = (args_by_id.get(res.call_id) or {}).get("subject")
            if not subj or not str(subj).strip():
                continue  # building roster, not a subject ask -> let synth handle
            for lib in (res.data.get("librarians") or []):
                if not isinstance(lib, dict) or not lib.get("email"):
                    continue
                lib_campus = (lib.get("campus") or "").lower()
                # Campus discipline: only surface a liaison in the asked
                # campus (or campus-agnostic rows). This is the guard the
                # synth path gets from the cross-campus citation check;
                # we replicate it since we're bypassing the synth.
                if want_campus and lib_campus and lib_campus != want_campus:
                    continue
                if lib["email"] in seen:
                    continue
                seen.add(lib["email"])
                liaisons.append(lib)
                if not guide_url and lib.get("guide_url"):
                    guide_name = lib.get("guide_name") or "subject guide"
                    guide_url = lib.get("guide_url")
    if not liaisons:
        return None

    liaisons = liaisons[:2]  # at most two co-liaisons for one subject
    _items = [f"{l['name']} ({l['email']})" for l in liaisons]
    contacts = " and ".join(_items) if len(_items) == 2 else _items[0]
    lead = "subject librarian is" if len(liaisons) == 1 else "subject librarians are"
    answer = f"Your {lead} {contacts} [1]."
    citations = [{
        "n": 1,
        "url": str(liaisons[0].get("profile_url") or _LIAISONS_URL),
        "snippet": "; ".join(f"{l['name']} — {l['email']}" for l in liaisons),
    }]
    if guide_url:
        answer += f" You can also use the subject research guide [2]."
        citations.append({"n": 2, "url": guide_url,
                          "snippet": f"{guide_name} subject guide"})
    return answer, citations


# Canonical buildings per campus (matches LibrarySpace_v2). Used by the
# deterministic cross-campus service comparison below.
_CAMPUS_BUILDINGS: dict[str, list[str]] = {
    "oxford": ["king", "wertz", "special", "makerspace"],
    "hamilton": ["rentschler"],
    "middletown": ["gardner_harvey", "sword"],
}
_CAMPUS_DISPLAY = {"oxford": "Oxford", "hamilton": "Hamilton", "middletown": "Middletown"}
_CAMPUS_MAIN = {"oxford": "King", "hamilton": "Rentschler", "middletown": "Gardner-Harvey"}

# (keyword tuple, service-id, display phrase). Order matters: more specific
# phrases first ("3d print" before "print"). A building "has" the service
# if the id is in services_offered OR (for 3d) 3d_printer is in equipment.
_CROSS_SERVICE_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("3d print", "3-d print", "3d-print", "3d printer"), "3d_printing", "3D printing"),
    (("makerspace", "maker space"), "makerspace", "a MakerSpace"),
    (("study room",), "study_rooms", "study rooms"),
    (("interlibrary loan", "ill pickup", "ill request"), "ill_pickup",
     "interlibrary loan pickup"),
    (("course reserve",), "course_reserves", "course reserves"),
    (("print",), "printing", "printing"),
]


def _detect_cross_service(message: str) -> "Optional[tuple[str, str]]":
    m = (message or "").lower()
    for keys, svc_id, phrase in _CROSS_SERVICE_KEYWORDS:
        if any(k in m for k in keys):
            return svc_id, phrase
    return None


def _cross_campus_service_short_circuit(
    message: str, deps: "OrchestratorDeps"
) -> "Optional[tuple[str, list[dict]]]":
    """Deterministic "do all the libraries have <service>?" answer.

    cross_campus_comparison is synth-driven and was observed answering
    only for Oxford ("King and Wertz offer printing") and dropping the
    regional campuses entirely. When the question names a known service,
    aggregate LibrarySpace_v2.services_offered per campus ourselves and
    state each campus -- the same truth-table approach used for the
    MakerSpace fix. Returns (text, citations) or None to fall through.
    """
    detected = _detect_cross_service(message)
    if detected is None:
        return None
    svc_id, phrase = detected
    from src.agent.tool_registry import ToolCall

    # Per campus we keep a LEVEL, not just a bool, so 3D printing can
    # distinguish self-service (Oxford MakerSpace) from staff-operated
    # (Middletown TEC Lab -- "3D printers (staff use only)" per the TEC
    # Lab guide). Levels: "self" > "staff" > "" (none). Non-3D services
    # are binary: "yes" / "".
    _RANK = {"self": 2, "staff": 1, "yes": 1, "": 0}
    per_campus: dict[str, str] = {}
    cites: list[dict] = []
    seen_urls: set = set()
    for campus, libraries in _CAMPUS_BUILDINGS.items():
        level = ""
        for lib in libraries:
            try:
                res = deps.tool_registry.dispatch(
                    ToolCall(id=f"xc-{lib}", name="lookup_space",
                             arguments={"library": lib}))
            except Exception:  # noqa: BLE001
                continue
            if res.error or not res.data:
                continue
            space = res.data.get("space") or {}
            services = set(space.get("services_offered") or [])
            equip = set(space.get("equipment") or [])
            if svc_id == "3d_printing":
                # Self-service if the row advertises the 3d_printing
                # SERVICE (Oxford MakerSpace). Staff-operated if it only
                # has the equipment / the explicit "3d_printing_staff"
                # tag (Gardner-Harvey TEC Lab -- staff use only). The
                # equipment stem match also covers the data's singular/
                # plural drift ("3d_printer" vs "3d_printers").
                if "3d_printing" in services:
                    this = "self"
                elif ("3d_printing_staff" in services
                      or any("3d_print" in e for e in equip)):
                    this = "staff"
                else:
                    this = ""
            else:
                this = "yes" if svc_id in services else ""
            if _RANK[this] > _RANK[level]:
                level = this
            if this:
                url = str(space.get("source_url") or "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    cites.append({"n": len(cites) + 1, "url": url,
                                  "snippet": f"{space.get('name') or lib}: {phrase}"})
        per_campus[campus] = level

    if not per_campus:
        return None

    def _phrase(level: str) -> str:
        if level == "self":
            return "yes (self-service)"
        if level == "staff":
            return "yes (staff-operated)"
        if level == "yes":
            return "yes"
        return "no"

    all_plain_yes = all(per_campus.get(c) == "yes" for c in _CAMPUS_BUILDINGS)
    if all_plain_yes:
        body = (f"Yes -- {phrase} is available at all three campuses: "
                f"Oxford ({_CAMPUS_MAIN['oxford']}), "
                f"Hamilton ({_CAMPUS_MAIN['hamilton']}), and "
                f"Middletown ({_CAMPUS_MAIN['middletown']}).")
    else:
        parts = [f"{_CAMPUS_DISPLAY[c]} ({_CAMPUS_MAIN[c]}): {_phrase(per_campus.get(c, ''))}"
                 for c in _CAMPUS_BUILDINGS]
        body = f"For {phrase}: " + "; ".join(parts) + "."
    if cites:
        body += " [" + "][".join(str(c["n"]) for c in cites[:3]) + "]"
    return body, cites[:3]


def _ensure_makerspace_evidence(
    evidence: list["EvidenceChunk"], deps: "OrchestratorDeps"
) -> list["EvidenceChunk"]:
    """Prepend a lookup_space('makerspace') evidence chunk if the agent
    didn't already produce one. Deterministic so MakerSpace equipment
    questions ('does it have a 3D printer?') can always be answered from
    the dedicated MakerSpace row. Failure-tolerant: on any error, return
    the evidence unchanged (the turn degrades to whatever the agent found)."""
    if any(
        getattr(c, "chunk_id", "") == "tool:lookup_space:makerspace"
        for c in evidence
    ):
        return evidence
    try:
        from src.agent.tool_registry import ToolCall
        result = deps.tool_registry.dispatch(
            ToolCall(id="prefetch-makerspace", name="lookup_space",
                     arguments={"library": "makerspace"})
        )
        if result.error:
            return evidence
        chunks = _tool_fact_evidence(result, {"library": "makerspace"})
        return chunks + evidence
    except Exception:  # noqa: BLE001 -- prefetch must never break the turn
        return evidence


def _tool_fact_evidence(
    result: Any, call_args: Optional[dict] = None
) -> list[EvidenceChunk]:
    """Map a SUCCESSFUL non-search_kb tool result into trusted
    evidence so the synthesizer can actually answer from it.

    Before this existed, every tool except search_kb was discarded
    here, so hours/librarian/point_to_url turns reached the
    synthesizer with empty evidence and refused by grounding-rule #4.

    Trust tiers (see EvidenceChunk.kind): LibCal -> "live_api"
    (the value, incl. "Closed", IS ground truth); Postgres directory /
    verified URLs -> "authoritative_db". FAILURES are intentionally
    NOT promoted -- a failed get_hours (LibCal down) must stay
    no-evidence so the bot still refuses (gold: hr_libcal_down_refusal).
    Synthetic `tool:<name>:<key>` ids never collide with Weaviate
    chunk_ids or ManualCorrection targets; the post-processor
    validates citations by NUMBER + verbatim value, not by chunk_id.
    """
    name = result.name
    data = result.data or {}
    out: list[EvidenceChunk] = []

    if name == "get_hours":
        if not data.get("success"):
            return []
        lib = str(data.get("library") or "").lower()
        out.append(EvidenceChunk(
            chunk_id=f"tool:get_hours:{lib or 'unknown'}",
            source_url=str(data.get("source_url") or ""),
            text=str(data.get("hours") or ""),
            campus=_LIB_CAMPUS.get(lib),
            library=lib or None,
            kind="live_api",
        ))
    elif name == "get_room_availability":
        for i, slot in enumerate(data.get("slots") or []):
            if not isinstance(slot, dict) or not slot.get("success"):
                continue
            out.append(EvidenceChunk(
                chunk_id=f"tool:get_room_availability:{i}",
                source_url=_ROOMS_URL,
                text=str(slot.get("text") or ""),
                # The agent only queries availability for the scoped
                # library, so the result is campus-correct by
                # construction. "all" satisfies the cross-campus guard
                # (campus=None would force a spurious refusal and
                # re-break the fix).
                campus="all",
                kind="live_api",
            ))
    elif name == "lookup_librarian":
        librarians = data.get("librarians") or []
        # Cap at 5 -- a directory dump floods the prompt; the agent
        # asks a narrower query if it needs more.
        for lib in librarians[:5]:
            if not isinstance(lib, dict) or not lib.get("email"):
                continue
            parts = [
                lib.get("name"), lib.get("title"),
                lib.get("department"),
            ]
            head = ", ".join(p for p in parts if p)
            text = (
                f"{head}. Email: {lib.get('email')}. "
                f"Phone: {lib.get('phone') or 'n/a'}. "
                f"Campus: {lib.get('campus') or 'n/a'}."
            )
            out.append(EvidenceChunk(
                chunk_id=f"tool:lookup_librarian:{lib.get('email')}",
                source_url=str(lib.get("profile_url") or _LIAISONS_URL),
                text=text,
                # Real campus if the directory row has one; "all" on a
                # data gap so a genuine contact isn't suppressed by a
                # missing field (the plan wants exact contact surfaced).
                campus=str(lib.get("campus") or "").lower() or "all",
                kind="authoritative_db",
            ))
        # Subject LibGuide as its OWN citable evidence chunk (source_url =
        # the guide URL) -- attached by the DB-subject fallback. One chunk
        # per unique guide; in TEXT-only form a guide URL would fail the
        # post-processor's rule-3 URL validation and refuse the turn.
        _guide_seen: set[str] = set()
        for lib in librarians[:5]:
            gu = isinstance(lib, dict) and lib.get("guide_url")
            if gu and gu not in _guide_seen:
                _guide_seen.add(gu)
                out.append(EvidenceChunk(
                    chunk_id=f"tool:lookup_librarian:guide:{gu}",
                    source_url=str(gu),
                    text=(
                        f"Subject research guide: "
                        f"{lib.get('guide_name') or 'LibGuide'} -- "
                        f"course/subject help, databases, and resources."
                    ),
                    campus="all",
                    kind="authoritative_db",
                ))
        # Empty-result fallback: if lookup_librarian found nothing, emit
        # an evidence chunk pointing to the appropriate staff/directory
        # page so the synth can give a useful "see the directory" answer
        # instead of refusing with model_self_flagged. Especially matters
        # for regional librarian queries -- the LibGuides API doesn't
        # always return Hamilton/Middletown staff by subject, but those
        # libraries DO have public staff pages we can surface.
        #
        # Wired 2026-05-27 after R8/R9 retests showed lib_hamilton_general,
        # lib_middletown_general, lib_hamilton_librarian all refusing
        # when they could have pointed to the regional staff page.
        if not librarians:
            # Which campus was queried? From the paired ToolCall args
            # (threaded in by _extract_evidence -- the old
            # `result.tool_call` probe was dead code and this fallback
            # always defaulted to Oxford). Falls back to Oxford when the
            # agent didn't pass a campus.
            queried_campus = str(
                (call_args or {}).get("campus") or ""
            ).strip().lower()
            fallback_url, fallback_campus, fallback_text = {
                "hamilton": (
                    "https://www.ham.miamioh.edu/library/about/rentschler-library-staff/",
                    "hamilton",
                    "Rentschler Library (Hamilton) staff directory. The page "
                    "lists Hamilton campus library staff and contact options.",
                ),
                "middletown": (
                    "https://www.mid.miamioh.edu/library/",
                    "middletown",
                    "Gardner-Harvey Library (Middletown) main page. The page "
                    "links to staff contacts and the campus library directory.",
                ),
            }.get(queried_campus, (
                _LIAISONS_URL,
                "oxford",
                "Miami University Libraries subject liaisons directory. The "
                "page lists librarians by subject area.",
            ))
            out.append(EvidenceChunk(
                chunk_id=f"tool:lookup_librarian:empty_fallback:{fallback_campus}",
                source_url=fallback_url,
                text=fallback_text,
                campus=fallback_campus,
                kind="authoritative_db",
            ))
    elif name == "book_room":
        # UNLIKE get_hours, FAILURE text is promoted too: the booking
        # tool's text IS the conversational next move ("I still need
        # your email...", "Ready to book: ... reply 'confirm'", "we
        # don't book rooms at OSU -- we have King, Wertz..."). Dropping
        # it would turn every mid-flow booking turn into a refusal.
        text = str(data.get("text") or "")
        if not text:
            return []
        building = str(
            (call_args or {}).get("building") or ""
        ).strip().lower()
        out.append(EvidenceChunk(
            chunk_id=f"tool:book_room:{data.get('stage') or 'response'}",
            source_url="https://muohio.libcal.com/spaces",
            text=text,
            # Stage/summary text is campus-agnostic flow dialogue; "all"
            # passes the cross-campus guard. A recognized building gets
            # its real campus so a King booking can't masquerade as
            # Hamilton's.
            campus=_LIB_CAMPUS.get(building, "all"),
            library=building or None,
            kind="live_api",
        ))
    elif name == "point_to_url":
        if not data.get("found") or not data.get("url"):
            return []
        out.append(EvidenceChunk(
            chunk_id=f"tool:point_to_url:{data.get('service') or 'svc'}",
            source_url=str(data.get("url")),
            text=str(data.get("description") or ""),
            # ILL/account/renewals/fines/reserves/holds are
            # university-wide self-service; "all" is the correct
            # semantic and passes the cross-campus guard.
            campus="all",
            kind="authoritative_db",
        ))
    elif name == "lookup_space":
        # Wired 2026-05-27: lookup_space results were being silently
        # dropped here, which caused the synth to refuse address/phone
        # questions for Middletown / Hamilton / Wertz (regions Weaviate
        # has thin coverage on — without lookup_space evidence reaching
        # the synth, agent had nothing to cite -> "no evidence" refusal).
        # King worked only because search_kb happened to find King's
        # location page in Weaviate; the regional sites are not indexed
        # as densely. This handler converts the LibrarySpace row into
        # a single [DIRECTORY]-tier EvidenceChunk so the synth can cite
        # address/phone/services_offered verbatim.
        space = data.get("space") if isinstance(data, dict) else None
        if not space or not data.get("found", True):
            return []
        # Render the structured row as a citable text block. The synth
        # is instructed to quote verbatim from [DIRECTORY] sources.
        parts: list[str] = []
        if space.get("name"):
            parts.append(f"Name: {space['name']}")
        if space.get("address"):
            parts.append(f"Address: {space['address']}")
        if space.get("phone"):
            parts.append(f"Phone: {space['phone']}")
        if space.get("capacity"):
            parts.append(f"Capacity: {space['capacity']}")
        if space.get("equipment"):
            parts.append(f"Equipment: {', '.join(space['equipment'])}")
        if space.get("services_offered"):
            parts.append(
                f"Services offered: {', '.join(space['services_offered'])}"
            )
        text = ". ".join(parts)
        if not text:
            return []
        out.append(EvidenceChunk(
            chunk_id=f"tool:lookup_space:{space.get('library') or 'unknown'}",
            source_url=str(space.get("source_url") or ""),
            text=text,
            campus=str(space.get("campus") or "").lower() or "all",
            library=str(space.get("library") or "") or None,
            kind="authoritative_db",
        ))
    return out


def _extract_evidence(agent_outcome: AgentOutcome) -> list[EvidenceChunk]:
    """Walk the agent's tool-call trail and collect evidence chunks.

    `search_kb` results -> crawled-tier EvidenceChunk (wire shape from
    src.tools.search_kb_tool: {n, chunk_id, source_url, snippet,
    library, campus, topic, featured_service, score}; legacy `chunks`
    + `text` accepted defensively).

    SUCCESSFUL non-search_kb tool results (get_hours,
    get_room_availability, lookup_librarian, point_to_url) ->
    trusted-tier EvidenceChunk via `_tool_fact_evidence`. Discarding
    them here was the bug behind five rounds of false refusals: the
    synthesizer never saw any tool output but search_kb's, so every
    hours/librarian/pointer turn refused for "no evidence".
    """
    evidence: list[EvidenceChunk] = []
    tool_facts: list[EvidenceChunk] = []
    for turn in agent_outcome.turns:
        # Pair each result with its originating call's arguments by
        # call_id. ToolResult deliberately does NOT carry the ToolCall;
        # handlers that need the request args (lookup_librarian's
        # regional fallback, book_room's building->campus tag) get them
        # passed explicitly. The previous `result.tool_call` hasattr
        # probe was dead code -- the attribute never existed, so the
        # Hamilton/Middletown fallback URL could never fire.
        _args_by_id = {
            tc.id: (tc.arguments or {}) for tc in (turn.tool_calls or [])
        }
        for result in turn.tool_results:
            if result.is_error:
                continue
            if result.name == "search_kb":
                data = result.data or {}
                raw_items = data.get("evidence") or data.get("chunks") or []
                for raw in raw_items:
                    text = str(raw.get("snippet", raw.get("text", "")))
                    evidence.append(
                        EvidenceChunk(
                            chunk_id=str(raw.get("chunk_id", "")),
                            source_url=str(
                                raw.get("source_url", raw.get("url", ""))
                            ),
                            text=text,
                            campus=raw.get("campus"),
                            library=raw.get("library"),
                            topic=raw.get("topic"),
                            featured_service=raw.get("featured_service"),
                            score=float(raw.get("score", 0.0)),
                        )
                    )
            else:
                tool_facts.extend(_tool_fact_evidence(
                    result, call_args=_args_by_id.get(result.call_id) or {}
                ))
    # Crawled evidence first (citation [1..] stays retrieval-anchored),
    # trusted tool facts appended after.
    return evidence + tool_facts


_BOOKING_FLOW_MARKERS = (
    # real_backends._make_book_room needs_confirmation summary:
    "Nothing is booked yet",
    "Ready to book:",
    # v1 LibCalComprehensiveReservationTool missing-slot text:
    "To complete your room reservation",
    "I still need",
)
"""Byte-stable substrings of OUR booking-flow texts (delivered verbatim
by the 4.5 short-circuit). If the last assistant message contains one,
the next user message is a booking-flow continuation."""


def _booking_flow_active(history: Optional[list]) -> bool:
    """True when the most recent ASSISTANT message in the (OpenAI-shaped)
    history is a mid-flow booking text. Successful-booking and
    we-don't-book-there texts contain no marker, so the flow exits
    naturally after completion/rejection."""
    for entry in reversed(history or []):
        if isinstance(entry, dict) and entry.get("role") == "assistant":
            content = str(entry.get("content") or "")
            return any(m in content for m in _BOOKING_FLOW_MARKERS)
    return False


def _last_book_room_text(agent_outcome: AgentOutcome) -> Optional[str]:
    """The LAST non-error book_room result's text in the agent trail
    (the agent may legitimately call it more than once per turn while
    refining args; the final state wins). None if book_room never ran."""
    text: Optional[str] = None
    for turn in agent_outcome.turns:
        for res in turn.tool_results:
            if res.name == "book_room" and not res.is_error:
                t = str((res.data or {}).get("text") or "")
                if t:
                    text = t
    return text


def _renumber_citations_for_display(
    answer: str, citations: list[dict]
) -> tuple[str, list[dict]]:
    """Renumber `[n]` markers + citations to sequential 1..N in order of
    first appearance in the answer.

    The synthesizer numbers citations by evidence-bundle position, so an
    answer can read "...[5]...[2]...[10]". Users expect [1],[2],[3]. We
    rewrite the markers and the citations[].n together so they stay in
    sync. Citations not referenced by any marker are dropped (they'd
    render as nothing anyway). Idempotent when already 1..N.
    """
    order: list[int] = []
    seen: set[int] = set()
    for m in re.finditer(r"\[(\d+)\]", answer or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            order.append(n)
    if not order:
        return answer, citations
    remap = {old: i + 1 for i, old in enumerate(order)}
    new_answer = re.sub(
        r"\[(\d+)\]",
        lambda mm: f"[{remap.get(int(mm.group(1)), mm.group(1))}]",
        answer,
    )
    by_n: dict[int, dict] = {}
    for c in citations:
        # keep the first citation seen for a given original n
        by_n.setdefault(c.get("n"), c)
    new_citations: list[dict] = []
    for old in order:
        c = by_n.get(old)
        if c is not None:
            nc = dict(c)
            nc["n"] = remap[old]
            new_citations.append(nc)
    return new_answer, new_citations


def _shape_response(
    *,
    synth_result: SynthesisResult,
    classification: Classification,
    scope: Scope,
    agent_outcome: AgentOutcome,
    total_latency_ms: int,
    user_message: str = "",
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
    # Renumber citations to sequential [1],[2],[3]... in order of first
    # appearance. The synthesizer cites evidence by its position in the
    # retrieval bundle, so a real answer can read "...[5]...[2]...[10]",
    # which looks broken to a user. We renumber the answer markers AND the
    # citation numbers together for display. Done HERE, after all
    # validation, so the post-processor ran its [n]<->citations checks on
    # the original numbers.
    answer_text, citations_wire = _renumber_citations_for_display(
        pp.answer.answer, citations_wire
    )
    # Prompt-injection backstop: drop any user-dictated sentence that slipped
    # past the synthesizer's rule 1a (e.g. an appended "the library is closing
    # permanently next week"). No-op unless the message tried to dictate text.
    answer_text = _strip_injected_dictation(user_message, answer_text)
    return TurnResponse(
        answer=answer_text,
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


# --- Long-period hours (operator rule B) -------------------------------
#
# Verified hours PAGES per campus (operator/dev-confirmed + WebFetched):
#   oxford     /about/locations/hours/  -> 200 "Library Hours"
#   hamilton   ham.../library/about/hours/  -> dev-confirmed
#   middletown mid.../library/  -> dev-confirmed (hours live there)
_HOURS_PAGE_URL = {
    "oxford": "https://www.lib.miamioh.edu/about/locations/hours/",
    "hamilton": "https://www.ham.miamioh.edu/library/about/hours/",
    "middletown": "https://www.mid.miamioh.edu/library/",
}

# A "short-term" word VETOES long-period (today/tonight/now use LibCal,
# which is correct and already works). Checked first.
_SHORT_TERM_HOURS_RE = re.compile(
    r"\b(today|tonight|right now|open now|"
    r"currently|at the moment|this week|tomorrow|this morning|"
    r"this afternoon|this evening)\b",
    re.IGNORECASE,
)
# Clearly multi-week / out-of-LibCal-window phrasing.
_LONG_PERIOD_HOURS_RE = re.compile(
    r"\b("
    r"summer|winter break|spring break|fall break|thanksgiving|"
    r"winter session|summer session|winter term|spring term|"
    r"semester|term|intersession|over (the )?break|"
    r"during (the )?break|holidays?|this year|next month|"
    r"next semester|next term|"
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december"
    r")\b",
    re.IGNORECASE,
)


def _is_long_period_hours(text: str, today=None) -> bool:
    """True only when the hours question can't be served live.

    Operator ruling (hr_thanksgiving): a SPECIFIC date <= ~1 month out
    IS answerable live (let the agent's get_hours handle that exact
    date) -> NOT long-period. A specific date further out (e.g.
    Thanksgiving 6 months away), a past date, or an open-ended range
    ("summer hours") -> long-period -> point-to-page + "too far ahead"
    explanation (PR #63).

    `today` is injectable for tests; the call site passes none ->
    real today.
    """
    t = text or ""
    # Short-term words always win (today/tonight/tomorrow -> live).
    if _SHORT_TERM_HOURS_RE.search(t):
        return False
    # Date-aware window check (the new bit).
    try:
        from datetime import date as _date
        from src.scope.date_window import resolve_target_date, within_window

        ref = today or _date.today()
        d = resolve_target_date(t, today=ref)
        if d is not None:
            # Specific date: live iff within the ~1-month window;
            # otherwise (far future OR in the past) -> long-period.
            return not within_window(d, today=ref)
    except Exception:  # noqa: BLE001 -- never let date logic break routing
        pass
    # No resolvable specific date -> fall back to open-ended phrasing.
    return bool(_LONG_PERIOD_HOURS_RE.search(t))


def _long_period_hours_response(
    classification: Classification,
    scope: Scope,
    latency_ms: int,
) -> TurnResponse:
    """Point a long-period hours question at the campus hours PAGE
    (rule B). Deterministic, zero-LLM, cited -> the URL is real and
    verified so it passes any downstream URL check."""
    url = _HOURS_PAGE_URL.get(scope.campus, _HOURS_PAGE_URL["oxford"])
    # Operator ruling 2026-05-17 (hr_thanksgiving): for a specific
    # holiday / far-off date the bot must EXPLAIN that the date is
    # beyond what it can check live and hand the lookup back to the
    # user -- not just drop a URL. (The complementary "<=1 month away
    # -> resolve the date + live LibCal lookup" branch is a deferred
    # follow-up: it needs a named-date/relative-date resolver and a
    # LibCal single-date call, which triggers the model/API freshness
    # rule. No current gold case exercises it; not bundled here.)
    msg = (
        "That's further out than I can look up live -- my hours check "
        "only covers the near term, and the schedule shifts by term, "
        "break, and holiday, so I can't reliably tell you that date "
        "myself. The library's hours page always shows the current and "
        f"upcoming schedule, so please check the date you need there: {url}."
    )
    return TurnResponse(
        answer=msg,
        is_refusal=False,
        refusal_trigger=None,
        citations=[{"n": 1, "url": url, "snippet": ""}],
        confidence="high",
        intent=classification.intent,
        scope=scope.as_filter(),
        model_used="(none -- long-period hours short-circuit)",
        tokens={"input": 0, "cached_input": 0, "output": 0},
        fired_corrections=[],
        agent_stopped_reason="point_to_url",
        latency_ms=latency_ms,
        cited_chunk_ids=[],
    )


def _capability_response(
    classification: Classification,
    scope: Scope,
    capability: IntentCapability,
    latency_ms: int,
    *,
    is_refusal: bool,
) -> TurnResponse:
    """Templated TurnResponse for POINT_TO_URL or REFUSE intents.

    The capability registry's `short_message` already includes the
    canonical URL, so we don't need synthesizer + post-processor to
    compose anything. The citation list is the canonical URL alone --
    the UI renders one citation chip linking to the right page.

    Zero LLM tokens consumed. Latency is just the routing path.
    """
    citations: list[dict] = []
    if capability.canonical_url:
        citations.append({
            "n": 1,
            "url": capability.canonical_url,
            "snippet": "",  # the short_message body already explains
        })

    return TurnResponse(
        answer=capability.short_message,
        is_refusal=is_refusal,
        refusal_trigger=capability.refusal_trigger or None,
        citations=citations,
        # Confidence is "high" for both POINT_TO_URL and REFUSE: the
        # response is deterministic (templated), so the bot is fully
        # confident in what it's emitting -- no LLM uncertainty here.
        confidence="high",
        intent=classification.intent,
        scope=scope.as_filter(),
        model_used="(none -- capability registry)",
        tokens={"input": 0, "cached_input": 0, "output": 0},
        fired_corrections=[],
        agent_stopped_reason=capability.tier.value,
        latency_ms=latency_ms,
        cited_chunk_ids=[],
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
