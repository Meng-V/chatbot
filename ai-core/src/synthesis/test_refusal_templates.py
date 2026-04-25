"""
Unit tests for the templated refusal copy.

Run: `python -m src.synthesis.test_refusal_templates` from ai-core/.

Refusals are templated (not LLM-generated) so the wording is predictable
and the affordance is consistent. Tests guard against three failure modes:

  1. Template references a placeholder field that's missing from
     RefusalContext -> KeyError at render (must NOT silently render
     "{campus_display}" to a user).
  2. Every RefusalTrigger enum value has a template registered.
  3. Scope-free triggers render without a context.

Tests:
  1. Each scope-free trigger renders without context, returns non-empty string.
  2. CROSS_CAMPUS_MISMATCH renders correctly with full context.
  3. CROSS_CAMPUS_MISMATCH raises KeyError if campus_display missing.
  4. CROSS_CAMPUS_MISMATCH raises KeyError if staff_directory_url missing.
  5. SERVICE_NOT_AT_BUILDING renders correctly with full context.
  6. SERVICE_NOT_AT_BUILDING raises KeyError if service_name missing.
  7. Every RefusalTrigger has a template (registry coverage).
  8. None of the rendered messages contain literal "{...}" placeholder syntax.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.synthesis.test_refusal_templates`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.synthesis.refusal_templates import (  # noqa: E402
    RefusalContext,
    RefusalTrigger,
    _TEMPLATES,
    render_refusal,
)


SCOPE_FREE_TRIGGERS = [
    RefusalTrigger.NO_RESULTS,
    RefusalTrigger.LOW_CONFIDENCE,
    RefusalTrigger.OUT_OF_SCOPE,
    RefusalTrigger.CAPABILITY_LIMIT,
    RefusalTrigger.LIVE_DATA_DOWN,
    RefusalTrigger.MODEL_SELF_FLAGGED,
    RefusalTrigger.CITATION_INVALID,
]

SCOPED_TRIGGERS = [
    RefusalTrigger.CROSS_CAMPUS_MISMATCH,
    RefusalTrigger.SERVICE_NOT_AT_BUILDING,
]


def test_scope_free_triggers_render_without_context() -> None:
    for trigger in SCOPE_FREE_TRIGGERS:
        msg = render_refusal(trigger)
        assert isinstance(msg, str), f"{trigger}: returned {type(msg)}"
        assert msg.strip(), f"{trigger}: empty message"
        # No leftover placeholder syntax should reach the user.
        assert "{" not in msg, f"{trigger}: unrendered placeholder in {msg!r}"


def test_cross_campus_renders_with_full_context() -> None:
    ctx = RefusalContext(
        campus_display="Hamilton",
        staff_directory_url="https://www.lib.miamioh.edu/about/organization/liaisons/",
    )
    msg = render_refusal(RefusalTrigger.CROSS_CAMPUS_MISMATCH, ctx)
    assert "Hamilton" in msg
    assert "https://www.lib.miamioh.edu/about/organization/liaisons/" in msg
    assert "{" not in msg


def test_cross_campus_raises_when_campus_missing() -> None:
    # Provide URL but not campus_display -- template needs both.
    ctx = RefusalContext(
        staff_directory_url="https://example.com/",
    )
    try:
        render_refusal(RefusalTrigger.CROSS_CAMPUS_MISMATCH, ctx)
    except KeyError as e:
        assert "campus_display" in str(e)
        return
    raise AssertionError("expected KeyError when campus_display missing")


def test_cross_campus_raises_when_staff_url_missing() -> None:
    ctx = RefusalContext(
        campus_display="Hamilton",
    )
    try:
        render_refusal(RefusalTrigger.CROSS_CAMPUS_MISMATCH, ctx)
    except KeyError as e:
        assert "staff_directory_url" in str(e)
        return
    raise AssertionError("expected KeyError when staff_directory_url missing")


def test_service_not_at_building_renders_with_full_context() -> None:
    ctx = RefusalContext(
        campus_display="Hamilton",
        service_name="MakerSpace",
        service_available_at="King Library on the Oxford campus",
    )
    msg = render_refusal(RefusalTrigger.SERVICE_NOT_AT_BUILDING, ctx)
    assert "MakerSpace" in msg
    assert "Hamilton" in msg
    assert "King Library" in msg
    assert "{" not in msg


def test_service_not_at_building_raises_when_service_name_missing() -> None:
    ctx = RefusalContext(
        campus_display="Hamilton",
        service_available_at="King Library on the Oxford campus",
    )
    try:
        render_refusal(RefusalTrigger.SERVICE_NOT_AT_BUILDING, ctx)
    except KeyError as e:
        assert "service_name" in str(e)
        return
    raise AssertionError("expected KeyError when service_name missing")


def test_every_trigger_has_a_template() -> None:
    """Coverage: if a future PR adds a new RefusalTrigger but forgets a
    template, this fails in CI rather than at production runtime."""
    for trigger in RefusalTrigger:
        assert trigger in _TEMPLATES, f"missing template for trigger: {trigger}"


def test_no_placeholders_in_scope_free_outputs() -> None:
    """Defense in depth: even if a scope-free template accidentally
    contains a placeholder, render must not ship it. (test_scope_free_
    triggers_render_without_context already asserts this; this test
    is the explicit lock.)"""
    for trigger in SCOPE_FREE_TRIGGERS:
        msg = render_refusal(trigger)
        # Common placeholder patterns:
        assert "{campus" not in msg
        assert "{library" not in msg
        assert "{service" not in msg
        assert "{staff" not in msg


def main() -> int:
    tests = [
        test_scope_free_triggers_render_without_context,
        test_cross_campus_renders_with_full_context,
        test_cross_campus_raises_when_campus_missing,
        test_cross_campus_raises_when_staff_url_missing,
        test_service_not_at_building_renders_with_full_context,
        test_service_not_at_building_raises_when_service_name_missing,
        test_every_trigger_has_a_template,
        test_no_placeholders_in_scope_free_outputs,
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
