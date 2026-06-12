"""
Tests for PrismaCorrectionsStore.

The Prisma round-trip is integration territory (needs a live DB).
What we lock down here is the pure mapping + the orchestrator-facing
shape: given fake DB rows, does the adapter return the right
`ManualCorrection` dataclass list?

Run: `python -m src.database.test_corrections_adapter` from ai-core/.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.database.corrections_adapter import (  # noqa: E402
    PrismaCorrectionsStore,
    _reset_module_cache_for_tests,
    _uuid_to_int,
)
from src.synthesis.corrections import ManualCorrection  # noqa: E402


# --- Stub Prisma client ----------------------------------------------------


class _FakeManualCorrectionTable:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.last_where: dict | None = None

    async def find_many(self, where: dict) -> list[SimpleNamespace]:
        self.last_where = where
        # Apply the where dict the way Prisma would, so the adapter's
        # filter assumptions stay honest.
        out = []
        for r in self.rows:
            if where.get("active") is not None and r.active != where["active"]:
                continue
            if "expiresAt" in where:
                cond = where["expiresAt"]
                if "gt" in cond and not (r.expiresAt > cond["gt"]):
                    continue
            out.append(r)
        return out


class _FakeClient:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.manualcorrection = _FakeManualCorrectionTable(rows)
        self._connected = True

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True


def _row(uuid: str, *, scope="url", target="https://example.com/", action="blacklist_url",
         replacement=None, query_pattern=None, reason="test", created_by="me@example.com",
         active=True, days_until_expiry=30) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid,
        scope=scope,
        target=target,
        action=action,
        replacement=replacement,
        queryPattern=query_pattern,
        reason=reason,
        createdBy=created_by,
        active=active,
        expiresAt=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days_until_expiry),
    )


# --- Tests ------------------------------------------------------------------


def test_uuid_to_int_is_deterministic() -> None:
    """Same UUID -> same int across calls. Operators rely on this for
    log-to-DB joinability."""
    u = "550e8400-e29b-41d4-a716-446655440000"
    assert _uuid_to_int(u) == _uuid_to_int(u)


def test_uuid_to_int_is_positive_31bit() -> None:
    """Stays in signed-int32-positive range so it JSON-serializes
    cleanly in TurnResponse.fired_corrections."""
    for u in [
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "abc-123",
        "z" * 50,
    ]:
        n = _uuid_to_int(u)
        assert 0 <= n <= 0x7FFFFFFF


def test_uuid_to_int_distinct_uuids_give_distinct_ints() -> None:
    """No catastrophic collisions on a small set of distinct UUIDs.
    Not a security property -- just a sanity check that the hash
    actually distinguishes corrections in the typical 10-30 row set."""
    uuids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(50)]
    ints = {_uuid_to_int(u) for u in uuids}
    assert len(ints) == 50, f"collision in {50} distinct UUIDs: only {len(ints)} unique ints"


def test_load_active_filters_inactive_and_expired() -> None:
    _reset_module_cache_for_tests()
    """The where clause must include active=true AND expiresAt > now."""
    client = _FakeClient([
        _row("u-active", active=True, days_until_expiry=10),
        _row("u-inactive", active=False, days_until_expiry=10),
        _row("u-expired", active=True, days_until_expiry=-1),
    ])
    store = PrismaCorrectionsStore(client=client)
    out = store.load_active()
    assert len(out) == 1
    assert out[0].id == _uuid_to_int("u-active")
    # Confirm the filter was actually issued, not faked at the test layer.
    where = client.manualcorrection.last_where
    assert where["active"] is True
    assert "gt" in where["expiresAt"]


def test_load_active_returns_empty_when_no_rows() -> None:
    _reset_module_cache_for_tests()
    store = PrismaCorrectionsStore(client=_FakeClient([]))
    assert store.load_active() == []


def test_load_active_maps_all_fields() -> None:
    _reset_module_cache_for_tests()
    client = _FakeClient([_row(
        "u-1",
        scope="chunk",
        target="chunk-abc",
        action="replace",
        replacement="The corrected text.",
        query_pattern=None,
        reason="Fixed by librarian on 2026-05-21",
        created_by="alice@library.miamioh.edu",
    )])
    store = PrismaCorrectionsStore(client=client)
    [c] = store.load_active()
    assert c.id == _uuid_to_int("u-1")
    assert c.scope == "chunk"
    assert c.target == "chunk-abc"
    assert c.action == "replace"
    assert c.replacement == "The corrected text."
    assert c.query_pattern is None
    assert c.reason.startswith("Fixed by")
    assert c.created_by == "alice@library.miamioh.edu"


def test_load_active_returns_manualcorrection_instances() -> None:
    """Type discipline: orchestrator types this as `list[ManualCorrection]`."""
    _reset_module_cache_for_tests()
    client = _FakeClient([_row("u-1")])
    store = PrismaCorrectionsStore(client=client)
    for c in store.load_active():
        assert isinstance(c, ManualCorrection)


def test_load_active_caches_first_result() -> None:
    """Caching contract: first call queries Postgres, subsequent calls
    return the cached list without re-querying. Module-level cache, so
    even a NEW store instance shares the result (this is the eval
    use case: _build_real_deps creates a fresh store per turn)."""
    _reset_module_cache_for_tests()
    client = _FakeClient([_row("u-1", scope="url", action="blacklist_url")])
    store = PrismaCorrectionsStore(client=client)
    first = store.load_active()
    assert len(first) == 1
    # Simulate the table changing under us. Cache should NOT reflect this.
    client.manualcorrection.rows.append(_row("u-2"))
    second = store.load_active()
    assert len(second) == 1, (
        "Caching contract violated: second load_active() picked up a new row."
    )
    # Module-level cache: a NEW store instance (per-turn pattern) also
    # uses the cache. THIS is the eval-path scenario the 2026-05-21 fix
    # was for.
    new_store = PrismaCorrectionsStore(client=client)
    via_new_store = new_store.load_active()
    assert len(via_new_store) == 1, (
        "Module-level cache must span store instances -- otherwise the per-turn "
        "_build_real_deps pattern re-queries Postgres every turn (the bug)."
    )
    # refresh() should re-read.
    refreshed = store.refresh()
    assert len(refreshed) == 2


def test_load_active_failure_does_not_poison_cache() -> None:
    """2026-06-11 semantics: a first-call failure RAISES and the next
    call RETRIES (the old behavior -- cache empty forever after one bad
    call -- is what silenced corrections on prod for a whole process)."""
    _reset_module_cache_for_tests()
    class _FailingClient:
        def __init__(self):
            self._connected = False
            self.call_count = 0
        def is_connected(self):
            return self._connected
        async def connect(self):
            self.call_count += 1
            raise RuntimeError("Postgres unreachable")

    client = _FailingClient()
    store = PrismaCorrectionsStore(client=client)
    for expected_calls in (1, 2):
        try:
            store.load_active()
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass
        assert client.call_count == expected_calls, (
            f"call {expected_calls}: expected a retry, got call_count="
            f"{client.call_count} (failure must not be cached)"
        )


def test_load_active_serves_stale_on_refresh_failure() -> None:
    """A transient pg blip after a good load must not strip the override
    layer: serve the last good value, don't raise."""
    _reset_module_cache_for_tests()
    client = _FakeClient([_row("u-1")])
    store = PrismaCorrectionsStore(client=client)
    assert len(store.load_active()) == 1

    async def _boom(where):
        raise RuntimeError("Postgres blip")
    client.manualcorrection.find_many = _boom
    import src.database.corrections_adapter as mod
    mod._module_cached_at = None  # force a refresh attempt past the TTL
    stale = store.load_active()
    assert len(stale) == 1, "refresh failure must serve the stale cache"


def test_pin_correction_passes_query_pattern() -> None:
    """The pin action requires query_pattern -- apply_corrections() uses
    it as a regex. Lock the field mapping."""
    _reset_module_cache_for_tests()
    client = _FakeClient([_row(
        "u-pin",
        scope="chunk",
        target="pinned-chunk-id",
        action="pin",
        query_pattern=r"how do I print",
        replacement=None,
    )])
    store = PrismaCorrectionsStore(client=client)
    [c] = store.load_active()
    assert c.action == "pin"
    assert c.query_pattern == r"how do I print"


def main() -> int:
    tests = [
        test_uuid_to_int_is_deterministic,
        test_uuid_to_int_is_positive_31bit,
        test_uuid_to_int_distinct_uuids_give_distinct_ints,
        test_load_active_filters_inactive_and_expired,
        test_load_active_returns_empty_when_no_rows,
        test_load_active_maps_all_fields,
        test_load_active_returns_manualcorrection_instances,
        test_load_active_caches_first_result,
        test_load_active_failure_does_not_poison_cache,
        test_load_active_serves_stale_on_refresh_failure,
        test_pin_correction_passes_query_pattern,
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
