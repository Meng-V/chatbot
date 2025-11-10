"""Health, Readiness, and Metrics endpoints for monitoring."""
import os
import psutil
import time
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status
from src.database.prisma_client import get_prisma_client

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
        
        return {
            "status": "healthy",
            "responseTime": response_time
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

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
        "external": int(process_memory.vms / 1024 / 1024)  # Virtual memory
    }

def check_environment_health() -> Dict[str, Any]:
    """Check required environment variables."""
    required_vars = [
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "WEAVIATE_HOST",
        "WEAVIATE_API_KEY"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    
    return {
        "status": "healthy" if not missing else "unhealthy",
        "missingVariables": missing
    }

@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    Returns overall application health status.
    """
    db_health = await check_database_health()
    memory_health = check_memory_health()
    
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    
    # Determine overall status
    is_healthy = (
        db_health["status"] == "healthy" and
        memory_health["status"] in ["healthy", "warning"]
    )
    
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "timestamp": datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p EST"),
        "uptime": time.time() - START_TIME,
        "memory": memory_health,
        "system": {
            "platform": os.sys.platform,
            "pythonVersion": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "cpuUsage": {
                "percent": cpu_percent
            }
        },
        "services": {
            "database": db_health,
            "openai": {
                "status": "healthy" if os.getenv("OPENAI_API_KEY") else "unconfigured"
            },
            "weaviate": {
                "status": "healthy" if os.getenv("WEAVIATE_API_KEY") else "unconfigured"
            }
        }
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
    checks.append({
        "name": "database",
        **db_health
    })
    if db_health["status"] != "healthy":
        all_ready = False
    
    # Memory check
    memory_health = check_memory_health()
    checks.append({
        "name": "memory",
        **memory_health
    })
    if memory_health["status"] not in ["healthy", "warning"]:
        all_ready = False
    
    # Environment variables check
    env_health = check_environment_health()
    checks.append({
        "name": "environment",
        **env_health
    })
    if env_health["status"] != "healthy":
        all_ready = False
    
    result = {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }
    
    if not all_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result
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
        "timestamp": datetime.now().isoformat()
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
        ""
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
        "note": "Application restart should be managed by process manager (PM2, systemd, etc.)"
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
        "timestamp": datetime.now().isoformat()
    }
