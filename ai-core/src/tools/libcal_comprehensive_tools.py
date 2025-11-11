"""Comprehensive LibCal tools matching legacy NestJS functionality."""
import os
import re
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
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

def _detect_dst(date_str: str) -> str:
    """Detect if date is in DST (EDT) or EST."""
    test_date = datetime.strptime(date_str, "%Y-%m-%d")
    # March-November is typically EDT, but this is simplified
    month = test_date.month
    if 3 <= month <= 11:
        return "-04:00"  # EDT
    else:
        return "-05:00"  # EST

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
                date = datetime.now().strftime("%Y-%m-%d")
            
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
        return "Check room availability with smart capacity fallback. Supports Oxford (King Library, Art & Architecture Library), Hamilton (Rentschler Library), and Middletown (Gardner-Harvey Library) campuses. Use 'building' parameter to specify location (e.g., 'king', 'rentschler', 'gardner-harvey')."
    
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
            
            # Convert time format HH-MM to HH:MM
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
        return "Book a study room with full validation (requires firstName, lastName, @miamioh.edu email, date, time). Supports Oxford (King Library, Art & Architecture Library), Hamilton (Rentschler Library), and Middletown (Gardner-Harvey Library) campuses. Use 'building' parameter to specify campus location."
    
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
            
            # Create timestamps with timezone
            offset = _detect_dst(date)
            start_formatted = start_time.replace("-", ":")
            end_formatted = end_time.replace("-", ":")
            
            start_timestamp = f"{date}T{start_formatted}:00{offset}"
            end_timestamp = f"{date}T{end_formatted}:00{offset}"
            
            # Make booking
            is_production = NODE_ENV == "production"
            payload = {
                "start": datetime.fromisoformat(start_timestamp).isoformat(),
                "fname": first_name,
                "lname": last_name,
                "email": email,
                "bookings": [
                    {
                        "id": selected_room["id"],
                        "to": datetime.fromisoformat(end_timestamp).isoformat()
                    }
                ]
            }
            
            if not is_production:
                payload["test"] = 1
            
            token = await _get_oauth_token()
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    LIBCAL_RESERVATION_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload
                )
                
                if response.status_code == 200 or response.status_code == 201:
                    result = response.json()
                    booking_id = result.get("booking_id")
                    
                    if log_callback:
                        log_callback(f"✅ [LibCal Comprehensive Reservation Tool] Booked room {selected_room['name']}")
                    
                    return {
                        "tool": self.name,
                        "success": True,
                        "booking_id": booking_id,
                        "text": f"{selected_room['name']} with capacity {selected_room['capacity']} is booked from {start_time} to {end_time} on {date} at {building.capitalize()} Library. Confirmation number: {booking_id}. A confirmation email has been sent to {email}."
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
    """Cancel a room reservation."""
    
    @property
    def name(self) -> str:
        return "libcal_cancel_reservation"
    
    @property
    def description(self) -> str:
        return "Cancel a room reservation using booking ID"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        booking_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Cancel reservation."""
        try:
            if not booking_id:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Missing booking ID. Please provide the booking ID to cancel."
                }
            
            if log_callback:
                log_callback(f"🗑️ [LibCal Cancel Reservation Tool] Cancelling booking {booking_id}")
            
            token = await _get_oauth_token()
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{LIBCAL_CANCEL_URL}/{booking_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        if data[0].get("cancelled"):
                            if log_callback:
                                log_callback(f"✅ [LibCal Cancel Reservation Tool] Booking cancelled")
                            return {
                                "tool": self.name,
                                "success": True,
                                "text": f"Room reservation with ID {booking_id} has been cancelled successfully."
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
                    "text": f"Could not cancel booking {booking_id}. Please contact the library."
                }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Cancel Reservation Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Cancellation failed. Please visit https://libcal.miamioh.edu/ or contact the library."
            }
