"""Comprehensive LibCal Agent with all tools."""
from typing import Dict, Any
import re
from datetime import datetime, timedelta
import pytz
try:
    import holidays
    HOLIDAYS_AVAILABLE = True
except ImportError:
    HOLIDAYS_AVAILABLE = False
try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False
from src.agents.base_agent import Agent
from src.tools.libcal_comprehensive_tools import (
    LibCalWeekHoursTool,
    LibCalEnhancedAvailabilityTool,
    LibCalComprehensiveReservationTool,
    LibCalCancelReservationTool,
    AskUsChatHoursTool
)

class LibCalComprehensiveAgent(Agent):
    """Comprehensive LibCal agent with hours, room search, booking, and cancellation."""
    
    @property
    def name(self) -> str:
        return "LibCal"
    
    def _register_tools(self):
        """Register all LibCal tools."""
        self.register_tool(LibCalWeekHoursTool())
        self.register_tool(LibCalEnhancedAvailabilityTool())
        self.register_tool(LibCalComprehensiveReservationTool())
        self.register_tool(LibCalCancelReservationTool())
        self.register_tool(AskUsChatHoursTool())
    
    def _extract_date_from_query(self, query: str) -> str | None:
        """Extract date reference from query and convert to YYYY-MM-DD format.
        
        Handles:
        - US holidays: New Year, MLK Day, Presidents Day, Memorial Day, Independence Day,
          Labor Day, Columbus Day, Veterans Day, Thanksgiving, Christmas
        - Relative dates: tomorrow, next week, day after tomorrow (via dateparser)
        - Explicit dates: 12/25/2025, January 1st, Dec 25
        """
        q_lower = query.lower()
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)
        current_year = now.year
        
        # Try dateparser first for explicit dates and relative expressions
        if DATEPARSER_AVAILABLE:
            # Configure dateparser to prefer future dates and US format
            parsed = dateparser.parse(
                query,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'TIMEZONE': 'America/New_York',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'DATE_ORDER': 'MDY'  # US format: month/day/year
                }
            )
            if parsed:
                # Only use if it found a clear date pattern (not just random numbers)
                date_patterns = [
                    r'\d{1,2}/\d{1,2}(/\d{2,4})?',  # 12/25 or 12/25/2025
                    r'\d{4}-\d{2}-\d{2}',  # 2025-12-25
                    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}',  # January 1
                    r'\b(tomorrow|today|yesterday)\b',
                    r'\bnext\s+(week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
                    r'\blast\s+(week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
                    r'\bday\s+(after|before)\s+(tomorrow|yesterday)\b',
                ]
                if any(re.search(pattern, q_lower) for pattern in date_patterns):
                    return parsed.strftime("%Y-%m-%d")
        
        # Check for holiday keywords using holidays package
        if HOLIDAYS_AVAILABLE:
            us_holidays = holidays.US(years=[current_year, current_year + 1])
            
            # Holiday name mapping (handles variations)
            holiday_keywords = {
                'new year': 'New Year\'s Day',
                'mlk': 'Martin Luther King Jr. Day',
                'martin luther king': 'Martin Luther King Jr. Day',
                'presidents day': 'Washington\'s Birthday',
                'president\'s day': 'Washington\'s Birthday',
                'memorial day': 'Memorial Day',
                'independence day': 'Independence Day',
                'fourth of july': 'Independence Day',
                '4th of july': 'Independence Day',
                'july 4': 'Independence Day',
                'labor day': 'Labor Day',
                'columbus day': 'Columbus Day',
                'veterans day': 'Veterans Day',
                'thanksgiving': 'Thanksgiving',
                'christmas': 'Christmas Day',
            }
            
            for keyword, official_name in holiday_keywords.items():
                if keyword in q_lower:
                    # Find this holiday in the next 365 days
                    for date, name in sorted(us_holidays.items()):
                        if official_name in name:
                            # Return the next occurrence of this holiday
                            if date >= now.date():
                                return date.strftime("%Y-%m-%d")
                            # If past this year, try next year
                            elif date.year == current_year:
                                next_year_date = date.replace(year=current_year + 1)
                                return next_year_date.strftime("%Y-%m-%d")
        
        # Fallback: Manual handling for New Year and Christmas if packages not available
        if not HOLIDAYS_AVAILABLE:
            if re.search(r'\bnew\s*year', q_lower):
                if now.month >= 11:
                    return f"{current_year + 1}-01-01"
                else:
                    return f"{current_year}-01-01"
            
            if re.search(r'\bchristmas', q_lower):
                if now.month >= 11:
                    return f"{current_year}-12-25"
                else:
                    return f"{current_year}-12-25"
        
        return None
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate LibCal tool based on query keywords."""
        q_lower = query.lower()
        
        # Ask Us Chat hours keywords
        if any(phrase in q_lower for phrase in [
            "ask us", "chat hours", "chat service", "librarian chat", 
            "talk to librarian", "human librarian hours", "chat with librarian",
            "when can i chat", "live chat hours", "librarian availability"
        ]):
            return "askus_chat_hours"
        
        # Cancellation keywords
        if any(word in q_lower for word in ["cancel", "remove", "delete reservation", "cancel booking"]):
            return "libcal_cancel_reservation"
        
        # Booking keywords (must come before room search)
        if any(word in q_lower for word in ["book", "reserve", "make a reservation", "schedule a room"]):
            return "libcal_comprehensive_reservation"
        
        # Room search keywords
        if any(word in q_lower for word in ["room", "study room", "study space", "available room", "find room"]):
            return "libcal_enhanced_availability"
        
        # Hours keywords (default for LibCal)
        return "libcal_week_hours"
    
    def _extract_building_from_query(self, query: str) -> str:
        """Extract building/library/space name from query.
        
        Supports: King, Art, Rentschler, Gardner-Harvey, Hamilton, Middletown,
                  Makerspace, Special Collections, and more
        """
        q_lower = query.lower()
        
        # Space keywords (check first - more specific)
        if any(word in q_lower for word in ["special collections", "special collection", "university archives"]):
            return "special collections"
        if any(word in q_lower for word in ["makerspace", "maker space", "makespace"]):
            return "makerspace"
        
        # Library keywords
        if "art & architecture" in q_lower or "art and architecture" in q_lower or "art library" in q_lower:
            return "art"
        if "gardner-harvey" in q_lower or "gardner harvey" in q_lower:
            return "gardner-harvey"
        if "rentschler" in q_lower or "hamilton" in q_lower:
            return "hamilton"
        if "middletown" in q_lower:
            return "middletown"
        if "art" in q_lower:
            return "art"
        if "king" in q_lower:
            return "king"
        
        # Default to King Library
        return "king"
    
    async def execute(self, query: str, log_callback=None, **kwargs) -> Dict[str, Any]:
        """Execute the agent with date and building extraction for hours queries."""
        # Route to specific tool
        tool_name = await self.route_to_tool(query)
        
        # For hours queries, extract date and building if present
        if tool_name == "libcal_week_hours":
            # Extract date
            extracted_date = self._extract_date_from_query(query)
            if extracted_date and "date" not in kwargs:
                kwargs["date"] = extracted_date
                if log_callback:
                    log_callback(f"📅 [LibCal Agent] Extracted date from query: {extracted_date}")
            
            # Extract building/space
            if "building" not in kwargs:
                building = self._extract_building_from_query(query)
                kwargs["building"] = building
                if log_callback:
                    log_callback(f"🏛️ [LibCal Agent] Extracted building from query: {building}")
        
        # Call parent execute method
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "agent": self.name,
                "tool": tool_name,
                "success": False,
                "error": f"Tool '{tool_name}' not registered"
            }
        
        # Execute the tool
        result = await tool.execute(query, log_callback=log_callback, **kwargs)
        result["agent"] = self.name
        return result
