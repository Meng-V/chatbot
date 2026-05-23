"""
v2 serving adapter: bridge the rebuilt orchestrator (`run_turn`) to the
existing Socket.IO `"message"` wire contract the React app already
speaks.

Context (plan: Rollout "Behind a flag", robustness-ladder Gap 1):
the frontend half is ALREADY done -- `services/RolloutFlag.js` routes
flagged sessions to the `/smartchatbot/v2/socket.io` path, and
`MessageContextProvider` + `ParseLinks`/`CitationChip` already render
`{answer, citations:[{n,url,snippet}], confidence}`. What was missing
is the BACKEND: nothing served that v2 socket path -- every entrypoint
in main.py calls the legacy `library_graph`.

This module is the seam. It is deliberately split so the part that
MUST be correct is the part that is fully offline-testable:

  * `turnresponse_to_wire()` -- PURE. Maps a `TurnResponse` to the
    exact dict the legacy handler emits, PLUS the additive v2 keys
    the frontend already consumes. Legacy keys are preserved verbatim
    so the existing client code path is untouched. 100% unit-tested.

  * `handle_v2_message()` -- the async turn flow (build TurnRequest
    from the wire payload + history, call an injected `run_turn`,
    map the result). `run_turn` is a parameter so tests inject a
    stub -> no OpenAI / Weaviate / DB needed to verify the flow.

  * `build_v2_deps()` -- constructs real `OrchestratorDeps`. This is
    the ONLY part that cannot be verified offline (real OpenAI +
    Weaviate + Postgres) and is bounded by Gap 10 (live tool
    backends). It mirrors the PROVEN `run_eval._build_real_deps`
    wiring rather than inventing one. Flagged for operator
    live-verification; never claimed production-perfect.

Nothing here imports or mutates the legacy path. Mounting it (main.py)
is an additive ASGI wrap around the untouched legacy `socketio.ASGIApp`
so legacy bytes are provably unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from src.graph.new_orchestrator import (
    OrchestratorDeps,
    TurnRequest,
    TurnResponse,
    run_turn,
)


def _extract_message(data: Any) -> str:
    """Same parse the legacy `message` handler uses: accept a bare
    string or `{"message": "..."}`."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return data.get("message", "") or ""
    return ""


def turnresponse_to_wire(
    resp: TurnResponse,
    *,
    message_id: Optional[str],
    conversation_id: str,
) -> dict:
    """Map a `TurnResponse` to the Socket.IO `"message"` payload.

    LEGACY KEYS (kept byte-for-byte so the existing React handler keeps
    working): messageId, message, conversationId, intent, agents_used,
    needs_human.

    ADDITIVE v2 KEYS (the frontend already reads these when present --
    see MessageContextProvider / ChatBotComponent): citations,
    confidence. `needs_human` is driven by the refusal flag so a
    refused turn surfaces the existing human-handoff widget.

    Pure + JSON-safe by construction (str / list[dict] / bool only).
    """
    citations = [
        {
            "n": c.get("n"),
            "url": c.get("url"),
            "snippet": c.get("snippet"),
        }
        for c in (resp.citations or [])
        if isinstance(c, dict)
    ]
    return {
        "messageId": message_id,
        "message": resp.answer or "",
        "conversationId": conversation_id,
        "intent": resp.intent,
        # Legacy clients show a handoff affordance off `agents_used`/
        # `needs_human`; a refusal is exactly when we want that.
        "agents_used": [resp.agent_stopped_reason]
        if resp.agent_stopped_reason
        else [],
        "needs_human": bool(resp.is_refusal),
        # --- additive v2 keys (already consumed by the frontend) ---
        "citations": citations,
        "confidence": resp.confidence,
        "is_refusal": bool(resp.is_refusal),
    }


async def handle_v2_message(
    data: Any,
    deps: OrchestratorDeps,
    *,
    conversation_id: str,
    message_id: Optional[str] = None,
    conversation_history: Optional[list[dict]] = None,
    session_origin_url: Optional[str] = None,
    run_turn_fn: Callable[..., TurnResponse] = run_turn,
) -> dict:
    """Run one v2 turn and return the wire payload.

    `run_turn_fn` is injectable so unit tests exercise the full flow
    with a stub (no OpenAI/Weaviate/DB). The real socket handler in
    main.py owns conversation-store reads/writes + `sio.emit`, exactly
    like the legacy handler -- this function is the pure middle.
    """
    text = _extract_message(data)
    req = TurnRequest(
        user_message=text,
        conversation_id=conversation_id,
        session_origin_url=session_origin_url,
        conversation_history=conversation_history or [],
    )
    # run_turn is SYNC and a turn takes seconds; calling it directly in
    # this async handler would block the whole event loop (every other
    # socket client stalls). Offload to the default thread executor so
    # concurrent turns don't serialize. In tests the injected stub is
    # sync too -> runs in the executor just the same.
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(None, run_turn_fn, req, deps)
    return turnresponse_to_wire(
        resp, message_id=message_id, conversation_id=conversation_id
    )


def build_v2_deps() -> OrchestratorDeps:
    """Construct real OrchestratorDeps for production v2 serving.

    MIRRORS the proven `src/eval/run_eval.py::_build_real_deps`
    construction (real classifier, the tools_v2 registry with real
    backends, agent/synth LLM = None -> orchestrator's real-OpenAI
    default). Scope/intent are NOT pre-resolved here (serving has no
    gold pre-pass): the orchestrator resolves them per turn
    internally, and the generic tools_v2 `search_kb` reads scope from
    the turn -- so we keep the registry's default search_kb rather
    than the eval's pre-bound one.

    OPERATOR / Gap-10 BOUNDARY (cannot be verified offline -- needs
    real OpenAI + Weaviate + Postgres, and live tool backends are
    Gap 10): treat this as the interim serving wiring behind a 0%
    rollout flag, not a finished production deps bundle. Verify with
    a real `?v2=1` session before raising VITE_V2_ROLLOUT_PERCENT.
    """
    import logging
    from src.eval.run_eval import _build_classifier
    from src.tools_v2.registry import build_tool_registry
    from src.eval.real_backends import build_eval_backends
    from src.scope.service_availability import build_service_guard
    from src.database.corrections_adapter import PrismaCorrectionsStore

    # Register the agent + synthesizer prompt prefixes BEFORE the
    # first run_turn fires. The prefix registry is module-import
    # driven: `prompts/agent_v1.py` calls `register_prefix()` at its
    # module level, so the prefix only exists after the module is
    # imported once. Without these imports, `run_turn`'s first LLM
    # call raises `PromptBuildError: unknown prefix_id 'agent_v1'`
    # and the whole v2 endpoint 500s on its first user turn.
    # Verified 2026-05-22 live: hitting /smoketest/v2 reproduces
    # the failure without these two lines.
    import src.prompts.agent_v1        # noqa: F401 -- registers prefix
    import src.prompts.synthesizer_v1  # noqa: F401 -- registers prefix

    classifier = _build_classifier()
    registry = build_tool_registry(build_eval_backends())

    # Wire the Op 2 corrections loader. The store re-queries Postgres
    # per turn (no caching at this layer), so a librarian's inserted
    # correction takes effect on the next request. Safe-degradation:
    # if Postgres is unreachable, return empty -- chat keeps working,
    # we just lose the override layer for this turn.
    _corrections_store = PrismaCorrectionsStore()
    _v2_log = logging.getLogger("v2_serving")

    def _safe_load_corrections():
        try:
            return _corrections_store.load_active()
        except Exception as e:  # noqa: BLE001 -- never break a turn over corrections
            _v2_log.warning(
                "ManualCorrection load failed (%s); continuing without overrides", e
            )
            return []

    return OrchestratorDeps(
        classifier=classifier,
        tool_registry=registry,
        agent_llm=None,        # -> orchestrator real-OpenAI default
        synthesizer_llm=None,  # -> ditto
        load_corrections=_safe_load_corrections,
        load_url_allowlist=lambda: set(),
        # Cross-campus service guard (plan §8/§9). Canonical seed
        # SPACES-backed -> pure/sync, no DB at request time, cannot be
        # silently disabled. Production serving MUST have this on.
        lookup_service_availability=build_service_guard(),
    )


__all__ = [
    "build_v2_deps",
    "handle_v2_message",
    "turnresponse_to_wire",
]
