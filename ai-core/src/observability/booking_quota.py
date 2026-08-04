"""How many rooms one person, or one conversation, may book through this bot.

Operator decision 2026-08-04, ahead of the beta launch.

  * **2 per conversation** — a student booking a study room wants one, maybe
    two. More than that in a single chat is a script or someone playing.
  * **2 per email per day** — the real abuse case: a stream of bookings in
    someone else's name, or under invented netids, to deny other students
    rooms.

WHY THIS IS NEEDED EVEN THOUGH THE EMAIL IS CHECKED
---------------------------------------------------
`_validate_email` already requires an @miamioh.edu address, so this is not
open to the whole internet. But we do NOT verify that the address belongs to
the person typing. LibCal does send a real confirmation email to whatever
address is given — which means an impersonated booking is *detectable* by
its victim, and that is genuinely useful. It does not make it *preventable*.
A per-address daily cap is what bounds the damage.

SCOPE OF WHAT THIS CAN PROMISE
------------------------------
This limits bookings made **through this chatbot only**. A student can still
book directly in LibCal, and should be able to. The claim is "our app cannot
be used to flood the room system", not "the room system cannot be flooded".
Do not let that distinction get lost in a summary.

WHY A FILE AND NOT A DATABASE TABLE
-----------------------------------
A new table needs a Prisma migration against the production database, which
holds live conversation history and has no current backup by operator
decision. The counter is small, append-cheap, and losing it means at worst a
day's counts reset — an acceptable failure next to a migration on an
unbacked database. Revisit once there is a backup.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.logging_config import get_logger

log = get_logger("booking_quota")


def _i_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        log.warning("%s=%r is not an integer -- using %s", name, raw, default)
        return default


MAX_PER_CONVERSATION = _i_env("BOOKING_MAX_PER_CONVERSATION", 2)
MAX_PER_EMAIL_PER_DAY = _i_env("BOOKING_MAX_PER_EMAIL_PER_DAY", 2)

_DEFAULT_LEDGER = "/opt/chatbot/data/booking_quota.json"

LEDGER_PATH = Path(os.getenv("BOOKING_QUOTA_PATH", _DEFAULT_LEDGER))
"""Module-level for readability; every read goes through _ledger() so an env
var set after import -- or a test's monkeypatch -- is honoured."""


def _ledger() -> Path:
    """Resolved per call, deliberately.

    A module constant frozen at import made the unit suite read and WRITE the
    production ledger: test_real_backends drives book_room with confirm=True
    against a fake LibCal, `record()` fired, and the operator's own address was
    left sitting at its daily cap in real state (caught 2026-08-04). Tests must
    be able to redirect this, and production must not depend on import order.
    """
    override = (os.getenv("BOOKING_QUOTA_PATH") or "").strip()
    if override:
        return Path(override)
    return LEDGER_PATH

# Keep a few days so a late-evening booking near midnight is still counted
# against the right day, and so the file can be read for a report.
_KEEP_DAYS = 7


@dataclass
class Verdict:
    allowed: bool
    reason: str = ""
    """Patron-facing when not allowed. Says what to do next, never just no."""


def _today() -> str:
    import pytz
    return _dt.datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        data = json.loads(_ledger().read_text())
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        log.error("booking quota ledger unreadable (%s) -- starting empty. "
                  "Counts for today are lost; the cap is not enforced until "
                  "the next successful write.", e)
        return {}


def _save(data: dict) -> None:
    """Atomic replace -- a half-written ledger read by the next request
    would parse as corrupt and silently reset every count."""
    cutoff = (_dt.date.fromisoformat(_today())
              - _dt.timedelta(days=_KEEP_DAYS)).isoformat()
    data = {"days": {d: v for d, v in (data.get("days") or {}).items()
                     if d >= cutoff},
            "conversations": data.get("conversations") or {}}
    try:
        target = _ledger()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, target)
    except Exception as e:  # noqa: BLE001 -- must never fail a booking
        log.error("could not write booking quota ledger: %s", e)


def check(email: str, conversation_id: "Optional[str]" = None) -> Verdict:
    """May this booking proceed? Called immediately before the write.

    FAILS OPEN. If the ledger cannot be read, a student trying to book one
    room is not turned away — the whole point of the cap is to stop bulk
    abuse, and bulk abuse needs many successful writes, which will be
    visible in LibCal and in the alerts either way.
    """
    addr = (email or "").strip().lower()
    data = _load()
    day = (data.get("days") or {}).get(_today(), {})
    used_email = int(day.get(addr, 0)) if addr else 0
    if addr and used_email >= MAX_PER_EMAIL_PER_DAY:
        return Verdict(False, (
            f"That address has already reserved {used_email} rooms through me "
            f"today, which is the daily limit here. You can still book "
            f"directly at muohio.libcal.com, or ask a librarian through "
            f"Ask Us if you need more than that."
        ))
    if conversation_id:
        used_conv = int((data.get("conversations") or {}).get(conversation_id, 0))
        if used_conv >= MAX_PER_CONVERSATION:
            return Verdict(False, (
                f"I've already booked {used_conv} rooms in this conversation, "
                f"which is as many as I do at once. Start a new chat for "
                f"another, or book directly at muohio.libcal.com."
            ))
    return Verdict(True)


def record(email: str, conversation_id: "Optional[str]" = None) -> None:
    """Count a booking that actually succeeded.

    Called AFTER the write, never before: counting an attempt would let a
    LibCal outage burn a student's daily allowance.
    """
    addr = (email or "").strip().lower()
    data = _load()
    days = data.setdefault("days", {})
    day = days.setdefault(_today(), {})
    if addr:
        day[addr] = int(day.get(addr, 0)) + 1
    if conversation_id:
        convs = data.setdefault("conversations", {})
        convs[conversation_id] = int(convs.get(conversation_id, 0)) + 1
    _save(data)
    log.info("booking recorded: %s (today=%s) conv=%s",
             addr or "(no email)", day.get(addr), conversation_id or "-")


def usage_today() -> dict:
    """{email: count} for today -- for the report and for debugging."""
    return dict((_load().get("days") or {}).get(_today(), {}))
