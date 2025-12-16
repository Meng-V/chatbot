"""Ask Us Chat Service hours API - checks business hours for human librarian chat availability."""
import os
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter
from zoneinfo import ZoneInfo

router = APIRouter()

# LibCal configuration
LIBCAL_OAUTH_URL = os.getenv("LIBCAL_OAUTH_URL", "")
LIBCAL_CLIENT_ID = os.getenv("LIBCAL_CLIENT_ID", "")
LIBCAL_CLIENT_SECRET = os.getenv("LIBCAL_CLIENT_SECRET", "")
LIBCAL_HOUR_URL = os.getenv("LIBCAL_HOUR_URL", "")
LIBCAL_ASKUS_ID = os.getenv("LIBCAL_ASKUS_ID", "")

# Cache token
_oauth_token: Optional[str] = None
_token_expiry: Optional[datetime] = None


async def _get_oauth_token() -> str:
    """Get LibCal OAuth token with caching."""
    global _oauth_token, _token_expiry
    
    # Check if cached token is still valid
    if _oauth_token and _token_expiry and datetime.now() < _token_expiry:
        return _oauth_token
    
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            LIBCAL_OAUTH_URL,
            data={
                "client_id": LIBCAL_CLIENT_ID,
                "client_secret": LIBCAL_CLIENT_SECRET,
                "grant_type": "client_credentials"
            }
        )
        response.raise_for_status()
        data = response.json()
        _oauth_token = data["access_token"]
        # Token typically expires in 1 hour, refresh at 50 minutes
        from datetime import timedelta
        _token_expiry = datetime.now() + timedelta(minutes=50)
        return _oauth_token


def _parse_time(time_str: str) -> Optional[datetime]:
    """Parse time string like '9:00am' or '5:00pm' to datetime for today."""
    if not time_str:
        return None
    
    try:
        # Handle formats like "9:00am", "10:30pm", "12:00pm"
        time_str = time_str.strip().lower()
        
        # Parse the time
        if 'am' in time_str or 'pm' in time_str:
            time_obj = datetime.strptime(time_str, "%I:%M%p")
        else:
            time_obj = datetime.strptime(time_str, "%H:%M")
        
        # Combine with today's date in EST timezone
        est = ZoneInfo("America/New_York")
        now = datetime.now(est)
        return now.replace(
            hour=time_obj.hour,
            minute=time_obj.minute,
            second=0,
            microsecond=0
        )
    except Exception:
        return None


def _is_within_hours(hours_list: list) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Check if current time is within any of the hour ranges.
    Returns (is_open, open_time, close_time) for the current/next period.
    """
    if not hours_list:
        return False, None, None
    
    est = ZoneInfo("America/New_York")
    now = datetime.now(est)
    
    for hour_range in hours_list:
        from_time = hour_range.get("from", "")
        to_time = hour_range.get("to", "")
        
        open_dt = _parse_time(from_time)
        close_dt = _parse_time(to_time)
        
        if open_dt and close_dt and open_dt <= now <= close_dt:
            return True, from_time, to_time
    
    # Return first hour range even if not currently open
    if hours_list:
        return False, hours_list[0].get("from"), hours_list[0].get("to")
    
    return False, None, None


async def get_askus_hours_for_date(date: str = None) -> Dict[str, Any]:
    """
    Fetch Ask Us Chat Service hours for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format (defaults to today)
    
    Returns:
        Dict with hours information
    """
    if not LIBCAL_ASKUS_ID:
        return {
            "error": "LIBCAL_ASKUS_ID not configured",
            "is_open": False,
            "hours": None
        }
    
    est = ZoneInfo("America/New_York")
    if not date:
        date = datetime.now(est).strftime("%Y-%m-%d")
    
    try:
        token = await _get_oauth_token()
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{LIBCAL_HOUR_URL}/{LIBCAL_ASKUS_ID}",
                headers={"Authorization": f"Bearer {token}"},
                params={"from": date, "to": date}
            )
            response.raise_for_status()
            data = response.json()
        
        # Parse response - API returns array with date keys
        if not data or not isinstance(data, list) or len(data) == 0:
            return {
                "date": date,
                "is_open": False,
                "status": "closed",
                "hours": None,
                "message": "No hours data available"
            }
        
        location_data = data[0]
        dates_data = location_data.get("dates", {})
        day_data = dates_data.get(date, {})
        
        status = day_data.get("status", "closed")
        hours_list = day_data.get("hours", [])
        
        # Check if currently within business hours
        is_open, open_time, close_time = _is_within_hours(hours_list)
        
        # If status is not "open", service is closed for the day
        if status != "open":
            is_open = False
        
        return {
            "date": date,
            "day_of_week": datetime.strptime(date, "%Y-%m-%d").strftime("%A"),
            "is_open": is_open,
            "status": status,
            "hours": hours_list,
            "current_period": {
                "open": open_time,
                "close": close_time
            } if open_time else None,
            "location_name": location_data.get("name", "Ask Us Chat Service"),
            "message": "Chat service is currently available!" if is_open else 
                      f"Chat service opens at {open_time}" if open_time and status == "open" else
                      "Chat service is closed today"
        }
        
    except httpx.HTTPError as e:
        return {
            "error": f"Failed to fetch hours: {str(e)}",
            "is_open": False,
            "hours": None
        }
    except Exception as e:
        return {
            "error": f"Error checking hours: {str(e)}",
            "is_open": False,
            "hours": None
        }


@router.get("/askus-hours")
async def get_askus_hours(date: str = None):
    """
    Get Ask Us Chat Service hours for a specific date.
    
    Query Parameters:
        date: Optional date in YYYY-MM-DD format (defaults to today)
    
    Returns:
        Hours information including whether currently open
    """
    return await get_askus_hours_for_date(date)


@router.get("/askus-hours/status")
async def get_askus_status():
    """
    Quick check if Ask Us Chat Service is currently available.
    Used by frontend to determine whether to show "Chat with human" option.
    
    Returns:
        Simple status object with is_open boolean
    """
    hours_data = await get_askus_hours_for_date()
    
    return {
        "is_open": hours_data.get("is_open", False),
        "message": hours_data.get("message", ""),
        "hours_today": hours_data.get("current_period"),
        "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat()
    }


@router.get("/askus-hours/week")
async def get_askus_hours_week():
    """
    Get Ask Us Chat Service hours for the current week.
    
    Returns:
        Hours for each day of the week
    """
    est = ZoneInfo("America/New_York")
    today = datetime.now(est)
    
    # Get hours for the next 7 days
    from datetime import timedelta
    week_hours = []
    
    for i in range(7):
        date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        day_hours = await get_askus_hours_for_date(date)
        week_hours.append(day_hours)
    
    return {
        "service_name": "Ask Us Chat Service",
        "description": "Live chat with a librarian",
        "week_hours": week_hours
    }
