"""
Offline tests for the Op-1 read-only review surface.

Run: `python -m src.api.admin.test_review` from ai-core/.

No real DB / no API: a stub Prisma-shaped object feeds canned rows.
Covers the load-bearing logic (filter selection, defensive empties,
handoff/outcome extraction) AND the security gate (fail-closed auth +
that the surface 401s without the token), via Starlette TestClient.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.api.admin.review_queries import conversation_detail, list_flagged
from src.api.admin.review_view_router import (
    build_review_view_router,
    make_token_guard,
)
from src.api.admin.reviews_router import build_reviews_router


def _msg(**kw):
    base = dict(id="m1", type="assistant", content="hi", timestamp="t",
                conversationId="c1", isPositiveRated=None, intent="hours",
                scopeCampus="oxford", scopeLibrary=None, modelUsed="x",
                confidence=None, wasRefusal=False, refusalTrigger=None,
                citedChunkIds=[])
    base.update(kw)
    return SimpleNamespace(**base)


class _StubDB:
    """Records the `where` list_flagged builds; returns canned rows."""

    def __init__(self, msgs=None, conv=None, toks=None, tools=None, fb=None):
        self._msgs = msgs or []
        self._conv = conv
        self._toks = toks or []
        self._tools = tools or []
        self._fb = fb
        self.last_where = None

        async def _find_many(**kw):
            self.last_where = kw.get("where")
            return self._msgs

        async def _find_unique(**kw):
            return self._conv

        self.message = SimpleNamespace(
            find_many=_find_many,
            count=lambda: _aw(len(self._msgs)),
        )
        self.conversation = SimpleNamespace(find_unique=_find_unique)
        self.modeltokenusage = SimpleNamespace(
            find_many=lambda **k: _aw(self._toks))
        self.toolexecution = SimpleNamespace(
            find_many=lambda **k: _aw(self._tools))
        self.conversationfeedback = SimpleNamespace(
            find_unique=lambda **k: _aw(self._fb))


def _aw(v):
    async def _c():
        return v
    return _c()


def _run(coro):
    return asyncio.run(coro)


# --- query logic ---------------------------------------------------------

def test_list_flagged_filter_presets_build_right_where() -> None:
    db = _StubDB(msgs=[_msg(isPositiveRated=False)])
    _run(list_flagged(db, filter_preset="thumbs_down"))
    assert db.last_where == {"isPositiveRated": False}, db.last_where
    _run(list_flagged(db, filter_preset="refusal"))
    assert db.last_where == {"wasRefusal": True}
    _run(list_flagged(db, filter_preset="all"))
    assert db.last_where == {}
    _run(list_flagged(db, filter_preset="bogus"))  # -> flagged union
    assert "OR" in db.last_where


def test_list_flagged_defensive_on_query_error() -> None:
    class _Boom:
        message = SimpleNamespace(
            find_many=lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = _run(list_flagged(_Boom(), filter_preset="all"))
    assert out == []  # never raises into the endpoint


def test_conversation_detail_extracts_handoff_and_outcome() -> None:
    msgs = [
        _msg(id="u", type="user", content="q", wasRefusal=False),
        _msg(id="a", type="assistant", content="final",
             wasRefusal=True, refusalTrigger="human_handoff",
             confidence="low"),
    ]
    db = _StubDB(
        msgs=msgs,
        conv=SimpleNamespace(createdAt="c", updatedAt="u", toolUsed=[]),
        toks=[SimpleNamespace(llmModelName="gpt-5.4-nano", callSite="judge",
                              promptTokens=10, cachedInputTokens=2,
                              completionTokens=3, totalTokens=13,
                              createdAt="t")],
        tools=[SimpleNamespace(agentName="A", toolName="search_kb",
                               success=True, executionTime=5,
                               timestamp="t")],
        fb=SimpleNamespace(rating=1, userComment="bad"),
    )
    d = _run(conversation_detail(db, "c1"))
    assert d is not None
    assert d["token_total"] == 13
    assert len(d["tools_called"]) == 1
    assert d["human_handoff"] and d["human_handoff"][0]["trigger"] == "human_handoff"
    assert d["outcome"]["final_answer"] == "final"
    assert d["outcome"]["was_refusal"] is True
    assert d["feedback"]["rating"] == 1


def test_conversation_detail_none_when_missing() -> None:
    assert _run(conversation_detail(_StubDB(conv=None), "nope")) is None
    assert _run(conversation_detail(_StubDB(), "")) is None


# --- security gate (fail-closed) -----------------------------------------

def _client(token: str):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    db = _StubDB(
        msgs=[_msg(isPositiveRated=False, conversationId="c1")],
        conv=SimpleNamespace(createdAt="c", updatedAt="u", toolUsed=[]),
    )
    guard = make_token_guard(token)
    deps = {"db": db, "require_librarian": guard, "guard": guard}
    app = FastAPI()
    app.include_router(build_reviews_router(deps))
    app.include_router(build_review_view_router(deps))
    return TestClient(app, raise_server_exceptions=False)


def test_html_and_json_401_without_token() -> None:
    c = _client("s3cret")
    assert c.get("/admin/review").status_code == 401
    assert c.get("/admin/reviews").status_code == 401
    assert c.get("/admin/review?key=wrong").status_code == 401


def test_html_and_json_ok_with_token() -> None:
    c = _client("s3cret")
    r = c.get("/admin/review?key=s3cret")
    assert r.status_code == 200 and "Review queue" in r.text
    rj = c.get("/admin/reviews", headers={"X-Admin-Token": "s3cret"})
    assert rj.status_code == 200 and "results" in rj.json()


def test_empty_token_is_fail_closed() -> None:
    c = _client("")  # misconfig -> everything 401, never open
    assert c.get("/admin/review?key=").status_code == 401
    assert c.get("/admin/reviews", headers={"X-Admin-Token": ""}).status_code == 401


def test_html_escapes_user_content() -> None:
    """Conversation content is attacker-controlled; it must be escaped
    in the librarian's browser (stored-XSS guard)."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    xss = "<script>alert(1)</script>"
    db = _StubDB(
        msgs=[_msg(id="x", type="user", content=xss, conversationId="c1")],
        conv=SimpleNamespace(createdAt="c", updatedAt="u", toolUsed=[]),
    )
    g = make_token_guard("k")
    app = FastAPI()
    app.include_router(build_review_view_router(
        {"db": db, "guard": g, "require_librarian": g}))
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/admin/review/c1?key=k")
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def main() -> int:
    tests = [
        test_list_flagged_filter_presets_build_right_where,
        test_list_flagged_defensive_on_query_error,
        test_conversation_detail_extracts_handoff_and_outcome,
        test_conversation_detail_none_when_missing,
        test_html_and_json_401_without_token,
        test_html_and_json_ok_with_token,
        test_empty_token_is_fail_closed,
        test_html_escapes_user_content,
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
