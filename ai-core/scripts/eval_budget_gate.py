#!/usr/bin/env python3
"""Refuse to start an eval run that would breach the $25 development purse.

    eval_budget_gate.py            # exit 0 = go ahead, 3 = purse too low
    eval_budget_gate.py --cost 2.5 # a partial run (one or two categories)
    eval_budget_gate.py --status   # print the purse and exit 0

Meant to be the first line of an eval script:

    .venv/bin/python scripts/eval_budget_gate.py || exit 0

Checked BEFORE the run rather than during it, because a full run takes
about 100 minutes and costs about $6: discovering the purse is empty at
minute 80 wastes both the money and the time, and leaves a half-finished
result set that cannot be compared to anything.

Exit 3, not 1, so a shell can tell "the purse is empty" (an expected,
fine outcome) apart from "the gate itself is broken".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import budget as B  # noqa: E402
from src.observability.spend_ledger import read_spend  # noqa: E402

GO, NO_GO, BROKEN = 0, 3, 2


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cost", type=float, default=B.EVAL_RUN_ESTIMATE_USD,
                    help=f"estimated cost of the run "
                         f"(default ${B.EVAL_RUN_ESTIMATE_USD:.2f}, one full "
                         f"234-case pass)")
    ap.add_argument("--status", action="store_true",
                    help="report the purse and always exit 0")
    args = ap.parse_args(argv)

    spend = read_spend()
    if spend is None:
        # Cannot read the ledger. Do NOT wave the run through -- an
        # unreadable ledger is exactly when spend is least visible.
        print("eval gate: could not read spend -- refusing to guess. "
              "Fix the DB connection or pass the run through by hand.",
              file=sys.stderr)
        return BROKEN

    used, purse = spend.eval_mtd, B.MONTHLY_EVAL_USD
    left = purse - used
    runs_left = int(max(0.0, left) // B.EVAL_RUN_ESTIMATE_USD)
    print(f"eval purse: ${used:.2f} used of ${purse:.2f} "
          f"(${left:.2f} left, ~{runs_left} full run(s))")
    if spend.eval_unpriced_calls:
        print(f"  WARNING: {spend.eval_unpriced_calls} eval calls used an "
              f"UNPRICED model and counted as $0 -- the real figure is higher.",
              file=sys.stderr)

    if args.status:
        return GO

    if used + args.cost > purse:
        print(f"eval gate: NO GO. This run is estimated at ${args.cost:.2f} and "
              f"only ${left:.2f} is left in the month's eval purse.\n"
              f"  Options: wait for the 1st, run a subset with "
              f"--filter (and pass --cost), or raise "
              f"BUDGET_MONTHLY_EVAL_USD deliberately.", file=sys.stderr)
        return NO_GO

    print(f"eval gate: GO (${args.cost:.2f} estimated, "
          f"${left - args.cost:.2f} would remain)")
    return GO


if __name__ == "__main__":
    raise SystemExit(main())
