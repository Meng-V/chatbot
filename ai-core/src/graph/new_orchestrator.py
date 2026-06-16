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
    classification: Classification = deps.classifier.classify(request.user_message)
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
