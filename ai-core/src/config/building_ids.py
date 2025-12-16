"""Building ID mappings for Miami University campuses.

DEPRECATED: This module is being migrated to use the database location service.
Use src.services.location_service instead for new code.

For backward compatibility, async wrapper functions are provided.
"""
import asyncio
from typing import Optional
from src.services.location_service import get_location_service


async def get_building_id_async(building_name: str) -> str:
    """
    Get building ID from building name (case-insensitive) - async version.
    Returns default building ID if building not found.
    """
    if not building_name:
        service = get_location_service()
        return await service.get_default_building_id()
    
    service = get_location_service()
    building_id = await service.get_building_id(building_name)
    
    if building_id:
        return building_id
    
    # Fallback to default
    return await service.get_default_building_id()


async def get_building_display_name_async(building_id: str) -> str:
    """Get display name for a building by its LibCal building ID - async version."""
    service = get_location_service()
    return await service.get_building_display_name(building_id)


async def get_all_buildings_async() -> dict:
    """Get all building mappings - async version."""
    service = get_location_service()
    return await service.get_all_buildings()


# LEGACY SYNCHRONOUS FUNCTIONS (for backward compatibility)
# These use asyncio.run() which is not ideal but maintains compatibility
# TODO: Migrate all callers to use async versions

def get_building_id(building_name: str) -> str:
    """
    DEPRECATED: Use get_building_id_async() instead.
    Get building ID from building name (case-insensitive).
    Returns default building ID if building not found.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, we can't use asyncio.run()
            # Fall back to hardcoded default
            return "2047"
        return loop.run_until_complete(get_building_id_async(building_name))
    except Exception:
        # Fallback to hardcoded default
        return "2047"


def get_building_display_name(building_name: str) -> str:
    """
    DEPRECATED: Use get_building_display_name_async() instead.
    Get display name for a building.
    """
    try:
        # Try to get building ID first
        building_id = get_building_id(building_name)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return "Library"
        return loop.run_until_complete(get_building_display_name_async(building_id))
    except Exception:
        return "Library"
