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
    _reload_clean()
    assert M.BASIC_MODEL == "gpt-5.4-mini", M.BASIC_MODEL
    assert M.REASONING_MODEL == "gpt-5.4", M.REASONING_MODEL
    assert M.CHEAP_MODEL == "gpt-5.4-nano", M.CHEAP_MODEL
    assert M.EMBEDDING_MODEL == "text-embedding-3-large"


def test_resolve_model_three_tiers() -> None:
    _reload_clean()
    assert M.resolve_model("basic") == "gpt-5.4-mini"
    assert M.resolve_model("reasoning") == "gpt-5.4"
    assert M.resolve_model("cheap") == "gpt-5.4-nano"
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
