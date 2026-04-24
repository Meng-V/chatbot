"""
Daily cost-rollup cron job.

Reads ModelTokenUsage rows from the previous day, multiplies tokens by
the current OpenAI per-model price, writes one DailyCost row per
(date, model) pair. The dashboard reads DailyCost for trend charts
and the alert-on-anomaly check.

Without this, a prompt-prefix drift that tanks the cache hit rate
burns budget silently for weeks before anyone notices. That's the
exact failure mode the plan calls out under Operations Op 3 "Cost
tracking".

Run via cron: `0 2 * * *` (2 AM daily, after the day's traffic is
logged and before the morning digest email).

Usage:
    python -m scripts.cost_rollup                 # roll up yesterday
    python -m scripts.cost_rollup --date 2026-04-22
    python -m scripts.cost_rollup --backfill 30   # last 30 days

Status: SCAFFOLD. Prisma isn't importable in the sandbox. The logic
is structured as pure functions around `compute_daily_cost()` so the
business logic is testable without the DB; the DB read/write is a
thin wrapper that's easy to add.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


logger = logging.getLogger("cost_rollup")


# --- Price table ---------------------------------------------------------
#
# USD per 1M tokens. Kept as a module constant (not a YAML / DB
# config) because (a) pricing changes are rare and deliberate,
# (b) grep-ability matters -- "where did we get that $X number" should
# resolve to a file, not a DB row.
#
# Note: cached input tokens are billed at ~50% of regular input per
# OpenAI's prompt-cache docs. The ratio is confirmable at the freshness-
# check point when touching the LLM client. Until then, treat these as
# PLACEHOLDER values -- a production deploy must reconcile with the
# billing-dashboard actual rates.

PRICE_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    # Stub rates; check openai.com/pricing at deploy.
    "gpt-5.4-mini": {
        "input": 0.15,
        "cached_input": 0.075,  # 50% of input
        "output": 0.60,
    },
    "gpt-5.2": {
        "input": 2.50,
        "cached_input": 1.25,
        "output": 10.00,
    },
    "text-embedding-3-large": {
        "input": 0.13,
        "cached_input": 0.13,  # embeddings don't cache
        "output": 0.0,
    },
}


# --- Data shapes ----------------------------------------------------------


@dataclass(frozen=True)
class UsageRow:
    """One ModelTokenUsage row, plus the call_site column added for
    per-site cost attribution."""

    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    call_site: str = "unknown"


@dataclass(frozen=True)
class DailyCostRow:
    """One DailyCost row -- the output of rollup."""

    the_date: date
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    usd: float

    def as_dict(self) -> dict:
        return {
            "date": self.the_date.isoformat(),
            "model": self.model,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "usd": round(self.usd, 4),
        }


# --- Pure rollup logic ---------------------------------------------------


def compute_cost_usd(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute USD cost for one usage row.

    Unknown models return 0.0 and log a warning. Treat unknown models
    as cost-free rather than crashing -- an experimental model
    mis-deployed shouldn't block the rollup for everyone else.

    NOTE: `input_tokens` in the OpenAI billing model is the TOTAL
    input tokens (including the cached portion). The cached portion
    gets a discount; the uncached portion is billed at full rate. So
    billable_uncached = input_tokens - cached_input_tokens.
    """
    rates = PRICE_PER_1M_TOKENS.get(model)
    if rates is None:
        logger.warning(
            "Unknown model %s -- treating as $0 for rollup (add to PRICE_PER_1M_TOKENS)",
            model,
        )
        return 0.0

    uncached = max(0, input_tokens - cached_input_tokens)
    cached = min(cached_input_tokens, input_tokens)
    return (
        uncached * rates["input"] / 1_000_000
        + cached * rates["cached_input"] / 1_000_000
        + output_tokens * rates["output"] / 1_000_000
    )


def rollup_by_model(
    usage_rows: list[UsageRow], the_date: date
) -> list[DailyCostRow]:
    """Aggregate a day's usage rows into one DailyCostRow per model."""
    totals: dict[str, dict] = {}
    for r in usage_rows:
        t = totals.setdefault(
            r.model,
            {"input": 0, "cached": 0, "output": 0},
        )
        t["input"] += r.input_tokens
        t["cached"] += r.cached_input_tokens
        t["output"] += r.output_tokens

    return [
        DailyCostRow(
            the_date=the_date,
            model=model,
            input_tokens=t["input"],
            cached_input_tokens=t["cached"],
            output_tokens=t["output"],
            usd=compute_cost_usd(
                model, t["input"], t["cached"], t["output"]
            ),
        )
        for model, t in totals.items()
    ]


def anomaly_ratio(today_total: float, trailing_avg: float) -> float:
    """Return today's spend as a multiple of the trailing 7-day average.

    Alert threshold per plan Op 3: ratio >= 1.5 pages Slack/email
    ("daily token cost > 1.5x the 7-day average").
    """
    if trailing_avg <= 0:
        return 0.0
    return today_total / trailing_avg


# --- DB wrapper (gated) ---------------------------------------------------


def _load_usage_rows(the_date: date) -> list[UsageRow]:
    """Load ModelTokenUsage rows for the given date. Gated on Prisma
    being importable. In the sandbox this raises; the orchestrator
    script catches and reports."""
    try:
        from prisma import Prisma  # type: ignore
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated. Run `npx prisma generate` "
            "after adding the cached_input_tokens and call_site columns "
            "to the ModelTokenUsage model, then retry."
        ) from e

    # TODO: real query
    #   async with Prisma() as db:
    #       rows = await db.modeltokenusage.find_many(
    #           where={"createdAt": {"gte": start, "lt": end}}
    #       )
    #       return [UsageRow(...) for r in rows]
    raise NotImplementedError("DB wiring -- week 6/7 task")


def _write_daily_cost(rows: list[DailyCostRow]) -> None:
    """Upsert DailyCost rows."""
    try:
        from prisma import Prisma  # type: ignore  # noqa: F401
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated. Cannot write DailyCost rows."
        ) from e
    raise NotImplementedError("DB wiring -- week 6/7 task")


# --- CLI -----------------------------------------------------------------


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Daily OpenAI cost rollup.")
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        help="ISO date (YYYY-MM-DD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Roll up the last N days (inclusive of today-1).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dates: list[date]
    if args.backfill:
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(1, args.backfill + 1)]
    else:
        dates = [args.date or (date.today() - timedelta(days=1))]

    for d in dates:
        try:
            usage = _load_usage_rows(d)
        except NotImplementedError as e:
            logger.error("Cannot roll up %s: %s", d, e)
            return 2
        rows = rollup_by_model(usage, d)
        logger.info(
            "%s: %d models, total $%.4f",
            d,
            len(rows),
            sum(r.usd for r in rows),
        )
        _write_daily_cost(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DailyCostRow",
    "PRICE_PER_1M_TOKENS",
    "UsageRow",
    "anomaly_ratio",
    "compute_cost_usd",
    "rollup_by_model",
]
