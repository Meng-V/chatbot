"""Unit tests for the eval's honest-baseline ToolBackends.

Run: `python -m src.eval.test_real_backends` from ai-core/.

These are OFFLINE tests -- no Postgres, no LibCal. The load-bearing
one is `test_point_to_url_urls_mirror_capability_scope`: it is the
anti-fabrication drift guard. The entire project exists to stop the
bot inventing URLs; this module must never be the thing that does.

Tests:
  1. point_to_url non-ILL URLs are all still literally present in a
     capability_scope.LIMITATIONS response (DRIFT GUARD).
  2. point_to_url ILL is campus-aware and sourced live from ILL_URLS
     (Oxford != Hamilton != Middletown).
  3. point_to_url for an unknown service returns NO url (never a guess).
  4. ONLY write/handoff tools + lookup_space stay unwired sentinels
     (get_hours / get_room_availability are now WIRED to legacy LibCal).
  5. every read-only backend is wired (none is the unwired sentinel).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.config.capability_scope import ILL_URLS, LIMITATIONS  # noqa: E402
from src.agent.tool_registry import ToolError  # noqa: E402
from src.eval.real_backends import (  # noqa: E402
    _POINT_TO_URL,
    _make_point_to_url,
    build_eval_backends,
)

_URL_RE = re.compile(r"https://[^\s\"',)]+")


def _capability_scope_urls() -> set[str]:
    """Every https URL that appears in a LIMITATIONS response string."""
    urls: set[str] = set()
    for entry in LIMITATIONS.values():
        resp = entry.get("response") or ""
        urls.update(_URL_RE.findall(resp))
    return urls


# --- 1. DRIFT GUARD ---


def test_point_to_url_urls_mirror_capability_scope() -> None:
    """Every non-ILL URL the eval can emit MUST still be literally
    present in capability_scope. If someone edits capability_scope and
    this map drifts, this fails loudly -- which is the entire point."""
    source_urls = _capability_scope_urls()
    for service, (url, _desc) in _POINT_TO_URL.items():
        assert url in source_urls, (
            f"point_to_url[{service!r}] = {url!r} is NOT present in any "
            f"capability_scope.LIMITATIONS response. Either the URL was "
            f"invented (forbidden) or capability_scope changed and this "
            f"map must be updated to match the new source of truth."
        )


# --- 2. ILL campus-awareness, live-sourced ---


def test_point_to_url_ill_is_campus_aware_and_live_sourced() -> None:
    point = _make_point_to_url()

    oxford = point("ill", {"campus": "oxford"})
    hamilton = point("ill", {"campus": "hamilton"})
    middletown = point("interlibrary_loan", {"campus": "middletown"})
    default = point("ill", {})  # no campus -> Oxford default

    # Sourced LIVE from capability_scope.ILL_URLS (cannot drift).
    assert oxford["url"] == ILL_URLS["main"]["url"]
    assert hamilton["url"] == ILL_URLS["hamilton"]["url"]
    assert middletown["url"] == ILL_URLS["middletown"]["url"]
    assert default["url"] == ILL_URLS["main"]["url"]

    # The whole reason ILL is campus-aware: never cross campuses.
    assert hamilton["url"] != oxford["url"]
    assert middletown["url"] != oxford["url"]
    assert all(r["found"] for r in (oxford, hamilton, middletown, default))


# --- 3. unknown service: NO fabrication ---


def test_point_to_url_unknown_service_returns_no_url() -> None:
    point = _make_point_to_url()
    out = point("teleportation", {"campus": "oxford"})
    assert out["found"] is False
    assert out["url"] is None
    # It must NOT have guessed a plausible-looking link.
    assert "http" not in (str(out["url"]) or "")
    assert "teleportation" in out["description"]


def test_point_to_url_known_service_shape() -> None:
    point = _make_point_to_url()
    out = point("course_reserves", {})
    assert out["found"] is True
    assert out["url"].startswith("https://")
    assert out["service"] == "course_reserves"


# --- 4. ONLY write/handoff/space tools stay unwired ---


def test_only_write_and_handoff_tools_stay_unwired() -> None:
    """get_hours / get_room_availability are now WIRED (legacy LibCal
    reuse) -- they must NOT be the sentinel. Only the write/handoff
    tools + lookup_space stay unwired (and `_build_real_deps` drops
    those four from the eval surface anyway)."""
    b = build_eval_backends()
    for name, call in (
        ("book_room", lambda: b.book_room({})),
        ("create_ticket", lambda: b.create_ticket({})),
        ("handoff_human", lambda: b.handoff_human({})),
        ("lookup_space", lambda: b.lookup_space({})),
    ):
        try:
            call()
        except ToolError as e:
            assert "not wired" in str(e).lower(), (name, str(e))
            continue
        raise AssertionError(f"{name} should raise the unwired ToolError")


# --- 5. every read-only backend is actually wired (not a sentinel) ---


def test_all_readonly_backends_wired() -> None:
    b = build_eval_backends()
    # point_to_url is exercisable offline -> prove it's the real one.
    out = b.point_to_url("ill", {"campus": "hamilton"})
    assert out["url"] == ILL_URLS["hamilton"]["url"]
    # The rest hit Postgres / LibCal (network) -> don't call here.
    # Prove none is the tools_v2 unwired sentinel (whose closure
    # qualname contains "_make_unwired_sentinel" -> "unwired").
    for name in (
        "validate_url",
        "lookup_librarian",
        "get_hours",
        "get_room_availability",
    ):
        backend = getattr(b, name)
        qualname = getattr(backend, "__qualname__", "")
        assert "unwired" not in qualname, (
            f"{name} is still the unwired sentinel ({qualname})"
        )
    # validate_url is the production UrlAllowlistValidator instance.
    assert type(b.validate_url).__name__ == "UrlAllowlistValidator"


def main() -> int:
    tests = [
        test_point_to_url_urls_mirror_capability_scope,
        test_point_to_url_ill_is_campus_aware_and_live_sourced,
        test_point_to_url_unknown_service_returns_no_url,
        test_point_to_url_known_service_shape,
        test_only_write_and_handoff_tools_stay_unwired,
        test_all_readonly_backends_wired,
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
