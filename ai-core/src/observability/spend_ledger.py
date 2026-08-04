"""Where the money went, for both purses, readable in one place.

Two sources, because the two purses are spent by different processes:

  serving  ModelTokenUsage, written per model call by the running service.
           Live to the minute.
  eval     DailyCost rows with callSite="eval", written by run_eval as each
           category finishes.

WHY THE EVAL WRITES TO DailyCost AND NOT ModelTokenUsage
--------------------------------------------------------
ModelTokenUsage.conversationId is a required foreign key to Conversation.
An eval run has no conversation, and inventing 234 fake ones per run would
corrupt the conversation count that the launch review reports. DailyCost
has a free-form `callSite` and no foreign key, and its unique key is
(date, model, callSite) -- so "eval" rows sit alongside the serving
rollup's rows without colliding and without a schema migration.

This closes a real hole found on 2026-08-04: eval spend was recorded
NOWHERE. The cost dashboard read $0.62 for the month on a day when the
eval had actually spent more than $10. A dashboard that silently omits a
quarter of the budget is worse than no dashboard, because it gets trusted.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from dataclasses import dataclass
from typing import Optional

from src.utils.logging_config import get_logger

log = get_logger("spend_ledger")

EVAL_CALL_SITE = "eval"


@dataclass
class Spend:
    serving_today: float = 0.0
    serving_mtd: float = 0.0
    eval_mtd: float = 0.0
    serving_unpriced_calls: int = 0
    eval_unpriced_calls: int = 0

    @property
    def total_mtd(self) -> float:
        return self.serving_mtd + self.eval_mtd


def _month_start(when: "Optional[_dt.date]" = None) -> _dt.date:
    """The 1st of the month, in the libraries' timezone.

    Natural calendar month per the operator: the purse refills at midnight on
    the 1st, Oxford time. `date.today()` on this UTC box rolls over four hours
    early -- see budget.library_today().
    """
    from src.config.budget import library_today
    d = when or library_today()
    return d.replace(day=1)


# --- writing eval spend --------------------------------------------------


async def _arecord_eval_spend(
    rows: list[dict], the_date: _dt.date,
) -> int:
    from prisma import Prisma

    from scripts.cost_rollup import compute_cost_usd, is_priced

    db = Prisma()
    await db.connect()
    written = 0
    try:
        for r in rows:
            model = str(r.get("model") or "")
            inp = int(r.get("input_tokens") or 0)
            cached = int(r.get("cached_input_tokens") or 0)
            outp = int(r.get("output_tokens") or 0)
            calls = int(r.get("calls") or 0)
            usd = compute_cost_usd(model, inp, cached, outp)
            if not is_priced(model):
                # Loud, because an unpriced model reads as free and would
                # let the eval purse overrun without the guard noticing.
                log.error("eval spend for UNPRICED model %s recorded as $0 -- "
                          "add it to PRICE_PER_1M_TOKENS or the eval budget "
                          "cannot be enforced", model)
            # The eval can run several times a day; accumulate rather than
            # overwrite, or the second run of the day erases the first.
            existing = await db.dailycost.find_first(
                where={"date": _dt.datetime.combine(the_date, _dt.time.min),
                       "model": model, "callSite": EVAL_CALL_SITE}
            )
            if existing:
                await db.dailycost.update(
                    where={"id": existing.id},
                    data={
                        "inputTokens": existing.inputTokens + inp,
                        "cachedTokens": existing.cachedTokens + cached,
                        "outputTokens": existing.outputTokens + outp,
                        "callCount": existing.callCount + calls,
                        "usd": existing.usd + usd,
                    },
                )
            else:
                await db.dailycost.create(
                    data={
                        "date": _dt.datetime.combine(the_date, _dt.time.min),
                        "model": model,
                        "callSite": EVAL_CALL_SITE,
                        "inputTokens": inp,
                        "cachedTokens": cached,
                        "outputTokens": outp,
                        "callCount": calls,
                        "usd": usd,
                    },
                )
            written += 1
    finally:
        await db.disconnect()
    return written


def record_eval_spend(
    rows: list[dict], *, the_date: "Optional[_dt.date]" = None,
) -> bool:
    """Record one eval batch. Returns False on failure; never raises.

    Never raises because this is called at the end of an eval category:
    losing the accounting for a run is bad, but killing a 100-minute run
    that has already produced its results is worse. A False return is
    logged at ERROR so it shows up in the report as a gap.

    `rows`: [{model, input_tokens, cached_input_tokens, output_tokens, calls}]
    """
    if not rows:
        return True
    from src.config.budget import library_today
    day = the_date or library_today()
    try:
        n = asyncio.run(_arecord_eval_spend(rows, day))
        total = sum(float(r.get("usd") or 0) for r in rows)
        log.info("recorded eval spend: %d model row(s) for %s%s", n, day,
                 f" (~${total:.2f})" if total else "")
        return True
    except Exception as e:  # noqa: BLE001
        log.error("could not record eval spend for %s (%s: %s) -- the eval "
                  "budget will under-report until this is fixed",
                  day, type(e).__name__, e)
        return False


# --- reading both purses -------------------------------------------------


async def _aread_spend(today: _dt.date) -> Spend:
    from prisma import Prisma

    from scripts.cost_rollup import compute_cost_usd, is_priced

    start = _month_start(today)
    db = Prisma()
    await db.connect()
    out = Spend()
    try:
        # Serving: straight from the live per-call table, so today's number
        # is current rather than waiting for the nightly rollup.
        rows = await db.query_raw(
            """
            SELECT "llmModelName" AS model,
                   ("createdAt"::date = $2::date) AS is_today,
                   SUM("promptTokens")      AS inp,
                   SUM("cachedInputTokens") AS cached,
                   SUM("completionTokens")  AS outp,
                   COUNT(*)                 AS calls
            FROM "ModelTokenUsage"
            WHERE "createdAt" >= $1::date
            GROUP BY 1, 2
            """,
            start.isoformat(), today.isoformat(),
        )
        for r in rows:
            model = str(r["model"] or "")
            usd = compute_cost_usd(model, int(r["inp"] or 0),
                                   int(r["cached"] or 0), int(r["outp"] or 0))
            out.serving_mtd += usd
            if r["is_today"]:
                out.serving_today += usd
            if not is_priced(model):
                out.serving_unpriced_calls += int(r["calls"] or 0)

        ev = await db.query_raw(
            """
            SELECT model, SUM(usd) AS usd, SUM("callCount") AS calls
            FROM "DailyCost"
            WHERE "callSite" = $1 AND date >= $2::date
            GROUP BY 1
            """,
            EVAL_CALL_SITE, start.isoformat(),
        )
        for r in ev:
            out.eval_mtd += float(r["usd"] or 0.0)
            if not is_priced(str(r["model"] or "")):
                out.eval_unpriced_calls += int(r["calls"] or 0)
    finally:
        await db.disconnect()
    return out


def read_spend(*, today: "Optional[_dt.date]" = None) -> Optional[Spend]:
    """Month-to-date spend for both purses, or None if the DB is unreachable.

    None rather than zeros: zeros would look like a quiet month and let the
    guard clear a degrade level it should be holding.
    """
    from src.config.budget import library_today
    day = today or library_today()
    try:
        return asyncio.run(_aread_spend(day))
    except Exception as e:  # noqa: BLE001
        log.error("could not read spend (%s: %s)", type(e).__name__, e)
        return None
