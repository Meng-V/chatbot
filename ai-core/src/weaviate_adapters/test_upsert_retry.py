"""A dropped connection must be retried, not answered with the other verb.

Real failure, 2026-07-29: the connection dropped mid-insert ("Server
disconnected without sending a response"). The code took any exception as
"wrong verb" and switched to `replace`, which 500'd with "no object with id"
because the insert had never landed -- and a real ETL apply died 2,664 chunks
into 20,068.
"""

import pytest

from src.weaviate_adapters.etl_adapter import WeaviateETLAdapter, _is_transient


@pytest.mark.parametrize("msg,transient", [
    # transport: the request got no verdict, so retry the same verb
    ("httpx.RemoteProtocolError: Server disconnected without sending a response.", True),
    ("ConnectError: [Errno 111] Connection refused", True),
    ("ReadTimeout", True),
    ("Server error 503 Service Unavailable", True),
    # semantic: Weaviate ANSWERED, and the answer is "wrong verb"
    ("UnexpectedStatusCodeError: Object was not replaced! Unexpected status "
     "code: 500 ... no object with id 'abc'", False),
    ("UnexpectedStatusCodeError: 422 invalid property", False),
])
def test_transient_classification(msg, transient):
    assert _is_transient(Exception(msg)) is transient


def test_a_500_naming_a_missing_object_is_not_transient():
    """This is the exact string that caused the bug. It contains '500', so a
    naive substring rule would call it transient and retry forever instead of
    switching verbs."""
    assert not _is_transient(Exception(
        "Object was not replaced.! Unexpected status code: 500, with response "
        "body: {'error': [{'message': \"no object with id 'f6a808a0'\"}]}"))


class _Coll:
    def __init__(self, script):
        self.script = list(script)   # exceptions or None per insert attempt
        self.insert_calls = 0
        self.replace_calls = 0

        outer = self

        class _Data:
            def insert(self, **kw):
                outer.insert_calls += 1
                exc = outer.script.pop(0) if outer.script else None
                if exc:
                    raise exc

            def replace(self, **kw):
                outer.replace_calls += 1

        self.data = _Data()


def _adapter(coll, monkeypatch):
    class _Client:
        class collections:
            @staticmethod
            def get(name):
                return coll

            @staticmethod
            def exists(name):
                return True

            @staticmethod
            def create(*a, **kw):
                return coll

    a = WeaviateETLAdapter(client=_Client())
    a._created_collections.add("Chunk_test")
    monkeypatch.setattr("time.sleep", lambda *_: None)   # no real backoff
    return a


def test_transport_failure_retries_the_same_verb(monkeypatch):
    """One dropped connection, then success -> insert twice, replace NEVER."""
    coll = _Coll([Exception("Server disconnected without sending a response."), None])
    a = _adapter(coll, monkeypatch)
    a.upsert_chunk(collection="Chunk_test", chunk_id="c-1",
                   properties={"text": "t"}, vector=[0.1], exists=False)
    assert coll.insert_calls == 2, "the same verb must be retried"
    assert coll.replace_calls == 0, "switching verbs on a transport error is the bug"


def test_semantic_failure_switches_verb_immediately(monkeypatch):
    """A 'already exists' answer means the snapshot was stale -> replace, and
    do NOT waste retries on it."""
    coll = _Coll([Exception("id 'abc' already exists")])
    a = _adapter(coll, monkeypatch)
    a.upsert_chunk(collection="Chunk_test", chunk_id="c-1",
                   properties={"text": "t"}, vector=[0.1], exists=False)
    assert coll.insert_calls == 1, "a semantic failure must not be retried"
    assert coll.replace_calls == 1


def test_persistent_transport_failure_eventually_raises(monkeypatch):
    coll = _Coll([Exception("Server disconnected")] * 10)

    class _Coll2(_Coll):
        pass

    a = _adapter(coll, monkeypatch)

    def boom(**kw):
        raise Exception("no object with id 'x'")
    coll.data.replace = boom

    with pytest.raises(RuntimeError) as ei:
        a.upsert_chunk(collection="Chunk_test", chunk_id="c-1",
                       properties={"text": "t"}, vector=[0.1], exists=False)
    assert coll.insert_calls >= 3, "should have retried before giving up"
    assert "c-1" in str(ei.value), "the error must name the chunk"
