"""
Diagnostic CLI: "what would the v2 bot do for this question?"

Runs a single user message through the real v2 orchestrator (with
stubbed LLM + Weaviate) and prints a step-by-step trace of every
routing decision: scope resolution, classification, capability tier,
agent path, synthesizer output, post-processor, final response.

Useful for:
  - Post-launch debugging: a user complained about answer X. What
    path did the bot take? Which classifier candidates competed?
    Why did it refuse / not refuse?
  - Pre-deploy review: does the new exemplar set route this
    question to the right intent? Eyeball before relying on eval.
  - Librarian QA: walk through a representative question and
    explain to a stakeholder how the bot decides.

Usage:
    python -m src.eval.inspect_turn "Will I get a confirmation when I place a hold?"
    python -m src.eval.inspect_turn "ILL form" --intent interlibrary_loan
    python -m src.eval.inspect_turn "the library" --session-origin https://ham.miamioh.edu/library/
    python -m src.eval.inspect_turn "Hamilton hours" --campus hamilton

Flags:
  --intent <name>          Force the classifier output (skip kNN; useful
                           when the kNN exemplar set isn't loaded yet)
  --session-origin <url>   Pass the chat-widget origin URL through scope
                           (the only way to bypass Oxford default --
                           e.g. https://ham.miamioh.edu/library/ to
                           simulate a Hamilton-page user)
  --service-unavailable    Simulate the LibrarySpace.services_offered
                           short-circuit (e.g. MakerSpace at Hamilton)
  --json                   Emit the full TurnResponse as JSON (for
                           piping into another tool)

The CLI is read-only and does not consume real LLM tokens. It's a
diagnostic. For a real answer use the deployed bot.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Allow `python -m src.eval.inspect_turn` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.smoke_e2e import (  # noqa: E402
    CannedAgentLLM,
    CannedClassifier,
    CannedSynthesizerLLM,
    _evidence_dict,
    _make_search_kb_tool_with_canned,
)
from src.graph.new_orchestrator import (  # noqa: E402
    OrchestratorDeps,
    TurnRequest,
    TurnResponse,
    run_turn,
)
from src.agent.tool_registry import ToolRegistry  # noqa: E402
from src.router.intent_capabilities import (  # noqa: E402
    CapabilityTier,
    get_intent_capability,
)
from src.router.intent_knn import INTENTS, Classification  # noqa: E402
from src.scope.resolver import (  # noqa: E402
    Scope,
    resolve_scope,
    resolve_session_origin,
)
from src.synthesis.refusal_templates import RefusalContext  # noqa: E402


# --- Tiny keyword classifier (fallback when --intent not provided) -------
#
# The real kNN classifier needs an exemplar set we don't have at sandbox
# time. For inspection purposes a simple keyword lookup is enough --
# users can pass --intent to force any specific intent.

_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "hours": ("hours", "open", "close"),
    "circulation_basic": (
        "place a hold", "place hold", "request a book",
        "confirmation", "ready for pickup", "did my request",
    ),
    "interlibrary_loan": (
        "interlibrary loan", "ohiolink", "worldcat", "another library",
    ),
    "renewal": ("renew", "extend my checkout"),
    "loan_policy": ("loan period", "how long can i", "late fee"),
    "account": ("my account", "my fines", "do i owe", "what i owe", "my checkouts"),
    "course_reserves": ("course reserve", "on reserve"),
    "find_resource": ("do you have", "looking for a book", "find a book"),
    "databases": ("database", "jstor", "ebsco", "psycinfo"),
    "citation_help": ("apa", "mla", "citation", "zotero"),
    "research_consultation": ("research help", "appointment with a librarian"),
    "data_services": ("data services", "gis", "data analysis"),
    "events_news": ("upcoming event", "exhibit", "library event"),
    "instruction_request": ("library instruction", "teach my class"),
    "room_booking": ("book a room", "reserve a room", "study room"),
    "space_info": ("quiet study", "silent floor", "lockers", "food in the library"),
    "makerspace_3d": ("makerspace", "3d printer"),
    "printing_wifi": ("print", "wifi", "scan", "copy"),
    "tech_checkout": ("borrow a laptop", "chromebook", "borrow a charger"),
    "software_access": ("software", "matlab", "spss"),
    "adobe_access": ("adobe", "photoshop", "illustrator", "indesign"),
    "subject_librarian": ("subject librarian", "liaison", "librarian for"),
    "staff_lookup": ("dean", "staff directory"),
    "newspapers": ("new york times", "nyt", "wall street journal"),
    "special_collections": ("special collections", "archives", "rare book"),
    "digital_collections": ("digital collection", "digital exhibit"),
    "human_handoff": ("talk to a person", "real person"),
    "cross_campus_comparison": ("all campuses", "every miami library"),
    "out_of_scope": ("weather", "score", "homework"),
}


def _keyword_classify(message: str) -> Classification:
    """Pick the intent whose keyword set has the most hits.

    Returns out_of_scope if nothing matches. This is a heuristic for
    INSPECTION ONLY -- prod uses the real kNN classifier with embedded
    exemplars.
    """
    lower = message.lower()
    scores: list[tuple[str, int]] = []
    for intent, keywords in _KEYWORD_HINTS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits > 0:
            scores.append((intent, hits))
    scores.sort(key=lambda kv: -kv[1])
    if not scores:
        return Classification(
            intent="out_of_scope", score=0.5, margin=0.5,
            needs_clarification=False,
            candidates=[("out_of_scope", 0.5)],
        )
    top, top_hits = scores[0]
    runner = scores[1] if len(scores) > 1 else None
    margin = (
        (top_hits - runner[1]) / max(top_hits, 1)
        if runner else 1.0
    )
    return Classification(
        intent=top,
        score=0.5 + 0.1 * top_hits,
        margin=margin,
        needs_clarification=margin < 0.05,
        candidates=[(intent, 0.5 + 0.1 * h) for intent, h in scores[:5]],
    )


# --- Pretty trace printer -----------------------------------------------


def _hr(title: str) -> None:
    print()
    print(f"--- {title} " + "-" * (60 - len(title)))


def _print_scope_step(scope: Scope) -> None:
    _hr("[1] Scope resolution")
    print(f"    campus  = {scope.campus}")
    print(f"    library = {scope.library or '(none)'}")
    print(f"    source  = {scope.source}")


def _print_classify_step(cls: Classification) -> None:
    _hr("[2] Intent classification")
    print(f"    intent  = {cls.intent}")
    print(f"    margin  = {cls.margin:.3f}")
    print(f"    score   = {cls.score:.3f}")
    print(f"    needs_clarification = {cls.needs_clarification}")
    if cls.candidates:
        print(f"    top candidates:")
        for intent, score in cls.candidates[:5]:
            print(f"      - {intent:<28}  {score:.3f}")


def _print_capability_step(intent: str) -> None:
    _hr("[3] Capability tier")
    cap = get_intent_capability(intent)
    print(f"    intent     = {intent}")
    print(f"    tier       = {cap.tier.value}")
    if cap.tier != CapabilityTier.READY:
        print(f"    canonical_url = {cap.canonical_url}")
        if cap.refusal_trigger:
            print(f"    refusal_trigger = {cap.refusal_trigger}")
        print(f"    -> orchestrator will SHORT-CIRCUIT (no LLM)")
    else:
        print(f"    -> orchestrator will run the agent")


def _print_response(resp: TurnResponse, latency_us: int) -> None:
    _hr("[final] TurnResponse")
    print(f"    is_refusal       = {resp.is_refusal}")
    print(f"    refusal_trigger  = {resp.refusal_trigger or '(none)'}")
    print(f"    intent           = {resp.intent}")
    print(f"    confidence       = {resp.confidence}")
    print(f"    model_used       = {resp.model_used}")
    print(f"    tokens           = {resp.tokens}")
    print(f"    agent_stopped    = {resp.agent_stopped_reason}")
    print(f"    citations        = {len(resp.citations)}")
    print(f"    latency          = {latency_us} us")
    print()
    print("    answer:")
    for line in resp.answer.splitlines() or [""]:
        print(f"      {line}")
    if resp.citations:
        print()
        print("    citations:")
        for c in resp.citations:
            n = c.get("n", "?")
            url = c.get("url", "")
            snippet = (c.get("snippet") or "").strip()
            print(f"      [{n}] {url}")
            if snippet:
                print(f"           \"{snippet[:200]}\"")


# --- Inspector ----------------------------------------------------------


def inspect(
    user_message: str,
    *,
    forced_intent: Optional[str] = None,
    session_origin_url: Optional[str] = None,
    service_unavailable: bool = False,
    print_trace: bool = True,
) -> tuple[TurnResponse, int]:
    """Run a single message through the v2 stack and print the trace.

    Returns (TurnResponse, latency_us).

    Scope is always derived by the real `resolve_scope` -- pass
    `session_origin_url` to bypass the Oxford default. The
    orchestrator owns scope resolution; this helper doesn't fake
    a forced scope (it would diverge from prod behavior).
    """
    # 1. Scope -- run the real resolver so the trace matches what
    # the orchestrator will pick up internally.
    origin_campus = resolve_session_origin(session_origin_url)
    scope = resolve_scope(user_message, origin_campus)

    # 2. Classification (real keyword classifier, or forced).
    if forced_intent:
        if forced_intent not in INTENTS:
            raise ValueError(
                f"unknown intent {forced_intent!r}; "
                f"valid: {sorted(INTENTS)}"
            )
        classification = Classification(
            intent=forced_intent,
            score=1.0, margin=1.0, needs_clarification=False,
            candidates=[(forced_intent, 1.0)],
        )
    else:
        classification = _keyword_classify(user_message)

    if print_trace:
        print()
        print("=" * 64)
        print(f"  Inspect Turn:  {user_message!r}")
        if session_origin_url:
            print(f"  Session origin: {session_origin_url}")
        if forced_intent:
            print(f"  Forced intent: {forced_intent}")
        print("=" * 64)
        _print_scope_step(scope)
        _print_classify_step(classification)
        _print_capability_step(classification.intent)

    # 3. Build deps (stubs).
    deps = OrchestratorDeps(
        classifier=CannedClassifier(classification),
        tool_registry=_build_registry(),
        agent_llm=CannedAgentLLM(),
        synthesizer_llm=CannedSynthesizerLLM(),
        load_corrections=lambda: [],
        load_url_allowlist=lambda: {"https://lib.miamioh.edu/king/cite-1/"},
        lookup_service_availability=(
            (lambda intent, campus: RefusalContext(
                campus_display=campus.title(),
                service_name="MakerSpace",
                service_available_at="King Library on the Oxford campus",
            ))
            if service_unavailable
            else (lambda intent, campus: None)
        ),
    )

    # 4. Run.
    request = TurnRequest(
        user_message=user_message,
        conversation_id="inspect",
        session_origin_url=session_origin_url,
    )
    start = time.perf_counter_ns()
    resp = run_turn(request, deps)
    latency_us = (time.perf_counter_ns() - start) // 1000

    if print_trace:
        _print_response(resp, latency_us)

    return resp, latency_us


def _build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_make_search_kb_tool_with_canned([_evidence_dict()]))
    return reg


def _response_to_jsonable(resp: TurnResponse) -> dict:
    return dataclasses.asdict(resp)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect what the v2 bot would do for one user message."
    )
    parser.add_argument("user_message", help="The question to inspect.")
    parser.add_argument("--intent", help="Force the classifier output.")
    parser.add_argument("--session-origin",
                        help="Chat widget origin URL (for campus default).")
    parser.add_argument("--service-unavailable", action="store_true",
                        help="Simulate LibrarySpace services_offered miss.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the full response as JSON instead of trace.")
    args = parser.parse_args()

    try:
        resp, latency_us = inspect(
            args.user_message,
            forced_intent=args.intent,
            session_origin_url=args.session_origin,
            service_unavailable=args.service_unavailable,
            print_trace=not args.json,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        out = _response_to_jsonable(resp)
        out["_latency_us"] = latency_us
        print(json.dumps(out, indent=2, default=str))

    return 0


__all__ = ["inspect"]


if __name__ == "__main__":
    sys.exit(main())
