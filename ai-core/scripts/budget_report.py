#!/usr/bin/env python3
"""The monthly spend report: two purses, where the money went, what is next.

    budget_report.py                      # this month, Markdown to stdout
    budget_report.py --month 2026-07
    budget_report.py --html out.html      # also write a standalone page
    budget_report.py --email              # send it (uses the alert mailer)

Written to answer four questions an operator actually has, in order:
  1. Are we going to breach the ceiling this month?
  2. If spend moved, WHICH number moved -- volume, model mix, or cache rate?
  3. What did the eval cost, and how many runs are left?
  4. Was the service degraded at any point, and when?

Question 2 is the one that matters most and the one a plain total cannot
answer. Cost is volume x model-mix x (1 - cache rate), and those three fail
independently: a cache regression alone multiplied measured terra spend by
2.7x on 2026-08-04 with no change in traffic at all.
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import datetime as _dt
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import budget as B  # noqa: E402
from src.observability.spend_ledger import EVAL_CALL_SITE  # noqa: E402
from src.utils.logging_config import get_logger  # noqa: E402
from scripts.cost_rollup import (  # noqa: E402
    PRICE_PER_1M_TOKENS, compute_cost_usd, is_priced, normalise_model,
)

log = get_logger("budget_report")


def _month_bounds(month: str) -> tuple[_dt.date, _dt.date]:
    y, m = (int(x) for x in month.split("-"))
    return _dt.date(y, m, 1), _dt.date(y, m, calendar.monthrange(y, m)[1])


async def _gather(first: _dt.date, last: _dt.date) -> dict:
    from prisma import Prisma

    db = Prisma()
    await db.connect()
    try:
        serving = await db.query_raw(
            """
            SELECT "llmModelName" AS model, COALESCE("callSite",'-') AS site,
                   SUM("promptTokens")      AS inp,
                   SUM("cachedInputTokens") AS cached,
                   SUM("completionTokens")  AS outp,
                   COUNT(*)                 AS calls
            FROM "ModelTokenUsage"
            WHERE "createdAt" >= $1::date AND "createdAt" < ($2::date + 1)
            GROUP BY 1, 2 ORDER BY 1, 2
            """,
            first.isoformat(), last.isoformat(),
        )
        daily = await db.query_raw(
            """
            SELECT "createdAt"::date AS d,
                   SUM("promptTokens")      AS inp,
                   SUM("cachedInputTokens") AS cached,
                   SUM("completionTokens")  AS outp,
                   "llmModelName"           AS model
            FROM "ModelTokenUsage"
            WHERE "createdAt" >= $1::date AND "createdAt" < ($2::date + 1)
            GROUP BY 1, 5 ORDER BY 1
            """,
            first.isoformat(), last.isoformat(),
        )
        ev = await db.query_raw(
            """
            SELECT date::date AS d, model,
                   SUM("inputTokens")  AS inp, SUM("cachedTokens") AS cached,
                   SUM("outputTokens") AS outp, SUM("callCount")   AS calls,
                   SUM(usd)            AS usd
            FROM "DailyCost"
            WHERE "callSite" = $1 AND date >= $2::date AND date <= $3::date
            GROUP BY 1, 2 ORDER BY 1, 2
            """,
            EVAL_CALL_SITE, first.isoformat(), last.isoformat(),
        )
        convs = await db.query_raw(
            """SELECT COUNT(*) AS n FROM "Conversation"
               WHERE "createdAt" >= $1::date AND "createdAt" < ($2::date + 1)""",
            first.isoformat(), last.isoformat(),
        )
        asks = await db.query_raw(
            """SELECT COUNT(*) AS n FROM "Message"
               WHERE timestamp >= $1::date AND timestamp < ($2::date + 1)""",
            first.isoformat(), last.isoformat(),
        )
    finally:
        await db.disconnect()
    return {"serving": serving, "daily": daily, "eval": ev,
            "conversations": int(convs[0]["n"] or 0),
            "messages": int(asks[0]["n"] or 0)}


def _bar(frac: float, width: int = 28) -> str:
    frac = max(0.0, min(1.5, frac))
    filled = int(round(min(frac, 1.0) * width))
    over = int(round(max(0.0, frac - 1.0) * width))
    return "#" * filled + ("!" * over) + "." * max(0, width - filled - over)


def _events(month: str) -> list[dict]:
    try:
        out = []
        for line in B.EVENT_LOG_PATH.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("at", "")).startswith(month):
                out.append(row)
        return out
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        log.warning("could not read budget events: %s", e)
        return []


def build(month: str) -> tuple[str, dict]:
    first, last = _month_bounds(month)
    today = _dt.date.today()
    data = asyncio.run(_gather(first, last))

    serve_rows, serve_total, unpriced = [], 0.0, []
    tok_in = tok_cached = tok_out = calls = 0
    per_model: dict[str, float] = {}
    for r in data["serving"]:
        m = str(r["model"] or "")
        i, c, o, n = (int(r["inp"] or 0), int(r["cached"] or 0),
                      int(r["outp"] or 0), int(r["calls"] or 0))
        usd = compute_cost_usd(m, i, c, o)
        serve_total += usd
        tok_in += i; tok_cached += c; tok_out += o; calls += n
        per_model[m] = per_model.get(m, 0.0) + usd
        serve_rows.append((m, str(r["site"]), n, i, c, o, usd, is_priced(m)))
        if not is_priced(m):
            unpriced.append((m, n))

    eval_rows, eval_total = [], 0.0
    eval_days: dict[str, float] = {}
    for r in data["eval"]:
        usd = float(r["usd"] or 0.0)
        eval_total += usd
        d = str(r["d"])[:10]
        eval_days[d] = eval_days.get(d, 0.0) + usd
        eval_rows.append((d, str(r["model"] or ""), int(r["calls"] or 0), usd))

    # Daily serving series, for the projection and the cache trend.
    by_day: dict[str, dict] = {}
    for r in data["daily"]:
        d = str(r["d"])[:10]
        slot = by_day.setdefault(d, {"usd": 0.0, "inp": 0, "cached": 0})
        slot["usd"] += compute_cost_usd(str(r["model"] or ""), int(r["inp"] or 0),
                                        int(r["cached"] or 0), int(r["outp"] or 0))
        slot["inp"] += int(r["inp"] or 0)
        slot["cached"] += int(r["cached"] or 0)

    dim = calendar.monthrange(first.year, first.month)[1]
    elapsed = (min(today, last) - first).days + 1 if today >= first else dim
    elapsed = max(1, min(elapsed, dim))
    line = B.MONTHLY_SERVING_USD / dim
    run_rate = serve_total / elapsed
    projected = run_rate * dim
    cache_rate = (tok_cached / tok_in) if tok_in else 0.0
    state = B.read_state()

    L: list[str] = []
    a = L.append
    a(f"# Chatbot budget report — {month}")
    a("")
    a(f"Generated {_dt.datetime.now().astimezone():%Y-%m-%d %H:%M %Z} · "
      f"day {elapsed} of {dim}")
    a("")
    a("## 1. Are we going to breach the ceiling?")
    a("")
    a("```")
    a(f"students  ${serve_total:7.2f} / ${B.MONTHLY_SERVING_USD:6.2f}  "
      f"[{_bar(serve_total / B.MONTHLY_SERVING_USD)}] "
      f"{serve_total / B.MONTHLY_SERVING_USD:5.1%}")
    a(f"eval      ${eval_total:7.2f} / ${B.MONTHLY_EVAL_USD:6.2f}  "
      f"[{_bar(eval_total / B.MONTHLY_EVAL_USD)}] "
      f"{eval_total / B.MONTHLY_EVAL_USD:5.1%}")
    a(f"total     ${serve_total + eval_total:7.2f} / "
      f"${B.MONTHLY_TOTAL_USD:6.2f}  "
      f"[{_bar((serve_total + eval_total) / B.MONTHLY_TOTAL_USD)}] "
      f"{(serve_total + eval_total) / B.MONTHLY_TOTAL_USD:5.1%}")
    a("```")
    a("")
    a(f"- Student run rate **${run_rate:.2f}/day** against a "
      f"**${line:.2f}/day** line.")
    verdict = ("**on track**" if projected <= B.MONTHLY_SERVING_USD
               else f"**projected to breach by ${projected - B.MONTHLY_SERVING_USD:.2f}**")
    a(f"- At this rate the month ends at **${projected:.2f}** — {verdict}.")
    runs_left = int(max(0.0, B.MONTHLY_EVAL_USD - eval_total)
                    // B.EVAL_RUN_ESTIMATE_USD)
    a(f"- Eval purse has room for **{runs_left} more full run(s)** at "
      f"${B.EVAL_RUN_ESTIMATE_USD:.2f} each.")
    a(f"- Current level: **{state.level} ({state.level_name})** — "
      f"{state.reason or 'n/a'}")
    if state.missing:
        a("- :warning: **No state file — the guard has never run.** Nothing is "
          "being enforced.")
    elif state.stale:
        a(f"- :warning: **State is stale** (last checked {state.checked_at}). "
          f"Check the cron entry.")
    a("")

    a("## 2. If spend moved, which number moved?")
    a("")
    a("Cost is volume × model mix × (1 − cache rate). These fail "
      "independently, so all three are here.")
    a("")
    a("| | value |")
    a("|---|---|")
    a(f"| Conversations | {data['conversations']:,} |")
    a(f"| Messages | {data['messages']:,} |")
    a(f"| Model calls | {calls:,} |")
    a(f"| Input tokens | {tok_in:,} |")
    a(f"| Cache rate | {cache_rate:.1%} |")
    a(f"| Output tokens | {tok_out:,} |")
    a(f"| Cost per conversation | "
      f"${serve_total / data['conversations']:.4f} |"
      if data["conversations"] else "| Cost per conversation | n/a |")
    a("")
    a("**Model mix** — the biggest single lever. The expensive model costs "
      "about 21× the cheap one per call, so its share of calls drives the total.")
    a("")
    a("| model | calls | share of calls | cost | share of cost |")
    a("|---|---:|---:|---:|---:|")
    for m, usd in sorted(per_model.items(), key=lambda kv: -kv[1]):
        mc = sum(r[2] for r in serve_rows if r[0] == m)
        a(f"| `{m}` | {mc:,} | {mc / calls:.1%} | "
          f"{'$' + format(usd, '.2f') if is_priced(m) else '**unpriced**'} | "
          f"{usd / serve_total:.1%} |" if calls and serve_total else
          f"| `{m}` | {mc:,} | — | — | — |")
    a("")
    if unpriced:
        a("> :warning: **Unpriced models counted as $0** — the ceiling cannot "
          "be enforced for these calls:")
        for m, n in unpriced:
            a(f"> - `{m}`: {n:,} calls. Add it to `PRICE_PER_1M_TOKENS`.")
        a("")

    if by_day:
        a("**Daily student spend and cache rate** — a cache rate falling while "
          "volume is flat is the silent 2.7× cost increase.")
        a("")
        a("| day | spend | vs line | cache rate |")
        a("|---|---:|---:|---:|")
        for d in sorted(by_day):
            v = by_day[d]
            cr = (v["cached"] / v["inp"]) if v["inp"] else 0.0
            flag = "" if v["usd"] <= line else (
                " :warning:" if v["usd"] <= line * 2.5 else " :rotating_light:")
            a(f"| {d} | ${v['usd']:.2f}{flag} | {v['usd'] / line:.1f}× | {cr:.0%} |")
        a("")

    a("## 3. What did the eval cost?")
    a("")
    if eval_rows:
        a("| day | model | calls | cost |")
        a("|---|---|---:|---:|")
        for d, m, n, usd in eval_rows:
            a(f"| {d} | `{m}` | {n:,} | ${usd:.2f} |")
        a("")
        a(f"Eval ran on **{len(eval_days)} day(s)** this month for "
          f"**${eval_total:.2f}**.")
    else:
        a("No eval spend recorded this month.")
        a("")
        a("> If the eval *did* run, this is the reporting hole found on "
          "2026-08-04, not a quiet month. `run_eval` must call "
          "`record_eval_spend()`; check its log for "
          "\"could not record eval spend\".")
    a("")

    a("## 4. Was the service degraded, and when?")
    a("")
    evs = _events(month)
    if evs:
        a("| when | change | why |")
        a("|---|---|---|")
        for e in evs:
            fr = B.LEVEL_NAMES.get(e.get("from"), e.get("from"))
            to = B.LEVEL_NAMES.get(e.get("to"), e.get("to"))
            arrow = "escalated" if (e.get("to") or 0) > (e.get("from") or 0) else "recovered"
            a(f"| {str(e.get('at'))[:16]} | {arrow} {fr} → **{to}** | "
              f"{e.get('reason', '')} |")
    else:
        a("No level changes this month — the service ran normally throughout.")
    a("")
    a("## What each level does")
    a("")
    a("| level | trigger | what changes for students |")
    a("|---|---|---|")
    a(f"| 0 normal | — | nothing |")
    for r in B.LADDER:
        trig = []
        if r.daily_multiple is not None:
            trig.append(f"day ≥ {r.daily_multiple:g}× (${line * r.daily_multiple:.2f})")
        if r.monthly_fraction is not None:
            trig.append(f"month ≥ {r.monthly_fraction:.0%} "
                        f"(${B.MONTHLY_SERVING_USD * r.monthly_fraction:.2f})")
        a(f"| {r.level} {B.LEVEL_NAMES[r.level]} | {' or '.join(trig)} | "
          f"{r.what_changes} |")
    a("")
    return "\n".join(L), {
        "serving": serve_total, "eval": eval_total, "projected": projected,
        "level": state.level, "runs_left": runs_left,
    }


_HTML = """<title>Chatbot budget — {month}</title>
<style>
 :root {{ --ink:#14161a; --soft:#4a5361; --bg:#fbfaf8; --card:#fff;
   --rule:#dbd7d1; --red:#b4122a; --ok:#1c6244; }}
 @media (prefers-color-scheme:dark) {{ :root {{ --ink:#eceae6; --soft:#a2aab6;
   --bg:#101216; --card:#181b21; --rule:#2c313a; --red:#ff6478; --ok:#4cc38a; }} }}
 :root[data-theme=dark] {{ --ink:#eceae6; --soft:#a2aab6; --bg:#101216;
   --card:#181b21; --rule:#2c313a; --red:#ff6478; --ok:#4cc38a; }}
 :root[data-theme=light] {{ --ink:#14161a; --soft:#4a5361; --bg:#fbfaf8;
   --card:#fff; --rule:#dbd7d1; --red:#b4122a; --ok:#1c6244; }}
 body {{ background:var(--bg); color:var(--ink); margin:0; padding:32px 18px 72px;
   font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
 main {{ max-width:860px; margin:0 auto; }}
 h1 {{ font-size:28px; margin:0 0 6px; letter-spacing:-.01em; }}
 h2 {{ font-size:20px; margin:32px 0 8px; padding-top:14px;
   border-top:1px solid var(--rule); }}
 pre {{ background:var(--card); border:1px solid var(--rule); padding:14px 16px;
   overflow-x:auto; font-size:13px; line-height:1.5; }}
 table {{ border-collapse:collapse; width:100%; font-size:14px; margin:6px 0 14px; }}
 th,td {{ text-align:left; padding:7px 12px 7px 0; border-bottom:1px solid var(--rule); }}
 th {{ font-size:11px; letter-spacing:.07em; text-transform:uppercase; color:var(--soft); }}
 td:nth-child(n+2) {{ font-variant-numeric:tabular-nums; }}
 code {{ font-size:13px; }} blockquote {{ border-left:3px solid var(--red);
   margin:0 0 14px; padding:2px 0 2px 14px; color:var(--soft); }}
 .scroll {{ overflow-x:auto; }}
</style>
<main>{body}</main>
"""


def _md_to_html(md: str) -> str:
    """Enough Markdown for this one report: headings, tables, code, quotes.

    A dependency-free renderer rather than a library, because this has to
    run from cron on a box where adding a package is a deployment.
    """
    out, in_tbl, in_pre = [], False, False
    for raw in md.splitlines():
        if raw.startswith("```"):
            out.append("</pre>" if in_pre else "<pre>")
            in_pre = not in_pre
            continue
        if in_pre:
            out.append(html.escape(raw))
            continue
        line = html.escape(raw)
        line = line.replace(":rotating_light:", "🚨").replace(":warning:", "⚠️")
        while "**" in line:
            line = line.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
        while line.count("`") >= 2:
            line = line.replace("`", "<code>", 1).replace("`", "</code>", 1)
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue
            if not in_tbl:
                out.append('<div class="scroll"><table>')
                in_tbl = True
                out.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                continue
            out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_tbl:
            out.append("</table></div>")
            in_tbl = False
        if line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line.startswith("- "):
            out.append(f"<p style='margin:0 0 4px'>• {line[2:]}</p>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
    if in_tbl:
        out.append("</table></div>")
    if in_pre:
        out.append("</pre>")
    return "\n".join(out)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", default=_dt.date.today().strftime("%Y-%m"),
                    help="YYYY-MM (default: this month)")
    ap.add_argument("--html", metavar="PATH", help="also write a standalone page")
    ap.add_argument("--email", action="store_true", help="send the report")
    args = ap.parse_args(argv)

    try:
        md, summary = build(args.month)
    except Exception as e:  # noqa: BLE001
        print(f"could not build the report ({type(e).__name__}: {e})",
              file=sys.stderr)
        return 2
    print(md)

    if args.html:
        Path(args.html).write_text(
            _HTML.format(month=html.escape(args.month), body=_md_to_html(md))
        )
        print(f"\n(wrote {args.html})", file=sys.stderr)

    if args.email:
        breach = summary["projected"] > B.MONTHLY_SERVING_USD
        subject = (f"[chatbot budget] {args.month}: students "
                   f"${summary['serving']:.2f}/{B.MONTHLY_SERVING_USD:.0f}, "
                   f"eval ${summary['eval']:.2f}/{B.MONTHLY_EVAL_USD:.0f}"
                   f"{' -- PROJECTED BREACH' if breach else ''}")
        try:
            from src.observability.incident_alerts import _send
            _send("budget_report", subject, md)
            print("(emailed)", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"(could not email: {e})", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
