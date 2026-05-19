"""
Abuse / cost guard for the public chat entry points (HTTP /ask and the
Socket.IO `message` event).

WHY: the bot is intentionally unauthenticated (a public library
assistant). With no auth, the only thing standing between a scripted
client and an unbounded OpenAI bill / DoS is input validation + rate
limiting -- and an audit (2026-05-18) confirmed there was NONE: a
single client could open many sockets, send arbitrarily large
messages, and spam turns, each one hitting `library_graph.ainvoke`
(real OpenAI spend). This directly threatens the (currently
exhausted) API budget, so it's the highest-value security item.

DESIGN -- deliberately dependency-free and in-process:
  * slowapi/fastapi-limiter need Redis and don't cover Socket.IO.
    The plan explicitly scopes this app to single-digit RPS with
    singleton clients, so a tiny in-memory sliding-window limiter is
    the right tool. (Multi-worker note: limits are PER WORKER. With
    one uvicorn worker that's exact; with N workers the effective
    limit is N x -- still a massive reduction vs. none. A shared
    Redis limiter is future work for horizontal scale, flagged not
    built.)
  * FAIL-OPEN: any internal error in the limiter must allow the
    request, never 500 the bot. A telemetry guard must not become an
    availability bug. (The opposite of the service guard, which
    fail-closes -- different risk: there, a wrong answer; here, a
    denied legitimate user.)

All limits are env-tunable with conservative defaults; a normal
library question is < 1 KB and a human sends a handful per minute.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque


def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, "").strip() or default)
        return v if v > 0 else default
    except (ValueError, TypeError):
        return default


# A library question is short. 4000 chars is ~1000 tokens -- generous
# for any real question; longer is a paste-bomb / token-burn attempt.
MAX_MESSAGE_CHARS = _int_env("CHAT_MAX_MESSAGE_CHARS", 4000)
# Sliding window: at most MAX msgs per WINDOW seconds per client key.
RATE_MAX = _int_env("CHAT_RATE_MAX", 20)
RATE_WINDOW_S = _int_env("CHAT_RATE_WINDOW_S", 60)
# Hard ceiling on turns in one conversation -- stops a single
# conversation from being driven forever.
MAX_TURNS_PER_CONVERSATION = _int_env("CHAT_MAX_TURNS_PER_CONVERSATION", 80)


class SlidingWindowLimiter:
    """In-memory sliding-window counter. asyncio-single-threaded, so
    no lock needed. Keys are evicted lazily as they age out, so memory
    is bounded by the number of ACTIVE clients in the last window."""

    def __init__(self, max_events: int, window_s: int) -> None:
        self.max_events = max_events
        self.window_s = window_s
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """True if `key` is under the limit (and records the hit).
        False if it should be throttled."""
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_s
        q = self._hits[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.max_events:
            if not q:                       # pragma: no cover - defensive
                del self._hits[key]
            return False
        q.append(now)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# Module-level singletons -- one process-wide limiter per surface.
_chat_limiter = SlidingWindowLimiter(RATE_MAX, RATE_WINDOW_S)


class MessageRejected(Exception):
    """Raised by `validate_message` with a user-safe reason + the
    wire-appropriate code (HTTP status / socket error kind)."""

    def __init__(self, reason: str, *, code: int = 400) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


def validate_message(raw: object) -> str:
    """Coerce + bound a user message. Returns the cleaned string or
    raises MessageRejected. Does NOT trust type, size, or emptiness."""
    if not isinstance(raw, str):
        raise MessageRejected("Message must be text.", code=400)
    text = raw.strip()
    if not text:
        raise MessageRejected("Message is empty.", code=400)
    if len(text) > MAX_MESSAGE_CHARS:
        raise MessageRejected(
            f"Message too long ({len(text)} chars; limit "
            f"{MAX_MESSAGE_CHARS}). Please shorten your question.",
            code=413,
        )
    return text


def check_rate(client_key: str) -> None:
    """Raise MessageRejected(429) if `client_key` is over the rate.
    FAIL-OPEN: a limiter bug must not deny a legitimate user."""
    try:
        if not _chat_limiter.allow(client_key or "unknown"):
            raise MessageRejected(
                "You're sending messages too quickly. Please wait a "
                "few seconds and try again.",
                code=429,
            )
    except MessageRejected:
        raise
    except Exception:  # noqa: BLE001 -- never let the guard 500 the bot
        return


def conversation_turn_exceeded(turn_count: int) -> bool:
    """True if this conversation has hit the hard turn ceiling."""
    return turn_count >= MAX_TURNS_PER_CONVERSATION


def client_ip_from_request(request) -> str:
    """Best-effort client IP for HTTP. The bot sits behind the Miami
    reverse proxy, so honor X-Forwarded-For's FIRST hop; fall back to
    the socket peer. Never raises."""
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return getattr(getattr(request, "client", None), "host", "") or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


__all__ = [
    "MAX_MESSAGE_CHARS",
    "MAX_TURNS_PER_CONVERSATION",
    "MessageRejected",
    "SlidingWindowLimiter",
    "check_rate",
    "client_ip_from_request",
    "conversation_turn_exceeded",
    "validate_message",
]
