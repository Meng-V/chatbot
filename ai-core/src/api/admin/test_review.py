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

    def __init__(self, msgs=None, conv=None, toks=None, tools=None, fb=None,
                 fb_many=None):
        self._fb_many = fb_many or []
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
        self.updated: dict = {}

        async def _update(**kw):
            self.updated = kw
            return SimpleNamespace(id=kw.get("where", {}).get("id"))

        self.message.update = _update
        self.conversationfeedback = SimpleNamespace(
            find_unique=lambda **k: _aw(self._fb),
            # list view batches ratings across the page
            find_many=lambda **k: _aw(self._fb_many))


def _aw(v):
    async def _c():
        return v
    return _c()


def _run(coro):
    return asyncio.run(coro)


# --- query logic ---------------------------------------------------------

def test_list_flagged_filter_presets_build_right_where() -> None:
    """Working views are scoped to UNREVIEWED rows (2026-07-27): the
    queue has to shrink as the operator triages, or fresh and
    already-handled rows are indistinguishable."""
    db = _StubDB(msgs=[_msg(isPositiveRated=False)])
    _run(list_flagged(db, filter_preset="thumbs_down"))
    assert db.last_where == {
        "AND": [{"isPositiveRated": False}, {"reviewedAt": None}]
    }, db.last_where
    _run(list_flagged(db, filter_preset="thumbs_up"))
    assert db.last_where == {
        "AND": [{"isPositiveRated": True}, {"reviewedAt": None}]
    }, db.last_where
    _run(list_flagged(db, filter_preset="refusal"))
    assert db.last_where == {
        "AND": [{"wasRefusal": True}, {"reviewedAt": None}]
    }
    _run(list_flagged(db, filter_preset="bogus"))  # -> flagged union
    assert "OR" in db.last_where["AND"][0]
    # The two escape hatches keep showing handled rows.
    _run(list_flagged(db, filter_preset="all"))
    assert db.last_where == {}
    _run(list_flagged(db, filter_preset="reviewed"))
    assert db.last_where == {"NOT": [{"reviewedAt": None}]}


def test_attach_feedback_annotates_rows_by_conversation() -> None:
    """Star ratings live on the conversation; the queue lists messages.
    One batched lookup projects them onto the rows so a reviewer can
    see WHICH rows have patron feedback without opening each."""
    from src.api.admin.review_queries import attach_feedback

    class _FBDB:
        conversationfeedback = SimpleNamespace(
            find_many=lambda **k: _aw([
                SimpleNamespace(conversationId="c1", rating=4,
                                userComment="helpful"),
            ])
        )

    rows = [{"conversation_id": "c1"}, {"conversation_id": "c2"}]
    out = _run(attach_feedback(_FBDB(), rows))
    assert out[0]["feedback_rating"] == 4
    assert out[0]["feedback_comment"] == "helpful"
    assert out[1]["feedback_rating"] is None


def test_attach_feedback_never_raises() -> None:
    from src.api.admin.review_queries import attach_feedback

    class _Boom:
        conversationfeedback = SimpleNamespace(
            find_many=lambda **k: (_ for _ in ()).throw(RuntimeError("x")))

    rows = [{"conversation_id": "c1"}]
    assert _run(attach_feedback(_Boom(), rows)) == rows


def test_mark_reviewed_sets_and_clears() -> None:
    from src.api.admin.review_queries import mark_reviewed

    seen: dict = {}

    class _UpDB:
        message = SimpleNamespace(
            update=lambda **k: (seen.update(k), _aw(True))[1])

    assert _run(mark_reviewed(_UpDB(), "m1", reviewed_by="qum")) is True
    assert seen["data"]["reviewedBy"] == "qum"
    assert seen["data"]["reviewedAt"] is not None
    assert _run(mark_reviewed(_UpDB(), "m1", undo=True)) is True
    assert seen["data"] == {"reviewedAt": None, "reviewedBy": None}


def test_mark_reviewed_never_raises() -> None:
    from src.api.admin.review_queries import mark_reviewed

    class _Boom:
        message = SimpleNamespace(
            update=lambda **k: (_ for _ in ()).throw(RuntimeError("x")))

    assert _run(mark_reviewed(_Boom(), "m1")) is False


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
    # renamed to match the nav label in the 2026-07-28 redesign
    assert r.status_code == 200 and "Flagged conversations" in r.text
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


def test_review_list_renders_thumbs_up_and_star_rating() -> None:
    from fastapi import FastAPI
    """Positive ratings and patron star ratings had no surface at all
    before 2026-07-27 -- the data existed but the list couldn't show it."""
    db = _StubDB(
        msgs=[_msg(id="m9", isPositiveRated=True, conversationId="c1")],
        fb_many=[SimpleNamespace(conversationId="c1", rating=5,
                                 userComment="great answer")],
    )
    guard = make_token_guard("s3cret")
    app = FastAPI()
    app.include_router(build_review_view_router(
        {"db": db, "guard": guard, "require_librarian": guard}))
    from starlette.testclient import TestClient
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/admin/review?filter=thumbs_up&key=s3cret")
    assert r.status_code == 200
    assert "thumbs-up" in r.text
    assert "5/5" in r.text                    # star rating projected in
    assert "great answer" in r.text           # patron comment visible
    assert "thumbs_up" in r.text              # filter tab present
    assert "mark reviewed" in r.text          # triage action present
    assert ">view<" in r.text                 # link relabeled from "open"


def test_review_mark_updates_and_redirects_back_to_filter() -> None:
    from fastapi import FastAPI
    db = _StubDB(msgs=[_msg(id="m9", conversationId="c1")])
    guard = make_token_guard("s3cret")
    app = FastAPI()
    app.include_router(build_review_view_router(
        {"db": db, "guard": guard, "require_librarian": guard}))
    from starlette.testclient import TestClient
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/admin/review/mark/m9?filter=refusal&key=s3cret",
              follow_redirects=False)
    assert r.status_code == 200
    assert db.updated["where"] == {"id": "m9"}
    assert db.updated["data"]["reviewedAt"] is not None
    # bounces back to the SAME filter the reviewer was working in
    assert "/admin/review?filter=refusal" in r.text
    # undo clears it
    c.get("/admin/review/mark/m9?filter=refusal&key=s3cret&undo=1")
    assert db.updated["data"] == {"reviewedAt": None, "reviewedBy": None}


def test_review_mark_401_without_token() -> None:
    from fastapi import FastAPI
    db = _StubDB(msgs=[])
    guard = make_token_guard("s3cret")
    app = FastAPI()
    app.include_router(build_review_view_router(
        {"db": db, "guard": guard, "require_librarian": guard}))
    from starlette.testclient import TestClient
    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/admin/review/mark/m9").status_code == 401
