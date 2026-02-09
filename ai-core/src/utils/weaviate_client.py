"""
Centralized Weaviate Client Factory (Singleton)
Uses connect_to_custom with POSITIONAL arguments only (team requirement).
Local Docker only - no cloud references.

CRITICAL: Uses singleton pattern to avoid connection exhaustion.
A single Weaviate v4 client is thread-safe and should be reused.
"""

import os
import logging
import threading
import weaviate
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton state
_client: Optional[weaviate.WeaviateClient] = None
_lock = threading.Lock()
_initialized = False


def get_weaviate_client() -> Optional[weaviate.WeaviateClient]:
    """
    Get or create a singleton Weaviate v4 client for LOCAL DOCKER.
    
    TEAM REQUIREMENT: Use POSITIONAL arguments only (no keyword names).
    Signature: connect_to_custom(http_host, http_port, http_secure, grpc_host, grpc_port, grpc_secure)
    
    Returns:
        weaviate.WeaviateClient if successful, None if disabled or connection fails
    """
    global _client, _initialized
    
    # Fast path: return existing client if healthy
    if _client is not None:
        try:
            if _client.is_ready():
                return _client
        except Exception:
            # Client is stale, recreate below
            _client = None
            _initialized = False
    
    with _lock:
        # Double-check after acquiring lock
        if _client is not None:
            try:
                if _client.is_ready():
                    return _client
            except Exception:
                _client = None
                _initialized = False
        
        # Check if Weaviate is enabled
        if os.getenv("WEAVIATE_ENABLED", "true").lower() != "true":
            logger.info("ℹ️  Weaviate disabled via WEAVIATE_ENABLED=false")
            return None
        
        # Read environment variables
        scheme = os.getenv("WEAVIATE_SCHEME", "http")
        host = os.getenv("WEAVIATE_HOST", "127.0.0.1")
        
        # Support both WEAVIATE_HTTP_PORT and legacy WEAVIATE_PORT for backward compatibility
        raw_http_port = os.getenv("WEAVIATE_HTTP_PORT")
        raw_legacy_port = os.getenv("WEAVIATE_PORT")
        if raw_http_port:  # Prefer WEAVIATE_HTTP_PORT if set and non-empty
            http_port = int(raw_http_port)
        elif raw_legacy_port:
            http_port = int(raw_legacy_port)
        else:
            http_port = 8888  # Default (unified local + server)
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
        
        if not _initialized:
            logger.info(f"🔗 [Weaviate] Connecting to {scheme}://{host}:{http_port} (gRPC: {grpc_port})")
            _initialized = True
        
        if not host:
            logger.error("❌ [Weaviate] WEAVIATE_HOST not set in .env")
            return None
        
        try:
            # CRITICAL: Use POSITIONAL arguments only (team requirement)
            # connect_to_custom(http_host, http_port, http_secure, grpc_host, grpc_port, grpc_secure)
            _client = weaviate.connect_to_custom(
                host,           # http_host
                http_port,      # http_port
                False,          # http_secure (always False for local)
                host,           # grpc_host (same as http_host)
                grpc_port,      # grpc_port
                False           # grpc_secure (always False for local)
            )
            
            # V4 client connects automatically, verify it's ready
            if not _client.is_ready():
                logger.warning(f"⚠️ [Weaviate] Not ready at {scheme}://{host}:{http_port} — client created but is_ready()=False")
                _client.close()
                _client = None
                return None
            
            return _client
            
        except Exception as e:
            logger.error(f"❌ [Weaviate] Connection error at {scheme}://{host}:{http_port}: {e}", exc_info=True)
            _client = None
            return None


def close_weaviate_client():
    """Close the singleton Weaviate client. Call on application shutdown."""
    global _client, _initialized
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None
            _initialized = False


def get_weaviate_url() -> str:
    """Get the Weaviate base URL from environment."""
    scheme = os.getenv("WEAVIATE_SCHEME", "http")
    host = os.getenv("WEAVIATE_HOST", "127.0.0.1")
    http_port = os.getenv("WEAVIATE_HTTP_PORT") or os.getenv("WEAVIATE_PORT", "8888")
    return f"{scheme}://{host}:{http_port}"
