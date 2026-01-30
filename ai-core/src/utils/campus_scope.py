"""
Campus Scope Detection Utility

Detects which campus (Oxford, Hamilton, Middletown) a user is asking about.
Defaults to Oxford for King Library and main campus.
"""

import re
from typing import Literal

CampusScope = Literal["oxford", "hamilton", "middletown"]


def detect_campus_scope(user_message: str) -> CampusScope:
    """
    Detect campus scope from user message.
    
    Defaults to Oxford/King unless explicitly mentioned:
    - Hamilton campus / Rentschler Library
    - Middletown campus / Gardner-Harvey Library
    - Regional campuses
    
    Args:
        user_message: User's query
        
    Returns:
        "oxford", "hamilton", or "middletown"
    """
    msg_lower = user_message.lower()
    
    # Hamilton indicators
    hamilton_keywords = [
        "hamilton",
        "rentschler",
        "rentschler library"
    ]
    
    # Middletown indicators
    middletown_keywords = [
        "middletown",
        "gardner",
        "gardner-harvey",
        "gardner harvey"
    ]
    
    # Regional indicator (could be either Hamilton or Middletown)
    regional_keywords = [
        "regional campus",
        "regional library"
    ]
    
    # Check for explicit campus mentions
    for keyword in hamilton_keywords:
        if keyword in msg_lower:
            return "hamilton"
    
    for keyword in middletown_keywords:
        if keyword in msg_lower:
            return "middletown"
    
    # If "regional" mentioned without specific campus, default to Hamilton (larger)
    for keyword in regional_keywords:
        if keyword in msg_lower:
            return "hamilton"
    
    # Default to Oxford for:
    # - King Library
    # - Wertz Art & Architecture Library
    # - Main campus / Oxford campus
    # - No campus specified
    return "oxford"


def is_oxford_default(user_message: str) -> bool:
    """
    Check if query should default to Oxford.
    
    Returns True unless user explicitly mentions regional campuses.
    """
    return detect_campus_scope(user_message) == "oxford"


def get_campus_display_name(campus_scope: CampusScope) -> str:
    """Get display name for campus."""
    names = {
        "oxford": "Oxford/King Library",
        "hamilton": "Hamilton/Rentschler Library",
        "middletown": "Middletown/Gardner-Harvey Library"
    }
    return names.get(campus_scope, "Oxford/King Library")
