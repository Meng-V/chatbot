"""
Springshare API observability -- one place for *seeing* what the bot's
LibCal / LibGuides / LibAnswers calls are doing.

Two jobs:

  1. `log_api_call(...)` / `log_token(...)` -- uniform, greppable console
     lines for every Springshare request and OAuth-token fetch, so when
     the APIs get flaky you can watch status, latency, retries and errors
     scroll by in the backend console. Every line is tagged
     `[Springshare:<Service>]` so `grep Springshare` (or a per-service
     `grep 'Springshare:LibCal'`) isolates the traffic.

  2. `check_springshare_health()` -- a pre-flight probe of each Springshare
     service (OAuth token round-trip, plus a cheap LibCal hours GET when
     configured). Called from the app startup lifespan BEFORE the bot
     serves traffic, and reusable by /health/ready. It never raises:
     live Springshare data has graceful degradation in the bot, so a
     down service is a loud WARN at boot, not a failed startup.

Secrets (client_secret, tokens, any `?...secret=`/`?...token=` query
value) are redacted before anything is logged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger("springshare")

# Canonical service labels -- keep these stable; they're what operators grep.
LIBCAL = "LibCal"
LIBGUIDES = "LibGuides"
LIBANSWERS = "LibAnswers"

_SECRET_QUERY_KEYS = re.compile(
    r"(client_secret|secret|access_token|token|key|password)=([^&\s]+)",
    re.IGNORECASE,
)


def _redact(text: Optional[str]) -> str:
    """Mask secret-looking query values so URLs are safe to log."""
    if not text:
        return ""
    return _SECRET_QUERY_KEYS.sub(lambda m: f"{m.group(1)}=***", str(text))


def _short_url(url: str) -> str:
    """`https://muohio.libcal.com/api/1.1/space/1234/availability?x=1`
    -> `muohio.libcal.com/api/1.1/space/1234/availability` (no query)."""
    try:
        p = urlparse(url)
        path = p.path or ""
        return _redact(f"{p.netloc}{path}")
    except Exception:
        return _redact(url)


def log_api_call(
    service: str,
    method: str,
    url: str,
    *,
    status: Optional[int] = None,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
    attempt: Optional[str] = None,  # e.g. "2/3"
    note: Optional[str] = None,
) -> None:
    """Log one Springshare API request outcome on a single console line.

    Pass `error` for failures (logged at WARNING), otherwise it's an
    INFO success line. `attempt` surfaces retry context.
    """
    bits = [f"{method.upper()} {_short_url(url)}"]
    if attempt:
        bits.append(f"attempt {attempt}")
    if status is not None:
        bits.append(f"-> HTTP {status}")
    if latency_ms is not None:
        bits.append(f"in {latency_ms}ms")
    if note:
        bits.append(_redact(note))
    body = " ".join(bits)

    if error:
        logger.warning("⚠️ [Springshare:%s] %s | ERROR: %s",
                       service, body, _redact(error))
    else:
        ok = status is None or status < 400
        emoji = "📡" if ok else "⚠️"
        logfn = logger.info if ok else logger.warning
        logfn("%s [Springshare:%s] %s", emoji, service, body)


def log_token(
    service: str,
    *,
    ok: bool,
    latency_ms: Optional[int] = None,
    expires_in: Optional[int] = None,
    cached: bool = False,
    error: Optional[str] = None,
) -> None:
    """Log an OAuth token fetch/refresh for a Springshare service."""
    if cached:
        logger.debug("🔑 [Springshare:%s] token cache hit", service)
        return
    suffix = []
    if latency_ms is not None:
        suffix.append(f"in {latency_ms}ms")
    if expires_in is not None:
        suffix.append(f"expires_in={expires_in}s")
    tail = (" " + " ".join(suffix)) if suffix else ""
    if ok:
        logger.info("✅ [Springshare:%s] OAuth token OK%s", service, tail)
    else:
        logger.warning("❌ [Springshare:%s] OAuth token FAILED%s | %s",
                       service, tail, _redact(error))


# --- Pre-flight health check ---------------------------------------------


@dataclass
class ServiceHealth:
    service: str
    ok: bool
    latency_ms: Optional[int] = None
    detail: Optional[str] = None
    configured: bool = True
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"service": self.service, "ok": self.ok,
                             "configured": self.configured}
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        if self.detail:
            d["detail"] = self.detail
        if self.extras:
            d["extras"] = self.extras
        return d


async def _probe_oauth(service: str, token_getter, *, timeout: float) -> ServiceHealth:
    """Time an OAuth token round-trip. A successful token proves creds +
    network + Springshare auth are all working for that product."""
    start = time.monotonic()
    try:
        token = await asyncio.wait_for(token_getter(), timeout=timeout)
        ms = int((time.monotonic() - start) * 1000)
        if not token:
            return ServiceHealth(service, False, ms, "empty token returned")
        return ServiceHealth(service, True, ms)
    except asyncio.TimeoutError:
        ms = int((time.monotonic() - start) * 1000)
        return ServiceHealth(service, False, ms, f"timeout (>{timeout:.0f}s)")
    except ValueError as e:
        # Raised by the OAuth services when creds aren't configured.
        return ServiceHealth(service, False, None,
                             f"not configured: {e}", configured=False)
    except Exception as e:  # noqa: BLE001
        ms = int((time.monotonic() - start) * 1000)
        return ServiceHealth(service, False, ms,
                             f"{type(e).__name__}: {str(e)[:140]}")


async def _probe_libcal_hours(timeout: float) -> Optional[ServiceHealth]:
    """Optional cheap real call: GET the LibCal hours endpoint. Only runs
    if LIBCAL_HOUR_URL is configured. Exercises the data path, not just
    auth."""
    hour_url = os.getenv("LIBCAL_HOUR_URL", "")
    if not hour_url:
        return None
    import httpx
    from src.services.libcal_oauth import get_libcal_oauth_service

    start = time.monotonic()
    try:
        token = await asyncio.wait_for(
            get_libcal_oauth_service().get_token(), timeout=timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                hour_url, headers={"Authorization": f"Bearer {token}"})
        ms = int((time.monotonic() - start) * 1000)
        sc = resp.status_code
        # Reachability, not correctness: the real call is
        # `{LIBCAL_HOUR_URL}/{location_id}`, so this bare URL legitimately
        # 404s -- which still proves the server answered. Only auth
        # (401/403) and server faults (5xx)/timeouts are real outages.
        ok = sc != 401 and sc != 403 and sc < 500
        detail = None if ok else f"HTTP {sc}"
        if ok and sc >= 400:
            detail = f"reachable (HTTP {sc} on bare URL, expected without a location id)"
        return ServiceHealth(
            f"{LIBCAL}/hours", ok, ms, detail, extras={"status": sc},
        )
    except Exception as e:  # noqa: BLE001
        ms = int((time.monotonic() - start) * 1000)
        return ServiceHealth(f"{LIBCAL}/hours", False, ms,
                             f"{type(e).__name__}: {str(e)[:140]}")


async def check_springshare_health(
    *, timeout: float = 6.0, include_hours: bool = True,
) -> list[ServiceHealth]:
    """Probe every Springshare service and log a pre-flight banner.

    Returns the per-service results (also usable by /health/ready).
    Never raises -- a down service degrades the bot's live data, it
    doesn't crash startup.
    """
    from src.services.libapps_oauth import get_libapps_oauth_service
    from src.services.libcal_oauth import get_libcal_oauth_service

    probes = [
        _probe_oauth(LIBCAL, get_libcal_oauth_service().get_token, timeout=timeout),
        _probe_oauth(LIBGUIDES, get_libapps_oauth_service().get_token, timeout=timeout),
    ]
    results = list(await asyncio.gather(*probes, return_exceptions=False))

    if include_hours:
        hours = await _probe_libcal_hours(timeout)
        if hours is not None:
            results.append(hours)

    _log_health_banner(results)
    return results


def _log_health_banner(results: list[ServiceHealth]) -> None:
    """Print a compact, scannable pre-flight summary."""
    logger.info("🛫 [Springshare] pre-flight health check:")
    any_down = False
    for r in results:
        if r.ok:
            lat = f" ({r.latency_ms}ms)" if r.latency_ms is not None else ""
            note = f" -- {r.detail}" if r.detail else ""
            logger.info("   ✅ %s reachable%s%s", r.service, lat, note)
        elif not r.configured:
            logger.warning("   ⚪ %s NOT CONFIGURED -- %s", r.service, r.detail)
        else:
            any_down = True
            lat = f" ({r.latency_ms}ms)" if r.latency_ms is not None else ""
            logger.warning("   ❌ %s DOWN%s -- %s", r.service, lat, r.detail)
    if any_down:
        logger.warning(
            "⚠️ [Springshare] one or more services are DOWN. The bot will "
            "still start; live hours/rooms/guides answers will degrade "
            "until they recover."
        )
    else:
        logger.info("✅ [Springshare] all configured services reachable.")


__all__ = [
    "LIBANSWERS",
    "LIBCAL",
    "LIBGUIDES",
    "ServiceHealth",
    "check_springshare_health",
    "log_api_call",
    "log_token",
]
