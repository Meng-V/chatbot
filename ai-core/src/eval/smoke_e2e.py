"""
End-to-end smoke test for the v2 stack.

Wires REAL instances of every layer (scope resolver, classifier,
agent loop, retrieval, synthesizer, post-processor, capability
registry) with STUB instances of the only two external dependencies:
  - LLM (OpenAI client) -- canned responses per call site
  - Weaviate -- canned hits per scope

Then runs a small fixture set of representative questions through
`run_turn` and asserts each took the expected path through the
orchestrator. Catches the class of bugs where every individual unit
test passes but the wires between them have drifted.

Six paths the orchestrator can take, all covered:
  1. clarify              kNN margin too low -> ask the user
  2. point_to_url          capability registry routes to a URL
                           (databases -> A-Z; find_resource -> Primo)
  3. refuse                capability registry refuses with an
                           explanation (account -> privacy;
                           events_news -> excluded by ETL design)
  4. service_unavailable   service-not-at-building (e.g. MakerSpace
                           at Hamilton) short-circuits before agent
  5. agent_then_answer     full path: classify -> agent -> evidence
                           -> synth -> post-processor -> answer
  6. agent_then_refusal    agent ran but synth/post-processor
                           refused (low confidence, no_results, etc.)

Run:
    python -m src.eval.smoke_e2e

Exit code: 0 if all paths take the expected route, 1 otherwise.
Useful as a CI gate -- runs in <500ms (no real LLM/Weaviate calls).

See plan: timeline week 4 ("Gate to advance: cache-hit rate ... +
total cost per question ...") -- this is the cheaper prelude that
verifies the wiring before the cost gate makes sense.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Allow `python -m src.eval.smoke_e2e` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.tool_registry import (  # noqa: E402
    Tool,
    ToolCall,
    ToolRegistry,
)
from src.graph.new_orchestrator import (  # noqa: E402
    OrchestratorDeps,
    TurnRequest,
    TurnResponse,
    run_turn,
)
from src.router.intent_knn import Classification, IntentKNN  # noqa: E402
from src.synthesis.refusal_templates import RefusalContext  # noqa: E402


# --- Stub LLMs ----------------------------------------------------------


class CannedAgentLLM:
    """Stub agent LLM. Returns a scripted (message, tool_calls, usage)
    per call. Cycles to terminal after one search_kb tool round-trip."""

    def __init__(
        self,
        *,
        request_search_kb: bool = True,
        terminal_text: str = "Drafted from evidence.",
    ):
        self._request_search_kb = request_search_kb
        self._terminal_text = terminal_text
        self._calls = 0

    def __call__(self, *, prefix_id, messages, tools, model):
        self._calls += 1
        if self._calls == 1 and self._request_search_kb:
            # First call: request search_kb so the orchestrator's
            # _extract_evidence path runs against real wiring.
            return (
                {"role": "assistant", "content": None},
                [ToolCall(id="tc1", name="search_kb", arguments={"query": "q"})],
                {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20},
            )
        return (
            {"role": "assistant", "content": self._terminal_text},
            [],
            {"input_tokens": 110, "cached_input_tokens": 100, "output_tokens": 30},
        )


class CannedSynthesizerLLM:
    """Stub synthesizer LLM. Returns canned structured output."""

    def __init__(
        self,
        *,
        answer: str = "King opens at 7am [1].",
        confidence: str = "high",
        citations_n: Optional[list[int]] = None,
    ):
        self._answer = answer
        self._confidence = confidence
        self._citations_n = citations_n or [1]

    def __call__(self, *, prefix_id, dynamic_suffix, model):
        return (
            {
                "answer": self._answer,
                "citations": [
                    {
                        "n": n,
                        "url": f"https://lib.miamioh.edu/king/cite-{n}/",
                        "snippet": "Hours snippet.",
                    }
                    for n in self._citations_n
                ],
                "confidence": self._confidence,
            },
            {
                "input_tokens": 200,
                "cached_input_tokens": 180,
                "output_tokens": 40,
            },
        )


# --- Stub classifier ----------------------------------------------------


class CannedClassifier(IntentKNN):
    """Returns a hard-coded Classification."""

    def __init__(self, classification: Classification):
        super().__init__(exemplars=[], embedder=lambda t: [0.0])
        self._cls = classification

    def classify(self, user_message: str) -> Classification:
        return self._cls


def _classification(
    intent: str,
    *,
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


# --- Stub tool registry --------------------------------------------------


def _make_search_kb_tool_with_canned(evidence_items: list[dict]) -> Tool:
    """Mimics src.tools.search_kb_tool's wire shape."""
    return Tool(
        name="search_kb",
        description="(stub) search the library knowledge base",
        parameters={"type": "object"},
        handler=lambda args: {"evidence": list(evidence_items)},
    )


def _build_registry(evidence_items: list[dict]) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_make_search_kb_tool_with_canned(evidence_items))
    return reg


def _evidence_dict(
    chunk_id: str = "c-king-hours",
    *,
    campus: str = "oxford",
    library: str = "king",
) -> dict:
    return {
        "n": 1,
        "chunk_id": chunk_id,
        "source_url": f"https://lib.miamioh.edu/king/cite-1/",
        "snippet": "King Library is open 7am-2am Monday through Friday.",
        "campus": campus,
        "library": library,
        "topic": "hours",
        "featured_service": None,
        "score": 0.9,
    }


# --- Path classification (post-hoc) -------------------------------------


def classify_response_path(resp: TurnResponse) -> str:
    """Categorize how the orchestrator handled this turn.

    Pure observation -- doesn't run anything; just inspects fields the
    orchestrator already set. Lets the smoke harness assert that each
    fixture took its EXPECTED path.
    """
    if resp.agent_stopped_reason == "clarify":
        return "clarify"
    if resp.agent_stopped_reason == "point_to_url":
        return "point_to_url"
    if resp.agent_stopped_reason == "refuse":
        return "refuse"
    # The agent ran (clean / max_iters / loop_detected / tool_failures).
    if resp.is_refusal:
        return "agent_then_refusal"
    return "agent_then_answer"


# --- Fixture --------------------------------------------------------------


@dataclass(frozen=True)
class SmokeFixture:
    name: str
    user_message: str
    expected_path: str
    classification: Classification
    synth_answer: str = "King opens at 7am [1]."
    synth_confidence: str = "high"
    synth_citations_n: tuple[int, ...] = (1,)
    service_refusal: Optional[RefusalContext] = None
    evidence: tuple[dict, ...] = ()


def _default_evidence() -> tuple[dict, ...]:
    return (_evidence_dict(),)


_FIXTURES: list[SmokeFixture] = [
    # 1. CLARIFY: low margin between top-2 intents
    SmokeFixture(
        name="ambiguous_when",
        user_message="when?",
        expected_path="clarify",
        classification=_classification(
            "hours", margin=0.01, needs_clarification=True,
            candidates=[("hours", 0.5), ("room_booking", 0.49)],
        ),
    ),
    # 2a. POINT_TO_URL: databases -> A-Z page
    SmokeFixture(
        name="databases_jstor",
        user_message="do you have JSTOR",
        expected_path="point_to_url",
        classification=_classification("databases"),
    ),
    # 2b. POINT_TO_URL: find_resource -> Primo
    SmokeFixture(
        name="find_book_hamlet",
        user_message="do you have a copy of Hamlet",
        expected_path="point_to_url",
        classification=_classification("find_resource"),
    ),
    # 3a. REFUSE: account -> privacy
    SmokeFixture(
        name="account_balance",
        user_message="how much do I owe?",
        expected_path="refuse",
        classification=_classification("account"),
    ),
    # 3b. REFUSE: events_news -> excluded by ETL
    SmokeFixture(
        name="events_this_week",
        user_message="what events are happening this week",
        expected_path="refuse",
        classification=_classification("events_news"),
    ),
    # 4. SERVICE_UNAVAILABLE: MakerSpace at Hamilton
    SmokeFixture(
        name="makerspace_hamilton",
        user_message="where is the makerspace at the Hamilton library",
        expected_path="agent_then_refusal",  # post-processor short-circuits
        classification=_classification("makerspace_3d"),
        service_refusal=RefusalContext(
            campus_display="Hamilton",
            service_name="MakerSpace",
            service_available_at="King Library on the Oxford campus",
        ),
    ),
    # 5. AGENT_THEN_ANSWER: full happy path
    SmokeFixture(
        name="king_hours",
        user_message="what time does King close tonight",
        expected_path="agent_then_answer",
        classification=_classification("hours"),
        evidence=_default_evidence(),
    ),
    # 6. AGENT_THEN_REFUSAL: synthesizer self-flagged low confidence
    SmokeFixture(
        name="low_confidence_obscure",
        user_message="some obscure question",
        expected_path="agent_then_refusal",
        classification=_classification("hours"),
        synth_confidence="low",
        evidence=_default_evidence(),
    ),
]


# --- Runner ---------------------------------------------------------------


def _build_deps(fixture: SmokeFixture) -> OrchestratorDeps:
    evidence = list(fixture.evidence) or [_evidence_dict()]
    return OrchestratorDeps(
        classifier=CannedClassifier(fixture.classification),
        tool_registry=_build_registry(evidence),
        agent_llm=CannedAgentLLM(),
        synthesizer_llm=CannedSynthesizerLLM(
            answer=fixture.synth_answer,
            confidence=fixture.synth_confidence,
            citations_n=list(fixture.synth_citations_n),
        ),
        load_corrections=lambda: [],
        load_url_allowlist=lambda: {
            f"https://lib.miamioh.edu/king/cite-{n}/"
            for n in fixture.synth_citations_n
        },
        lookup_service_availability=lambda intent, campus: fixture.service_refusal,
    )


@dataclass
class SmokeResult:
    fixture: SmokeFixture
    actual_path: str
    response: TurnResponse
    duration_us: int
    """Wall-clock duration in MICROseconds. The smoke runs against
    stubbed LLM/Weaviate so per-fixture time is dominated by Python
    overhead -- typically 5-50 us. Storing microseconds (not ms)
    means every fixture has nonzero, comparable timing in the
    output, instead of every entry rounding to 0ms."""

    ok: bool

    @property
    def duration_ms(self) -> float:
        """Convenience for callers that want milliseconds. Returns a
        float (not int) so sub-millisecond fixtures don't truncate."""
        return self.duration_us / 1000

    @property
    def status_line(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        # Pick a unit that makes the number readable: us for sub-ms,
        # ms otherwise. The smoke is supposed to run sub-ms per
        # fixture (it's a wiring check, not a perf benchmark) so us
        # is the common case.
        if self.duration_us < 1000:
            time_str = f"{self.duration_us:>5d} us"
        elif self.duration_us < 1_000_000:
            time_str = f"{self.duration_us / 1000:>5.1f} ms"
        else:
            time_str = f"{self.duration_us / 1_000_000:>5.2f} s"
        return (
            f"{mark} {self.fixture.name:<28} "
            f"path={self.actual_path:<22} "
            f"({time_str})"
        )


def _now_us() -> int:
    """Microsecond-precision wall clock. perf_counter_ns gives us
    microseconds even on macOS where time.monotonic rounds to ms."""
    return time.perf_counter_ns() // 1000


def run_smoke(fixtures: Optional[list[SmokeFixture]] = None) -> list[SmokeResult]:
    """Run every fixture through `run_turn` and report which path it took."""
    fixtures = fixtures if fixtures is not None else _FIXTURES
    results: list[SmokeResult] = []
    for fix in fixtures:
        deps = _build_deps(fix)
        request = TurnRequest(
            user_message=fix.user_message,
            conversation_id=f"smoke-{fix.name}",
        )
        start_us = _now_us()
        try:
            resp = run_turn(request, deps)
        except Exception as e:  # noqa: BLE001
            results.append(
                SmokeResult(
                    fixture=fix,
                    actual_path=f"crash:{type(e).__name__}",
                    response=None,  # type: ignore[arg-type]
                    duration_us=_now_us() - start_us,
                    ok=False,
                )
            )
            continue
        duration_us = _now_us() - start_us
        path = classify_response_path(resp)
        results.append(
            SmokeResult(
                fixture=fix,
                actual_path=path,
                response=resp,
                duration_us=duration_us,
                ok=path == fix.expected_path,
            )
        )
    return results


def _format_total(total_us: int) -> str:
    """Pick a reasonable unit for the bottom-line total."""
    if total_us < 1000:
        return f"{total_us} us"
    if total_us < 1_000_000:
        return f"{total_us / 1000:.1f} ms"
    return f"{total_us / 1_000_000:.2f} s"


def main() -> int:
    results = run_smoke()
    print()
    print("v2 stack smoke results:")
    print("-" * 70)
    for r in results:
        print(r.status_line)
        if not r.ok:
            print(
                f"     expected={r.fixture.expected_path!r}; "
                f"got={r.actual_path!r}"
            )
            print(
                f"     answer preview: "
                f"{(r.response.answer if r.response else '(crash)')[:120]!r}"
            )
    failed = [r for r in results if not r.ok]
    print("-" * 70)
    total_us = sum(r.duration_us for r in results)
    print(
        f"{len(results) - len(failed)}/{len(results)} passed "
        f"in {_format_total(total_us)} total "
        f"(stubbed LLM + Weaviate; this is wiring overhead only)"
    )
    return 1 if failed else 0


__all__ = [
    "CannedAgentLLM",
    "CannedClassifier",
    "CannedSynthesizerLLM",
    "SmokeFixture",
    "SmokeResult",
    "classify_response_path",
    "run_smoke",
]


if __name__ == "__main__":
    sys.exit(main())
