"""
Offline tests for the env-driven model config + call-shape gate.

Run: `python -m src.config.test_models` from ai-core/.

models.py resolves env at IMPORT time, so env-override tests reload
the module (and always restore os.environ + a clean reload after, so
later tests/imports see the real config).
"""

from __future__ import annotations

import importlib
import os
import pytest
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

import src.config.models as M

_TIER_ENV = (
    "LLM_MODEL_BASIC", "LLM_MODEL_REASONING",
    "LLM_MODEL_CHEAP", "LLM_MODEL_EMBEDDING",
)


def _reload_clean():
    for k in _TIER_ENV:
        os.environ.pop(k, None)
    importlib.reload(M)


def test_defaults_are_gpt54_family() -> None:
    """The BASIC/REASONING fallbacks are still the 5.4 family on purpose --
    they are what runs if .env is missing, and a conservative fallback is the
    point. CHEAP moved to luna on 2026-07-30 because the repricing made luna
    cheaper than nano outright (0.20/0.02/1.20 against 0.20/0.02/1.25) with a
    1.05M window instead of 400K, so the cheap fallback is now also the better
    model."""
    _reload_clean()
    assert M.BASIC_MODEL == "gpt-5.4-mini", M.BASIC_MODEL
    assert M.REASONING_MODEL == "gpt-5.4", M.REASONING_MODEL
    assert M.CHEAP_MODEL == "gpt-5.6-luna", M.CHEAP_MODEL
    assert M.EMBEDDING_MODEL == "text-embedding-3-large"


def test_cheap_default_is_not_dearer_than_basic() -> None:
    """CHEAP must never cost more than BASIC -- that would invert the tiers.

    Pins the relationship rather than the model id, so the next repricing is
    caught by arithmetic instead of by someone remembering.
    """
    from scripts.cost_rollup import PRICE_PER_1M_TOKENS as P

    _reload_clean()
    cheap, basic = P.get(M.CHEAP_MODEL), P.get(M.BASIC_MODEL)
    assert cheap and basic, (M.CHEAP_MODEL, M.BASIC_MODEL)
    for k in ("input", "cached_input", "output"):
        assert cheap[k] <= basic[k], (k, cheap[k], basic[k])


def test_resolve_model_three_tiers() -> None:
    _reload_clean()
    assert M.resolve_model("basic") == "gpt-5.4-mini"
    assert M.resolve_model("reasoning") == "gpt-5.4"
    assert M.resolve_model("cheap") == "gpt-5.6-luna"
    try:
        M.resolve_model("bogus")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_env_override() -> None:
    os.environ["LLM_MODEL_BASIC"] = "gpt-5.4-mini-2099"
    os.environ["LLM_MODEL_REASONING"] = "gpt-6"
    os.environ["LLM_MODEL_CHEAP"] = "gpt-5.4-nano-x"
    try:
        importlib.reload(M)
        assert M.resolve_model("basic") == "gpt-5.4-mini-2099"
        assert M.resolve_model("reasoning") == "gpt-6"
        assert M.resolve_model("cheap") == "gpt-5.4-nano-x"
    finally:
        _reload_clean()  # restore real config for any later import


def test_is_reasoning_model() -> None:
    _reload_clean()
    for yes in ("o4-mini", "o1", "o3-mini", "gpt-5.2", "gpt-5.4",
                "gpt-5.4-mini", "gpt-5.4-nano", "GPT-5.4-NANO"):
        assert M.is_reasoning_model(yes) is True, yes
    for no in ("gpt-4o", "gpt-4", "gpt-4o-mini", "gpt-3.5-turbo",
               "text-embedding-3-large", "", None):
        assert M.is_reasoning_model(no) is False, no  # must not raise


def main() -> int:
    tests = [
        test_defaults_are_gpt54_family,
        test_resolve_model_three_tiers,
        test_env_override,
        test_is_reasoning_model,
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
    _reload_clean()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


# budget.py keeps a process-global 15-second cache of the state file so the
# hot path does not re-read it per turn. That cache leaks between tests: a
# test that writes level 4 leaves the next test resolving `reasoning` as the
# cheap model, which failed test_resolve_model_three_tiers with a completely
# unrelated-looking error. Reset it around EVERY test in this module.
@pytest.fixture(autouse=True)
def _isolate_budget_cache():
    from src.config import budget as B
    B.reset_cache()
    yield
    B.reset_cache()

# --- budget-driven downgrade (level 2) -----------------------------------
#
# The reasoning model costs 21x the cheap one per call and is 83% of spend on
# 15% of calls (measured 2026-08-04), so substituting it is the single
# strongest cost lever -- and it keeps every feature working, which is why it
# sits two rungs below refusing students.


def _budget_state(tmp_path, monkeypatch, level):
    import datetime
    from src.config import budget as B
    p = tmp_path / "state.json"
    monkeypatch.setattr(B, "STATE_PATH", p)
    B.write_state(B.BudgetState(
        level=level, month=datetime.date.today().strftime("%Y-%m")), p)
    B.reset_cache()
    return p


def test_reasoning_tier_is_normal_below_level_two(tmp_path, monkeypatch):
    from src.config import budget as B
    for lvl in (B.L_NORMAL, B.L_ALERT):
        _budget_state(tmp_path, monkeypatch, lvl)
        assert M.resolve_model("reasoning") == M.resolve_model("reasoning")
        assert M.resolve_model("reasoning") != M.resolve_model("cheap"), (
            f"level {lvl} must not downgrade the reasoning tier"
        )


def test_level_two_serves_reasoning_from_the_cheap_tier(tmp_path, monkeypatch):
    from src.config import budget as B
    _budget_state(tmp_path, monkeypatch, B.L_CHEAP)
    assert M.resolve_model("reasoning") == M.resolve_model("cheap")


def test_higher_levels_stay_downgraded(tmp_path, monkeypatch):
    from src.config import budget as B
    for lvl in (B.L_TIGHTEN, B.L_REFUSE):
        _budget_state(tmp_path, monkeypatch, lvl)
        assert M.resolve_model("reasoning") == M.resolve_model("cheap")


def test_basic_and_cheap_tiers_are_never_touched(tmp_path, monkeypatch):
    """Only the expensive tier is substituted. Downgrading `basic` would
    change every routine turn for no meaningful saving."""
    from src.config import budget as B
    _budget_state(tmp_path, monkeypatch, B.L_NORMAL)
    basic, cheap = M.resolve_model("basic"), M.resolve_model("cheap")
    _budget_state(tmp_path, monkeypatch, B.L_REFUSE)
    assert M.resolve_model("basic") == basic
    assert M.resolve_model("cheap") == cheap


def test_unreadable_budget_state_does_not_downgrade(tmp_path, monkeypatch):
    """Model resolution must never fail or silently change behaviour because
    of a bad JSON file."""
    from src.config import budget as B
    p = tmp_path / "state.json"
    p.write_text("{ not json")
    monkeypatch.setattr(B, "STATE_PATH", p)
    B.reset_cache()
    assert M.resolve_model("reasoning") != M.resolve_model("cheap")


def test_budget_lookup_cannot_raise(tmp_path, monkeypatch):
    from src.config import budget as B

    def boom():
        raise RuntimeError("budget exploded")

    monkeypatch.setattr(B, "current_state", boom)
    assert M._budget_forces_cheap() is False
    assert M.resolve_model("reasoning")  # still resolves


def test_the_eval_is_exempt_from_budget_degradation(tmp_path, monkeypatch):
    """A degraded eval measures a DIFFERENT system and reads as a quality
    collapse. run_eval sets BUDGET_IGNORE_DEGRADE for its own process; serving
    never does."""
    from src.config import budget as B
    _budget_state(tmp_path, monkeypatch, B.L_REFUSE)
    # Serving: downgraded.
    assert M.resolve_model("reasoning") == M.resolve_model("cheap")
    # Eval: not.
    monkeypatch.setenv("BUDGET_IGNORE_DEGRADE", "1")
    assert M._budget_forces_cheap() is False
    assert M.resolve_model("reasoning") != M.resolve_model("cheap")


def test_the_exemption_needs_a_real_truthy_value(tmp_path, monkeypatch):
    from src.config import budget as B
    _budget_state(tmp_path, monkeypatch, B.L_CHEAP)
    for val in ("0", "false", "no", "", "maybe"):
        monkeypatch.setenv("BUDGET_IGNORE_DEGRADE", val)
        assert M._budget_forces_cheap() is True, val
    for val in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("BUDGET_IGNORE_DEGRADE", val)
        assert M._budget_forces_cheap() is False, val
