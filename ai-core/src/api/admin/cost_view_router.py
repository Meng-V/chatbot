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
    from scripts.cost_rollup import (
        PRICE_PER_1M_TOKENS,
        compute_cost_usd,
        is_priced,
        normalise_model,
    )
except Exception:  # noqa: BLE001 -- keep importable if pricing module moves
    PRICE_PER_1M_TOKENS: dict = {}  # type: ignore

    def compute_cost_usd(model, input_tokens, cached_input_tokens, output_tokens):  # type: ignore
        return 0.0

    def is_priced(model):  # type: ignore
        return False

    def normalise_model(model):  # type: ignore
        return model

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
    ".warn{color:#a11;font-weight:700}"
    ".alert{border:1px solid #e0b4b4;background:#fdf6f6;border-radius:8px;"
    "padding:10px 14px;margin:12px 0;font-size:13px}"
    "code{background:#f4f4f4;padding:1px 4px;border-radius:3px}"
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
            # A $0 here can mean "free" or "we have no rate" -- say which.
            "priced": bool(is_priced(model)),
        })
        total["in"] += a["in"]; total["cached"] += a["cached"]
        total["out"] += a["out"]; total["n"] += a["n"]; total["usd"] += usd
    rows_out.sort(key=lambda x: (x["day"], -x["usd"]), reverse=True)
    days_out = [{"day": d, **v} for d, v in sorted(by_day.items(), reverse=True)]
    return {"window_days": days, "rows": rows_out, "days": days_out, "total": total}


async def _model_history(db: Any) -> list[dict]:
    """Every model this deployment has EVER billed, all-time. Never raises.

    Uses a single group_by aggregate rather than scanning ModelTokenUsage, so
    this stays cheap as the table grows (2,554 rows on 2026-07-31).

    This panel exists because o4-mini-2025-04-16 served 1,518 turns between
    2025-12-17 and 2026-05-12 -- the whole pre-rebuild era -- and was absent
    from the price table, so every cost report read $0.00. A model you have
    forgotten you ran is exactly the one you cannot see the bill for, hence
    all-time and hence the explicit `priced` flag.
    """
    try:
        if not db.is_connected():
            await db.connect()
        groups = await db.modeltokenusage.group_by(
            by=["llmModelName"],
            count=True,
            sum={
                "promptTokens": True,
                "cachedInputTokens": True,
                "completionTokens": True,
            },
            min={"createdAt": True},
            max={"createdAt": True},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("cost panel: model history aggregate failed: %s", e)
        return []

    out: list[dict] = []
    for g in groups:
        model = g.get("llmModelName") or "?"
        s = g.get("_sum") or {}
        inp = int(s.get("promptTokens") or 0)
        cached = int(s.get("cachedInputTokens") or 0)
        outp = int(s.get("completionTokens") or 0)
        base = normalise_model(model)
        out.append({
            "model": model,
            # Shown when a dated snapshot was billed as its base model, so the
            # rate a row was priced at is never a mystery.
            "priced_as": base if base != model else None,
            "priced": bool(is_priced(model)),
            "turns": int((g.get("_count") or {}).get("_all") or 0),
            "input": inp,
            "cached": cached,
            "output": outp,
            "first_seen": _day_of(g.get("_min", {}).get("createdAt")),
            "last_seen": _day_of(g.get("_max", {}).get("createdAt")),
            "usd": compute_cost_usd(model, inp, cached, outp),
        })
    out.sort(key=lambda r: -r["turns"])
    return out


def _day_of(value: Any) -> str:
    """group_by returns createdAt as an ISO string, find_many as a datetime."""
    if value is None:
        return "—"
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)[:10]


# Models we DO call but never write a ModelTokenUsage row for, so the usage
# log cannot see them. src/llm/client.py:embed() calls the embeddings API
# directly -- once per turn for kNN intent classification, plus once per
# uncached exemplar at startup -- without recording anything.
#
# Left uninstrumented deliberately: embed() is synchronous and on the hot
# path, and the spend is trivial (~$0.014 to embed all 5,300 exemplars at
# $0.13/1M). But the rate card must not print "never used" about a model we
# call every single turn, so it says "not logged" instead of lying.
_USED_BUT_UNLOGGED = frozenset({"text-embedding-3-large"})


def _rate_card(history: list[dict]) -> list[dict]:
    """The price table itself, annotated with whether we've ever used each row.

    Rendering the rate card next to the usage makes the failure modes visible
    at a glance: a model with usage but no price (bills as $0), a price with no
    usage (dead row worth pruning), and a model whose usage we never log."""
    used = {normalise_model(h["model"]) for h in history}
    return [
        {
            "model": name,
            "input": r["input"],
            "cached_input": r["cached_input"],
            "output": r["output"],
            "used": name in used,
            "unlogged": name in _USED_BUT_UNLOGGED,
        }
        for name, r in sorted(PRICE_PER_1M_TOKENS.items())
    ]


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
        history = await _model_history(db)
        data["total"]["usd"] = round(data["total"]["usd"], 4)
        for r in data["rows"]:
            r["usd"] = round(r["usd"], 6)
        for d in data["days"]:
            d["usd"] = round(d["usd"], 4)
        for h in history:
            h["usd"] = round(h["usd"], 4)
        data["model_history"] = history
        data["rate_card"] = _rate_card(history)
        data["unpriced_models"] = [h["model"] for h in history if not h["priced"]]
        return JSONResponse(data)

    @router.get("/admin/cost", response_class=HTMLResponse)
    async def cost_html(days: int = Query(7, ge=1, le=90), _g=Depends(guard)):
        d = await _aggregate(db, days)
        history = await _model_history(db)
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
            f"<td>{_e(r['site'])}</td>"
            + (f"<td>${r['usd']:.4f}</td>" if r["priced"] else "<td class='warn'>unpriced</td>")
            + f"<td>{r['turns']:,}</td>"
            f"<td>{r['input']:,}</td><td>{r['cached']:,}</td><td>{r['output']:,}</td></tr>"
            for r in d["rows"]
        ) or "<tr><td colspan='8' class='muted'>—</td></tr>"
        # All-time history. Sits ABOVE the window tables on purpose: the
        # window can only ever show models still in use, and the expensive
        # surprise is the one you stopped running months ago.
        hist_rows = "".join(
            "<tr>"
            f"<td>{_e(h['model'])}"
            + (
                f" <span class='muted'>→ priced as {_e(h['priced_as'])}</span>"
                if h["priced_as"] else ""
            )
            + "</td>"
            + (
                f"<td>${h['usd']:.2f}</td>"
                if h["priced"]
                else "<td class='warn'>unpriced</td>"
            )
            + f"<td>{h['turns']:,}</td><td>{h['input']:,}</td>"
            f"<td>{h['cached']:,}</td><td>{h['output']:,}</td>"
            f"<td>{_e(h['first_seen'])}</td><td>{_e(h['last_seen'])}</td></tr>"
            for h in history
        ) or "<tr><td colspan='8' class='muted'>No usage ever logged.</td></tr>"
        hist_total = sum(h["usd"] for h in history if h["priced"])
        unpriced = [h for h in history if not h["priced"]]
        banner = ""
        if unpriced:
            names = ", ".join(_e(h["model"]) for h in unpriced)
            banner = (
                f"<div class='alert'><b>{len(unpriced)} model(s) have usage but "
                f"no price row, so they are billing as $0 here:</b> {names}. "
                f"Add them to <code>PRICE_PER_1M_TOKENS</code> in "
                f"<code>scripts/cost_rollup.py</code> — the all-time total below "
                f"is an UNDER-count until you do.</div>"
            )
        card_rows = "".join(
            f"<tr><td>{_e(c['model'])}</td><td>${c['input']:.3f}</td>"
            f"<td>${c['cached_input']:.3f}</td><td>${c['output']:.3f}</td>"
            + (
                "<td>yes</td>" if c["used"]
                else "<td class='warn'>used, not logged</td>" if c["unlogged"]
                else "<td class='muted'>never</td>"
            )
            + "</tr>"
            for c in _rate_card(history)
        )

        body = (
            f"<h1>Smart Chatbot — Cost</h1>"
            f"{banner}"
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
            f"<h2>Every model ever used — all time (${hist_total:.2f})</h2>"
            f"<div class='muted'>Ignores the {days}-day window. Sorted by turns. "
            f"A dated snapshot (e.g. <code>-2026-03-17</code>) is priced at its "
            f"base model's rate.</div>"
            f"<table><tr><th>Model</th><th>USD</th><th>Turns</th><th>Input tok</th>"
            f"<th>Cached tok</th><th>Output tok</th><th>First used</th>"
            f"<th>Last used</th></tr>{hist_rows}</table>"
            f"<h2>Rate card — $ per 1M tokens</h2>"
            f"<div class='muted'>From <code>PRICE_PER_1M_TOKENS</code>. One rate "
            f"per model applied to ALL history, so a price change also moves past "
            f"totals; treat old figures as indicative, not invoice-grade. "
            f"<b>used, not logged</b> = we call it but write no ModelTokenUsage "
            f"row, so its spend appears nowhere above (embeddings: roughly "
            f"$0.01 all-time, hence untracked rather than urgent).</div>"
            f"<table><tr><th>Model</th><th>Input</th><th>Cached input</th>"
            f"<th>Output</th><th>Ever used here</th></tr>{card_rows}</table>"
        )
        return HTMLResponse(_page("Smart Chatbot — Cost", body))

    return router
