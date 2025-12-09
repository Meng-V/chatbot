"""Comprehensive LibCal tools matching legacy NestJS functionality."""
import os
import re
import httpx
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import pytz
from src.tools.base import Tool
from src.services.libcal_oauth import get_libcal_oauth_service
from src.config.building_ids import get_building_id, get_building_display_name

# Environment variables
LIBCAL_OAUTH_URL = os.getenv("LIBCAL_OAUTH_URL", "")
LIBCAL_CLIENT_ID = os.getenv("LIBCAL_CLIENT_ID", "")
LIBCAL_CLIENT_SECRET = os.getenv("LIBCAL_CLIENT_SECRET", "")
LIBCAL_GRANT_TYPE = os.getenv("LIBCAL_GRANT_TYPE", "client_credentials")
LIBCAL_HOUR_URL = os.getenv("LIBCAL_HOUR_URL", "")
LIBCAL_SEARCH_AVAILABLE_URL = os.getenv("LIBCAL_SEARCH_AVAILABLE_URL", "")
LIBCAL_RESERVATION_URL = os.getenv("LIBCAL_RESERVATION_URL", "")
LIBCAL_BOOKING_INFO_URL = os.getenv("LIBCAL_BOOKING_INFO_URL", "")  # GET /space/booking/{id}
LIBCAL_CANCEL_URL = os.getenv("LIBCAL_CANCEL_URL", "")
NODE_ENV = os.getenv("NODE_ENV", "development")

# Building IDs for Miami University Campuses
BUILDINGS = {
    # Oxford Campus (Main Campus)
    "king": os.getenv("OXFORD_KING_LIBRARY", "2047"),
    "king library": os.getenv("OXFORD_KING_LIBRARY", "2047"),
    "art": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    "art library": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    "art and architecture": os.getenv("OXFORD_ART_ARCHITECTURE_LIBRARY", "4089"),
    
    # Hamilton Campus (Regional)
    "hamilton": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    "rentschler": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    "rentschler library": os.getenv("HAMILTON_RENTSCHLER_LIBRARY", "4792"),
    
    # Middletown Campus (Regional)
    "middletown": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner-harvey": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner harvey": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
    "gardner-harvey library": os.getenv("MIDDLETOWN_GARDNER_HARVEY_LIBRARY", "4845"),
}

# Default building
DEFAULT_BUILDING = os.getenv("OXFORD_KING_LIBRARY", "2047")

# Building ID to Location ID mapping for hours API
BUILDING_TO_LOCATION_ID = {
    "2047": "8113",  # King Library
    "4089": "10997",  # Art & Architecture Library
    "4792": "12082",  # Rentschler Library
    "4845": "12083",  # Gardner-Harvey Library
}

# Campus mapping for building information
CAMPUS_INFO = {
    "oxford": {
        "name": "Oxford Campus",
        "libraries": ["King Library", "Art and Architecture Library"],
        "centers": ["Maker Space", "Special Collections", "Writing Center"]
    },
    "hamilton": {
        "name": "Hamilton Campus",
        "libraries": ["Rentschler Library"],
        "centers": []
    },
    "middletown": {
        "name": "Middletown Campus",
        "libraries": ["Gardner-Harvey Library"],
        "centers": []
    }
}

async def _get_oauth_token() -> str:
    """Get LibCal OAuth token using centralized service."""
    oauth_service = get_libcal_oauth_service()
    return await oauth_service.get_token()

def _validate_email(email: str) -> bool:
    """Validate email is @miamioh.edu."""
    return email.lower().endswith("@miamioh.edu")

def _get_capacity_range(capacity: Optional[int]) -> int:
    """Map capacity to LibCal range (1-4=1, 5-8=2, 9+=3)."""
    if capacity is None or capacity <= 4:
        return 1
    elif capacity <= 8:
        return 2
    else:
        return 3

def _parse_date_intelligent(date_input: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Intelligently parse various date formats to YYYY-MM-DD.
    
    Handles:
    - American format: 11/12/2025, 11-12-2025
    - ISO format: 2025-11-12
    - Word format: November 12, 2025, Nov 12 2025
    - Chinese format: 2025年11月12日
    - Relative dates: today, tomorrow, next Monday, next week
    
    Args:
        date_input: Date string in various formats
    
    Returns:
        Tuple of (success, formatted_date, error_message)
    """
    if not date_input:
        return False, None, "No date provided"
    
    # Get current time in New York timezone
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    
    date_lower = date_input.lower().strip()
    
    try:
        # Handle relative dates
        if date_lower in ['today', 'now']:
            result_date = now.date()
        elif date_lower in ['tomorrow', 'tmr', 'tmrw']:
            result_date = (now + timedelta(days=1)).date()
        elif date_lower in ['yesterday']:
            result_date = (now - timedelta(days=1)).date()
        elif date_lower.startswith('next '):
            # Handle "next Monday", "next week", etc.
            remainder = date_lower.replace('next ', '')
            
            if remainder == 'week':
                result_date = (now + timedelta(days=7)).date()
            elif remainder == 'month':
                # Add approximately 30 days
                result_date = (now + timedelta(days=30)).date()
            else:
                # Try parsing as day of week
                weekdays = {
                    'monday': 0, 'mon': 0,
                    'tuesday': 1, 'tue': 1, 'tues': 1,
                    'wednesday': 2, 'wed': 2,
                    'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
                    'friday': 4, 'fri': 4,
                    'saturday': 5, 'sat': 5,
                    'sunday': 6, 'sun': 6
                }
                
                if remainder in weekdays:
                    target_weekday = weekdays[remainder]
                    current_weekday = now.weekday()
                    days_ahead = target_weekday - current_weekday
                    if days_ahead <= 0:  # Target day already happened this week
                        days_ahead += 7
                    result_date = (now + timedelta(days=days_ahead)).date()
                else:
                    return False, None, f"Could not understand 'next {remainder}'"
        
        elif date_lower.startswith('this '):
            # Handle "this Monday", "this week", etc.
            remainder = date_lower.replace('this ', '')
            
            weekdays = {
                'monday': 0, 'mon': 0,
                'tuesday': 1, 'tue': 1, 'tues': 1,
                'wednesday': 2, 'wed': 2,
                'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
                'friday': 4, 'fri': 4,
                'saturday': 5, 'sat': 5,
                'sunday': 6, 'sun': 6
            }
            
            if remainder in weekdays:
                target_weekday = weekdays[remainder]
                current_weekday = now.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead < 0:  # Already passed this week, go to next week
                    days_ahead += 7
                result_date = (now + timedelta(days=days_ahead)).date()
            else:
                return False, None, f"Could not understand 'this {remainder}'"
        
        else:
            # Try parsing with dateutil for flexibility
            # Set dayfirst=False for American format (MM/DD/YYYY)
            parsed = date_parser.parse(date_input, dayfirst=False, fuzzy=True)
            
            # Convert to New York timezone if not already aware
            if parsed.tzinfo is None:
                parsed = ny_tz.localize(parsed)
            else:
                parsed = parsed.astimezone(ny_tz)
            
            result_date = parsed.date()
        
        # Format as YYYY-MM-DD
        formatted_date = result_date.strftime("%Y-%m-%d")
        return True, formatted_date, None
    
    except Exception as e:
        return False, None, f"Could not parse date '{date_input}': {str(e)}"

def _parse_time_intelligent(time_input: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Intelligently parse various time formats to HH:MM (24-hour).
    
    Handles:
    - 12-hour format: 8:00pm, 8pm, 8.00pm, 8:00 PM, 8 PM
    - 24-hour format: 20:00, 20-00, 2000
    - Words: noon, midnight
    
    Args:
        time_input: Time string in various formats
    
    Returns:
        Tuple of (success, formatted_time, error_message)
    """
    if not time_input:
        return False, None, "No time provided"
    
    time_lower = time_input.lower().strip()
    
    try:
        # Handle special words
        if time_lower in ['noon', '12pm', '12:00pm']:
            return True, "12:00", None
        elif time_lower in ['midnight', '12am', '12:00am']:
            return True, "00:00", None
        
        # Check for AM/PM
        is_pm = 'pm' in time_lower or 'p.m.' in time_lower
        is_am = 'am' in time_lower or 'a.m.' in time_lower
        
        # Remove AM/PM markers and clean up
        time_clean = re.sub(r'[ap]\.?m\.?', '', time_lower, flags=re.IGNORECASE)
        time_clean = time_clean.strip()
        
        # Replace various separators with colon
        time_clean = time_clean.replace('.', ':').replace('-', ':').replace(' ', '')
        
        # Try to parse the time
        if ':' in time_clean:
            parts = time_clean.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            # No separator, try to parse as pure number
            if len(time_clean) <= 2:
                # Single or double digit: just hour
                hour = int(time_clean)
                minute = 0
            elif len(time_clean) == 3:
                # Three digits: H:MM or HH:M
                hour = int(time_clean[0])
                minute = int(time_clean[1:3])
            elif len(time_clean) == 4:
                # Four digits: HH:MM
                hour = int(time_clean[0:2])
                minute = int(time_clean[2:4])
            else:
                return False, None, f"Could not parse time format '{time_input}'"
        
        # Convert 12-hour to 24-hour
        if is_pm and hour != 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0
        
        # Validate ranges
        if hour < 0 or hour > 23:
            return False, None, f"Hour must be between 0-23 (got {hour})"
        if minute < 0 or minute > 59:
            return False, None, f"Minute must be between 0-59 (got {minute})"
        
        # Format as HH:MM
        formatted_time = f"{hour:02d}:{minute:02d}"
        return True, formatted_time, None
    
    except Exception as e:
        return False, None, f"Could not parse time '{time_input}': {str(e)}"

def _detect_dst(date_str: str) -> str:
    """Detect if date is in DST (EDT) or EST using accurate timezone calculation."""
    # Parse date and localize to New York timezone
    ny_tz = pytz.timezone('America/New_York')
    test_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Create a datetime at noon on that date (arbitrary time)
    test_datetime = test_date.replace(hour=12, minute=0, second=0)
    
    # Localize to NY timezone - this will correctly handle DST
    localized = ny_tz.localize(test_datetime)
    
    # Get the UTC offset
    offset = localized.strftime("%z")
    
    # Format as +HH:MM or -HH:MM
    if len(offset) == 5:  # e.g., "-0500"
        return f"{offset[:3]}:{offset[3:]}"  # "-05:00"
    
    # Fallback to EST if something goes wrong
    return "-05:00"

def _validate_booking_duration(start_time: str, end_time: str) -> tuple[bool, float]:
    """Validate booking duration is within 2 hour maximum.
    
    Args:
        start_time: Time in HH:MM or HH-MM format
        end_time: Time in HH:MM or HH-MM format
    
    Returns:
        Tuple of (is_valid, duration_hours)
    """
    try:
        # Normalize time format
        start_normalized = start_time.replace("-", ":")
        end_normalized = end_time.replace("-", ":")
        
        # Parse times
        start_parts = start_normalized.split(":")
        end_parts = end_normalized.split(":")
        
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
        
        # Calculate duration in hours
        duration_minutes = end_minutes - start_minutes
        if duration_minutes < 0:
            duration_minutes += 24 * 60  # Handle overnight
        
        duration_hours = duration_minutes / 60.0
        
        # Maximum 2 hours (120 minutes)
        is_valid = duration_minutes <= 120
        
        return is_valid, duration_hours
    except Exception:
        return False, 0.0

async def _check_building_hours(building_id: str, date: str, start_time: str, end_time: str) -> tuple[bool, Optional[str]]:
    """Check if booking time is within building operating hours.
    
    Args:
        building_id: Building ID (e.g., "2047" for King Library)
        date: Date in YYYY-MM-DD format
        start_time: Start time in HH:MM or HH-MM format
        end_time: End time in HH:MM or HH-MM format
    
    Returns:
        Tuple of (is_valid, building_hours_message)
    """
    try:
        # Get location ID for hours API
        location_id = BUILDING_TO_LOCATION_ID.get(building_id)
        if not location_id:
            # If not in our mapping, assume valid (skip check)
            return True, None
        
        token = await _get_oauth_token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{LIBCAL_HOUR_URL}/{location_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"from": date, "to": date}
            )
            response.raise_for_status()
            data = response.json()
            
            if not data or len(data) == 0:
                # No hours data, assume valid
                return True, None
            
            location = data[0]
            dates = location.get("dates", {})
            day_data = dates.get(date)
            
            if not day_data or not day_data.get("hours"):
                # Building closed on this date
                return False, f"The building is closed on {date}"
            
            # Parse booking times
            start_normalized = start_time.replace("-", ":")
            end_normalized = end_time.replace("-", ":")
            
            def time_to_minutes(time_str: str) -> int:
                """Convert time string to minutes since midnight."""
                parts = time_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            
            booking_start = time_to_minutes(start_normalized)
            booking_end = time_to_minutes(end_normalized)
            
            # Check against all operating hour blocks
            hours_list = day_data["hours"]
            building_name = location.get("name", "Building")
            
            for hours_block in hours_list:
                from_time = hours_block.get("from")
                to_time = hours_block.get("to")
                
                if from_time and to_time:
                    # Convert to 24-hour format if needed and parse
                    building_open = time_to_minutes(from_time)
                    building_close = time_to_minutes(to_time)
                    
                    # Check if booking fits within this hours block
                    if booking_start >= building_open and booking_end <= building_close:
                        return True, None
            
            # If we get here, booking time is outside all operating hours
            hours_str = ", ".join([f"{h['from']} to {h['to']}" for h in hours_list])
            return False, f"{building_name} is open {hours_str} on {date}. Your requested time is outside these hours."
    
    except Exception as e:
        # On error, assume valid to not block legitimate bookings
        print(f"Warning: Building hours check failed: {e}")
        return True, None

class LibCalWeekHoursTool(Tool):
    """Tool for checking building hours for entire week."""
    
    @property
    def name(self) -> str:
        return "libcal_week_hours"
    
    @property
    def description(self) -> str:
        return "Get building hours for entire week (Monday-Sunday). Supports Oxford (King Library, Art & Architecture Library), Hamilton (Rentschler Library), and Middletown (Gardner-Harvey Library) campuses."
    
    async def execute(self, query: str, log_callback=None, date: str = None, **kwargs) -> Dict[str, Any]:
        """Get week-range hours."""
        try:
            if log_callback:
                log_callback("🗓️ [LibCal Week Hours Tool] Fetching weekly hours")
            
            # If no date provided, use today
            if not date:
                ny_tz = pytz.timezone('America/New_York')
                date = datetime.now(ny_tz).strftime("%Y-%m-%d")
            else:
                # Parse date intelligently
                date_success, parsed_date, date_error = _parse_date_intelligent(date)
                if not date_success:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": f"Date parsing error: {date_error}"
                    }
                date = parsed_date
            
            # Calculate Monday-Sunday range
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            day_of_week = date_obj.weekday()  # 0=Monday, 6=Sunday
            monday = date_obj - timedelta(days=day_of_week)
            sunday = monday + timedelta(days=6)
            
            from_date = monday.strftime("%Y-%m-%d")
            to_date = sunday.strftime("%Y-%m-%d")
            
            token = await _get_oauth_token()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{LIBCAL_HOUR_URL}/8113",  # Location ID for King
                    headers={"Authorization": f"Bearer {token}"},
                    params={"from": from_date, "to": to_date}
                )
                response.raise_for_status()
                data = response.json()
                
                if not data or len(data) == 0:
                    return {"tool": self.name, "success": False, "text": "No hours data available."}
                
                # Extract hours by day
                location = data[0]
                dates = location.get("dates", {})
                
                hours_text = f"**{location.get('name', 'King Library')} Hours (Week of {from_date}):**\n\n"
                
                day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                current_date = monday
                
                for day_name in day_names:
                    date_str = current_date.strftime("%Y-%m-%d")
                    day_data = dates.get(date_str)
                    
                    if day_data and day_data.get("hours"):
                        hours_list = day_data["hours"]
                        hours_str = " - ".join([f"{h['from']} to {h['to']}" for h in hours_list])
                        hours_text += f"• **{day_name} ({date_str})**: {hours_str}\n"
                    else:
                        hours_text += f"• **{day_name} ({date_str})**: Closed\n"
                    
                    current_date += timedelta(days=1)
                
                if log_callback:
                    log_callback("✅ [LibCal Week Hours Tool] Weekly hours retrieved")
                
                return {
                    "tool": self.name,
                    "success": True,
                    "text": hours_text
                }
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Week Hours Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Couldn't retrieve hours. Visit https://www.lib.miamioh.edu/hours"
            }

class LibCalEnhancedAvailabilityTool(Tool):
    """Enhanced room availability with capacity range fallback."""
    
    @property
    def name(self) -> str:
        return "libcal_enhanced_availability"
    
    @property
    def description(self) -> str:
        return "Check room availability with smart capacity fallback. Supports flexible date formats (11/12/2025, tomorrow, next Monday) and time formats (8pm, 20:00, 8:00 PM). Works with Oxford (King Library, Art & Architecture Library), Hamilton (Rentschler Library), and Middletown (Gardner-Harvey Library) campuses. Use 'building' parameter to specify location (e.g., 'king', 'rentschler', 'gardner-harvey')."
    
    async def execute(
        self, 
        query: str, 
        log_callback=None,
        date: str = None,
        start_time: str = None,
        end_time: str = None,
        capacity: int = None,
        building: str = "king",
        **kwargs
    ) -> Dict[str, Any]:
        """Check availability with capacity range fallback."""
        try:
            if log_callback:
                log_callback(f"🔍 [LibCal Enhanced Availability Tool] Searching {building} building")
            
            # Validate required parameters
            if not all([date, start_time, end_time]):
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Missing required parameters: date, start_time, end_time. Please provide these."
                }
            
            # Parse date intelligently
            date_success, parsed_date, date_error = _parse_date_intelligent(date)
            if not date_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Date parsing error: {date_error}"
                }
            date = parsed_date
            
            # Parse start time intelligently
            time_success, parsed_start_time, time_error = _parse_time_intelligent(start_time)
            if not time_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Start time parsing error: {time_error}"
                }
            start_time = parsed_start_time
            
            # Parse end time intelligently
            time_success, parsed_end_time, time_error = _parse_time_intelligent(end_time)
            if not time_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"End time parsing error: {time_error}"
                }
            end_time = parsed_end_time
            
            # Convert time format HH-MM to HH:MM (already in HH:MM from parser)
            start_formatted = start_time.replace("-", ":")
            end_formatted = end_time.replace("-", ":")
            
            # Resolve building ID
            building_key = building.lower().strip()
            building_id = BUILDINGS.get(building_key, DEFAULT_BUILDING)
            
            token = await _get_oauth_token()
            
            # Try capacity ranges with smart fallback
            capacity_range = _get_capacity_range(capacity)
            available_rooms = []
            
            for current_range in range(capacity_range, 4):  # Try up to range 3
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        f"{LIBCAL_SEARCH_AVAILABLE_URL}/{building_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        params={
                            "date": date,
                            "time_start": start_formatted,
                            "time_end": end_formatted,
                            "type": "space",
                            "capacity": current_range
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    exact_matches = data.get("exact_matches", [])
                    if exact_matches:
                        available_rooms = exact_matches
                        break
            
            if not available_rooms:
                return {
                    "tool": self.name,
                    "success": True,
                    "text": f"No rooms available at {building.capitalize()} Library for {date} from {start_time} to {end_time}."
                }
            
            # Sort by capacity and censor IDs
            rooms_data = []
            for room in available_rooms:
                space = room.get("space", {})
                rooms_data.append({
                    "name": space.get("name"),
                    "capacity": space.get("capacity"),
                    "id": space.get("id")  # Keep for booking, but mark as internal
                })
            
            rooms_data.sort(key=lambda x: x["capacity"])
            
            # Format for user (censor IDs)
            room_list = [f"• {r['name']} (capacity: {r['capacity']})" for r in rooms_data[:5]]
            
            if log_callback:
                log_callback(f"✅ [LibCal Enhanced Availability Tool] Found {len(rooms_data)} rooms")
            
            return {
                "tool": self.name,
                "success": True,
                "text": f"Available rooms at {building.capitalize()} Library:\n\n" + "\n".join(room_list),
                "rooms_data": rooms_data,  # Keep full data for booking
                "building": building
            }
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Enhanced Availability Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Couldn't search rooms. Visit https://libcal.miamioh.edu/"
            }

class LibCalComprehensiveReservationTool(Tool):
    """Comprehensive room booking with full validation and multi-building support."""
    
    @property
    def name(self) -> str:
        return "libcal_comprehensive_reservation"
    
    @property
    def description(self) -> str:
        return "Book a study room with full validation (requires firstName, lastName, @miamioh.edu email, date, time). Accepts flexible date formats (11/12/2025, tomorrow, next Monday) and time formats (8pm, 20:00, 8:00 PM). Automatically converts to 24-hour format and validates against building hours. Supports Oxford (King Library, Art & Architecture Library), Hamilton (Rentschler Library), and Middletown (Gardner-Harvey Library) campuses. Use 'building' parameter to specify campus location."
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        first_name: str = None,
        last_name: str = None,
        email: str = None,
        date: str = None,
        start_time: str = None,
        end_time: str = None,
        room_capacity: int = None,
        room_code_name: str = None,
        building: str = "king",
        **kwargs
    ) -> Dict[str, Any]:
        """Book a room with comprehensive validation."""
        try:
            # Validate all required parameters
            missing_params = []
            if not first_name:
                missing_params.append("firstName")
            if not last_name:
                missing_params.append("lastName")
            if not email:
                missing_params.append("email")
            if not date:
                missing_params.append("date")
            if not start_time:
                missing_params.append("startTime")
            if not end_time:
                missing_params.append("endTime")
            
            if missing_params:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Missing required parameters: {', '.join(missing_params)}. Please ask the customer to provide these."
                }
            
            # Validate email
            if not _validate_email(email):
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Email must be a valid @miamioh.edu address. Please provide your Miami University email."
                }
            
            # Parse date intelligently
            date_success, parsed_date, date_error = _parse_date_intelligent(date)
            if not date_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Date parsing error: {date_error}. Please provide a valid date (e.g., '11/12/2025', 'tomorrow', 'next Monday')."
                }
            date = parsed_date
            
            if log_callback:
                log_callback(f"📅 [Date Parsed] {parsed_date}")
            
            # Parse start time intelligently
            time_success, parsed_start_time, time_error = _parse_time_intelligent(start_time)
            if not time_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Start time parsing error: {time_error}. Please provide a valid time (e.g., '8pm', '20:00', '8:00 PM')."
                }
            start_time = parsed_start_time
            
            # Parse end time intelligently
            time_success, parsed_end_time, time_error = _parse_time_intelligent(end_time)
            if not time_success:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"End time parsing error: {time_error}. Please provide a valid time (e.g., '10pm', '22:00', '10:00 PM')."
                }
            end_time = parsed_end_time
            
            if log_callback:
                log_callback(f"🕐 [Time Parsed] {parsed_start_time} to {parsed_end_time}")
            
            # Validate booking duration (2 hour maximum)
            is_valid_duration, duration_hours = _validate_booking_duration(start_time, end_time)
            if not is_valid_duration:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Booking duration ({duration_hours:.1f} hours) exceeds the 2-hour maximum. Please reduce your booking time to 2 hours or less."
                }
            
            # Resolve building ID first for hours check
            building_key = building.lower().strip()
            building_id = BUILDINGS.get(building_key, DEFAULT_BUILDING)
            
            # Validate building hours (only for King and Art libraries)
            if building_id in ["2047", "4089"]:
                hours_valid, hours_message = await _check_building_hours(building_id, date, start_time, end_time)
                if not hours_valid:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": hours_message
                    }
            
            # Validate room selection
            if not room_capacity and not room_code_name:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Please specify either roomCapacity (number of people) or roomCodeName (e.g., '145', '211')."
                }
            
            if log_callback:
                log_callback(f"📝 [LibCal Comprehensive Reservation Tool] Booking for {first_name} {last_name}")
            
            # Check availability first
            availability_tool = LibCalEnhancedAvailabilityTool()
            availability_result = await availability_tool.execute(
                query=query,
                log_callback=log_callback,
                date=date,
                start_time=start_time,
                end_time=end_time,
                capacity=room_capacity,
                building=building
            )
            
            if not availability_result.get("success") or not availability_result.get("rooms_data"):
                # Try fallback LIBRARY buildings only (Oxford libraries)
                fallback_libraries = []
                if building != "king":
                    fallback_libraries.append("king")
                if building != "art":
                    fallback_libraries.append("art")
                
                for fallback_building in fallback_libraries:
                    if log_callback:
                        log_callback(f"🔄 [LibCal Comprehensive Reservation Tool] Trying {fallback_building} library")
                    
                    availability_result = await availability_tool.execute(
                        query=query,
                        log_callback=log_callback,
                        date=date,
                        start_time=start_time,
                        end_time=end_time,
                        capacity=room_capacity,
                        building=fallback_building
                    )
                    
                    if availability_result.get("success") and availability_result.get("rooms_data"):
                        building = fallback_building
                        if log_callback:
                            log_callback(f"✅ [LibCal Comprehensive Reservation Tool] Found availability at {fallback_building} library")
                        break
                
                if not availability_result.get("rooms_data"):
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": "No rooms available at any library building for the requested time. Please try a different time or contact the library at (513) 529-4141."
                    }
            
            rooms_data = availability_result.get("rooms_data", [])
            
            # Select room
            selected_room = None
            if room_code_name:
                # Find by name
                for room in rooms_data:
                    if room_code_name.lower() in room["name"].lower():
                        selected_room = room
                        break
                if not selected_room:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": f"Room {room_code_name} is not available at the requested time."
                    }
            else:
                # Find smallest room that fits
                for room in rooms_data:
                    if room["capacity"] >= room_capacity:
                        selected_room = room
                        break
                
                if not selected_room:
                    selected_room = rooms_data[0]  # Take smallest available
            
            # Create ISO 8601 timestamps with timezone
            offset = _detect_dst(date)
            start_formatted = start_time.replace("-", ":")
            end_formatted = end_time.replace("-", ":")
            
            # Build proper ISO 8601 timestamps (e.g., "2024-11-12T14:00:00-05:00")
            start_timestamp = f"{date}T{start_formatted}:00{offset}"
            end_timestamp = f"{date}T{end_formatted}:00{offset}"
            
            # Make booking
            is_production = NODE_ENV == "production"
            payload = {
                "start": start_timestamp,  # ISO 8601 format with timezone
                "fname": first_name,
                "lname": last_name,
                "email": email,
                "bookings": [
                    {
                        "id": selected_room["id"],  # Space ID from availability check
                        "to": end_timestamp  # ISO 8601 format with timezone
                    }
                ]
            }
            
            token = await _get_oauth_token()
            
            # Log POST request for debugging
            print(f"\n[LibCal POST Request]")
            print(f"URL: {LIBCAL_RESERVATION_URL}")
            print(f"Payload: {payload}")
            print(f"Headers: Authorization: Bearer {token[:20]}...\n")
            
            if log_callback:
                log_callback(f"🔄 [LibCal POST] {LIBCAL_RESERVATION_URL}")
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    LIBCAL_RESERVATION_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload
                )
                
                # Log response for debugging
                print(f"[LibCal POST Response]")
                print(f"Status Code: {response.status_code}")
                print(f"Response Body: {response.text}\n")
                
                if response.status_code == 200 or response.status_code == 201:
                    result = response.json()
                    booking_id = result.get("booking_id")
                    
                    # Log booking ID
                    print(f"[Booking Success] ID: {booking_id}")
                    
                    if not booking_id:
                        print(f"[WARNING] No booking_id in response: {result}")
                    
                    if log_callback:
                        log_callback(f"✅ [LibCal Comprehensive Reservation Tool] Booked room {selected_room['name']} - ID: {booking_id}")
                    
                    # Build confirmation message
                    if booking_id:
                        confirmation_text = f"{selected_room['name']} with capacity {selected_room['capacity']} is booked from {start_time} to {end_time} on {date} at {building.capitalize()} Library. Confirmation number: {booking_id}. A confirmation email has been sent to {email}."
                    else:
                        # Fallback if no booking_id
                        confirmation_text = f"{selected_room['name']} with capacity {selected_room['capacity']} is booked from {start_time} to {end_time} on {date} at {building.capitalize()} Library. A confirmation email has been sent to {email}."
                    
                    return {
                        "tool": self.name,
                        "success": True,
                        "booking_id": booking_id,
                        "text": confirmation_text
                    }
                else:
                    error_data = response.text
                    
                    # Handle specific errors
                    if "not a valid starting slot" in error_data or "not a valid ending slot" in error_data:
                        error_msg = "Time slot is not available for your room"
                    elif "exceeds the 120 minute booking limit" in error_data:
                        error_msg = "Booking exceeds the 120 minute daily booking limit"
                    else:
                        error_msg = f"Booking failed: {error_data}"
                    
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": error_msg
                    }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Comprehensive Reservation Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Booking failed. Please visit https://libcal.miamioh.edu/ to book directly."
            }

class LibCalCancelReservationTool(Tool):
    """Cancel a room reservation with email verification."""
    
    @property
    def name(self) -> str:
        return "libcal_cancel_reservation"
    
    @property
    def description(self) -> str:
        return "Cancel a room reservation. Requires confirmation number and email address for verification."
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        booking_id: str = None,
        email: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Cancel reservation after verifying email."""
        try:
            # Validate required parameters
            if not booking_id:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Missing confirmation number. Please provide the booking confirmation number."
                }
            
            if not email:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Missing email address. Please provide the email address used for the booking."
                }
            
            # Validate email format
            if not _validate_email(email):
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Email must be a valid @miamioh.edu address."
                }
            
            # Check if LIBCAL_BOOKING_INFO_URL is configured
            if not LIBCAL_BOOKING_INFO_URL:
                if log_callback:
                    log_callback(f"❌ [LibCal Cancel] LIBCAL_BOOKING_INFO_URL not configured")
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Cancellation service is not configured. Please contact the library at (513) 529-4141 to cancel your reservation."
                }
            
            if log_callback:
                log_callback(f"🔍 [LibCal Cancel] Verifying booking {booking_id}")
            
            token = await _get_oauth_token()
            
            if log_callback:
                log_callback(f"✅ [LibCal Cancel] OAuth token obtained")
            
            # Step 1: Get booking information to verify email
            async with httpx.AsyncClient(timeout=10) as client:
                # GET booking info
                booking_info_url = f"{LIBCAL_BOOKING_INFO_URL}/{booking_id}"
                if log_callback:
                    log_callback(f"📡 [LibCal Cancel] GET {booking_info_url}")
                
                info_response = await client.get(
                    booking_info_url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if log_callback:
                    log_callback(f"📊 [LibCal Cancel] GET response: status={info_response.status_code}")
                
                if info_response.status_code != 200:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": f"Reservation with confirmation number {booking_id} not found. Please check the confirmation number and try again."
                    }
                
                # Parse booking data
                booking_data = info_response.json()
                
                if log_callback:
                    log_callback(f"📦 [LibCal Cancel] Booking data type: {type(booking_data)}, is_list: {isinstance(booking_data, list)}")
                
                # Handle array response
                if isinstance(booking_data, list):
                    if len(booking_data) == 0:
                        if log_callback:
                            log_callback(f"❌ [LibCal Cancel] Empty booking data array")
                        return {
                            "tool": self.name,
                            "success": False,
                            "text": f"Reservation with confirmation number {booking_id} not found."
                        }
                    booking_info = booking_data[0]
                else:
                    booking_info = booking_data
                
                # Extract email from booking
                booking_email = booking_info.get("email", "").lower().strip()
                provided_email = email.lower().strip()
                
                if log_callback:
                    log_callback(f"📝 [LibCal Cancel] Booking found, verifying email (match: {booking_email == provided_email})")
                
                # Step 2: Verify email matches
                if booking_email != provided_email:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": f"The email address does not match the booking records. Please provide the email address that was used to make this reservation."
                    }
                
                if log_callback:
                    log_callback(f"✅ [LibCal Cancel] Email verified, proceeding with cancellation")
                
                # Step 3: Cancel the booking
                cancel_url = f"{LIBCAL_CANCEL_URL}/{booking_id}"
                if log_callback:
                    log_callback(f"📡 [LibCal Cancel] POST {cancel_url}")
                
                cancel_response = await client.post(
                    cancel_url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if log_callback:
                    log_callback(f"📊 [LibCal Cancel] POST response: status={cancel_response.status_code}")
                
                if cancel_response.status_code == 200:
                    data = cancel_response.json()
                    if isinstance(data, list) and len(data) > 0:
                        if data[0].get("cancelled"):
                            if log_callback:
                                log_callback(f"✅ [LibCal Cancel] Booking cancelled successfully")
                            
                            # Extract room info for confirmation message
                            room_name = booking_info.get("item_name", "Study room")
                            from_date = booking_info.get("fromDate", "")
                            
                            return {
                                "tool": self.name,
                                "success": True,
                                "text": f"Your reservation for {room_name} (confirmation number: {booking_id}) has been cancelled successfully. You will receive a cancellation confirmation email at {email}."
                            }
                        else:
                            error = data[0].get("error", "Unknown error")
                            return {
                                "tool": self.name,
                                "success": False,
                                "text": f"Cancellation failed: {error}"
                            }
                
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Could not cancel booking. Please visit https://www.lib.miamioh.edu/use/spaces/room-reservations/ or contact the library at (513) 529-4141."
                }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Cancel] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Cancellation failed. Please visit https://www.lib.miamioh.edu/use/spaces/room-reservations/ or contact the library."
            }


# Ask Us Chat Service ID from environment
LIBCAL_ASKUS_ID = os.getenv("LIBCAL_ASKUS_ID", "")


class AskUsChatHoursTool(Tool):
    """Tool to check Ask Us Chat Service business hours."""
    
    @property
    def name(self) -> str:
        return "askus_chat_hours"
    
    @property
    def description(self) -> str:
        return "Check Ask Us Chat Service business hours - live chat with a librarian. Use this when users ask about chat service hours, librarian availability for live chat, or when to talk to a human librarian."
    
    async def execute(
        self, 
        query: str, 
        log_callback=None,
        date: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Get Ask Us Chat Service hours for today or specified date."""
        try:
            if log_callback:
                log_callback("🔍 [Ask Us Hours Tool] Checking chat service hours")
            
            if not LIBCAL_ASKUS_ID:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Ask Us Chat hours configuration not available. Please visit https://www.lib.miamioh.edu/ask/"
                }
            
            # Use today if no date specified
            if not date:
                from zoneinfo import ZoneInfo
                est = ZoneInfo("America/New_York")
                date = datetime.now(est).strftime("%Y-%m-%d")
            else:
                # Parse the date if provided
                date_success, parsed_date, date_error = _parse_date_intelligent(date)
                if not date_success:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": f"Date parsing error: {date_error}"
                    }
                date = parsed_date
            
            # Calculate week range (Monday to Sunday)
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            day_of_week = date_obj.weekday()
            monday = date_obj - timedelta(days=day_of_week)
            sunday = monday + timedelta(days=6)
            
            from_date = monday.strftime("%Y-%m-%d")
            to_date = sunday.strftime("%Y-%m-%d")
            
            token = await _get_oauth_token()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{LIBCAL_HOUR_URL}/{LIBCAL_ASKUS_ID}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"from": from_date, "to": to_date}
                )
                response.raise_for_status()
                data = response.json()
                
                if not data or len(data) == 0:
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": "No hours data available. Please visit https://www.lib.miamioh.edu/ask/"
                    }
                
                # Extract hours by day
                location = data[0]
                dates = location.get("dates", {})
                
                hours_text = f"**{location.get('name', 'Ask Us Chat Service')} Hours (Week of {monday.strftime('%B %d')}):**\n\n"
                hours_text += "_Chat with a librarian online during these hours:_\n\n"
                
                day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                current_date = monday
                
                # Check if currently open
                from zoneinfo import ZoneInfo
                est = ZoneInfo("America/New_York")
                now = datetime.now(est)
                today_str = now.strftime("%Y-%m-%d")
                is_currently_open = False
                
                for day_name in day_names:
                    date_str = current_date.strftime("%Y-%m-%d")
                    day_data = dates.get(date_str)
                    
                    is_today = date_str == today_str
                    
                    if day_data and day_data.get("status") == "open" and day_data.get("hours"):
                        hours_list = day_data["hours"]
                        hours_str = ", ".join([f"{h['from']} - {h['to']}" for h in hours_list])
                        
                        # Check if currently within hours
                        if is_today:
                            for h in hours_list:
                                try:
                                    open_time = datetime.strptime(h['from'], "%I:%M%p").replace(
                                        year=now.year, month=now.month, day=now.day, tzinfo=est
                                    )
                                    close_time = datetime.strptime(h['to'], "%I:%M%p").replace(
                                        year=now.year, month=now.month, day=now.day, tzinfo=est
                                    )
                                    if open_time <= now <= close_time:
                                        is_currently_open = True
                                except:
                                    pass
                        
                        today_marker = " ← **TODAY**" if is_today else ""
                        hours_text += f"• **{day_name}** ({current_date.strftime('%m/%d')}): {hours_str}{today_marker}\n"
                    else:
                        today_marker = " ← **TODAY**" if is_today else ""
                        hours_text += f"• **{day_name}** ({current_date.strftime('%m/%d')}): Closed{today_marker}\n"
                    
                    current_date += timedelta(days=1)
                
                # Add current status
                if is_currently_open:
                    hours_text += "\n✅ **The Ask Us Chat is currently OPEN!** Click the chat widget on the library website to connect with a librarian.\n"
                else:
                    hours_text += "\n⏰ **The Ask Us Chat is currently closed.** Please submit a ticket or check back during business hours.\n"
                
                hours_text += "\n**Need help outside these hours?**\n"
                hours_text += "• Submit a ticket: https://www.lib.miamioh.edu/ask/\n"
                hours_text += "• Call: (513) 529-4141\n"
                
                if log_callback:
                    log_callback("✅ [Ask Us Hours Tool] Hours retrieved successfully")
                
                return {
                    "tool": self.name,
                    "success": True,
                    "text": hours_text
                }
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Ask Us Hours Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Couldn't retrieve Ask Us Chat hours. Please visit https://www.lib.miamioh.edu/ask/"
            }
