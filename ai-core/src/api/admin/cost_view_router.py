"""
Read-only cost panel (Op 3 "Cost tracking" -- the viewable surface).

There was no way to SEE spend: ModelTokenUsage logs every turn's tokens and
cost_rollup.py aggregates DailyCost, but nothing rendered it. This adds a
token-gated `/admin/cost` HTML page (and `/admin/cost.json`) that computes USD
LIVE from ModelTokenUsage via cost_rollup.compute_cost_usd -- so it shows real
dollars even before the DailyCost cron is scheduled.

SECURITY: same fail-closed model as the review surface -- mounted only when
ADMIN_API_TOKEN is set, gated by make_token_guard (X-Admin-Token header or
?key=). It exposes only AGGREGATE token/cost numbers (no conversation content),
but the token gate keeps spend figures internal anyway.

READ-ONLY: find_many on ModelTokenUsage only. Any DB error degrades to an empty
panel, never a 500.
"""
from __future__ import annotations

import html
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from src.api.admin.review_view_router import make_token_guard  # reuse the guard

try:
    from scripts.cost_rollup import compute_cost_usd
except Exception:  # noqa: BLE001 -- keep importable if pricing module moves
    def compute_cost_usd(model, input_tokens, cached_input_tokens, output_tokens):  # type: ignore
        return 0.0

try:
    from starlette.requests import Request  # type: ignore
except Exception:  # noqa: BLE001
    Request = Any  # type: ignore

logger = logging.getLogger(__name__)

__all__ = ["build_cost_view_router", "make_token_guard"]


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


_STYLE = (
    "body{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#111}"
    "h1{font-size:20px}h2{font-size:15px;margin-top:24px;color:#444}"
    "table{border-collapse:collapse;width:100%;margin-top:8px}"
    "td,th{border:1px solid #ddd;padding:6px 10px;text-align:right}"
    "th:first-child,td:first-child{text-align:left}"
    "th{background:#f4f4f4}"
    ".big{font-size:28px;font-weight:700}.muted{color:#777;font-size:12px}"
    ".card{display:inline-block;border:1px solid #e3e3e3;border-radius:8px;"
    "padding:12px 18px;margin:6px 14px 6px 0;min-width:140px}"
)


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )


async def _aggregate(db: Any, days: int) -> dict:
    """Read ModelTokenUsage for the window, group by (day, model, callSite),
    compute USD live. Returns a dict the views render. Never raises."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list = []
    try:
        if not db.is_connected():
            await db.connect()
        rows = await db.modeltokenusage.find_many(where={"createdAt": {"gte": since}})
    except Exception as e:  # noqa: BLE001
        logger.warning("cost panel: ModelTokenUsage read failed: %s", e)
        rows = []

    by_key: dict = defaultdict(lambda: {"in": 0, "cached": 0, "out": 0, "n": 0})
    by_day: dict = defaultdict(lambda: {"in": 0, "cached": 0, "out": 0, "n": 0, "usd": 0.0})
    for r in rows:
        day = r.createdAt.date().isoformat()
        model = r.llmModelName or "?"
        site = r.callSite or "—"
        p = int(r.promptTokens or 0)
        c = int(r.cachedInputTokens or 0)
        o = int(r.completionTokens or 0)
        for bucket in (by_key[(day, model, site)], by_day[day]):
            bucket["in"] += p
            bucket["cached"] += c
            bucket["out"] += o
            bucket["n"] += 1

    rows_out = []
    total = {"in": 0, "cached": 0, "out": 0, "n": 0, "usd": 0.0}
    for (day, model, site), a in by_key.items():
        usd = compute_cost_usd(model, a["in"], a["cached"], a["out"])
        by_day[day]["usd"] += usd
        rows_out.append({
            "day": day, "model": model, "site": site,
            "turns": a["n"], "input": a["in"], "cached": a["cached"],
            "output": a["out"], "usd": usd,
        })
        total["in"] += a["in"]; total["cached"] += a["cached"]
        total["out"] += a["out"]; total["n"] += a["n"]; total["usd"] += usd
    rows_out.sort(key=lambda x: (x["day"], -x["usd"]), reverse=True)
    days_out = [{"day": d, **v} for d, v in sorted(by_day.items(), reverse=True)]
    return {"window_days": days, "rows": rows_out, "days": days_out, "total": total}


def _cache_pct(d: dict) -> str:
    inp = d.get("in", 0)
    return f"{(100.0 * d.get('cached', 0) / inp):.1f}%" if inp else "—"


def build_cost_view_router(deps: dict) -> Any:
    """deps: {db: PrismaClient, guard: token-guard dependency}."""
    try:
        from fastapi import APIRouter, Depends, Query  # type: ignore
        from fastapi.responses import HTMLResponse, JSONResponse  # type: ignore
    except Exception:  # noqa: BLE001 -- offline sandbox placeholder
        class _Placeholder:
            def __init__(self, *a, **k): ...
        return _Placeholder()

    db = deps["db"]
    guard = deps["guard"]
    router = APIRouter(tags=["admin-cost"])

    @router.get("/admin/cost.json")
    async def cost_json(days: int = Query(7, ge=1, le=90), _g=Depends(guard)):
        data = await _aggregate(db, days)
        data["total"]["usd"] = round(data["total"]["usd"], 4)
        for r in data["rows"]:
            r["usd"] = round(r["usd"], 6)
        for d in data["days"]:
            d["usd"] = round(d["usd"], 4)
        return JSONResponse(data)

    @router.get("/admin/cost", response_class=HTMLResponse)
    async def cost_html(days: int = Query(7, ge=1, le=90), _g=Depends(guard)):
        d = await _aggregate(db, days)
        t = d["total"]
        cards = (
            f"<div class='card'><div class='muted'>Spend (last {days}d)</div>"
            f"<div class='big'>${t['usd']:.2f}</div></div>"
            f"<div class='card'><div class='muted'>Conversations turns</div>"
            f"<div class='big'>{t['n']:,}</div></div>"
            f"<div class='card'><div class='muted'>Total tokens</div>"
            f"<div class='big'>{(t['in'] + t['out']):,}</div></div>"
            f"<div class='card'><div class='muted'>Input cache hit</div>"
            f"<div class='big'>{_cache_pct(t)}</div></div>"
        )
        day_rows = "".join(
            f"<tr><td>{_e(x['day'])}</td><td>${x['usd']:.4f}</td>"
            f"<td>{x['n']:,}</td><td>{x['in']:,}</td><td>{x['out']:,}</td>"
            f"<td>{_cache_pct(x)}</td></tr>"
            for x in d["days"]
        ) or "<tr><td colspan='6' class='muted'>No usage logged in this window.</td></tr>"
        brk_rows = "".join(
            f"<tr><td>{_e(r['day'])}</td><td>{_e(r['model'])}</td>"
            f"<td>{_e(r['site'])}</td><td>${r['usd']:.4f}</td><td>{r['turns']:,}</td>"
            f"<td>{r['input']:,}</td><td>{r['cached']:,}</td><td>{r['output']:,}</td></tr>"
            for r in d["rows"]
        ) or "<tr><td colspan='8' class='muted'>—</td></tr>"
        body = (
            f"<h1>Smart Chatbot — Cost</h1>"
            f"<div class='muted'>Live from ModelTokenUsage, priced with current "
            f"per-model rates. Window: last {days} days "
            f"(<a href='/admin/cost?days=1&key=…'>1d</a> · "
            f"<a href='/admin/cost?days=30&key=…'>30d</a> · "
            f"<a href='/admin/cost.json?days={days}&key=…'>JSON</a> — keep your "
            f"&amp;key=).</div>"
            f"<div style='margin-top:14px'>{cards}</div>"
            f"<h2>By day</h2><table><tr><th>Day</th><th>USD</th><th>Turns</th>"
            f"<th>Input tok</th><th>Output tok</th><th>Cache hit</th></tr>{day_rows}</table>"
            f"<h2>By day · model · call site</h2><table><tr><th>Day</th><th>Model</th>"
            f"<th>Call site</th><th>USD</th><th>Turns</th><th>Input</th>"
            f"<th>Cached</th><th>Output</th></tr>{brk_rows}</table>"
        )
        return HTMLResponse(_page("Smart Chatbot — Cost", body))

    return router
