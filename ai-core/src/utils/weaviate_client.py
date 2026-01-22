"""
Centralized Weaviate Client Factory
Uses connect_to_custom with POSITIONAL arguments only (team requirement).
Local Docker only - no cloud references.
"""

import os
import weaviate
from typing import Optional


def get_weaviate_client() -> Optional[weaviate.WeaviateClient]:
    """
    Create Weaviate v4 client for LOCAL DOCKER using connect_to_custom.
    
    TEAM REQUIREMENT: Use POSITIONAL arguments only (no keyword names).
    Signature: connect_to_custom(http_host, http_port, http_secure, grpc_host, grpc_port, grpc_secure)
    
    Returns:
        weaviate.WeaviateClient if successful, None if disabled or connection fails
    """
    # Check if Weaviate is enabled
    if os.getenv("WEAVIATE_ENABLED", "true").lower() != "true":
        print("ℹ️  Weaviate disabled via WEAVIATE_ENABLED=false")
        return None
    
    # Read environment variables
    scheme = os.getenv("WEAVIATE_SCHEME", "http")
    host = os.getenv("WEAVIATE_HOST", "127.0.0.1")
    
    # Support both WEAVIATE_HTTP_PORT and legacy WEAVIATE_PORT for backward compatibility
    http_port = int(os.getenv("WEAVIATE_HTTP_PORT") or os.getenv("WEAVIATE_PORT", "8081"))
    grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50052"))
    
    if not host:
        print("❌ WEAVIATE_HOST not set in .env")
        return None
    
    # Determine secure flags from scheme (False for local http)
    http_secure = (scheme == "https")
    grpc_secure = (scheme == "https")
    
    # Force False for local Docker
    if host in ("127.0.0.1", "localhost"):
        http_secure = False
        grpc_secure = False
    
    try:
        # CRITICAL: Use POSITIONAL arguments only (team requirement)
        # connect_to_custom(http_host, http_port, http_secure, grpc_host, grpc_port, grpc_secure)
        client = weaviate.connect_to_custom(
            host,           # http_host
            http_port,      # http_port
            False,          # http_secure (always False for local)
            host,           # grpc_host (same as http_host)
            grpc_port,      # grpc_port
            False           # grpc_secure (always False for local)
        )
        
        # V4 client connects automatically, verify it's ready
        if not client.is_ready():
            print(f"❌ Weaviate not ready at {scheme}://{host}:{http_port}")
            client.close()
            return None
        
        return client
        
    except Exception as e:
        print(f"❌ Weaviate connection error: {e}")
        return None


def get_weaviate_url() -> str:
    """Get the Weaviate base URL from environment."""
    scheme = os.getenv("WEAVIATE_SCHEME", "http")
    host = os.getenv("WEAVIATE_HOST", "127.0.0.1")
    http_port = os.getenv("WEAVIATE_HTTP_PORT") or os.getenv("WEAVIATE_PORT", "8081")
    return f"{scheme}://{host}:{http_port}"
