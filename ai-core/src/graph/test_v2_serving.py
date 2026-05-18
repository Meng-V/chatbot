"""
Offline tests for src.graph.v2_serving.

Run: `python -m src.graph.test_v2_serving` from ai-core/.

Covers the parts that MUST be correct and CAN be verified without
OpenAI / Weaviate / Postgres:
  * turnresponse_to_wire -- legacy keys preserved byte-for-byte;
    additive v2 keys present; refusal -> needs_human; citations
    sanitized; output is JSON-serializable.
  * _extract_message -- str / dict / junk parsing parity with legacy.
  * handle_v2_message -- builds the TurnRequest from the wire payload
    + history and maps the result, using an INJECTED stub run_turn
    (no network).

`build_v2_deps()` is intentionally NOT executed here: it constructs a
real classifier / tool backends (OpenAI + Weaviate + Postgres) and is
the documented operator-verify boundary. We only assert it's importable
and callable so a rename can't silently break the mount.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.graph.new_orchestrator import TurnResponse
from src.graph import v2_serving as V


def _resp(**over) -> TurnResponse:
    base = dict(
        answer="King opens at 7am [1].",
        is_refusal=False,
        refusal_trigger=None,
        citations=[{"n": 1, "url": "https://x/y", "snippet": "7am"}],
        confidence="high",
        intent="hours",
        scope={"campus": "oxford", "library": "king"},
        model_used="gpt-5.4-mini",
        tokens={"input": 10, "cached_input": 0, "output": 5},
        fired_corrections=[],
        agent_stopped_reason="answered",
        latency_ms=42,
        cited_chunk_ids=["c-1"],
    )
    base.update(over)
    return TurnResponse(**base)


def test_extract_message_parity() -> None:
    assert V._extract_message("hi") == "hi"
    assert V._extract_message({"message": "hi"}) == "hi"
    assert V._extract_message({"nope": 1}) == ""
    assert V._extract_message(None) == ""
    assert V._extract_message(12345) == ""


def test_wire_preserves_legacy_keys() -> None:
    w = V.turnresponse_to_wire(_resp(), message_id="m1", conversation_id="c1")
    # Exactly the keys the legacy React handler already reads.
    for k in (
        "messageId", "message", "conversationId", "intent",
        "agents_used", "needs_human",
    ):
        assert k in w, f"missing legacy key {k}"
    assert w["messageId"] == "m1"
    assert w["conversationId"] == "c1"
    assert w["message"] == "King opens at 7am [1]."
    assert w["intent"] == "hours"
    assert w["agents_used"] == ["answered"]
    assert w["needs_human"] is False


def test_wire_additive_v2_keys() -> None:
    w = V.turnresponse_to_wire(_resp(), message_id=None, conversation_id="c")
    assert w["confidence"] == "high"
    assert w["is_refusal"] is False
    assert w["citations"] == [
        {"n": 1, "url": "https://x/y", "snippet": "7am"}
    ]


def test_refusal_sets_needs_human_and_flag() -> None:
    w = V.turnresponse_to_wire(
        _resp(is_refusal=True, refusal_trigger="no_results",
              answer="I don't have a reliable answer.", citations=[]),
        message_id="m", conversation_id="c",
    )
    assert w["needs_human"] is True
    assert w["is_refusal"] is True
    assert w["citations"] == []


def test_wire_is_json_serializable() -> None:
    w = V.turnresponse_to_wire(_resp(), message_id="m", conversation_id="c")
    s = json.dumps(w)  # must not raise
    assert json.loads(s)["message"] == "King opens at 7am [1]."


def test_wire_sanitizes_non_dict_citations() -> None:
    w = V.turnresponse_to_wire(
        _resp(citations=[{"n": 1, "url": "u", "snippet": "s"}, "garbage", None]),
        message_id="m", conversation_id="c",
    )
    assert w["citations"] == [{"n": 1, "url": "u", "snippet": "s"}]


def test_handle_v2_message_builds_request_and_maps() -> None:
    captured = {}

    def stub_run_turn(req, deps):
        captured["req"] = req
        captured["deps"] = deps
        return _resp(answer="stubbed [1].")

    out = asyncio.run(
        V.handle_v2_message(
            {"message": "when does king open?"},
            deps=object(),
            conversation_id="conv-9",
            message_id="mid-9",
            conversation_history=[{"role": "user", "content": "hi"}],
            run_turn_fn=stub_run_turn,
        )
    )
    req = captured["req"]
    assert req.user_message == "when does king open?"
    assert req.conversation_id == "conv-9"
    assert req.conversation_history == [{"role": "user", "content": "hi"}]
    assert out["message"] == "stubbed [1]."
    assert out["conversationId"] == "conv-9"
    assert out["messageId"] == "mid-9"


def test_handle_v2_message_accepts_bare_string() -> None:
    def stub_run_turn(req, deps):
        assert req.user_message == "bare"
        return _resp()

    out = asyncio.run(
        V.handle_v2_message(
            "bare", deps=object(), conversation_id="c",
            run_turn_fn=stub_run_turn,
        )
    )
    assert out["conversationId"] == "c"


def test_build_v2_deps_importable_not_invoked() -> None:
    # Operator-verify boundary: must exist + be callable, but we do
    # NOT call it (it builds a real classifier / backends).
    assert callable(V.build_v2_deps)


def main() -> int:
    tests = [
        test_extract_message_parity,
        test_wire_preserves_legacy_keys,
        test_wire_additive_v2_keys,
        test_refusal_sets_needs_human_and_flag,
        test_wire_is_json_serializable,
        test_wire_sanitizes_non_dict_citations,
        test_handle_v2_message_builds_request_and_maps,
        test_handle_v2_message_accepts_bare_string,
        test_build_v2_deps_importable_not_invoked,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
