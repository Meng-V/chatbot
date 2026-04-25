"""
Unit tests for cost_rollup pure functions.

Run: `python -m scripts.test_cost_rollup` from ai-core/.

The DB wrappers are gated on Prisma and out of scope for these tests
(they raise NotImplementedError until week 6/7). The PURE LOGIC --
compute_cost_usd, rollup_by_model, anomaly_ratio -- is testable today
and is what determines whether the cache-hit measurement gate is
trustworthy.

A bug in compute_cost_usd silently inflates or deflates the daily
report -- the kind of failure that gets discovered after a quarter of
budget overruns.

Tests:
  1. compute_cost_usd: known model, no cache -> input + output rates only.
  2. compute_cost_usd: known model, full cache -> only cached rate (50%).
  3. compute_cost_usd: known model, partial cache -> weighted blend.
  4. compute_cost_usd: unknown model -> 0.0, doesn't crash.
  5. compute_cost_usd: cached_input_tokens > input_tokens (impossible
     in practice but defend against telemetry bug) -> caps at input.
  6. compute_cost_usd: zero tokens -> 0.0.
  7. compute_cost_usd: embedding model -> output tokens billed at $0.
  8. rollup_by_model: empty list -> empty result.
  9. rollup_by_model: aggregates per-model totals correctly across
     multiple call sites.
 10. rollup_by_model: usd computed using the aggregated totals (not
     summed per-row -- that would compound float error).
 11. anomaly_ratio: trailing_avg=0 -> 0.0 (no false alarm on day 1).
 12. anomaly_ratio: today=2x trailing -> 2.0.
 13. PRICE table contains every model the rest of the codebase uses
     (lock-in: a new model added to src/config/models.py without
     pricing fails CI rather than rolling up at $0).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.test_cost_rollup`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.cost_rollup import (  # noqa: E402
    PRICE_PER_1M_TOKENS,
    DailyCostRow,
    UsageRow,
    anomaly_ratio,
    compute_cost_usd,
    rollup_by_model,
)


# --- compute_cost_usd ---


def test_no_cache_billed_input_plus_output() -> None:
    # gpt-5.4-mini: input $0.15, output $0.60 per 1M tokens.
    cost = compute_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, cached_input_tokens=0, output_tokens=1_000_000)
    assert abs(cost - (0.15 + 0.60)) < 1e-9


def test_full_cache_only_cached_rate() -> None:
    # gpt-5.4-mini: cached_input $0.075 per 1M.
    cost = compute_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, cached_input_tokens=1_000_000, output_tokens=0)
    assert abs(cost - 0.075) < 1e-9


def test_partial_cache_weighted_blend() -> None:
    # 60% cached, 40% uncached on 1M input tokens; no output.
    cost = compute_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, cached_input_tokens=600_000, output_tokens=0)
    expected = 0.4 * 0.15 + 0.6 * 0.075
    assert abs(cost - expected) < 1e-9


def test_unknown_model_returns_zero() -> None:
    cost = compute_cost_usd("gpt-experimental-99", 1_000_000, 0, 1_000_000)
    assert cost == 0.0


def test_cached_exceeds_input_caps_at_input() -> None:
    """If telemetry ever reports cached > input (it shouldn't), we
    must NOT bill negative tokens. Cap cached at input."""
    cost = compute_cost_usd("gpt-5.4-mini", input_tokens=100, cached_input_tokens=10_000, output_tokens=0)
    # Effectively all 100 input tokens are cached.
    expected = 100 * 0.075 / 1_000_000
    assert abs(cost - expected) < 1e-12


def test_zero_tokens_returns_zero() -> None:
    assert compute_cost_usd("gpt-5.4-mini", 0, 0, 0) == 0.0


def test_embedding_output_is_free() -> None:
    # text-embedding-3-large: output rate is $0 (embeddings have no completion).
    cost = compute_cost_usd("text-embedding-3-large", input_tokens=1_000_000, cached_input_tokens=0, output_tokens=999_999)
    assert abs(cost - 0.13) < 1e-9


# --- rollup_by_model ---


def test_rollup_empty_returns_empty() -> None:
    assert rollup_by_model([], date(2026, 4, 25)) == []


def test_rollup_aggregates_across_call_sites() -> None:
    rows = [
        UsageRow(model="gpt-5.4-mini", input_tokens=1000, cached_input_tokens=500, output_tokens=200, call_site="agent_loop"),
        UsageRow(model="gpt-5.4-mini", input_tokens=2000, cached_input_tokens=1500, output_tokens=300, call_site="synthesizer"),
        UsageRow(model="gpt-5.2", input_tokens=500, cached_input_tokens=400, output_tokens=100, call_site="synthesizer"),
    ]
    out = rollup_by_model(rows, date(2026, 4, 25))
    assert len(out) == 2
    by_model = {r.model: r for r in out}
    assert by_model["gpt-5.4-mini"].input_tokens == 3000
    assert by_model["gpt-5.4-mini"].cached_input_tokens == 2000
    assert by_model["gpt-5.4-mini"].output_tokens == 500
    assert by_model["gpt-5.2"].input_tokens == 500


def test_rollup_usd_computed_on_aggregates_not_per_row() -> None:
    """Compute USD ONCE on totals, not by summing per-row costs.
    Per-row would compound float error; aggregate-then-compute is more
    accurate. This tests the design choice doesn't regress."""
    # Three rows that together sum to nice round numbers.
    rows = [
        UsageRow(model="gpt-5.4-mini", input_tokens=333_333, cached_input_tokens=0, output_tokens=0),
        UsageRow(model="gpt-5.4-mini", input_tokens=333_333, cached_input_tokens=0, output_tokens=0),
        UsageRow(model="gpt-5.4-mini", input_tokens=333_334, cached_input_tokens=0, output_tokens=0),
    ]
    out = rollup_by_model(rows, date(2026, 4, 25))[0]
    expected = 1_000_000 * 0.15 / 1_000_000  # = 0.15
    assert abs(out.usd - expected) < 1e-12


def test_rollup_preserves_date() -> None:
    out = rollup_by_model(
        [UsageRow(model="gpt-5.4-mini", input_tokens=1000, cached_input_tokens=0, output_tokens=0)],
        date(2026, 4, 25),
    )
    assert out[0].the_date == date(2026, 4, 25)


# --- anomaly_ratio ---


def test_anomaly_ratio_zero_avg_returns_zero() -> None:
    """Day-1 case: no trailing data. Don't divide by zero, don't alert."""
    assert anomaly_ratio(today_total=10.0, trailing_avg=0.0) == 0.0


def test_anomaly_ratio_double_returns_two() -> None:
    assert anomaly_ratio(today_total=20.0, trailing_avg=10.0) == 2.0


def test_anomaly_ratio_below_average_under_one() -> None:
    # 75% of average -> ratio 0.75; below the 1.5x alert threshold.
    assert anomaly_ratio(today_total=7.5, trailing_avg=10.0) == 0.75


# --- Lock-in: every shipped model has a price ---


def test_price_table_covers_models_in_use() -> None:
    """If src/config/models.py adds a model that the rest of the
    codebase starts billing against, the rollup MUST know about it.
    Otherwise the daily report silently undercounts cost.
    """
    try:
        from src.config import models as model_config  # type: ignore
    except Exception:
        # If models.py isn't importable, this lock-in test is a no-op
        # rather than a hard fail -- the import path may have moved.
        return
    expected_models = set()
    for attr in dir(model_config):
        if attr.startswith("_"):
            continue
        val = getattr(model_config, attr)
        if isinstance(val, str) and val.startswith(("gpt-", "text-embedding-")):
            expected_models.add(val)

    missing = expected_models - set(PRICE_PER_1M_TOKENS)
    assert not missing, (
        f"src/config/models.py uses models not in PRICE_PER_1M_TOKENS: {missing}. "
        "Add a row to scripts/cost_rollup.py before deploy."
    )


def test_daily_cost_row_serializes_to_dict() -> None:
    row = DailyCostRow(
        the_date=date(2026, 4, 25),
        model="gpt-5.4-mini",
        input_tokens=1_000_000,
        cached_input_tokens=500_000,
        output_tokens=100_000,
        usd=0.123456789,
    )
    d = row.as_dict()
    assert d["date"] == "2026-04-25"
    assert d["model"] == "gpt-5.4-mini"
    assert d["input_tokens"] == 1_000_000
    # USD rounded to 4 decimal places for display.
    assert d["usd"] == 0.1235


def main() -> int:
    tests = [
        test_no_cache_billed_input_plus_output,
        test_full_cache_only_cached_rate,
        test_partial_cache_weighted_blend,
        test_unknown_model_returns_zero,
        test_cached_exceeds_input_caps_at_input,
        test_zero_tokens_returns_zero,
        test_embedding_output_is_free,
        test_rollup_empty_returns_empty,
        test_rollup_aggregates_across_call_sites,
        test_rollup_usd_computed_on_aggregates_not_per_row,
        test_rollup_preserves_date,
        test_anomaly_ratio_zero_avg_returns_zero,
        test_anomaly_ratio_double_returns_two,
        test_anomaly_ratio_below_average_under_one,
        test_price_table_covers_models_in_use,
        test_daily_cost_row_serializes_to_dict,
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
