#!/usr/bin/env python3
"""Decide the current budget level and write it where the service reads it.

    budget_guard.py                 # check, write state, alert on a change
    budget_guard.py --dry-run       # print what it would do, write nothing
    budget_guard.py --show          # just print the current state file

Run from cron every 15 minutes. See src/config/budget.py for why the
interval matters: one client at the default rate limit can spend the whole
monthly ceiling in about six hours, so a control that only looks once a day
is not a control.

Exit codes:  0 fine (any level)   2 could not determine spend
A non-zero exit on "could not determine" is deliberate -- cron mails it,
and a guard that silently fails is indistinguishable from a guard that
says everything is fine.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import budget as B  # noqa: E402
from src.observability.spend_ledger import read_spend  # noqa: E402
from src.utils.logging_config import get_logger  # noqa: E402

log = get_logger("budget_guard")


def _append_event(payload: dict) -> None:
    """Append-only history of every level change, for the monthly report.

    The report needs to say "the service ran on the cheap model from the
    14th to the 16th"; without this it could only say what the level is
    right now, which is useless after the fact.
    """
    try:
        B.EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with B.EVENT_LOG_PATH.open("a") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception as e:  # noqa: BLE001
        log.error("could not append budget event: %s", e)


def _alert(old: int, new: int, state: B.BudgetState) -> None:
    rising = new > old
    rung = next((r for r in B.LADDER if r.level == new), None)
    verb = "ESCALATED to" if rising else "recovered to"
    subject = (f"[chatbot budget] {verb} {B.LEVEL_NAMES.get(new, new)} "
               f"({state.month})")
    line = B.daily_serving_line()
    body = [
        f"Budget level {verb} {new} ({B.LEVEL_NAMES.get(new, new)}) "
        f"from {old} ({B.LEVEL_NAMES.get(old, old)}).",
        "",
        f"Trigger: {state.reason}",
        "",
        f"Students  month-to-date  ${state.serving_mtd:8.2f} "
        f"of ${B.MONTHLY_SERVING_USD:.2f}",
        f"Students  today          ${state.serving_today:8.2f} "
        f"of ${line:.2f} daily line",
        f"Eval      month-to-date  ${state.eval_mtd:8.2f} "
        f"of ${B.MONTHLY_EVAL_USD:.2f}",
        "",
        f"What this changes: {rung.what_changes if rung else 'nothing'}",
        "",
        f"State file: {B.STATE_PATH}",
        "Full report: .venv/bin/python scripts/budget_report.py",
    ]
    # Reaching level 4 turns students away, which is the one budget event that
    # needs a person rather than a line in tomorrow's digest. Levels 1-3 are
    # invisible to students by design, so they ride the digest.
    kind = "budget_exhausted" if new >= B.L_REFUSE else "budget_level"
    try:
        from src.observability.incident_alerts import _send
        _send(kind, subject, "\n".join(body))
    except Exception as e:  # noqa: BLE001
        log.error("could not send budget alert: %s", e)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the decision, write nothing, send nothing")
    ap.add_argument("--show", action="store_true",
                    help="print the current state file and exit")
    args = ap.parse_args(argv)

    if args.show:
        st = B.read_state()
        print(json.dumps(st.to_json(), indent=2))
        if st.missing:
            print("\n(no state file -- the guard has never run)", file=sys.stderr)
        if st.stale:
            print(f"\n(STALE: last checked {st.checked_at})", file=sys.stderr)
        return 0

    spend = read_spend()
    if spend is None:
        log.error("could not read spend -- leaving the existing state alone")
        return 2

    previous = B.read_state()
    raw_level, reason = B.level_for(serving_today=spend.serving_today,
                                   serving_mtd=spend.serving_mtd)
    level = B.apply_hysteresis(raw_level, previous.level,
                              serving_today=spend.serving_today,
                              serving_mtd=spend.serving_mtd)
    if level != raw_level:
        reason = (f"holding {B.LEVEL_NAMES.get(level, level)}: {reason}, but "
                  f"recovery needs {B.RECOVERY_MARGIN:.0%} clearance below "
                  f"the trigger")

    now = _dt.datetime.now().astimezone()
    state = B.BudgetState(
        level=level, reason=reason,
        serving_today=spend.serving_today, serving_mtd=spend.serving_mtd,
        eval_mtd=spend.eval_mtd,
        month=now.strftime("%Y-%m"), checked_at=now.isoformat(),
        missing=False,
    )

    line = B.daily_serving_line()
    print(f"students  mtd ${spend.serving_mtd:.2f}/{B.MONTHLY_SERVING_USD:.2f}"
          f"   today ${spend.serving_today:.2f}/{line:.2f}")
    print(f"eval      mtd ${spend.eval_mtd:.2f}/{B.MONTHLY_EVAL_USD:.2f}")
    print(f"level     {level} ({B.LEVEL_NAMES.get(level, level)})  <- {reason}")
    if spend.serving_unpriced_calls or spend.eval_unpriced_calls:
        print(f"WARNING: {spend.serving_unpriced_calls} serving and "
              f"{spend.eval_unpriced_calls} eval calls used an UNPRICED model "
              f"and counted as $0. The ceiling cannot be enforced for those.")

    if args.dry_run:
        print("\n(dry run -- nothing written, nothing sent)")
        return 0

    B.write_state(state)
    B.reset_cache()

    if level != previous.level:
        _append_event({
            "at": now.isoformat(), "from": previous.level, "to": level,
            "reason": reason, "serving_mtd": round(spend.serving_mtd, 4),
            "serving_today": round(spend.serving_today, 4),
            "eval_mtd": round(spend.eval_mtd, 4),
        })
        _alert(previous.level, level, state)
        log.info("budget level %d -> %d (%s)", previous.level, level, reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
