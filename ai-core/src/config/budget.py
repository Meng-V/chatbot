"""The spend ceiling, and what the service does as it approaches it.

Operator decision 2026-08-04: $100/month total, split
  * $75 for students  (serving traffic)
  * $25 for the eval  (development)

Two separate purses, because they fail differently and need different
controls. Student spend arrives continuously and is throttled; eval spend
arrives in ~$6 lumps and is simply refused once the purse is empty.

WHY A DAILY LINE AND NOT JUST A MONTHLY ONE
-------------------------------------------
Measured on 2026-08-04: one client at the then-current rate limit of 20
messages/minute can issue 28,800 messages/day. On gpt-5.6-terra at
$0.01379/call that is $397/day -- the whole monthly ceiling in about six
hours. A ceiling checked at the end of the month is not a control; by the
time the invoice reads $400 the money is gone. So the guard runs every 15
minutes and compares against a DAILY line as well as the monthly one.

WHY DEGRADE BEFORE DENYING
--------------------------
gpt-5.6-terra costs 21x gpt-5.6-luna per call ($0.01379 vs $0.00066,
measured over 1,054 calls). Routing everything to luna therefore cuts
spend by ~95% while leaving every feature working -- hard questions get
answered less well, but they get answered. That is a far better first
response than turning students away, so it sits two rungs below refusal.

FAIL OPEN, LOUDLY
-----------------
If the state file is missing or corrupt, `current_state()` returns NORMAL
and logs an error. A bot that refuses every student because of a typo in a
JSON file is a worse outcome than a bot that overspends for the fifteen
minutes until the next guard run. Staleness is reported, not corrected:
a stale file keeps its level rather than silently reverting to normal.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.utils.logging_config import get_logger

log = get_logger("budget")


def _f_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("%s=%r is not a number -- using %s", name, raw, default)
        return default


def _i_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer -- using %s", name, raw, default)
        return default


# --- the two purses ------------------------------------------------------

MONTHLY_SERVING_USD = _f_env("BUDGET_MONTHLY_SERVING_USD", 75.00)
MONTHLY_EVAL_USD = _f_env("BUDGET_MONTHLY_EVAL_USD", 25.00)
MONTHLY_TOTAL_USD = MONTHLY_SERVING_USD + MONTHLY_EVAL_USD

# What one full 234-case eval run costs, measured 2026-08-04 ($5.74 at
# gpt-5.6-terra rates). Used to refuse a run that would breach the purse
# BEFORE it starts spending, rather than discovering it halfway through.
EVAL_RUN_ESTIMATE_USD = _f_env("BUDGET_EVAL_RUN_ESTIMATE_USD", 6.00)

STATE_PATH = Path(
    os.getenv("BUDGET_STATE_PATH", "/opt/chatbot/data/budget_state.json")
)
EVENT_LOG_PATH = Path(
    os.getenv("BUDGET_EVENT_LOG_PATH", "/opt/chatbot/data/budget_events.jsonl")
)

# A state file older than this is reported as stale in the report and the
# alert. Two guard runs missed in a row means the cron is broken, and that
# is worth knowing about before the invoice says so.
STALE_AFTER_S = _i_env("BUDGET_STALE_AFTER_S", 3 * 3600)


LIBRARY_TZ = "America/New_York"


def library_today() -> "_dt.date":
    """Today in the libraries' own timezone, not the box's.

    The box runs UTC and Oxford is UTC-4 in summer, so from 8pm ET on the last
    day of a month `date.today()` already reports the NEXT month -- and the
    purse would refill about four hours early, every month. The operator
    accounts by natural calendar month starting at midnight on the 1st, which
    means midnight in Oxford.

    Same trap as real_backends._library_today, which was added after
    "what time do you close today" named the wrong day for four hours each
    evening. Fixed here before it could be observed rather than after.
    """
    import pytz
    return _dt.datetime.now(pytz.timezone(LIBRARY_TZ)).date()


def days_in_month(when: "Optional[_dt.date]" = None) -> int:
    d = when or library_today()
    return calendar.monthrange(d.year, d.month)[1]


def daily_serving_line(when: "Optional[_dt.date]" = None) -> float:
    """The student purse spread evenly over the month.

    Evenly, not pro-rata-to-date: a quiet first week should not license a
    spike in the second. The monthly trigger catches cumulative drift; this
    one catches a single bad day while it is still happening.
    """
    return MONTHLY_SERVING_USD / days_in_month(when)


# --- the ladder ----------------------------------------------------------
#
# Each rung names its trigger in multiples of the daily line AND as a
# fraction of the monthly purse. Whichever fires first wins, so a slow
# month-long creep and a single runaway afternoon are both caught.

L_NORMAL = 0
L_ALERT = 1
L_CHEAP = 2
L_TIGHTEN = 3
L_REFUSE = 4

LEVEL_NAMES = {
    L_NORMAL: "normal",
    L_ALERT: "alert",
    L_CHEAP: "cheap_model",
    L_TIGHTEN: "tightened",
    L_REFUSE: "refusing_new",
}


@dataclass(frozen=True)
class Rung:
    level: int
    daily_multiple: Optional[float]   # today's spend vs the daily line
    monthly_fraction: Optional[float]  # month-to-date vs the student purse
    what_changes: str


LADDER: tuple[Rung, ...] = (
    Rung(L_ALERT, 1.0, 0.70,
         "Email only. Nothing changes for students."),
    Rung(L_CHEAP, 1.5, 0.85,
         "Reasoning model forced to the cheap one (~21x cheaper per call). "
         "Every feature still works; hard questions get answered less well."),
    Rung(L_TIGHTEN, 2.5, 0.95,
         "Per-client rate limit and per-conversation turn cap tightened. "
         "A real student asks 3-5 questions and is unaffected; a script is not."),
    # No daily trigger on refusal. One expensive day must never take the
    # service away from students -- only an exhausted monthly purse can.
    Rung(L_REFUSE, None, 1.00,
         "New conversations are declined with a pointer to Ask Us. "
         "Conversations already open are allowed to finish."),
)

# Degrade instantly, recover slowly: a level is only given up once spend
# drops this far below the trigger that put us there. Without it the guard
# flaps between rungs every 15 minutes around a threshold, and each flap
# is an email.
RECOVERY_MARGIN = _f_env("BUDGET_RECOVERY_MARGIN", 0.10)

# What each rung does to the knobs the app actually reads.
RATE_MAX_NORMAL = _i_env("CHAT_RATE_MAX", 20)
RATE_MAX_TIGHTENED = _i_env("BUDGET_TIGHTENED_RATE_MAX", 6)
MAX_TURNS_NORMAL = _i_env("CHAT_MAX_TURNS_PER_CONVERSATION", 80)
MAX_TURNS_TIGHTENED = _i_env("BUDGET_TIGHTENED_MAX_TURNS", 20)


def level_for(
    *, serving_today: float, serving_mtd: float,
    when: "Optional[_dt.date]" = None,
) -> tuple[int, str]:
    """The rung this spend lands on, and the reason in words.

    The reason is carried all the way into the alert and the report,
    because "level 3" on its own tells an operator nothing about which of
    the two triggers fired or by how much.
    """
    line = daily_serving_line(when)
    level, reason = L_NORMAL, "within budget"
    for rung in LADDER:
        if rung.daily_multiple is not None:
            threshold = line * rung.daily_multiple
            if serving_today >= threshold:
                level, reason = rung.level, (
                    f"today ${serving_today:.2f} >= ${threshold:.2f} "
                    f"({rung.daily_multiple:g}x the ${line:.2f} daily line)"
                )
        if rung.monthly_fraction is not None:
            threshold = MONTHLY_SERVING_USD * rung.monthly_fraction
            if serving_mtd >= threshold:
                level, reason = rung.level, (
                    f"month-to-date ${serving_mtd:.2f} >= ${threshold:.2f} "
                    f"({rung.monthly_fraction:.0%} of the "
                    f"${MONTHLY_SERVING_USD:.2f} student budget)"
                )
    return level, reason


def apply_hysteresis(new_level: int, old_level: int, *,
                     serving_today: float, serving_mtd: float,
                     when: "Optional[_dt.date]" = None) -> int:
    """Escalate at once; step down only one rung, and only past the margin.

    Escalation is never delayed -- money is leaving. De-escalation is
    deliberately slow so the service does not oscillate between "cheap
    model" and "normal" across a threshold, mailing on every crossing.
    """
    if new_level >= old_level:
        return new_level
    target = old_level - 1
    rung = next((r for r in LADDER if r.level == old_level), None)
    if rung is None:
        return new_level
    line = daily_serving_line(when)
    below = True
    if rung.daily_multiple is not None:
        below &= serving_today < line * rung.daily_multiple * (1 - RECOVERY_MARGIN)
    if rung.monthly_fraction is not None:
        below &= serving_mtd < (MONTHLY_SERVING_USD * rung.monthly_fraction
                                * (1 - RECOVERY_MARGIN))
    if not below:
        return old_level
    return max(new_level, target)


# --- state the running app reads ----------------------------------------


@dataclass
class BudgetState:
    level: int = L_NORMAL
    reason: str = "no state file yet"
    serving_today: float = 0.0
    serving_mtd: float = 0.0
    eval_mtd: float = 0.0
    month: str = ""
    checked_at: str = ""
    stale: bool = False
    missing: bool = True
    raw: dict = field(default_factory=dict)

    @property
    def level_name(self) -> str:
        return LEVEL_NAMES.get(self.level, str(self.level))

    @property
    def force_cheap_model(self) -> bool:
        return self.level >= L_CHEAP

    @property
    def refuse_new_conversations(self) -> bool:
        return self.level >= L_REFUSE

    @property
    def rate_max(self) -> int:
        return RATE_MAX_TIGHTENED if self.level >= L_TIGHTEN else RATE_MAX_NORMAL

    @property
    def max_turns(self) -> int:
        return MAX_TURNS_TIGHTENED if self.level >= L_TIGHTEN else MAX_TURNS_NORMAL

    def to_json(self) -> dict:
        return {
            "level": self.level,
            "level_name": self.level_name,
            "reason": self.reason,
            "serving_today": round(self.serving_today, 4),
            "serving_mtd": round(self.serving_mtd, 4),
            "eval_mtd": round(self.eval_mtd, 4),
            "month": self.month,
            "checked_at": self.checked_at,
            # Denormalised so an operator reading the file by eye, or any
            # other process, does not have to re-derive the ladder.
            "force_cheap_model": self.force_cheap_model,
            "refuse_new_conversations": self.refuse_new_conversations,
            "rate_max": self.rate_max,
            "max_turns": self.max_turns,
            "monthly_serving_usd": MONTHLY_SERVING_USD,
            "monthly_eval_usd": MONTHLY_EVAL_USD,
        }


def write_state(state: BudgetState, path: "Optional[Path]" = None) -> None:
    """Atomically replace the state file.

    Atomically because the serving process reads it on a hot path: a
    half-written file read between two writes would be corrupt JSON, and
    the reader would fall back to NORMAL for no reason.
    """
    target = path or STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_json(), indent=2) + "\n")
    os.replace(tmp, target)


def _parse_state(data: dict, *, now: "Optional[_dt.datetime]" = None) -> BudgetState:
    st = BudgetState(
        level=int(data.get("level") or 0),
        reason=str(data.get("reason") or ""),
        serving_today=float(data.get("serving_today") or 0.0),
        serving_mtd=float(data.get("serving_mtd") or 0.0),
        eval_mtd=float(data.get("eval_mtd") or 0.0),
        month=str(data.get("month") or ""),
        checked_at=str(data.get("checked_at") or ""),
        missing=False,
        raw=data,
    )
    stamp = st.checked_at
    if stamp:
        try:
            when = _dt.datetime.fromisoformat(stamp)
            ref = now or _dt.datetime.now(when.tzinfo)
            st.stale = (ref - when).total_seconds() > STALE_AFTER_S
        except ValueError:
            st.stale = True
    # A state file from a previous month is not stale, it is void: the
    # purse refilled at midnight on the 1st and nobody should still be
    # refusing students on last month's numbers.
    # Oxford's month, not the box's -- see library_today().
    this_month = (now.date() if now else library_today()).strftime("%Y-%m")
    if st.month and st.month != this_month:
        log.info("budget state is from %s, this is %s -- treating as normal",
                 st.month, this_month)
        return BudgetState(level=L_NORMAL, reason=f"new month ({this_month})",
                           month=this_month, missing=False, raw=data)
    return st


def read_state(path: "Optional[Path]" = None) -> BudgetState:
    """The current level, or NORMAL if it cannot be determined.

    Never raises. See FAIL OPEN, LOUDLY in the module docstring.
    """
    target = path or STATE_PATH
    try:
        data = json.loads(target.read_text())
        if not isinstance(data, dict):
            raise ValueError("state file is not an object")
        return _parse_state(data)
    except FileNotFoundError:
        return BudgetState(reason="no state file yet")
    except Exception as e:  # noqa: BLE001 -- must never break a turn
        log.error("budget state at %s is unreadable (%s) -- failing OPEN at "
                  "normal. Students are not throttled and spend is NOT being "
                  "enforced until the next guard run fixes this.", target, e)
        return BudgetState(reason=f"unreadable state file: {e}")


# --- cheap cached accessor for the hot path ------------------------------

_CACHE_TTL_S = _f_env("BUDGET_STATE_CACHE_TTL_S", 15.0)
_cache: dict[str, Any] = {"at": 0.0, "state": None}


def current_state() -> BudgetState:
    """read_state(), re-read at most every _CACHE_TTL_S seconds.

    Called per turn, so it must not stat+parse a file every time; 15
    seconds of staleness against a guard that runs every 15 minutes costs
    nothing.
    """
    import time as _time
    now = _time.monotonic()
    cached = _cache.get("state")
    if cached is not None and (now - float(_cache["at"])) < _CACHE_TTL_S:
        return cached  # type: ignore[return-value]
    state = read_state()
    _cache["at"] = now
    _cache["state"] = state
    return state


def reset_cache() -> None:
    """For tests, and for anything that has just written the state file."""
    _cache["at"] = 0.0
    _cache["state"] = None
