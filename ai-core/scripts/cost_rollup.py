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
import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional


logger = logging.getLogger("cost_rollup")


# --- Price table ---------------------------------------------------------
#
# USD per 1M tokens. Kept as a module constant (not a YAML / DB
# config) because (a) pricing changes are rare and deliberate,
# (b) grep-ability matters -- "where did we get that $X number" should
# resolve to a file, not a DB row.
#
# gpt-5.4 family rates VERIFIED 2026-05-19 against the operator's
# OpenAI dashboard (same source that set src/config/models.py). An
# UNKNOWN model (e.g. a dated snapshot like "o4-mini-2025-04-16", or a
# model not yet priced here) -> compute_cost_usd returns $0 and logs a
# WARN: the rollup still records the token counts, it just can't price
# them until someone adds a row here. That is the deliberate safe
# behavior (a mis-priced/guessed rate is worse than a flagged $0).
# Operator-maintained: add a row when a new model ships.

PRICE_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "gpt-5.4": {
        "input": 2.50,
        "cached_input": 0.25,
        "output": 15.00,
    },
    "gpt-5.4-mini": {
        "input": 0.75,
        "cached_input": 0.08,
        "output": 4.50,
    },
    "gpt-5.4-nano": {
        "input": 0.20,
        "cached_input": 0.02,
        "output": 1.25,
    },
    # Pre-rebuild model; kept so historical ModelTokenUsage rows price
    # correctly. (Superseded by the gpt-5.4 tiers per the model-tier
    # refactor; safe to leave.)
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
    """One DailyCost row -- the output of rollup. One row per
    (date, model, call_site) to match the DailyCost @@unique key, so
    the dashboard answers "which part of the pipeline costs money"
    (synthesizer vs judge vs agent), not just "gpt-5.4 in general"."""

    the_date: date
    model: str
    call_site: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    call_count: int
    usd: float

    def as_dict(self) -> dict:
        return {
            "date": self.the_date.isoformat(),
            "model": self.model,
            "call_site": self.call_site,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "call_count": self.call_count,
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
    """Aggregate a day's usage into one DailyCostRow per
    (model, call_site). Name kept for back-compat with callers; it now
    rolls up per (model, call_site) per the operator's Option-A
    decision (the DailyCost @@unique key is (date, model, callSite)).
    `call_count` = number of ModelTokenUsage rows in that bucket."""
    totals: dict[tuple[str, str], dict] = {}
    for r in usage_rows:
        key = (r.model, r.call_site or "unknown")
        t = totals.setdefault(
            key, {"input": 0, "cached": 0, "output": 0, "n": 0}
        )
        t["input"] += r.input_tokens
        t["cached"] += r.cached_input_tokens
        t["output"] += r.output_tokens
        t["n"] += 1

    return [
        DailyCostRow(
            the_date=the_date,
            model=model,
            call_site=call_site,
            input_tokens=t["input"],
            cached_input_tokens=t["cached"],
            output_tokens=t["output"],
            call_count=t["n"],
            usd=compute_cost_usd(
                model, t["input"], t["cached"], t["output"]
            ),
        )
        for (model, call_site), t in totals.items()
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


async def _aload_usage_rows(the_date: date) -> list[UsageRow]:
    from prisma import Prisma  # type: ignore

    # [00:00, next 00:00) UTC for the bucket date. createdAt is
    # timestamptz; tz-aware bounds avoid an off-by-a-few-hours bleed.
    start = datetime(
        the_date.year, the_date.month, the_date.day, tzinfo=timezone.utc
    )
    end = start + timedelta(days=1)
    db = Prisma()
    await db.connect()
    try:
        recs = await db.modeltokenusage.find_many(
            where={"createdAt": {"gte": start, "lt": end}}
        )
    finally:
        await db.disconnect()
    return [
        UsageRow(
            model=getattr(r, "llmModelName", "") or "unknown",
            input_tokens=getattr(r, "promptTokens", 0) or 0,
            cached_input_tokens=getattr(r, "cachedInputTokens", 0) or 0,
            output_tokens=getattr(r, "completionTokens", 0) or 0,
            # Legacy rows have callSite=None -> bucket as "unknown"
            # (DailyCost.callSite is a non-null column).
            call_site=getattr(r, "callSite", None) or "unknown",
        )
        for r in (recs or [])
    ]


def _load_usage_rows(the_date: date) -> list[UsageRow]:
    """Load ModelTokenUsage rows for `the_date` (UTC day). Sync wrapper
    around async Prisma -- this is a one-shot cron script, no running
    loop, so asyncio.run is correct. Any failure (Prisma not
    generated, tunnel/DB down) -> NotImplementedError so the CLI
    reports cleanly and exits 2 instead of dumping a traceback."""
    try:
        return asyncio.run(_aload_usage_rows(the_date))
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated -- run `python -m prisma "
            "generate` (venv-targeted), then retry."
        ) from e
    except Exception as e:  # noqa: BLE001
        raise NotImplementedError(
            f"Could not load ModelTokenUsage for {the_date} "
            f"({type(e).__name__}: {e}). Is the DB/tunnel up?"
        ) from e


async def _awrite_daily_cost(rows: list[DailyCostRow]) -> int:
    from prisma import Prisma  # type: ignore

    db = Prisma()
    await db.connect()
    n = 0
    try:
        for row in rows:
            # prisma-client-py can't serialize a bare datetime.date;
            # the @db.Date column takes a datetime. Midnight UTC of the
            # bucket day -> the DB still stores just the date part.
            dt = datetime(
                row.the_date.year, row.the_date.month, row.the_date.day,
                tzinfo=timezone.utc,
            )
            payload = {
                "date": dt,
                "model": row.model,
                "callSite": row.call_site,
                "inputTokens": row.input_tokens,
                "cachedTokens": row.cached_input_tokens,
                "outputTokens": row.output_tokens,
                "callCount": row.call_count,
                "usd": float(round(row.usd, 6)),
            }
            # Idempotent: the @@unique([date, model, callSite]) key ->
            # prisma compound key `date_model_callSite`. Re-running a
            # date overwrites that bucket (no duplicate rows).
            await db.dailycost.upsert(
                where={
                    "date_model_callSite": {
                        "date": dt,
                        "model": row.model,
                        "callSite": row.call_site,
                    }
                },
                data={"create": payload, "update": payload},
            )
            n += 1
    finally:
        await db.disconnect()
    return n


def _write_daily_cost(rows: list[DailyCostRow]) -> None:
    """Idempotent upsert of DailyCost rows. Sync wrapper (cron script).
    A failure raises NotImplementedError so the CLI exits 2 cleanly."""
    if not rows:
        return
    try:
        n = asyncio.run(_awrite_daily_cost(rows))
        logger.info("wrote/updated %d DailyCost row(s)", n)
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated -- cannot write DailyCost."
        ) from e
    except Exception as e:  # noqa: BLE001
        raise NotImplementedError(
            f"Could not write DailyCost ({type(e).__name__}: {e}). "
            f"Is the DB/tunnel up?"
        ) from e


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
