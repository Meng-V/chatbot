"""
Unit tests for the per-intent capability registry.

Run: `python -m src.router.test_intent_capabilities` from ai-core/.

The registry decides whether the orchestrator runs the agent or
short-circuits to a templated response. Bugs go two ways:

  - False POINT_TO_URL or REFUSE for an intent that should run the
    agent: the librarian-flagged "circulation_basic" question gets
    a generic refusal instead of a real answer.
  - False READY for an intent that should short-circuit: the bot
    burns agent + synth tokens trying to answer "how much do I owe"
    and produces a hallucinated balance.

Tests pin every registered capability and every default behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.router.test_intent_capabilities`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_capabilities import (  # noqa: E402
    CapabilityTier,
    IntentCapability,
    all_capabilities,
    get_intent_capability,
)
from src.router.intent_knn import INTENTS  # noqa: E402


# --- POINT_TO_URL intents ------------------------------------------------


def test_databases_is_point_to_url() -> None:
    """Per librarian decision: never look up DB by name; always route
    to A-Z. Users misspell DB names too often to risk a wrong-DB
    answer."""
    cap = get_intent_capability("databases")
    assert cap.tier == CapabilityTier.POINT_TO_URL
    assert "libguides.lib.miamioh.edu/az/databases" in cap.canonical_url
    assert "Databases A-Z" in cap.short_message
    # Defends the design decision in the body so it's readable to
    # future maintainers.
    assert "Web of Science" in cap.short_message  # the disambiguation example


def test_find_resource_is_point_to_url_to_primo() -> None:
    cap = get_intent_capability("find_resource")
    assert cap.tier == CapabilityTier.POINT_TO_URL
    assert "primo" in cap.canonical_url.lower()
    assert "Primo" in cap.short_message
    # Includes the ILL fallback for "we don't have it" path.
    assert "Interlibrary Loan" in cap.short_message


# --- REFUSE intents ------------------------------------------------------


def test_account_is_refuse_with_privacy_trigger() -> None:
    cap = get_intent_capability("account")
    assert cap.tier == CapabilityTier.REFUSE
    assert cap.refusal_trigger == "account_privacy"
    assert cap.canonical_url is not None
    assert "MyAccount" in cap.short_message
    # The refusal must be explicit -- "I can't access your account",
    # not just "I don't know" -- so the user understands the boundary.
    assert "can't access your library account" in cap.short_message


def test_events_news_is_refuse_with_news_excluded_trigger() -> None:
    cap = get_intent_capability("events_news")
    assert cap.tier == CapabilityTier.REFUSE
    assert cap.refusal_trigger == "news_excluded"
    assert cap.canonical_url is not None
    # Must explain WHY (stale events are misleading).
    assert (
        "old event" in cap.short_message.lower()
        or "stale" in cap.short_message.lower()
    )


# --- READY default ------------------------------------------------------


def test_unregistered_intent_defaults_to_ready() -> None:
    """Any intent not explicitly POINT_TO_URL or REFUSE runs the
    agent. Default-allow is safer than default-deny: a typo'd intent
    name produces a real answer attempt rather than silently
    refusing."""
    cap = get_intent_capability("hours")
    assert cap.tier == CapabilityTier.READY
    assert cap.canonical_url is None
    assert cap.short_message == ""
    assert cap.refusal_trigger == ""


def test_makerspace_is_ready() -> None:
    """Sanity check that bread-and-butter intents stay READY."""
    cap = get_intent_capability("makerspace_3d")
    assert cap.tier == CapabilityTier.READY


def test_subject_librarian_is_ready() -> None:
    cap = get_intent_capability("subject_librarian")
    assert cap.tier == CapabilityTier.READY


def test_interlibrary_loan_is_ready() -> None:
    """ILL stays READY -- the agent calls point_to_url to return
    the form. Per plan: action vs guidance distinction."""
    cap = get_intent_capability("interlibrary_loan")
    assert cap.tier == CapabilityTier.READY


def test_unknown_intent_string_does_not_crash() -> None:
    """Defensive: garbage input doesn't crash the lookup."""
    cap = get_intent_capability("totally_made_up_intent_xyz")
    assert cap.tier == CapabilityTier.READY


# --- Coverage / lock-in -------------------------------------------------


def test_every_registered_capability_has_canonical_url() -> None:
    """POINT_TO_URL and REFUSE both require a destination URL --
    that's the whole point. A registry entry without one is a bug."""
    for cap in all_capabilities().values():
        assert cap.canonical_url, (
            f"{cap.intent} has tier={cap.tier} but no canonical_url"
        )


def test_every_registered_capability_has_short_message() -> None:
    for cap in all_capabilities().values():
        assert cap.short_message.strip(), (
            f"{cap.intent} has empty short_message"
        )


def test_refuse_capabilities_have_refusal_trigger() -> None:
    for cap in all_capabilities().values():
        if cap.tier == CapabilityTier.REFUSE:
            assert cap.refusal_trigger, (
                f"REFUSE capability {cap.intent} missing refusal_trigger"
            )


def test_point_to_url_capabilities_have_no_refusal_trigger() -> None:
    """POINT_TO_URL is an answer, not a refusal -- the trigger field
    should be empty."""
    for cap in all_capabilities().values():
        if cap.tier == CapabilityTier.POINT_TO_URL:
            assert not cap.refusal_trigger, (
                f"POINT_TO_URL capability {cap.intent} should not have "
                f"a refusal_trigger; got {cap.refusal_trigger!r}"
            )


def test_registered_intents_are_in_INTENTS_tuple() -> None:
    """Every key in the registry must be a real intent. A typo'd key
    here would silently never fire."""
    for intent in all_capabilities():
        assert intent in INTENTS, (
            f"capability registered for unknown intent: {intent!r}"
        )


def test_every_intent_resolves_without_crash() -> None:
    """Smoke check: get_intent_capability handles every intent the
    classifier might return."""
    for intent in INTENTS:
        cap = get_intent_capability(intent)
        assert cap is not None
        assert cap.tier in (
            CapabilityTier.READY,
            CapabilityTier.POINT_TO_URL,
            CapabilityTier.REFUSE,
        )


def test_capability_tier_string_values() -> None:
    """JSON-serializable enum values for log shipping."""
    assert CapabilityTier.READY.value == "ready"
    assert CapabilityTier.POINT_TO_URL.value == "point_to_url"
    assert CapabilityTier.REFUSE.value == "refuse"


def test_intent_capability_dataclass_immutability() -> None:
    """Frozen dataclass -- prevents callers from mutating registry
    entries (which would persist across requests)."""
    cap = get_intent_capability("databases")
    try:
        cap.canonical_url = "https://attacker.example/"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("expected frozen dataclass to reject mutation")


def main() -> int:
    tests = [
        test_databases_is_point_to_url,
        test_find_resource_is_point_to_url_to_primo,
        test_account_is_refuse_with_privacy_trigger,
        test_events_news_is_refuse_with_news_excluded_trigger,
        test_unregistered_intent_defaults_to_ready,
        test_makerspace_is_ready,
        test_subject_librarian_is_ready,
        test_interlibrary_loan_is_ready,
        test_unknown_intent_string_does_not_crash,
        test_every_registered_capability_has_canonical_url,
        test_every_registered_capability_has_short_message,
        test_refuse_capabilities_have_refusal_trigger,
        test_point_to_url_capabilities_have_no_refusal_trigger,
        test_registered_intents_are_in_INTENTS_tuple,
        test_every_intent_resolves_without_crash,
        test_capability_tier_string_values,
        test_intent_capability_dataclass_immutability,
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
