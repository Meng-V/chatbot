"""Building ID mappings for Miami University campuses."""
import os
from typing import Dict

# Building IDs for LibCal room booking
BUILDING_IDS: Dict[str, str] = {
    # Oxford Campus (Main)
    "king": os.getenv("OXFORD_KING_LIBRARY", "2047"),
    "king library": os.getenv("OXFORD_KING_LIBRARY", "2047"),
    "art": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    "art library": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    "art and architecture": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    "architecture": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    
    # Hamilton Campus (Regional)
    "hamilton": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    "rentschler": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    "rentschler library": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    
    # Middletown Campus (Regional)
    "middletown": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner-harvey": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner harvey": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
}

# Default building (King Library - Main Oxford Campus)
DEFAULT_BUILDING_ID = os.getenv("OXFORD_KING_LIBRARY", "2047")

def get_building_id(building_name: str) -> str:
    """
    Get building ID from building name (case-insensitive).
    Returns DEFAULT_BUILDING_ID if building not found.
    """
    if not building_name:
        return DEFAULT_BUILDING_ID
    
    building_key = building_name.lower().strip()
    return BUILDING_IDS.get(building_key, DEFAULT_BUILDING_ID)

def get_building_display_name(building_name: str) -> str:
    """Get display name for a building."""
    building_key = building_name.lower().strip() if building_name else ""
    
    display_names = {
        "king": "King Library (Oxford)",
        "king library": "King Library (Oxford)",
        "art": "Art & Architecture Library (Oxford)",
        "art library": "Art & Architecture Library (Oxford)",
        "art and architecture": "Art & Architecture Library (Oxford)",
        "architecture": "Art & Architecture Library (Oxford)",
        "hamilton": "Rentschler Library (Hamilton)",
        "rentschler": "Rentschler Library (Hamilton)",
        "rentschler library": "Rentschler Library (Hamilton)",
        "middletown": "Gardner-Harvey Library (Middletown)",
        "gardner-harvey": "Gardner-Harvey Library (Middletown)",
        "gardner harvey": "Gardner-Harvey Library (Middletown)",
        "gardner": "Gardner-Harvey Library (Middletown)",
    }
    
    return display_names.get(building_key, "King Library (Oxford)")
