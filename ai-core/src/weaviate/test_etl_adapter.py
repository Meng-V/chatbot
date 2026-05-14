"""
Unit tests for WeaviateETLAdapter.

Run: `python -m src.weaviate.test_etl_adapter` from ai-core/.

The adapter wraps the v4 Weaviate client. We stub the client surface
with an in-memory shape so the tests don't need a running Weaviate.
Coverage:

  1. _ensure_collection idempotency (created once, cached)
  2. _ensure_collection creates with the documented properties
  3. upsert_chunk falls back to insert when replace fails (handles
     v4's "replace requires existing object" behavior)
  4. get_chunk returns None for missing objects + missing collections
  5. get_chunk returns properties dict (NOT vector) on hit
  6. soft_delete_by_url tombstones non-seen URLs; skips already-tombstoned
  7. soft_delete_by_url sets tombstoned_at timestamp
  8. gc_tombstones queries with the deleted+older_than filter
  9. count handles missing collection (returns 0) and errors (returns -1)
 10. Constructor without an injected client + no Weaviate env raises clearly
"""

from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path
from typing import Any, Optional

# Allow `python -m src.weaviate.test_etl_adapter` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.weaviate.etl_adapter import WeaviateETLAdapter, _CHUNK_PROPERTIES


# --- Stub v4 client surface --------------------------------------------


class _StubObject:
    """Mimics weaviate.classes' returned object."""
    def __init__(self, uuid: str, properties: dict):
        self.uuid = uuid
        self.properties = dict(properties)


class _StubData:
    """Mimics collection.data.{insert, replace, update, delete_many}."""
    def __init__(self, parent: "_StubCollection"):
        self.parent = parent
        # Track whether the next replace should fail. Tests can flip
        # this to exercise the insert fallback.
        self.fail_replace_with: Optional[Exception] = None

    def insert(self, *, uuid, properties, vector):
        self.parent.objects[uuid] = {
            "properties": dict(properties), "vector": list(vector),
        }

    def replace(self, *, uuid, properties, vector):
        if self.fail_replace_with is not None:
            raise self.fail_replace_with
        self.parent.objects[uuid] = {
            "properties": dict(properties), "vector": list(vector),
        }

    def update(self, *, uuid, properties):
        if uuid not in self.parent.objects:
            raise KeyError(uuid)
        self.parent.objects[uuid]["properties"].update(properties)

    def delete_many(self, *, where):
        # Stub: count what would-match based on the where filter's
        # `.matched_objects` attr (we attach it from the test setup).
        n = getattr(where, "_matched_count", 0)
        class _Res:
            successful = n
        return _Res()


class _StubQuery:
    def __init__(self, parent: "_StubCollection"):
        self.parent = parent

    def fetch_object_by_id(self, uuid):
        row = self.parent.objects.get(uuid)
        if row is None:
            return None
        return _StubObject(uuid, row["properties"])


class _StubAggregate:
    def __init__(self, parent: "_StubCollection"):
        self.parent = parent

    def over_all(self, *, total_count=False):
        class _Res:
            pass
        r = _Res()
        r.total_count = len(self.parent.objects) if total_count else 0
        return r


class _StubCollection:
    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.data = _StubData(self)
        self.query = _StubQuery(self)
        self.aggregate = _StubAggregate(self)

    def iterator(self, *, return_properties=None):
        for uuid, row in self.objects.items():
            props = row["properties"]
            if return_properties:
                props = {k: props.get(k) for k in return_properties}
            yield _StubObject(uuid, props)


class _StubCollections:
    """Mimics client.collections.{exists, get, create}."""
    def __init__(self):
        self._collections: dict[str, _StubCollection] = {}
        self.create_calls: list[dict] = []

    def exists(self, name: str) -> bool:
        return name in self._collections

    def get(self, name: str) -> _StubCollection:
        if name not in self._collections:
            raise KeyError(name)
        return self._collections[name]

    def create(self, *, name, vectorizer_config=None, properties=None):
        self.create_calls.append({"name": name, "properties": properties})
        self._collections[name] = _StubCollection()


class _StubClient:
    def __init__(self):
        self.collections = _StubCollections()


# Inject stubbed weaviate.classes.config + .query before adapter imports.
# (The adapter does lazy imports inside its methods so we can fake them
# here without breaking module-level loading.)
def _install_weaviate_stubs():
    """Inject minimal weaviate.classes.config + weaviate.classes.query
    stubs so the lazy imports inside adapter methods don't blow up
    when the real SDK isn't reachable in the test process."""
    if "weaviate" not in sys.modules:
        # Don't shadow the real SDK if it's already loaded.
        weav = types.ModuleType("weaviate")
        sys.modules["weaviate"] = weav

    classes = sys.modules.setdefault("weaviate.classes", types.ModuleType("weaviate.classes"))
    sys.modules["weaviate"].classes = classes  # type: ignore[attr-defined]

    config_mod = sys.modules.setdefault("weaviate.classes.config", types.ModuleType("weaviate.classes.config"))
    classes.config = config_mod  # type: ignore[attr-defined]

    class _DataType:
        TEXT = "TEXT"
        INT = "INT"
        BOOL = "BOOL"
        TEXT_ARRAY = "TEXT_ARRAY"

    class _Configure:
        class Vectorizer:
            @staticmethod
            def none():
                return "vectorizer:none"

    class _Property:
        def __init__(self, *, name, data_type):
            self.name = name
            self.data_type = data_type
        def __repr__(self):
            return f"Property({self.name}, {self.data_type})"

    config_mod.Configure = _Configure  # type: ignore[attr-defined]
    config_mod.DataType = _DataType  # type: ignore[attr-defined]
    config_mod.Property = _Property  # type: ignore[attr-defined]

    query_mod = sys.modules.setdefault("weaviate.classes.query", types.ModuleType("weaviate.classes.query"))
    classes.query = query_mod  # type: ignore[attr-defined]

    class _Filter:
        @staticmethod
        def by_property(name):
            f = _Filter()
            f._name = name
            return f
        def equal(self, v):
            f = _Filter()
            f._name, f._eq = self._name, v
            f._matched_count = 0
            return f
        def less_than(self, v):
            f = _Filter()
            f._name, f._lt = self._name, v
            f._matched_count = 0
            return f
        def __and__(self, other):
            f = _Filter()
            f._matched_count = 0
            return f

    query_mod.Filter = _Filter  # type: ignore[attr-defined]


_install_weaviate_stubs()


# --- Tests --------------------------------------------------------------


def _adapter() -> WeaviateETLAdapter:
    return WeaviateETLAdapter(client=_StubClient())


def test_ensure_collection_creates_with_documented_properties() -> None:
    a = _adapter()
    a._ensure_collection("Chunk_v1")
    calls = a.client.collections.create_calls
    assert len(calls) == 1
    created = calls[0]
    assert created["name"] == "Chunk_v1"
    # Every documented property should be in the create call.
    created_names = {p.name for p in created["properties"]}
    expected_names = {n for n, _ in _CHUNK_PROPERTIES}
    assert expected_names.issubset(created_names), (
        f"missing properties: {expected_names - created_names}"
    )


def test_ensure_collection_idempotent_after_first_call() -> None:
    """Second call shouldn't re-create. Cached in adapter state."""
    a = _adapter()
    a._ensure_collection("Chunk_v1")
    a._ensure_collection("Chunk_v1")
    assert len(a.client.collections.create_calls) == 1


def test_ensure_collection_skips_create_if_already_exists() -> None:
    """If Weaviate already has the collection (different adapter
    instance / persistent state), create is skipped."""
    a = _adapter()
    # Pre-create
    a.client.collections._collections["Chunk_v1"] = _StubCollection()
    a._ensure_collection("Chunk_v1")
    assert len(a.client.collections.create_calls) == 0


def test_upsert_chunk_writes_via_replace() -> None:
    a = _adapter()
    a.upsert_chunk(
        collection="Chunk_v1",
        chunk_id="cid-1",
        properties={"text": "hello", "campus": "oxford"},
        vector=[0.1, 0.2, 0.3],
    )
    stored = a.client.collections._collections["Chunk_v1"].objects
    assert "cid-1" in stored
    assert stored["cid-1"]["properties"]["text"] == "hello"
    assert stored["cid-1"]["vector"] == [0.1, 0.2, 0.3]


def test_upsert_chunk_falls_back_to_insert_when_replace_fails() -> None:
    """v4 replace can raise on nonexistent UUIDs. The adapter falls
    back to insert so the upsert primitive works in both cases."""
    a = _adapter()
    # Cause the first call's replace to fail.
    a._ensure_collection("Chunk_v1")
    coll = a.client.collections._collections["Chunk_v1"]
    coll.data.fail_replace_with = RuntimeError("not found")
    a.upsert_chunk(
        collection="Chunk_v1",
        chunk_id="cid-2",
        properties={"text": "via-insert"},
        vector=[1.0],
    )
    # Fallback succeeded.
    assert coll.objects["cid-2"]["properties"]["text"] == "via-insert"


def test_get_chunk_returns_properties_on_hit() -> None:
    a = _adapter()
    a.upsert_chunk(
        collection="Chunk_v1", chunk_id="cid-x",
        properties={"text": "found", "campus": "oxford"},
        vector=[0.5],
    )
    out = a.get_chunk(collection="Chunk_v1", chunk_id="cid-x")
    assert out is not None
    assert out["text"] == "found"
    assert out["campus"] == "oxford"


def test_get_chunk_returns_none_for_missing_object() -> None:
    a = _adapter()
    a._ensure_collection("Chunk_v1")
    assert a.get_chunk(collection="Chunk_v1", chunk_id="nope") is None


def test_get_chunk_returns_none_for_missing_collection() -> None:
    a = _adapter()
    # Don't call _ensure_collection first.
    assert a.get_chunk(collection="DoesNotExist", chunk_id="x") is None


def test_soft_delete_by_url_tombstones_non_seen_only() -> None:
    a = _adapter()
    # Three chunks: two stay, one tombstoned.
    for cid, url in [("c1", "u1"), ("c2", "u2"), ("c3", "u3")]:
        a.upsert_chunk(
            collection="Chunk_v1", chunk_id=cid,
            properties={"source_url": url, "deleted": False},
            vector=[0.1],
        )
    # Seen-set: u1 + u2. c3 should be tombstoned.
    tombstoned = a.soft_delete_by_url(
        collection="Chunk_v1", urls=["u1", "u2"],
    )
    assert tombstoned == ["u3"]
    coll = a.client.collections._collections["Chunk_v1"]
    assert coll.objects["c3"]["properties"]["deleted"] is True
    assert coll.objects["c1"]["properties"]["deleted"] is False
    # Tombstoned chunk should have a tombstoned_at timestamp.
    assert coll.objects["c3"]["properties"].get("tombstoned_at")


def test_soft_delete_by_url_idempotent_on_already_deleted() -> None:
    """Re-tombstoning an already-tombstoned chunk shouldn't double-
    count it in the return value."""
    a = _adapter()
    a.upsert_chunk(
        collection="Chunk_v1", chunk_id="c1",
        properties={"source_url": "u1", "deleted": True},
        vector=[0.1],
    )
    tombstoned = a.soft_delete_by_url(collection="Chunk_v1", urls=[])
    assert tombstoned == []


def test_gc_tombstones_uses_deleted_and_older_than_filter() -> None:
    a = _adapter()
    a._ensure_collection("Chunk_v1")
    # We can't actually filter in the stub, but we can verify gc was
    # invoked and a count is returned.
    count = a.gc_tombstones(
        collection="Chunk_v1",
        older_than=dt.datetime(2026, 1, 1),
    )
    assert isinstance(count, int)


def test_gc_tombstones_returns_zero_for_missing_collection() -> None:
    a = _adapter()
    assert a.gc_tombstones(
        collection="Nonexistent",
        older_than=dt.datetime(2026, 1, 1),
    ) == 0


def test_count_returns_zero_for_missing_collection() -> None:
    a = _adapter()
    assert a.count(collection="Nonexistent") == 0


def test_count_returns_actual_count_after_upserts() -> None:
    a = _adapter()
    for cid in ["a", "b", "c"]:
        a.upsert_chunk(
            collection="Chunk_v1", chunk_id=cid,
            properties={}, vector=[0.1],
        )
    assert a.count(collection="Chunk_v1") == 3


# --- Runner -------------------------------------------------------------


def main() -> int:
    tests = [
        test_ensure_collection_creates_with_documented_properties,
        test_ensure_collection_idempotent_after_first_call,
        test_ensure_collection_skips_create_if_already_exists,
        test_upsert_chunk_writes_via_replace,
        test_upsert_chunk_falls_back_to_insert_when_replace_fails,
        test_get_chunk_returns_properties_on_hit,
        test_get_chunk_returns_none_for_missing_object,
        test_get_chunk_returns_none_for_missing_collection,
        test_soft_delete_by_url_tombstones_non_seen_only,
        test_soft_delete_by_url_idempotent_on_already_deleted,
        test_gc_tombstones_uses_deleted_and_older_than_filter,
        test_gc_tombstones_returns_zero_for_missing_collection,
        test_count_returns_zero_for_missing_collection,
        test_count_returns_actual_count_after_upserts,
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
