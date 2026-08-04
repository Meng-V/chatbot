"""
Operator alerts for the three things the operator told colleagues we watch.

    (1) server crashes / API connection failures  -- already handled by
        `main._health_alert_watcher`; not duplicated here.
    (2) thumbs-down, or a 1-2 star conversation rating.
    (3) suspicious activity: abuse of the rate limiter, or a message that
        looks like an attempt to talk the bot out of its instructions.

WHO GETS THESE, AND WHEN (revised 2026-08-04 for the handover)
    Two tiers, because handing somebody 30-50 emails a day guarantees they
    build a filter rule and stop reading. That is worse than not adding
    them, since everyone then believes it is being watched.

      URGENT   -- something needs a person: the service or a dependency is
                  down, or the monthly budget is exhausted. Sent
                  immediately to `ALERT_EMAIL_TO_URGENT` (the operator plus
                  whoever is covering). Falls back to ALERT_EMAIL_TO when
                  unset, so nothing changes until that variable is set.

      DIGEST   -- worth reading, not worth waking for: a thumbs-down, an
                  injection attempt that was refused, a rate-limit trip, a
                  low rating. Appended to a queue and mailed as ONE message
                  by scripts/alert_digest.py.

    The commitment made to colleagues was that suspicious activity reaches
    us -- not that it pages us. A daily count of injection attempts is more
    useful than thirty separate emails, each of which says the bot
    correctly refused something.

    NOTHING here pages anyone overnight. The bot is promoted after hours,
    when nobody is on duty; its failure mode is a refusal plus a pointer to
    Ask Us, the budget throttles itself, and the kill switch can wait until
    morning. Whoever covers the handover is not on a night shift.

NEVER BLOCK A TURN
    Every function here is best-effort. A patron's answer must not depend on
    an SMTP handshake, so failures log and return.

RATE-LIMITED BY DESIGN
    A hostile session can emit hundreds of matching events. Each alert KIND
    is capped per window (`_MIN_GAP_SECONDS`), and the mail says how many
    were suppressed, so a burst produces one useful message instead of a
    hundred that get filtered to trash.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# One alert per kind per this many seconds. 15 minutes is short enough that a
# real incident is noticed promptly and long enough that a burst collapses.
_MIN_GAP_SECONDS = float(os.getenv("ALERT_MIN_GAP_SECONDS", "900"))

# A conversation rating at or below this is "low" per the operator's note to
# colleagues ("1-2 star").
LOW_RATING_MAX = 2

_lock = threading.Lock()
_last_sent: dict[str, float] = {}
_suppressed: dict[str, int] = {}


def _should_send(kind: str) -> tuple[bool, int]:
    """(send_now, how_many_were_suppressed_since_the_last_send)."""
    now = time.monotonic()
    with _lock:
        last = _last_sent.get(kind)
        if last is not None and (now - last) < _MIN_GAP_SECONDS:
            _suppressed[kind] = _suppressed.get(kind, 0) + 1
            return False, _suppressed[kind]
        held = _suppressed.pop(kind, 0)
        _last_sent[kind] = now
        return True, held


# Kinds that need a person, and therefore go out at once to the wider list.
# Everything else is queued for the daily digest. Keep this set SMALL: its
# whole value is that a message from it is worth interrupting someone for.
URGENT_KINDS = frozenset({
    "health",          # the service or a dependency is down
    "budget_exhausted",  # the monthly student purse is spent; students are
                         # being turned away
})

DIGEST_PATH = Path(
    os.getenv("ALERT_DIGEST_PATH", "/opt/chatbot/data/alert_digest.jsonl")
)


def urgent_recipients() -> "str | None":
    """The wider list, or None to use the default single recipient."""
    return (os.getenv("ALERT_EMAIL_TO_URGENT") or "").strip() or None


def _queue_for_digest(kind: str, subject: str, body: str) -> bool:
    """Append to the digest queue. Returns True when queued."""
    try:
        DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DIGEST_PATH.open("a") as fh:
            fh.write(json.dumps({
                "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "kind": kind, "subject": subject, "body": body,
            }) + "\n")
        return True
    except Exception as e:  # noqa: BLE001 -- must never break a turn
        logger.error("could not queue %s for the digest: %s", kind, e)
        return False


def _send(kind: str, subject: str, body: str) -> bool:
    ok, held = _should_send(kind)
    if not ok:
        logger.info("alert %s suppressed (%d held in this window)", kind, held)
        return False
    if held:
        body += (f"\n\n{held} further {kind} event(s) occurred in the last "
                 f"{int(_MIN_GAP_SECONDS // 60)} minutes and were folded into "
                 f"this one message.")
    if kind not in URGENT_KINDS:
        queued = _queue_for_digest(kind, subject, body)
        logger.info("alert %s %s for the daily digest", kind,
                    "queued" if queued else "NOT queued")
        return queued
    try:
        from src.observability.alerting import send_alert_email

        return bool(send_alert_email(subject, body, to=urgent_recipients()))
    except Exception as e:  # noqa: BLE001 -- alerting must never break a turn
        logger.error("could not send %s alert: %s", kind, e)
        return False


# --- (2) negative feedback -------------------------------------------------


def alert_thumbs_down(*, message_id: str, question: str, answer: str,
                      conversation_id: str = "") -> bool:
    """A patron marked one answer as bad. Includes the QUESTION, because the
    answer alone never tells you what went wrong."""
    return _send(
        "thumbs-down",
        "[chatbot] a patron marked an answer as unhelpful",
        f"Someone gave a thumbs-down. The question is what matters here:\n\n"
        f"  asked:  {(question or '(not captured)')[:600]}\n\n"
        f"  answered: {(answer or '(not captured)')[:900]}\n\n"
        f"  message id:      {message_id}\n"
        f"  conversation id: {conversation_id or '(unknown)'}\n\n"
        f"Review it at /admin/review (filter: thumbs_down). If the answer is "
        f"wrong and the fix is content, a manual correction takes effect on "
        f"the next message with no deploy.",
    )


def alert_low_rating(*, conversation_id: str, rating: int,
                     comment: str = "") -> bool:
    """End-of-conversation rating of 1-2 stars."""
    return _send(
        "low-rating",
        f"[chatbot] a conversation was rated {rating}/5",
        f"A patron rated a whole conversation {rating} out of 5.\n\n"
        f"  their comment: {(comment or '(none left)')[:900]}\n"
        f"  conversation id: {conversation_id}\n\n"
        f"Read the transcript at /admin/review (filter: rated).",
    )


# --- (3) suspicious activity ----------------------------------------------

# Phrases whose only purpose is to get the bot to abandon its instructions.
# Deliberately narrow: this decides whether to EMAIL THE OPERATOR, so a false
# positive costs their attention. It does not block anything -- the refusal
# machinery and the rate limiter do that independently of this.
_INJECTION_PATTERNS = (
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|the)\s+instructions",
    r"disregard\s+(?:all\s+|your\s+)?(?:previous|prior|the)\s+(?:instructions|rules|prompt)",
    # Requires the POSSESSIVE ("your ...") or the unambiguous "the system
    # prompt". Allowing a bare "the" made "Show me the rules for interlibrary
    # loan" -- an ordinary borrowing question -- email the operator, which a
    # test caught before this shipped.
    r"(?:reveal|show|print|repeat|output|dump)\s+(?:me\s+)?your\s+"
    r"(?:system\s+)?(?:prompt|instructions|rules|configuration)",
    r"(?:reveal|show|print|repeat|output|dump)\s+(?:me\s+)?the\s+system\s+"
    r"(?:prompt|instructions|message)",
    # "the instructions you were given" -- possessive by construction
    r"(?:prompt|instructions|rules)\s+(?:that\s+)?you\s+(?:were\s+given|"
    r"received|are\s+following|got)",
    r"you\s+are\s+now\s+(?:a|an|in)\b.{0,40}\bmode\b",
    r"\bDAN\b\s+mode",
    r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a\s+)?(?:different|another)\b",
    r"(?:api|openai)[\s_-]?key",
    r"\.env\b|DATABASE_URL|ADMIN_API_TOKEN",
    r"\b(?:drop|delete)\s+table\b|\bunion\s+select\b|';\s*--",
)
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def looks_like_injection(message: str) -> str | None:
    """The matched phrase, or None. Public so it can be unit-tested against
    both attacks and the ordinary questions that must NOT trip it."""
    if not message:
        return None
    m = _INJECTION_RE.search(message)
    return m.group(0) if m else None


def alert_suspicious_message(*, message: str, matched: str,
                             client_key: str = "") -> bool:
    return _send(
        "injection",
        "[chatbot] a message looked like a prompt-injection attempt",
        f"A message matched a pattern associated with trying to override the "
        f"bot's instructions or extract its configuration.\n\n"
        f"  matched:  {matched!r}\n"
        f"  message:  {(message or '')[:600]}\n"
        f"  client:   {client_key or '(unknown)'}\n\n"
        f"NOTHING WAS BLOCKED BY THIS ALERT -- it is a notification only. The "
        f"bot's own grounding rules are what stop it answering from anything "
        f"but retrieved evidence, and the rate limiter is what stops volume.\n\n"
        f"If this is a real probe rather than a curious student, consider "
        f"whether the pattern list needs tightening.",
    )


def alert_rate_limit_abuse(*, client_key: str, hits: int,
                           window_seconds: int) -> bool:
    """The rate limiter tripped repeatedly for one client -- i.e. someone is
    hammering, not just clicking fast."""
    return _send(
        "rate-abuse",
        "[chatbot] one client is hitting the rate limit repeatedly",
        f"A single client tripped the message rate limit {hits} times within "
        f"{window_seconds}s.\n\n"
        f"  client: {client_key}\n\n"
        f"The limiter is already refusing the excess traffic, so this is a "
        f"heads-up rather than an outage. If it continues, the next step is a "
        f"block at the proxy or WAF layer, which needs infrastructure access.",
    )


__all__ = [
    "LOW_RATING_MAX",
    "alert_low_rating",
    "alert_rate_limit_abuse",
    "alert_suspicious_message",
    "alert_thumbs_down",
    "looks_like_injection",
]
