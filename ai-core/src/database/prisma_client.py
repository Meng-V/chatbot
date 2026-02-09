"""Prisma client initialization and management."""
import logging
from prisma import Prisma
from typing import Optional

logger = logging.getLogger(__name__)

_prisma_client: Optional[Prisma] = None

def get_prisma_client() -> Prisma:
    """
    Get or create Prisma client instance (singleton pattern).
    """
    global _prisma_client
    
    if _prisma_client is None:
        _prisma_client = Prisma()
    
    return _prisma_client

async def connect_database():
    """Connect to database on application startup."""
    client = get_prisma_client()
    if not client.is_connected():
        await client.connect()
        logger.info("✅ Database connected successfully")

async def disconnect_database():
    """Disconnect from database on application shutdown."""
    client = get_prisma_client()
    if client.is_connected():
        await client.disconnect()
        logger.info("🔌 Database disconnected")
