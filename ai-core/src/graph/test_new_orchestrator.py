"""
Unit tests for the v2 orchestrator (`src.graph.new_orchestrator`).

Run: `python -m src.graph.test_new_orchestrator` from ai-core/.

The orchestrator is the integration point for every layer (scope,
classifier, agent, synthesizer, post-processor). Bugs here ripple
through every turn, so coverage is non-negotiable.

Tests use STUB DEPENDENCIES across the board:
  - Stub IntentKNN that returns a canned classification.
  - Stub agent LLM + tool registry whose tool calls are scripted.
  - Stub synthesizer LLM that returns canned structured output.
  - Stub corrections / allowlist / service-availability functions.
  - log_turn captured for assertions on telemetry shape.

Tests:
  1. Happy path: hours intent -> tool calls search_kb -> synthesizer
     returns answer -> TurnResponse.is_refusal=False, citations rendered.
  2. Clarification path: low-margin classifier short-circuits BEFORE
     calling the agent or synthesizer.
  3. Service-unavailable: refusal context wired through ->
     post-processor short-circuits to SERVICE_NOT_AT_BUILDING.
  4. Refusal path: synthesizer's confidence=low -> shaped response
     carries refusal_trigger.
  5. Token accumulation: agent + synthesizer tokens summed in response.
  6. _extract_evidence: pulls from `evidence` (new shape).
  7. _extract_evidence: also handles legacy `chunks` shape.
  8. _extract_evidence: ignores errored search_kb results.
  9. _extract_evidence: a tool result WITHOUT success is not promoted
     (preserves the LibCal-down refusal).
  9b. _tool_fact_evidence: get_hours/lookup_librarian/point_to_url
      SUCCESS -> trusted EvidenceChunk (kind, campus, source_url);
      failure / not-found -> []. search_kb crawled chunks come first.
 10. Reasoning intent (cross_campus_comparison) routes to gpt-5.2.
 11. Multi-hop evidence (>5 chunks, multi-topic) promotes to gpt-5.2.
 12. log_turn called with full telemetry payload.
 13. cited_chunk_ids surfaces from citations[] for librarian review join.
 14. Session origin URL resolves to campus default.
 15. Booking regressions (P3 live check 2026-07-14): dated availability
     QUESTIONS answer via get_room_availability (never book_room slot
     collection), and book_room args are back-filled with slots the
     user gave in earlier turns (LLM args win; confirm never filled).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Allow running from ai-core/ as `python -m src.graph.test_new_orchestrator`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.agent import AgentOutcome, AgentTurn  # noqa: E402
from src.agent.tool_registry import (  # noqa: E402
    Tool,
    ToolCall,
    ToolRegistry,
    ToolResult,
)
from src.graph.new_orchestrator import (  # noqa: E402
    OrchestratorDeps,
    TurnRequest,
    TurnResponse,
    _extract_evidence,
    _is_long_period_hours,
    _is_reasoning_intent,
    run_turn,
)
from src.router.intent_knn import Classification, IntentKNN  # noqa: E402
from src.synthesis.corrections import EvidenceChunk  # noqa: E402
from src.synthesis.post_processor import (  # noqa: E402
    Citation,
    PostProcessorResult,
    Refusal,
    SynthesizerOutput,
)
from src.synthesis.refusal_templates import RefusalContext, RefusalTrigger  # noqa: E402
from src.synthesis.synthesizer import SynthesisResult  # noqa: E402


# --- Stubs ---------------------------------------------------------------


class StubClassifier(IntentKNN):
    """IntentKNN that returns a hard-coded classification."""

    def __init__(self, classification: Classification):
        super().__init__(exemplars=[], embedder=lambda t: [0.0])
        self._cls = classification

    def classify(self, user_message: str) -> Classification:
        return self._cls


def _classification(
    intent: str = "hours",
    margin: float = 0.5,
    needs_clarification: bool = False,
    candidates: Optional[list] = None,
) -> Classification:
    return Classification(
        intent=intent,
        score=0.9,
        margin=margin,
        needs_clarification=needs_clarification,
        candidates=candidates or [(intent, 0.9), ("out_of_scope", 0.4)],
    )


def _stub_agent_llm_with_search(evidence_chunks: list[dict]):
    """Stub agent LLM that requests one search_kb call (yielding
    `evidence_chunks`), then terminates."""
    state = {"calls": 0}

    def call(*, prefix_id, messages, tools, model):
        state["calls"] += 1
        if state["calls"] == 1:
            # First call: request search_kb.
            return (
                {"role": "assistant", "content": None},
                [ToolCall(id="tc1", name="search_kb", arguments={"query": "q"})],
                {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20},
            )
        # Second call: terminal.
        return (
            {"role": "assistant", "content": "Drafted answer."},
            [],
            {"input_tokens": 110, "cached_input_tokens": 100, "output_tokens": 30},
        )

    return call


def _stub_search_kb_tool(canned_evidence: list[dict]) -> Tool:
    """Tool whose handler always returns `{"evidence": canned_evidence}`."""
    return Tool(
        name="search_kb",
        description="stub search",
        parameters={"type": "object"},
        handler=lambda args: {"evidence": list(canned_evidence)},
    )


def _stub_synth_llm(
    answer_text: str = "King opens at 7am [1].",
    confidence: str = "high",
    citations_n: Optional[list[int]] = None,
):
    """Stub synthesizer LLM. Returns a parsed-response dict + usage."""

    def call(*, prefix_id, dynamic_suffix, model):
        return (
            {
                "answer": answer_text,
                "citations": [
                    # No url -> parse_synthesizer_response back-fills it from
                    # evidence[n-1].source_url, mirroring how the real
                    # synthesizer cites a retrieved chunk's URL. Keeps the
                    # citation evidence-backed so the post-processor's A3
                    # "cited URL must be a real evidence source_url" check
                    # passes (a hardcoded https://lib/{n} would not match the
                    # evidence's https://lib/{chunk_id}).
                    {"n": n, "snippet": "..."}
                    for n in (citations_n or [1])
                ],
                "confidence": confidence,
            },
            {"input_tokens": 200, "cached_input_tokens": 180, "output_tokens": 40},
        )

    return call


def _build_deps(
    *,
    classification: Classification,
    evidence_in_search_kb_result: list[dict],
    synth_answer: str = "King opens at 7am [1].",
    synth_confidence: str = "high",
    synth_citations_n: Optional[list[int]] = None,
    service_refusal: Optional[RefusalContext] = None,
    log_capture: Optional[list] = None,
):
    registry = ToolRegistry()
    registry.register(_stub_search_kb_tool(evidence_in_search_kb_result))

    return OrchestratorDeps(
        classifier=StubClassifier(classification),
        tool_registry=registry,
        agent_llm=_stub_agent_llm_with_search(evidence_in_search_kb_result),
        synthesizer_llm=_stub_synth_llm(
            answer_text=synth_answer,
            confidence=synth_confidence,
            citations_n=synth_citations_n,
        ),
        load_corrections=lambda: [],
        load_url_allowlist=lambda: {f"https://lib/{n}" for n in (synth_citations_n or [1])},
        lookup_service_availability=lambda intent, campus: service_refusal,
        log_turn=(log_capture.append if log_capture is not None else (lambda _: None)),
    )


def _evidence_dict(
    chunk_id: str = "c1",
    *,
    campus: str = "oxford",
    library: str = "king",
    topic: Optional[str] = "hours",
) -> dict:
    return {
        "n": 1,
        "chunk_id": chunk_id,
        "source_url": f"https://lib/{chunk_id}",
        "snippet": "King opens 7am.",
        "campus": campus,
        "library": library,
        "topic": topic,
        "featured_service": None,
        "score": 0.9,
    }


# --- Tests ---------------------------------------------------------------


def test_happy_path_returns_answer() -> None:
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
        synth_citations_n=[1],
    )
    request = TurnRequest(
        user_message="What time does King close?",
        conversation_id="conv-1",
    )
    resp = run_turn(request, deps)
    assert not resp.is_refusal
    assert "King opens" in resp.answer
    assert resp.intent == "hours"
    assert resp.scope["campus"] == "oxford"
    assert len(resp.citations) == 1
    assert resp.citations[0]["n"] == 1
    assert resp.refusal_trigger is None


def test_clarification_short_circuits_before_agent() -> None:
    """Low-margin classification skips agent + synthesizer entirely."""
    cls = _classification(
        "hours", margin=0.01, needs_clarification=True,
        candidates=[("hours", 0.5), ("room_booking", 0.49)],
    )
    deps = _build_deps(
        classification=cls,
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(user_message="when?", conversation_id="conv-1")
    resp = run_turn(request, deps)
    # Clarification is not a refusal but has no real answer.
    assert resp.agent_stopped_reason == "clarify"
    assert resp.tokens["input"] == 0  # no LLM calls
    assert resp.confidence == "low"


# --- Capability-registry early-out paths --------------------------------


def test_databases_intent_short_circuits_to_a_z_page() -> None:
    """Per librarian decision: never look up DB by name. Always route
    to the A-Z list. Saves agent + synth tokens AND avoids the
    name-misspelling failure mode."""
    deps = _build_deps(
        classification=_classification("databases"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(
        user_message="do you have JSTOR",
        conversation_id="conv-1",
    )
    resp = run_turn(request, deps)
    assert not resp.is_refusal
    assert resp.agent_stopped_reason == "point_to_url"
    # Zero LLM tokens -- agent + synth skipped entirely.
    assert resp.tokens == {"input": 0, "cached_input": 0, "output": 0}
    # Citation is the A-Z page itself.
    assert len(resp.citations) == 1
    assert "az/databases" in resp.citations[0]["url"]
    assert "Databases A-Z" in resp.answer


def test_find_resource_intent_short_circuits_to_primo() -> None:
    deps = _build_deps(
        classification=_classification("find_resource"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(
        user_message="do you have a copy of Hamlet",
        conversation_id="conv-1",
    )
    resp = run_turn(request, deps)
    assert not resp.is_refusal
    assert resp.agent_stopped_reason == "point_to_url"
    assert resp.tokens["input"] == 0
    assert "primo" in resp.citations[0]["url"].lower()
    assert "Primo" in resp.answer
    # ILL fallback also mentioned for "we don't have it" path.
    assert "Interlibrary Loan" in resp.answer


def test_account_intent_short_circuits_with_privacy_refusal() -> None:
    deps = _build_deps(
        classification=_classification("account"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(
        user_message="how much do I owe?",
        conversation_id="conv-1",
    )
    resp = run_turn(request, deps)
    assert resp.is_refusal
    # Either trigger is acceptable -- both produce the same user-facing
    # refusal (MyAccount pointer). capability_scope's check_account
    # regex (added 2026-05-23) fires before intent_capabilities' account
    # tier; for "how much do I owe?" it's now the canonical path.
    assert resp.refusal_trigger in (
        "account_privacy",
        "capability_limitation:check_account",
    )
    assert resp.tokens["input"] == 0
    # Both refusal templates point to the same Primo MyAccount URL
    # ("MyAccount" link text on the intent_capabilities side; bare URL
    # on the capability_scope side). The URL is what matters.
    assert "ohiolink-mu.primo.exlibrisgroup.com/discovery/account" in resp.answer
    # Either "can't access" (intent_capabilities) or "don't have access"
    # (capability_scope) -- both express "I can't see your account".
    answer_lower = resp.answer.lower()
    assert ("can't access" in answer_lower) or ("don't have access" in answer_lower)


def test_events_news_intent_short_circuits_with_news_refusal() -> None:
    deps = _build_deps(
        classification=_classification("events_news"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(
        user_message="what events are happening this week",
        conversation_id="conv-1",
    )
    resp = run_turn(request, deps)
    assert resp.is_refusal
    assert resp.refusal_trigger == "news_excluded"
    assert resp.tokens["input"] == 0
    # The refusal must explain WHY (stale events would mislead).
    assert (
        "old event" in resp.answer.lower()
        or "stale" in resp.answer.lower()
    )
    # Points to the live News & Events page.
    assert "news-events" in resp.citations[0]["url"]


def test_capability_early_out_logs_telemetry() -> None:
    """The log_turn callback fires with the right shape even when the
    orchestrator short-circuits before the agent."""
    captured: list[dict] = []
    deps = _build_deps(
        classification=_classification("databases"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
        log_capture=captured,
    )
    # The orchestrator's log_turn is invoked from the agent path; for
    # short-circuit responses we don't currently call it (the response
    # IS the log). This test pins that behavior so a future change to
    # log short-circuits is intentional, not accidental.
    request = TurnRequest(user_message="any", conversation_id="conv-1")
    resp = run_turn(request, deps)
    assert resp.intent == "databases"
    assert resp.agent_stopped_reason == "point_to_url"
    # No log_turn call yet for short-circuits -- documented behavior.
    # If we add it later, change this assertion in the same PR.
    assert captured == []


def test_service_unavailable_short_circuits_to_refusal() -> None:
    """If the service isn't offered at this campus, post-processor
    short-circuits to SERVICE_NOT_AT_BUILDING regardless of
    synthesizer output."""
    refusal_ctx = RefusalContext(
        campus_display="Hamilton",
        service_name="MakerSpace",
        service_available_at="King Library on the Oxford campus",
    )
    deps = _build_deps(
        classification=_classification("makerspace_3d"),
        evidence_in_search_kb_result=[_evidence_dict("c1", campus="oxford")],
        service_refusal=refusal_ctx,
    )
    request = TurnRequest(
        user_message="MakerSpace at Hamilton?",
        conversation_id="conv-1",
        session_origin_url="https://ham.miamioh.edu/library/",
    )
    resp = run_turn(request, deps)
    assert resp.is_refusal
    assert resp.refusal_trigger == RefusalTrigger.SERVICE_NOT_AT_BUILDING.value
    assert "MakerSpace" in resp.answer


def test_low_confidence_synthesis_becomes_refusal() -> None:
    """Synthesizer-flagged low confidence -> post-processor refuses."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
        synth_confidence="low",
    )
    request = TurnRequest(user_message="q", conversation_id="conv-1")
    resp = run_turn(request, deps)
    assert resp.is_refusal
    assert resp.refusal_trigger == RefusalTrigger.MODEL_SELF_FLAGGED.value


def test_token_accumulation() -> None:
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    request = TurnRequest(user_message="q", conversation_id="conv-1")
    resp = run_turn(request, deps)
    # Agent: 100+110=210 input, 80+100=180 cached, 20+30=50 output.
    # Synth: 200 / 180 / 40.
    # Sum: 410 / 360 / 90.
    assert resp.tokens["input"] == 410
    assert resp.tokens["cached_input"] == 360
    assert resp.tokens["output"] == 90


# --- _extract_evidence direct tests ---


def test_extract_evidence_handles_new_evidence_shape() -> None:
    """The current search_kb_tool returns `{"evidence": [...]}` with
    `snippet` per item. Orchestrator must read this shape."""
    outcome = AgentOutcome(
        terminal_message={"role": "assistant", "content": "x"},
        turns=[
            AgentTurn(
                iteration=0,
                llm_message={"role": "assistant"},
                tool_calls=[ToolCall(id="t1", name="search_kb", arguments={})],
                tool_results=[
                    ToolResult(
                        call_id="t1", name="search_kb",
                        data={"evidence": [_evidence_dict("c1")]},
                    )
                ],
            ),
        ],
        stopped_reason="clean",
    )
    ev = _extract_evidence(outcome)
    assert len(ev) == 1
    assert ev[0].chunk_id == "c1"
    assert ev[0].text == "King opens 7am."  # snippet -> text mapping
    assert ev[0].campus == "oxford"


def test_extract_evidence_falls_back_to_legacy_chunks_shape() -> None:
    """Older fixtures may emit `{"chunks": [...]}` with `text`. Must
    still work for backwards compat."""
    outcome = AgentOutcome(
        terminal_message={"role": "assistant", "content": "x"},
        turns=[
            AgentTurn(
                iteration=0,
                llm_message={"role": "assistant"},
                tool_calls=[ToolCall(id="t1", name="search_kb", arguments={})],
                tool_results=[
                    ToolResult(
                        call_id="t1", name="search_kb",
                        data={
                            "chunks": [
                                {
                                    "chunk_id": "c1",
                                    "source_url": "https://lib/c1",
                                    "text": "Legacy text.",
                                    "campus": "oxford",
                                    "library": "king",
                                }
                            ]
                        },
                    )
                ],
            ),
        ],
        stopped_reason="clean",
    )
    ev = _extract_evidence(outcome)
    assert len(ev) == 1
    assert ev[0].text == "Legacy text."


def test_extract_evidence_drops_denylisted_urls() -> None:
    """The COVID-era libraryhealthy pages must never reach the
    synthesizer (operator ruling 2026-07-14: an Adobe answer cited
    /libraryhealthy/virtual/ next to the authoritative /software/)."""
    healthy = _evidence_dict("bad")
    healthy["source_url"] = "https://www.lib.miamioh.edu/libraryhealthy/virtual/"
    outcome = AgentOutcome(
        terminal_message={"role": "assistant", "content": "x"},
        turns=[
            AgentTurn(
                iteration=0,
                llm_message={"role": "assistant"},
                tool_calls=[ToolCall(id="t1", name="search_kb", arguments={})],
                tool_results=[
                    ToolResult(
                        call_id="t1", name="search_kb",
                        data={"evidence": [_evidence_dict("good"), healthy]},
                    )
                ],
            ),
        ],
        stopped_reason="clean",
    )
    ev = _extract_evidence(outcome)
    assert [c.chunk_id for c in ev] == ["good"]


def test_renumber_merges_same_url_citations() -> None:
    """Two citations to the SAME page must render as one Sources row
    (operator report 2026-07-14: '[1] .../software/ [2] .../software/')."""
    from src.graph.new_orchestrator import _renumber_citations_for_display
    answer = "Get Adobe via Software Checkout [1] [2] [3]."
    citations = [
        {"n": 1, "url": "https://www.lib.miamioh.edu/software/", "snippet": "a"},
        {"n": 2, "url": "https://www.lib.miamioh.edu/software/", "snippet": "b"},
        {"n": 3, "url": "https://www.lib.miamioh.edu/tech/", "snippet": "c"},
    ]
    new_answer, new_cites = _renumber_citations_for_display(answer, citations)
    assert new_answer == "Get Adobe via Software Checkout [1] [2]."
    assert [c["url"] for c in new_cites] == [
        "https://www.lib.miamioh.edu/software/",
        "https://www.lib.miamioh.edu/tech/",
    ]
    assert [c["n"] for c in new_cites] == [1, 2]


def test_renumber_still_orders_by_first_appearance() -> None:
    from src.graph.new_orchestrator import _renumber_citations_for_display
    answer = "See [5] and [2]."
    citations = [
        {"n": 2, "url": "https://lib/b", "snippet": "b"},
        {"n": 5, "url": "https://lib/a", "snippet": "a"},
    ]
    new_answer, new_cites = _renumber_citations_for_display(answer, citations)
    assert new_answer == "See [1] and [2]."
    assert [c["url"] for c in new_cites] == ["https://lib/a", "https://lib/b"]


def test_extract_evidence_skips_errored_search_kb() -> None:
    outcome = AgentOutcome(
        terminal_message={"role": "assistant", "content": "x"},
        turns=[
            AgentTurn(
                iteration=0,
                llm_message={"role": "assistant"},
                tool_calls=[ToolCall(id="t1", name="search_kb", arguments={})],
                tool_results=[
                    ToolResult(call_id="t1", name="search_kb", error="Weaviate down"),
                ],
            ),
        ],
        stopped_reason="clean",
    )
    ev = _extract_evidence(outcome)
    assert ev == []


def _turn(*results) -> AgentOutcome:
    return AgentOutcome(
        terminal_message={"role": "assistant", "content": "x"},
        turns=[AgentTurn(
            iteration=0, llm_message={"role": "assistant"},
            tool_calls=[], tool_results=list(results),
        )],
        stopped_reason="clean",
    )


def test_extract_evidence_skips_unsuccessful_tool_results() -> None:
    """A get_hours result WITHOUT success (e.g. LibCal down) must NOT
    become evidence -- the bot has to still refuse (gold:
    hr_libcal_down_refusal). search_kb is still extracted."""
    outcome = _turn(
        ToolResult(call_id="t1", name="get_hours",
                   data={"success": False, "hours": "couldn't retrieve"}),
        ToolResult(call_id="t2", name="search_kb",
                   data={"evidence": [_evidence_dict("c-search")]}),
    )
    ev = _extract_evidence(outcome)
    assert [c.chunk_id for c in ev] == ["c-search"]


def test_extract_evidence_promotes_get_hours_success() -> None:
    """The core fix: a successful get_hours becomes a trusted
    live_api EvidenceChunk with real campus + source_url, so the
    synthesizer can actually answer 'closed today' instead of
    refusing for no evidence."""
    outcome = _turn(ToolResult(
        call_id="t1", name="get_hours",
        data={"success": True, "library": "king",
              "hours": "King — Fri 2026-05-16: Closed",
              "source_url": "https://www.lib.miamioh.edu/about/hours/"},
    ))
    ev = _extract_evidence(outcome)
    assert len(ev) == 1
    c = ev[0]
    assert c.kind == "live_api"
    assert c.campus == "oxford"            # cross-campus guard tag
    assert "Closed" in c.text              # "Closed" is a real answer
    assert c.source_url.endswith("/about/hours/")
    assert c.chunk_id == "tool:get_hours:king"


def test_extract_evidence_promotes_librarian_and_pointer() -> None:
    outcome = _turn(
        ToolResult(call_id="t1", name="lookup_librarian", data={
            "librarians": [{"name": "Ginny Boehme", "title": "Librarian",
                            "department": "Sciences",
                            "email": "boehmevm@miamioh.edu",
                            "phone": "513-529-1234", "campus": "Oxford",
                            "profile_url": "https://lib/p/ginny"}],
            "count": 1}),
        ToolResult(call_id="t2", name="point_to_url", data={
            "service": "ill", "url": "https://www.lib.miamioh.edu/use/borrow/ill/",
            "found": True, "description": "ILL form."}),
    )
    ev = _extract_evidence(outcome)
    kinds = {c.chunk_id: c for c in ev}
    lib = kinds["tool:lookup_librarian:boehmevm@miamioh.edu"]
    assert lib.kind == "authoritative_db"
    assert "boehmevm@miamioh.edu" in lib.text   # exact email surfaced
    assert lib.campus == "oxford"
    ptr = kinds["tool:point_to_url:ill"]
    assert ptr.kind == "authoritative_db"
    assert ptr.campus == "all"                  # university-wide
    assert ptr.source_url.endswith("/use/borrow/ill/")


def test_extract_evidence_pointer_not_found_not_promoted() -> None:
    outcome = _turn(ToolResult(
        call_id="t1", name="point_to_url",
        data={"service": "teleport", "url": None, "found": False},
    ))
    assert _extract_evidence(outcome) == []


def test_extract_evidence_crawled_first_then_tool_facts() -> None:
    outcome = _turn(
        ToolResult(call_id="t1", name="search_kb",
                   data={"evidence": [_evidence_dict("c-search")]}),
        ToolResult(call_id="t2", name="get_hours",
                   data={"success": True, "library": "rentschler",
                         "hours": "open", "source_url": "https://lib/h"}),
    )
    ev = _extract_evidence(outcome)
    assert [c.chunk_id for c in ev] == [
        "c-search", "tool:get_hours:rentschler",
    ]
    assert ev[1].campus == "hamilton"   # rentschler -> hamilton


# --- Model routing ---


def test_reasoning_intent_routes_to_gpt_5_2() -> None:
    assert _is_reasoning_intent("cross_campus_comparison") is True
    assert _is_reasoning_intent("loan_policy") is True
    assert _is_reasoning_intent("research_consultation") is True
    assert _is_reasoning_intent("hours") is False
    assert _is_reasoning_intent("interlibrary_loan") is False


# --- Telemetry / log_turn ---


def test_log_turn_called_with_full_payload() -> None:
    captured: list[dict] = []
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
        log_capture=captured,
    )
    request = TurnRequest(user_message="q", conversation_id="conv-1")
    run_turn(request, deps)
    assert len(captured) == 1
    payload = captured[0]
    # Required fields per Op 3 telemetry list.
    for key in (
        "conversation_id",
        "intent",
        "scope",
        "model_used",
        "tokens",
        "confidence",
        "was_refusal",
        "refusal_trigger",
        "cited_chunk_ids",
        "fired_corrections",
        "agent_stopped_reason",
        "latency_ms",
    ):
        assert key in payload, f"missing {key} from log_turn payload"
    assert payload["intent"] == "hours"
    assert payload["was_refusal"] is False


def test_cited_chunk_ids_surfaces_for_librarian_review() -> None:
    """Message.cited_chunk_ids is the join key from a logged turn back
    to ChunkProvenance for forensic review (Op 1). Must be populated
    on success path."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c-real")],
        synth_citations_n=[1],
    )
    request = TurnRequest(user_message="q", conversation_id="conv-1")
    resp = run_turn(request, deps)
    # The synthesizer joined citations[1] back to evidence[0]
    # (chunk_id=c-real); cited_chunk_ids reflects that.
    assert resp.cited_chunk_ids == ["c-real"]


def test_session_origin_url_resolves_campus_default() -> None:
    """A request from ham.miamioh.edu defaults scope.campus=hamilton
    when the message doesn't otherwise specify."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1", campus="hamilton", library="rentschler")],
        synth_citations_n=[1],
    )
    request = TurnRequest(
        user_message="when does the library open today?",
        conversation_id="conv-1",
        session_origin_url="https://ham.miamioh.edu/library/",
    )
    resp = run_turn(request, deps)
    assert resp.scope["campus"] == "hamilton"


# --- Rule B: long-period hours -> hours PAGE, not LibCal ---


def test_is_long_period_hours_detector() -> None:
    LP = _is_long_period_hours
    assert LP("What are the summer hours at King?")
    assert LP("Is Rentschler open during winter break?")
    assert LP("hours this semester?")
    assert LP("library hours in December")
    # Short-term words VETO (LibCal handles those correctly):
    assert not LP("Is the library open right now?")
    assert not LP("what time does King close today")
    assert not LP("hours tonight")
    assert not LP("are you open tomorrow")
    # No period marker at all -> not long-period:
    assert not LP("what are the hours")


def test_long_period_hours_short_circuits_to_oxford_page() -> None:
    """Operator rule B: a summer/semester hours question must point to
    the hours PAGE (LibCal is date-window-limited), zero LLM, before
    any clarify/agent step."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    resp = run_turn(
        TurnRequest(user_message="What are the summer hours at King?",
                    conversation_id="c1"),
        deps,
    )
    assert not resp.is_refusal
    assert resp.agent_stopped_reason == "point_to_url"
    assert resp.tokens == {"input": 0, "cached_input": 0, "output": 0}
    assert len(resp.citations) == 1
    assert resp.citations[0]["url"] == (
        "https://www.lib.miamioh.edu/about/locations/hours/"
    )


def test_long_period_hours_resolves_campus() -> None:
    """Campus-correct: a Hamilton long-period hours question points to
    the Hamilton hours page, not Oxford's."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    resp = run_turn(
        TurnRequest(
            user_message="Is Rentschler open during winter break?",
            conversation_id="c1",
        ),
        deps,
    )
    assert resp.agent_stopped_reason == "point_to_url"
    assert resp.scope["campus"] == "hamilton"
    assert resp.citations[0]["url"] == (
        "https://www.ham.miamioh.edu/library/about/hours/"
    )


def test_short_term_hours_not_short_circuited() -> None:
    """'open right now' must still go to the agent/LibCal path, NOT
    the hours-page short-circuit."""
    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    resp = run_turn(
        TurnRequest(user_message="Is the library open right now?",
                    conversation_id="c1"),
        deps,
    )
    assert resp.agent_stopped_reason != "point_to_url" or any(
        "about/locations/hours" not in (c.get("url") or "")
        for c in resp.citations
    )


# --- Rule A: bare library-bound question -> King@Oxford, no clarify ---


def test_rule_a_bare_question_defaults_king_no_clarify() -> None:
    """Operator rule A: when no library/campus is named, default to
    King (Oxford flagship) and ANSWER -- never ask 'which library?'.
    This is already implemented in resolve_scope; this test LOCKS it
    so a future clarify-gate change can't silently regress it."""
    from src.scope.resolver import resolve_scope

    s = resolve_scope("what are the hours")
    assert s.campus == "oxford"
    assert s.library is None
    assert s.source == "default"

    deps = _build_deps(
        classification=_classification("hours"),
        evidence_in_search_kb_result=[_evidence_dict("c1")],
    )
    resp = run_turn(
        TurnRequest(user_message="what are the hours",
                    conversation_id="c1"),
        deps,
    )
    # Did NOT clarify, and resolved to the King/Oxford default.
    assert resp.agent_stopped_reason != "clarify"
    assert resp.scope["campus"] == "oxford"
    assert resp.scope.get("library") in (None, "")


# --- Booking flow: availability questions + slot accumulation -------------
# Regressions for the P3 live check 2026-07-14:
#   1. An availability QUESTION ("What study rooms are available at King
#      tomorrow from 9am to 10am?") entered book_room's slot-collection
#      flow instead of listing open rooms.
#   2. Slot accumulation was leaky: turn 1's date/times were dropped
#      when turn 2 supplied name/email, and the flow re-asked for them.


_BOOKING_HISTORY = [
    {"role": "user",
     "content": "Book a study room at King tomorrow from 9am to 10am."},
    {"role": "assistant",
     "content": ("To complete your room reservation, I still need: your "
                 "first name, last name, and @miamioh.edu email.")},
]


def _stub_agent_llm_book_room(book_args: dict):
    """Stub agent LLM that calls book_room once with `book_args` (the
    args the LIVE model was observed passing -- current-turn details
    only), then terminates."""
    state = {"calls": 0}

    def call(*, prefix_id, messages, tools, model):
        state["calls"] += 1
        if state["calls"] == 1:
            return (
                {"role": "assistant", "content": None},
                [ToolCall(id="bk1", name="book_room",
                          arguments=dict(book_args))],
                {"input_tokens": 100, "cached_input_tokens": 0,
                 "output_tokens": 10},
            )
        return (
            {"role": "assistant", "content": "done"},
            [],
            {"input_tokens": 10, "cached_input_tokens": 0,
             "output_tokens": 5},
        )

    return call


def _no_llm(*, prefix_id, dynamic_suffix=None, messages=None, tools=None,
            model=None):
    raise AssertionError("LLM must not be called on this path")


def _booking_registry(
    book_calls: list,
    avail_calls: Optional[list] = None,
    avail_raises: bool = False,
) -> ToolRegistry:
    """Registry with book_room + get_room_availability stubs that mimic
    real_backends' return shapes and capture their args."""
    from src.agent.tool_registry import ToolError

    registry = ToolRegistry()

    def book_handler(args: dict) -> dict:
        book_calls.append(dict(args))
        required = ("date", "start_time", "end_time",
                    "first_name", "last_name", "email")
        missing = [k for k in required if not args.get(k)]
        if missing:
            return {"success": False, "stage": "missing_slots",
                    "text": ("To complete your room reservation, I still "
                             "need: " + ", ".join(missing))}
        if not args.get("confirm"):
            return {"success": False, "stage": "needs_confirmation",
                    "text": (f"Ready to book: a study room at King Library "
                             f"on {args['date']}, {args['start_time']} to "
                             f"{args['end_time']}, for {args['first_name']} "
                             f"{args['last_name']} ({args['email']}). Reply "
                             f"'confirm' to book it. Nothing is booked yet.")}
        return {"success": True, "stage": "booked",
                "text": "Booked! Confirmation: abc123"}

    def avail_handler(args: dict) -> dict:
        if avail_calls is not None:
            avail_calls.append(dict(args))
        if avail_raises:
            raise ToolError("LibCal down")
        return {"slots": [{"success": True,
                           "text": ("Available rooms at King Library:\n\n"
                                    "• Room 205 (capacity: 4)")}],
                "count": 1}

    registry.register(Tool(
        name="book_room", description="stub booking",
        parameters={"type": "object"}, handler=book_handler,
        is_read_only=False,
    ))
    registry.register(Tool(
        name="get_room_availability", description="stub availability",
        parameters={"type": "object"}, handler=avail_handler,
    ))
    registry.register(_stub_search_kb_tool([]))
    return registry


def _booking_deps(registry: ToolRegistry, agent_llm,
                  intent: str = "room_booking") -> OrchestratorDeps:
    return OrchestratorDeps(
        classifier=StubClassifier(_classification(intent)),
        tool_registry=registry,
        agent_llm=agent_llm,
        synthesizer_llm=_stub_synth_llm(),
        load_corrections=lambda: [],
        load_url_allowlist=lambda: set(),
        lookup_service_availability=lambda intent, campus: None,
    )


def test_availability_question_answers_with_availability_tool() -> None:
    """P3 defect #1: a dated availability QUESTION must list open rooms
    via get_room_availability -- never enter book_room slot collection."""
    book_calls: list = []
    avail_calls: list = []
    deps = _booking_deps(
        _booking_registry(book_calls, avail_calls),
        agent_llm=_no_llm,  # deterministic path -- no LLM at all
    )
    resp = run_turn(
        TurnRequest(
            user_message=("What study rooms are available at King tomorrow "
                          "from 9am to 10am?"),
            conversation_id="c1",
        ),
        deps,
    )
    assert resp.agent_stopped_reason == "room_availability_short_circuit"
    assert not resp.is_refusal
    assert "Room 205" in resp.answer
    assert "I still need" not in resp.answer      # no slot collection
    assert book_calls == []                       # book_room never ran
    assert resp.tokens == {"input": 0, "cached_input": 0, "output": 0}
    # The live lookup got the question's window, verbatim slots.
    assert len(avail_calls) == 1
    call = avail_calls[0]
    assert call["library"] == "king"
    assert call["date"] == "tomorrow"
    assert call["start_time"] == "9am"
    assert call["end_time"] == "10am"
    # Citation: the reservation page (allspaces for King).
    assert resp.citations[0]["url"] == "https://muohio.libcal.com/allspaces"


def test_availability_question_without_window_points_to_page() -> None:
    """Dated availability question WITHOUT a start/end window: the live
    grid can't be queried, so point at the reservation page -- still no
    booking flow."""
    book_calls: list = []
    deps = _booking_deps(_booking_registry(book_calls), agent_llm=_no_llm)
    resp = run_turn(
        TurnRequest(
            user_message="Are there any study rooms available tomorrow?",
            conversation_id="c1",
        ),
        deps,
    )
    assert resp.agent_stopped_reason == "room_availability_short_circuit"
    assert "reservation page" in resp.answer
    assert book_calls == []
    assert resp.citations[0]["url"] == "https://muohio.libcal.com/allspaces"


def test_availability_libcal_down_degrades_to_pointer() -> None:
    """LibCal error on the availability lookup degrades to the
    reservation-page pointer, not a crash and not the booking flow."""
    book_calls: list = []
    deps = _booking_deps(
        _booking_registry(book_calls, avail_raises=True), agent_llm=_no_llm,
    )
    resp = run_turn(
        TurnRequest(
            user_message=("What rooms are available at King tomorrow from "
                          "9am to 10am?"),
            conversation_id="c1",
        ),
        deps,
    )
    assert resp.agent_stopped_reason == "room_availability_short_circuit"
    assert "reservation page" in resp.answer
    assert book_calls == []


def test_availability_detector_boundaries() -> None:
    """Booking requests and undated existence questions must NOT be
    hijacked by the availability short-circuit."""
    from src.graph.new_orchestrator import _room_availability_answer
    from src.scope.resolver import resolve_scope

    deps = _booking_deps(_booking_registry([]), agent_llm=_no_llm)

    def helper(msg):
        return _room_availability_answer(msg, resolve_scope(msg), deps)

    # Booking verb -> the agent's book_room flow keeps it.
    assert helper("Book me a study room tomorrow from 9am to 10am") is None
    assert helper("Can I reserve a room that's available tomorrow?") is None
    # Undated existence question -> agent / 2.14 pointer keep it.
    assert helper("Are there study rooms available at King?") is None
    # Cancel and other-space questions fall through too.
    assert helper("Is my cancelled room still available tomorrow?") is None
    assert helper(
        "Any rooms available at Special Collections tomorrow 1pm to 2pm?"
    ) is None
    # Regional campus resolves the regional reservation page.
    res = helper("What rooms are free at Rentschler tomorrow 1pm to 2pm?")
    assert res is not None
    _ans, _cites = res
    assert _cites[0]["url"] == "https://muohio.libcal.com/reserve/hamilton"


def test_booking_slots_accumulate_across_turns() -> None:
    """P3 defect #2: turn 1 gave date + times, turn 2 gives name/email.
    The live model passed only current-turn details to book_room; the
    slot-filling registry must back-fill turn 1's date/start/end so the
    flow advances to the confirmation summary instead of re-asking."""
    book_calls: list = []
    registry = _booking_registry(book_calls)
    # The LIVE failure: model drops earlier-turn slots from the args.
    agent_llm = _stub_agent_llm_book_room({
        "building": "King", "first_name": "Meng", "last_name": "Qu",
        "email": "qum@miamioh.edu", "room_capacity": 3,
    })
    # Classifier returns out_of_scope (the mid-flow message has no
    # library vocabulary) -- the booking-flow override must force
    # room_booking AND the merge must still apply.
    deps = _booking_deps(registry, agent_llm, intent="out_of_scope")
    resp = run_turn(
        TurnRequest(
            user_message="My name is Meng Qu, email qum@miamioh.edu, party of 3.",
            conversation_id="c1",
            conversation_history=list(_BOOKING_HISTORY),
        ),
        deps,
    )
    assert len(book_calls) == 1
    merged = book_calls[0]
    # Earlier-turn slots survived:
    assert merged["date"] == "tomorrow"
    assert merged["start_time"] == "9am"
    assert merged["end_time"] == "10am"
    # Current-turn slots kept:
    assert merged["first_name"] == "Meng"
    assert merged["email"] == "qum@miamioh.edu"
    # confirm is NEVER auto-filled -- nothing books without the user.
    assert not merged.get("confirm")
    # And the reply is the confirmation summary, not a re-ask.
    assert "Ready to book" in resp.answer
    assert "I still need" not in resp.answer
    assert resp.intent == "room_booking"   # override held


def test_booking_slot_merge_never_overrides_llm_args() -> None:
    """An in-flow correction ('actually 2pm to 3pm') that the LLM passes
    must win over the extracted history slots."""
    book_calls: list = []
    registry = _booking_registry(book_calls)
    agent_llm = _stub_agent_llm_book_room({
        "building": "King", "first_name": "Meng", "last_name": "Qu",
        "email": "qum@miamioh.edu",
        "start_time": "2pm", "end_time": "3pm",   # the LLM's own args
    })
    deps = _booking_deps(registry, agent_llm, intent="out_of_scope")
    run_turn(
        TurnRequest(
            user_message=("Actually make it 2pm to 3pm. My name is Meng Qu, "
                          "email qum@miamioh.edu."),
            conversation_id="c1",
            conversation_history=list(_BOOKING_HISTORY),
        ),
        deps,
    )
    merged = book_calls[0]
    assert merged["start_time"] == "2pm"    # LLM/current turn wins
    assert merged["end_time"] == "3pm"
    assert merged["date"] == "tomorrow"     # still back-filled


def test_availability_short_circuit_skipped_mid_booking_flow() -> None:
    """Mid-booking-flow, '9am to 10am, any room available?' is a
    slot-fill -- it must reach the agent, not the availability
    short-circuit."""
    book_calls: list = []
    registry = _booking_registry(book_calls)
    agent_llm = _stub_agent_llm_book_room({"building": "King"})
    deps = _booking_deps(registry, agent_llm, intent="out_of_scope")
    resp = run_turn(
        TurnRequest(
            user_message="9am to 10am tomorrow -- any room available?",
            conversation_id="c1",
            conversation_history=list(_BOOKING_HISTORY),
        ),
        deps,
    )
    assert resp.agent_stopped_reason != "room_availability_short_circuit"
    assert len(book_calls) == 1              # the agent's flow ran


def test_extract_booking_slots_patterns() -> None:
    from src.graph.new_orchestrator import _extract_booking_slots

    slots = _extract_booking_slots([
        "Book a study room at King tomorrow from 9am to 10am",
        "My name is Meng Qu, email qum@miamioh.edu, party of 3",
    ])
    assert slots == {
        "building": "King", "date": "tomorrow",
        "start_time": "9am", "end_time": "10am",
        "email": "qum@miamioh.edu", "room_capacity": 3,
        "first_name": "Meng", "last_name": "Qu",
    }
    # Later mentions override earlier ones.
    assert _extract_booking_slots(
        ["tomorrow 9am to 10am", "actually Friday 2pm to 3pm"]
    ) == {"date": "Friday", "start_time": "2pm", "end_time": "3pm"}
    # Meridiem-less start inherits the end's; bare "9 to 10" never matches.
    assert _extract_booking_slots(["9 to 10am works"])["start_time"] == "9am"
    assert "start_time" not in _extract_booking_slots(["rooms for 9 to 10"])
    # "I'm looking for a room" is NOT a name.
    assert _extract_booking_slots(["I'm looking for a room"]) == {}


def main() -> int:
    tests = [
        test_rule_a_bare_question_defaults_king_no_clarify,
        test_is_long_period_hours_detector,
        test_long_period_hours_short_circuits_to_oxford_page,
        test_long_period_hours_resolves_campus,
        test_short_term_hours_not_short_circuited,
        test_happy_path_returns_answer,
        test_clarification_short_circuits_before_agent,
        test_databases_intent_short_circuits_to_a_z_page,
        test_find_resource_intent_short_circuits_to_primo,
        test_account_intent_short_circuits_with_privacy_refusal,
        test_events_news_intent_short_circuits_with_news_refusal,
        test_capability_early_out_logs_telemetry,
        test_service_unavailable_short_circuits_to_refusal,
        test_low_confidence_synthesis_becomes_refusal,
        test_token_accumulation,
        test_extract_evidence_handles_new_evidence_shape,
        test_extract_evidence_falls_back_to_legacy_chunks_shape,
        test_extract_evidence_skips_errored_search_kb,
        test_extract_evidence_skips_unsuccessful_tool_results,
        test_extract_evidence_promotes_get_hours_success,
        test_extract_evidence_promotes_librarian_and_pointer,
        test_extract_evidence_pointer_not_found_not_promoted,
        test_extract_evidence_crawled_first_then_tool_facts,
        test_reasoning_intent_routes_to_gpt_5_2,
        test_log_turn_called_with_full_payload,
        test_cited_chunk_ids_surfaces_for_librarian_review,
        test_session_origin_url_resolves_campus_default,
        test_availability_question_answers_with_availability_tool,
        test_availability_question_without_window_points_to_page,
        test_availability_libcal_down_degrades_to_pointer,
        test_availability_detector_boundaries,
        test_booking_slots_accumulate_across_turns,
        test_booking_slot_merge_never_overrides_llm_args,
        test_availability_short_circuit_skipped_mid_booking_flow,
        test_extract_booking_slots_patterns,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
