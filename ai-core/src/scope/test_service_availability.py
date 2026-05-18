"""
Offline tests for the cross-campus service-availability guard.

Run: `python -m src.scope.test_service_availability` from ai-core/.

Pure/sync/no-DB/no-OpenAI. Synthetic rows give deterministic control;
the final test locks the REAL production behavior against the
canonical seed SPACES (the load-bearing "MakerSpace at Hamilton"
case the whole guard exists for).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.scope.service_availability import build_service_guard
from src.synthesis.refusal_templates import RefusalContext


@dataclass(frozen=True)
class _Row:
    campus: str
    library: str
    name: str
    services_offered: list = field(default_factory=list)


# King has makerspace; Rentschler (Hamilton) does not -- the canonical
# shape of the real data, in miniature.
_SYNTH = [
    _Row("oxford", "king", "Edward King Library",
         ["printing", "makerspace", "study_rooms"]),
    _Row("oxford", "special", "Special Collections",
         ["rare_books_access", "archival_research"]),
    _Row("hamilton", "rentschler", "Rentschler Library",
         ["printing", "study_rooms"]),
    _Row("middletown", "gardner_harvey", "Gardner-Harvey Library",
         ["printing", "study_rooms"]),
]


def test_gated_missing_campus_refuses_with_context() -> None:
    g = build_service_guard(_SYNTH)
    r = g("makerspace_3d", "hamilton")
    assert isinstance(r, RefusalContext), r
    assert r.service_name == "the MakerSpace"
    assert r.campus_display == "Hamilton"
    assert r.service_available_at == "Edward King Library on the Oxford campus"


def test_gated_present_campus_allows() -> None:
    g = build_service_guard(_SYNTH)
    assert g("makerspace_3d", "oxford") is None


def test_special_collections_gating() -> None:
    g = build_service_guard(_SYNTH)
    assert g("special_collections", "middletown") is not None
    assert g("special_collections", "oxford") is None


def test_ungated_intent_never_refuses() -> None:
    g = build_service_guard(_SYNTH)
    # University-wide / common services must NOT be gated anywhere.
    for intent in ("interlibrary_loan", "printing_wifi", "adobe_access",
                   "newspapers", "hours", "subject_librarian"):
        assert g(intent, "hamilton") is None, intent


def test_unknown_intent_returns_none() -> None:
    g = build_service_guard(_SYNTH)
    assert g("totally_unknown_intent", "middletown") is None


def test_empty_or_none_campus_defaults_oxford() -> None:
    g = build_service_guard(_SYNTH)
    # Default scope is Oxford -> King has makerspace -> no refusal.
    assert g("makerspace_3d", "") is None
    assert g("makerspace_3d", None) is None


def test_no_spaces_disables_guard_safely() -> None:
    """Safe degradation: if the truth table can't load, the guard must
    NOT start refusing legitimate questions."""
    g = build_service_guard([])
    assert g("makerspace_3d", "hamilton") is None


def test_canonical_seed_locks_real_behavior() -> None:
    """No-arg build reads the real seed SPACES. This locks the plan's
    load-bearing behavior against the actual shipped data."""
    g = build_service_guard()  # canonical SPACES
    hamilton = g("makerspace_3d", "hamilton")
    assert isinstance(hamilton, RefusalContext), hamilton
    assert "MakerSpace" in (hamilton.service_name or "")
    assert "Oxford" in (hamilton.service_available_at or "")
    assert g("makerspace_3d", "oxford") is None
    assert g("special_collections", "middletown") is not None
    assert g("special_collections", "oxford") is None
    # Ungated stays open campus-wide.
    assert g("interlibrary_loan", "hamilton") is None


def main() -> int:
    tests = [
        test_gated_missing_campus_refuses_with_context,
        test_gated_present_campus_allows,
        test_special_collections_gating,
        test_ungated_intent_never_refuses,
        test_unknown_intent_returns_none,
        test_empty_or_none_campus_defaults_oxford,
        test_no_spaces_disables_guard_safely,
        test_canonical_seed_locks_real_behavior,
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
