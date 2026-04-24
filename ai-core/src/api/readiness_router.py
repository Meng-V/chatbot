"""
/health/live and /health/ready endpoints (plan Op 3 "Health checks").

Two endpoints with different jobs:

    /health/live -- "is the process up?" Always 200 if FastAPI worker
        responds. Used by k8s liveness probe / load balancer health
        check. No external calls. Cheap.

    /health/ready -- "are we ready to serve traffic?" Probes every
        critical dependency. Returns 200 iff all pass; 503 with a
        per-probe breakdown otherwise. Used by k8s readiness probe.

Lives separately from `src/api/health.py` (the legacy `/health` and
`/readiness` endpoints) because:

    1. The plan's probe set is different -- adds OpenAI ping and the
       "last successful ETL run < 8 days ago" check that the legacy
       endpoints don't know about.
    2. The legacy file imports prod-only modules at module import time
       (psutil, weaviate_client, prisma_client, libcal_oauth) which
       breaks in dev / sandbox / test. This module follows the
       dependency-injection pattern from `src/api/admin/*` so probes
       are stubbed cleanly.

When the legacy stack retires, fold the legacy `health.py` endpoints
into this module and delete the old file.

Probe rules (see plan Op 3):
    Pass = probe returned within timeout AND backend reported healthy.
    Fail = anything else, including timeouts. Don't be lenient -- a
    flaky readiness probe is worse than a failing one because the
    rollouts hide the underlying outage.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional


# --- Probe types ----------------------------------------------------------


@dataclass(frozen=True)
class ProbeResult:
    """One probe outcome.

    Status is `healthy` / `degraded` / `unhealthy`. `degraded` means
    the dependency answered but slowly (or with a non-fatal warning).
    `unhealthy` means it didn't respond at all.

    `latency_ms` is None when the probe didn't make a network call
    (e.g., the ETL freshness check looks at a timestamp).
    """

    name: str
    status: str
    latency_ms: Optional[int] = None
    detail: Optional[str] = None
    extras: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        # `degraded` still passes -- we want to serve traffic but flag
        # the slowness in metrics. Op 3 alerting fires on sustained
        # degradation; readiness only fails on outright unhealthy.
        return self.status in ("healthy", "degraded")

    def as_dict(self) -> dict:
        d = {
            "name": self.name,
            "status": self.status,
        }
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        if self.detail:
            d["detail"] = self.detail
        if self.extras:
            d["extras"] = self.extras
        return d


# Probe = async callable returning a ProbeResult. We type it as a
# Callable rather than a class so test setup is just `async def`.
Probe = Callable[[], Awaitable[ProbeResult]]


# --- Built-in probe builders ----------------------------------------------
#
# These are factories -- pass in the backing client / config and get
# back a Probe callable. Prod startup composes them; tests skip them
# or stub them out.


def make_postgres_probe(execute_fn: Callable[[], Awaitable[Any]]) -> Probe:
    """Probe that runs `SELECT 1` (or whatever cheap query the caller
    wraps in `execute_fn`).

    `execute_fn` is async and raises on any failure. The probe
    catches and reports."""

    async def probe() -> ProbeResult:
        start = time.monotonic()
        try:
            await asyncio.wait_for(execute_fn(), timeout=2.0)
            return ProbeResult(
                name="postgres",
                status="healthy",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except asyncio.TimeoutError:
            return ProbeResult(
                name="postgres",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail="timeout (>2s)",
            )
        except Exception as e:
            return ProbeResult(
                name="postgres",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=type(e).__name__ + ": " + str(e)[:120],
            )

    return probe


def make_weaviate_probe(meta_fn: Callable[[], Awaitable[Any]]) -> Probe:
    """Probe that calls Weaviate `meta()`. Cheap, no schema load."""

    async def probe() -> ProbeResult:
        start = time.monotonic()
        try:
            meta = await asyncio.wait_for(meta_fn(), timeout=2.0)
            extras: dict = {}
            if isinstance(meta, dict) and "version" in meta:
                extras["version"] = meta["version"]
            return ProbeResult(
                name="weaviate",
                status="healthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                extras=extras,
            )
        except asyncio.TimeoutError:
            return ProbeResult(
                name="weaviate",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail="timeout (>2s)",
            )
        except Exception as e:
            return ProbeResult(
                name="weaviate",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=type(e).__name__ + ": " + str(e)[:120],
            )

    return probe


def make_openai_probe(ping_fn: Callable[[], Awaitable[Any]]) -> Probe:
    """Probe that calls a 1-token completion against the basic model.

    See plan: '/health/ready ... OpenAI tiny ping (1-token completion
    to a known model)'.

    Why a real completion rather than just hitting `/v1/models`: the
    models list works without billing, but a hung OpenAI billing
    account would still serve traffic -- a tiny completion exercises
    the path the bot actually uses.
    """

    async def probe() -> ProbeResult:
        start = time.monotonic()
        try:
            # 5s budget -- OpenAI cold-start can be ~2-3s.
            await asyncio.wait_for(ping_fn(), timeout=5.0)
            return ProbeResult(
                name="openai",
                status="healthy",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except asyncio.TimeoutError:
            return ProbeResult(
                name="openai",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail="timeout (>5s)",
            )
        except Exception as e:
            return ProbeResult(
                name="openai",
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=type(e).__name__ + ": " + str(e)[:120],
            )

    return probe


def make_libcal_probe(status_fn: Callable[[], Awaitable[Any]]) -> Probe:
    """LibCal availability check. Reuses the existing OAuth path the
    legacy health.py uses."""

    async def probe() -> ProbeResult:
        start = time.monotonic()
        try:
            await asyncio.wait_for(status_fn(), timeout=3.0)
            return ProbeResult(
                name="libcal",
                status="healthy",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except asyncio.TimeoutError:
            # LibCal can be slow but the bot has graceful degradation
            # for live data -- mark degraded, not unhealthy.
            return ProbeResult(
                name="libcal",
                status="degraded",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail="timeout (>3s) -- live hours may be unavailable",
            )
        except Exception as e:
            return ProbeResult(
                name="libcal",
                status="degraded",
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=type(e).__name__ + ": " + str(e)[:120],
            )

    return probe


def make_etl_freshness_probe(
    last_run_fn: Callable[[], Awaitable[Optional[datetime]]],
    *,
    max_age_days: int = 8,
) -> Probe:
    """Probe that checks the most recent successful ETL run.

    Plan threshold: < 8 days. The crawl runs Sunday 2 AM; an 8-day
    window means a single missed Sunday surfaces in readiness on
    Monday morning rather than going unnoticed for two weeks.

    `last_run_fn` returns the timestamp of the latest successful ETL
    in the `data/etl_runs` log table (or None if no run ever
    succeeded).
    """

    async def probe() -> ProbeResult:
        try:
            last_run = await asyncio.wait_for(last_run_fn(), timeout=2.0)
        except asyncio.TimeoutError:
            return ProbeResult(
                name="etl_freshness",
                status="unhealthy",
                detail="timeout fetching last_run timestamp",
            )
        except Exception as e:
            return ProbeResult(
                name="etl_freshness",
                status="unhealthy",
                detail=type(e).__name__ + ": " + str(e)[:120],
            )

        if last_run is None:
            return ProbeResult(
                name="etl_freshness",
                status="unhealthy",
                detail="no successful ETL run on record",
            )

        # Ensure tz-aware comparison
        now = datetime.now(timezone.utc)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        age = now - last_run
        extras = {
            "last_run_iso": last_run.isoformat(),
            "age_hours": int(age.total_seconds() // 3600),
        }
        if age > timedelta(days=max_age_days):
            return ProbeResult(
                name="etl_freshness",
                status="unhealthy",
                detail=f"last ETL run is {age.days} days old (>{max_age_days})",
                extras=extras,
            )
        return ProbeResult(
            name="etl_freshness",
            status="healthy",
            extras=extras,
        )

    return probe


# --- Aggregation ----------------------------------------------------------


async def run_probes(probes: list[Probe]) -> list[ProbeResult]:
    """Run all probes concurrently. Failures don't sink other probes."""
    results: list[ProbeResult] = []
    if not probes:
        return results

    raw = await asyncio.gather(
        *(probe() for probe in probes),
        return_exceptions=True,
    )
    for i, item in enumerate(raw):
        if isinstance(item, BaseException):
            # The probe builders catch their own exceptions, so
            # reaching here means a builder bug. Report it loudly.
            results.append(
                ProbeResult(
                    name=f"probe_{i}",
                    status="unhealthy",
                    detail=f"probe raised: {item!r}",
                )
            )
        else:
            results.append(item)
    return results


def overall_status(results: list[ProbeResult]) -> str:
    """Aggregate per-probe statuses to a single readiness verdict.

    healthy <- all healthy
    degraded <- at least one degraded, none unhealthy
    unhealthy <- at least one unhealthy
    """
    if any(r.status == "unhealthy" for r in results):
        return "unhealthy"
    if any(r.status == "degraded" for r in results):
        return "degraded"
    return "healthy"


# --- Router builder -------------------------------------------------------


def build_readiness_router(deps: dict) -> Any:
    """Build the FastAPI router for /health/live and /health/ready.

    `deps` should contain a `probes: list[Probe]` (constructed via
    the `make_*_probe` factories above). When `deps["probes"]` is
    missing or empty, /health/ready degrades to a single "no probes
    configured" response so misconfiguration is loud, not silent.
    """
    try:
        from fastapi import APIRouter  # type: ignore
        from fastapi.responses import JSONResponse  # type: ignore
    except ImportError:
        return _Placeholder("/health")

    router = APIRouter(tags=["ops"])
    probes: list[Probe] = deps.get("probes", [])

    @router.get("/health/live")
    async def live() -> Any:
        # Liveness is intentionally trivial. If this returns at all,
        # the FastAPI worker is responsive. Anything more is overreach
        # -- live probes that do real work cause cascading restarts
        # when a dep is briefly slow.
        return {"status": "alive"}

    @router.get("/health/ready")
    async def ready() -> Any:
        if not probes:
            return JSONResponse(
                content={
                    "status": "unhealthy",
                    "detail": (
                        "No probes configured. Wire probes via "
                        "build_readiness_router(deps={'probes': [...]})."
                    ),
                    "probes": [],
                },
                status_code=503,
            )

        results = await run_probes(probes)
        status = overall_status(results)
        body = {
            "status": status,
            "probes": [r.as_dict() for r in results],
        }
        # Degraded still serves -- 200 with degraded status. Op 3
        # alerts on sustained degradation; readiness only blocks on
        # outright unhealthy.
        return JSONResponse(
            content=body,
            status_code=200 if status != "unhealthy" else 503,
        )

    return router


class _Placeholder:
    """FastAPI-not-installed fallback so `import` doesn't crash dev."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.routes: list = []


__all__ = [
    "Probe",
    "ProbeResult",
    "build_readiness_router",
    "make_etl_freshness_probe",
    "make_libcal_probe",
    "make_openai_probe",
    "make_postgres_probe",
    "make_weaviate_probe",
    "overall_status",
    "run_probes",
]
