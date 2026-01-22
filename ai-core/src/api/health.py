"""Health, Readiness, and Metrics endpoints for monitoring."""

import os
import psutil
import time
import httpx
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.weaviate_client import get_weaviate_client, get_weaviate_url
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
from src.database.prisma_client import get_prisma_client
from src.services.libcal_oauth import get_libcal_oauth_service
from src.services.libapps_oauth import get_libapps_oauth_service

router = APIRouter()

# Application start time
START_TIME = time.time()


async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and response time."""
    try:
        start = time.time()
        prisma = get_prisma_client()

        if not prisma.is_connected():
            await prisma.connect()

        # Simple query to test connection
        await prisma.conversation.count()

        response_time = int((time.time() - start) * 1000)  # ms

        return {"status": "healthy", "responseTime": response_time}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def check_memory_health() -> Dict[str, Any]:
    """Check memory usage."""
    memory = psutil.virtual_memory()
    process = psutil.Process()
    process_memory = process.memory_info()

    # Memory usage in MB
    used_mb = process_memory.rss / 1024 / 1024
    total_mb = memory.total / 1024 / 1024

    # Consider unhealthy if using > 80% of available memory or > 1GB
    threshold_mb = min(total_mb * 0.8, 1024)
    is_healthy = used_mb < threshold_mb

    return {
        "status": "healthy" if is_healthy else "warning",
        "used": int(used_mb),
        "total": int(total_mb),
        "external": int(process_memory.vms / 1024 / 1024),  # Virtual memory
    }


def check_environment_health() -> Dict[str, Any]:
    """Check required environment variables."""
    required_vars = ["OPENAI_API_KEY", "DATABASE_URL", "WEAVIATE_HOST"]

    missing = [var for var in required_vars if not os.getenv(var)]

    return {
        "status": "healthy" if not missing else "unhealthy",
        "missingVariables": missing,
    }


async def check_openai_health() -> Dict[str, Any]:
    """Check OpenAI API connectivity with actual API call."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unconfigured", "error": "OPENAI_API_KEY not set"}

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response_time = int((time.time() - start) * 1000)

            if response.status_code == 200:
                return {"status": "healthy", "responseTime": response_time}
            else:
                return {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}",
                    "responseTime": response_time,
                }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_weaviate_health() -> Dict[str, Any]:
    """Check Weaviate connectivity using centralized client factory (v4 API)."""
    host = os.getenv("WEAVIATE_HOST", "")
    if not host:
        return {"status": "unconfigured", "error": "WEAVIATE_HOST not set"}

    try:
        start = time.time()
        
        # Use centralized client factory
        client = get_weaviate_client()
        if not client:
            return {"status": "unhealthy", "error": "Could not create Weaviate client"}
        
        response_time = int((time.time() - start) * 1000)
        
        # Test connection
        is_ready = client.is_ready()
        if is_ready:
            # V4 API: Get collections count
            collections = client.collections.list_all()
            meta = client.get_meta()
            result = {
                "status": "healthy",
                "responseTime": response_time,
                "collections": len(collections),
                "version": meta.get("version", "unknown"),
                "url": get_weaviate_url()
            }
            client.close()
            return result
        else:
            client.close()
            return {
                "status": "unhealthy",
                "error": "Weaviate not ready",
                "responseTime": response_time
            }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_libcal_health() -> Dict[str, Any]:
    """Check LibCal API connectivity via OAuth token fetch."""
    oauth_url = os.getenv("LIBCAL_OAUTH_URL", "")
    client_id = os.getenv("LIBCAL_CLIENT_ID", "")
    client_secret = os.getenv("LIBCAL_CLIENT_SECRET", "")

    if not all([oauth_url, client_id, client_secret]):
        return {"status": "unconfigured", "error": "LibCal credentials not configured"}

    try:
        start = time.time()
        oauth_service = get_libcal_oauth_service()
        token = await oauth_service.get_token()
        response_time = int((time.time() - start) * 1000)

        if token:
            return {"status": "healthy", "responseTime": response_time}
        else:
            return {"status": "unhealthy", "error": "Failed to obtain OAuth token"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_libguides_health() -> Dict[str, Any]:
    """Check LibGuides API connectivity via OAuth token fetch."""
    oauth_url = os.getenv("LIBGUIDE_OAUTH_URL", "")
    client_id = os.getenv("LIBGUIDE_CLIENT_ID", "")
    client_secret = os.getenv("LIBGUIDE_CLIENT_SECRET", "")

    if not all([oauth_url, client_id, client_secret]):
        return {
            "status": "unconfigured",
            "error": "LibGuides credentials not configured",
        }

    try:
        start = time.time()
        oauth_service = get_libapps_oauth_service()
        token = await oauth_service.get_token()
        response_time = int((time.time() - start) * 1000)

        if token:
            return {"status": "healthy", "responseTime": response_time}
        else:
            return {"status": "unhealthy", "error": "Failed to obtain OAuth token"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_google_cse_health() -> Dict[str, Any]:
    """Check Google Custom Search Engine API connectivity."""
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_LIBRARY_SEARCH_CSE_ID", "")

    if not api_key or not cse_id:
        return {
            "status": "unconfigured",
            "error": "Google CSE credentials not configured",
        }

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=10) as client:
            # Perform a minimal test search
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cse_id, "q": "test", "num": 1},
            )
            response_time = int((time.time() - start) * 1000)

            if response.status_code == 200:
                return {"status": "healthy", "responseTime": response_time}
            else:
                return {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}",
                    "responseTime": response_time,
                }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_libanswers_health() -> Dict[str, Any]:
    """Check LibAnswers API connectivity (for chat handoff)."""
    client_id = os.getenv("LIBANSWERS_CLIENT_ID", "")
    client_secret = os.getenv("LIBANSWERS_CLIENT_SECRET", "")
    token_url = os.getenv("LIBANSWERS_TOKEN_URL", "")

    if not all([client_id, client_secret, token_url]):
        return {
            "status": "unconfigured",
            "error": "LibAnswers credentials not configured",
        }

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response_time = int((time.time() - start) * 1000)

            if response.status_code == 200:
                data = response.json()
                if data.get("access_token"):
                    return {"status": "healthy", "responseTime": response_time}

            return {
                "status": "unhealthy",
                "error": f"HTTP {response.status_code}",
                "responseTime": response_time,
            }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint with external API status.
    Returns overall application health status and connectivity to all external services.
    """
    # Core checks
    db_health = await check_database_health()
    memory_health = check_memory_health()

    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # External API checks (run in parallel for speed)
    import asyncio

    (
        openai_health,
        weaviate_health,
        libcal_health,
        libguides_health,
        google_health,
        libanswers_health,
    ) = await asyncio.gather(
        check_openai_health(),
        check_weaviate_health(),
        check_libcal_health(),
        check_libguides_health(),
        check_google_cse_health(),
        check_libanswers_health(),
        return_exceptions=True,
    )

    # Handle any exceptions from parallel checks
    def safe_result(result, service_name):
        if isinstance(result, Exception):
            return {
                "status": "unhealthy",
                "error": f"{service_name} check failed: {str(result)}",
            }
        return result

    openai_health = safe_result(openai_health, "OpenAI")
    weaviate_health = safe_result(weaviate_health, "Weaviate")
    libcal_health = safe_result(libcal_health, "LibCal")
    libguides_health = safe_result(libguides_health, "LibGuides")
    google_health = safe_result(google_health, "Google CSE")
    libanswers_health = safe_result(libanswers_health, "LibAnswers")

    # Determine overall status (critical services only)
    critical_services_healthy = (
        db_health["status"] == "healthy"
        and memory_health["status"] in ["healthy", "warning"]
        and openai_health["status"] == "healthy"
        and weaviate_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if critical_services_healthy else "unhealthy",
        "timestamp": datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p EST"),
        "uptime": time.time() - START_TIME,
        "memory": memory_health,
        "system": {
            "platform": os.sys.platform,
            "pythonVersion": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "cpuUsage": {"percent": cpu_percent},
        },
        "services": {
            "database": db_health,
            "openai": openai_health,
            "weaviate": weaviate_health,
            "libcal": libcal_health,
            "libguides": libguides_health,
            "googleCSE": google_health,
            "libanswers": libanswers_health,
        },
    }


@router.get("/readiness")
async def readiness_check():
    """
    Kubernetes readiness probe endpoint.
    Checks if the service is ready to accept traffic.
    """
    checks = []
    all_ready = True

    # Database connectivity check
    db_health = await check_database_health()
    checks.append({"name": "database", **db_health})
    if db_health["status"] != "healthy":
        all_ready = False

    # Memory check
    memory_health = check_memory_health()
    checks.append({"name": "memory", **memory_health})
    if memory_health["status"] not in ["healthy", "warning"]:
        all_ready = False

    # Environment variables check
    env_health = check_environment_health()
    checks.append({"name": "environment", **env_health})
    if env_health["status"] != "healthy":
        all_ready = False

    result = {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }

    if not all_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result
        )

    return result


@router.get("/metrics")
async def metrics_endpoint():
    """
    Basic metrics endpoint (JSON format).
    For Prometheus format, see /metrics/prometheus
    """
    db_health = await check_database_health()
    memory_health = check_memory_health()
    process = psutil.Process()
    memory_info = process.memory_info()

    uptime = time.time() - START_TIME

    return {
        "uptime_seconds": uptime,
        "memory_used_mb": memory_health["used"],
        "memory_total_mb": memory_health["total"],
        "memory_rss_bytes": memory_info.rss,
        "memory_vms_bytes": memory_info.vms,
        "database_healthy": 1 if db_health["status"] == "healthy" else 0,
        "database_response_time_ms": db_health.get("responseTime", -1),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/metrics/prometheus")
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    metrics_data = await metrics_endpoint()

    # Convert to Prometheus format
    prometheus_output = [
        "# HELP smartchatbot_uptime_seconds Application uptime in seconds",
        "# TYPE smartchatbot_uptime_seconds counter",
        f"smartchatbot_uptime_seconds {metrics_data['uptime_seconds']:.2f}",
        "",
        "# HELP smartchatbot_memory_used_mb Memory used in MB",
        "# TYPE smartchatbot_memory_used_mb gauge",
        f"smartchatbot_memory_used_mb {metrics_data['memory_used_mb']}",
        "",
        "# HELP smartchatbot_memory_rss_bytes RSS memory in bytes",
        "# TYPE smartchatbot_memory_rss_bytes gauge",
        f"smartchatbot_memory_rss_bytes {metrics_data['memory_rss_bytes']}",
        "",
        "# HELP smartchatbot_database_healthy Database health status (1=healthy, 0=unhealthy)",
        "# TYPE smartchatbot_database_healthy gauge",
        f"smartchatbot_database_healthy {metrics_data['database_healthy']}",
        "",
        "# HELP smartchatbot_database_response_time_ms Database response time in milliseconds",
        "# TYPE smartchatbot_database_response_time_ms gauge",
        f"smartchatbot_database_response_time_ms {metrics_data['database_response_time_ms']}",
        "",
        "# HELP smartchatbot_cpu_percent CPU usage percentage",
        "# TYPE smartchatbot_cpu_percent gauge",
        f"smartchatbot_cpu_percent {metrics_data['cpu_percent']}",
        "",
    ]

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(prometheus_output))


@router.post("/health/restart")
async def health_restart():
    """
    Trigger application restart (for compatibility with NestJS endpoint).
    In production, this should be handled by process manager.
    """
    return {
        "message": "Restart acknowledged",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "note": "Application restart should be managed by process manager (PM2, systemd, etc.)",
    }


@router.get("/health/status")
async def detailed_health_status():
    """Detailed health status with all checks."""
    return await health_check()


@router.get("/health/restart-status")
async def restart_status():
    """Get restart status (for compatibility)."""
    return {
        "status": "no_restart_pending",
        "uptime": time.time() - START_TIME,
        "timestamp": datetime.now().isoformat(),
    }
