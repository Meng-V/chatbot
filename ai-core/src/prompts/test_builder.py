"""
Unit tests for the cache-aware prompt builder.

Run: `python -m src.prompts.test_builder` from ai-core/.

The builder is the only thing standing between a careless prompt edit
and a quietly tanked cache hit rate -- which directly translates to
~3-4x cost per query. Test coverage is non-negotiable.

Tests:
  1. register + build round-trip.
  2. Drift refusal: re-registering the same id with different content fails loud.
  3. Idempotent same-content re-register: no error.
  4. build_prompt with unknown id fails loud.
  5. Optional `extra_system_suffix` is appended after the cached prefix.
  6. Threshold check: every shipped prefix clears the 1024-token cache window.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.prompts.test_builder`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.prompts import builder  # noqa: E402
from src.prompts.builder import (  # noqa: E402
    PromptBuildError,
    assert_prefix_clears_cache_threshold,
    build_prompt,
    register_prefix,
    registered_prefix_ids,
)


# OpenAI's automatic prompt cache requires a >=1024-token identical
# prefix (verify against current docs at code-change time per the
# freshness rule). Conservative test threshold.
CACHE_THRESHOLD_TOKENS = 1024


def _reset_registry() -> None:
    """Clean the module-level registry between tests so they don't bleed."""
    builder._REGISTRY.clear()


def test_register_and_build_round_trip() -> None:
    _reset_registry()
    prefix = "You are a test assistant. " + ("padding " * 100)
    register_prefix("test_v1", prefix)

    msgs = build_prompt(
        prefix_id="test_v1",
        dynamic_messages=[{"role": "user", "content": "hello"}],
    )
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == prefix
    assert msgs[1] == {"role": "user", "content": "hello"}
    assert "test_v1" in registered_prefix_ids()


def test_register_drift_refuses() -> None:
    _reset_registry()
    register_prefix("drift_v1", "original content")
    try:
        register_prefix("drift_v1", "MUTATED content")
    except PromptBuildError as e:
        assert "different body" in str(e)
        assert "Bump the version" in str(e)
        return
    raise AssertionError("expected PromptBuildError on drift")


def test_register_same_content_is_idempotent() -> None:
    _reset_registry()
    register_prefix("idem_v1", "same content")
    # Second call with byte-identical content should NOT raise.
    register_prefix("idem_v1", "same content")
    assert "idem_v1" in registered_prefix_ids()


def test_build_unknown_prefix_refuses() -> None:
    _reset_registry()
    try:
        build_prompt(prefix_id="nonexistent_v9", dynamic_messages=[])
    except PromptBuildError as e:
        assert "unknown prefix_id" in str(e)
        return
    raise AssertionError("expected PromptBuildError on unknown prefix_id")


def test_extra_suffix_appended_to_system() -> None:
    _reset_registry()
    register_prefix("suffix_v1", "STABLE PART")
    msgs = build_prompt(
        prefix_id="suffix_v1",
        dynamic_messages=[{"role": "user", "content": "q"}],
        extra_system_suffix="DYNAMIC PART",
    )
    assert msgs[0]["content"].startswith("STABLE PART")
    assert "DYNAMIC PART" in msgs[0]["content"]
    # Suffix comes AFTER the stable part so the cached prefix is intact.
    assert msgs[0]["content"].index("STABLE PART") < msgs[0]["content"].index("DYNAMIC PART")


def test_dynamic_messages_appended_after_system() -> None:
    _reset_registry()
    register_prefix("order_v1", "system text")
    msgs = build_prompt(
        prefix_id="order_v1",
        dynamic_messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ],
    )
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[3]["content"] == "second"


def test_assert_threshold_passes_when_long_enough() -> None:
    _reset_registry()
    # 4 chars per token estimate -> need >= 4096 chars for 1024 tokens.
    long = "x" * 5000
    register_prefix("long_v1", long)
    # Should not raise.
    assert_prefix_clears_cache_threshold("long_v1", 1024)


def test_assert_threshold_fails_when_too_short() -> None:
    _reset_registry()
    register_prefix("short_v1", "tiny")
    try:
        assert_prefix_clears_cache_threshold("short_v1", 1024)
    except PromptBuildError as e:
        assert "below cache threshold" in str(e)
        assert "Pad with terminology" in str(e)
        return
    raise AssertionError("expected PromptBuildError on short prefix")


def test_all_shipped_prefixes_clear_cache_threshold() -> None:
    """Lock-in test: every prefix file in src/prompts/ must register a
    prefix that clears the 1024-token cache window. This is the gate
    that makes the cost-savings target actually achievable -- a future
    PR that trims a prompt below threshold will fail here in CI.
    """
    _reset_registry()
    # Trigger registration of every shipped prefix.
    from src.prompts import (  # noqa: F401
        agent_v1,
        clarifier_v1,
        judge_v1,
        synthesizer_v1,
    )

    expected_ids = {"agent_v1", "synthesizer_v1", "clarifier_v1", "judge_v1"}
    actual_ids = set(registered_prefix_ids())
    missing = expected_ids - actual_ids
    assert not missing, f"prefix modules failed to register: {missing}"

    for prefix_id in expected_ids:
        # Will raise PromptBuildError if any shipped prefix is too short.
        assert_prefix_clears_cache_threshold(prefix_id, CACHE_THRESHOLD_TOKENS)


def main() -> int:
    tests = [
        test_register_and_build_round_trip,
        test_register_drift_refuses,
        test_register_same_content_is_idempotent,
        test_build_unknown_prefix_refuses,
        test_extra_suffix_appended_to_system,
        test_dynamic_messages_appended_after_system,
        test_assert_threshold_passes_when_long_enough,
        test_assert_threshold_fails_when_too_short,
        test_all_shipped_prefixes_clear_cache_threshold,
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
