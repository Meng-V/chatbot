"""Comprehensive LibCal Agent with all tools."""
from typing import Dict, Any, Optional
import re
import os
import json
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
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
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
    
    async def route_to_tool(self, query: str, intent_summary: str = "", conversation_history: list = None) -> str:
        """Route to appropriate LibCal tool based on query keywords and conversation context."""
        q_lower = query.lower()
        context_lower = (intent_summary or "").lower()
        
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
        if any(word in q_lower for word in ["reserve", "make a reservation", "schedule a room"]):
            return "libcal_comprehensive_reservation"
        
        # Check intent summary for booking context (from intent normalizer)
        if any(word in context_lower for word in ["booking", "reservation", "reserve", "book a room"]):
            return "libcal_comprehensive_reservation"
        
        # Check conversation history for ongoing booking context
        if conversation_history:
            for msg in conversation_history[-6:]:
                content = (msg.get("content", "") or "").lower()
                if any(phrase in content for phrase in [
                    "reserve", "reservation", "room booking",
                    "confirmation number", "room reserved",
                    "i still need", "complete your room reservation",
                    "finalize your", "confirm which date",
                ]):
                    return "libcal_comprehensive_reservation"
        
        # Room search keywords
        if any(word in q_lower for word in ["room", "study room", "study space", "available room", "find room"]):
            return "libcal_enhanced_availability"
        
        # Hours keywords (default for LibCal)
        return "libcal_week_hours"
    
    def _extract_building_from_query(self, query: str) -> str:
        """Extract building/library/space name from query.
        
        Delegates to the shared function in libcal_comprehensive_tools
        which handles all library names, spaces, and unknown building detection.
        """
        from src.tools.libcal_comprehensive_tools import _extract_building_from_query as _shared_extract
        return _shared_extract(query)
    
    async def _extract_booking_params(self, query: str, log_callback=None) -> Dict[str, Any]:
        """Use LLM to extract booking parameters from natural language.
        
        Parses free-form text like 'Meng Qu, qum@miamioh.edu, tomorrow, 5-6 afternoon, party for 2'
        into structured params: first_name, last_name, email, date, start_time, end_time, room_capacity.
        Also handles US holidays and relative dates.
        """
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)
        
        system_prompt = f"""You are a booking parameter extractor for Miami University Libraries.
Extract booking details from the user's message into structured JSON.

TODAY'S DATE: {now.strftime('%A, %B %d, %Y')} (Eastern Time)
TOMORROW: {(now + timedelta(days=1)).strftime('%A, %B %d, %Y')}

Rules:
- "tomorrow" = {(now + timedelta(days=1)).strftime('%Y-%m-%d')}
- "today" = {now.strftime('%Y-%m-%d')}
- For relative days ("next Monday", "this Friday"), calculate from today
- US holidays: resolve to their actual date for the current/next year
  (e.g., "Thanksgiving" = 4th Thursday of November, "MLK Day" = 3rd Monday of January)
- Convert ALL times to 24-hour HH:MM format:
  - "5 afternoon" / "5pm" / "5 in the afternoon" = "17:00"
  - "5-6 afternoon" = start "17:00", end "18:00"
  - "2-4pm" = start "14:00", end "16:00" 
  - "10am to noon" = start "10:00", end "12:00"
  - "morning" without specific time = don't guess, leave null
- Extract name parts: first_name and last_name separately
- Email must contain @miamioh.edu to be valid
- room_capacity = number of people ("party of 2" = 2, "4 people" = 4, "for 2" = 2)

Respond with ONLY valid JSON:
{{
  "first_name": "string or null",
  "last_name": "string or null",
  "email": "string or null",
  "date": "YYYY-MM-DD or null",
  "start_time": "HH:MM (24h) or null",
  "end_time": "HH:MM (24h) or null",
  "room_capacity": integer or null
}}"""
        
        try:
            model_name = os.getenv("OPENAI_MODEL", "o4-mini")
            api_key = os.getenv("OPENAI_API_KEY", "")
            llm_kwargs = {"model": model_name, "api_key": api_key}
            if not model_name.startswith("o"):
                llm_kwargs["temperature"] = 0
            llm = ChatOpenAI(**llm_kwargs)
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f'Extract booking params from: "{query}"')
            ]
            
            response = await llm.ainvoke(messages)
            text = response.content.strip()
            
            # Handle markdown code blocks
            if text.startswith("```"):
                lines = text.split("\n")
                json_lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(json_lines)
            
            params = json.loads(text)
            
            if log_callback:
                extracted = {k: v for k, v in params.items() if v is not None}
                log_callback(f"📋 [LibCal Agent] LLM extracted booking params: {extracted}")
            
            return params
            
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ [LibCal Agent] LLM param extraction failed: {e}, falling back to regex")
            return self._extract_booking_params_regex(query)
    
    def _extract_booking_params_regex(self, query: str) -> Dict[str, Any]:
        """Regex fallback for booking parameter extraction."""
        params = {
            "first_name": None, "last_name": None, "email": None,
            "date": None, "start_time": None, "end_time": None, "room_capacity": None
        }
        
        # Extract email
        email_match = re.search(r'[\w.+-]+@miamioh\.edu', query, re.IGNORECASE)
        if email_match:
            params["email"] = email_match.group(0)
        
        # Extract date using existing method
        extracted_date = self._extract_date_from_query(query)
        if extracted_date:
            params["date"] = extracted_date
        
        # Extract capacity
        cap_match = re.search(r'(?:party\s+(?:of|for)|for|group\s+of)\s+(\d+)', query, re.IGNORECASE)
        if cap_match:
            params["room_capacity"] = int(cap_match.group(1))
        else:
            cap_match = re.search(r'(\d+)\s*(?:people|persons|ppl)', query, re.IGNORECASE)
            if cap_match:
                params["room_capacity"] = int(cap_match.group(1))
        
        return params

    async def execute(self, query: str, log_callback=None, **kwargs) -> Dict[str, Any]:
        """Execute the agent with date and building extraction for all tool types."""
        conversation_history = kwargs.pop("conversation_history", [])
        intent_summary = kwargs.pop("intent_summary", "")
        
        # Route to specific tool - use intent summary and conversation history for context
        tool_name = await self.route_to_tool(
            query,
            intent_summary=intent_summary,
            conversation_history=conversation_history
        )
        
        if log_callback:
            log_callback(f"🔧 [LibCal Agent] Routed to tool: {tool_name}")
        
        # For booking/availability from conversation context, build combined query
        # so the LLM can extract params from the full multi-turn conversation
        extraction_query = query
        if tool_name in ("libcal_comprehensive_reservation", "libcal_enhanced_availability") and conversation_history:
            # Build combined context from conversation history + current message
            history_parts = []
            for msg in conversation_history[-6:]:
                role = "User" if msg.get("type") == "user" else "Assistant"
                content = msg.get("content", "")
                if content:
                    history_parts.append(f"{role}: {content}")
            if history_parts:
                extraction_query = "\n".join(history_parts) + f"\nUser: {query}"
                if log_callback:
                    log_callback(f"📋 [LibCal Agent] Using multi-turn context for param extraction")
        
        # Extract building/space for ALL LibCal tools (hours, availability, reservation)
        if "building" not in kwargs:
            # Try extracting building from both current query and conversation context
            building = self._extract_building_from_query(query)
            if building.startswith("UNKNOWN:") and conversation_history:
                # Try extracting from conversation history
                for msg in conversation_history[-6:]:
                    content = msg.get("content", "") or ""
                    hist_building = self._extract_building_from_query(content)
                    if not hist_building.startswith("UNKNOWN:"):
                        building = hist_building
                        break
            if log_callback:
                log_callback(f"🏛️ [LibCal Agent] Extracted building from query: {building}")
            
            # Handle unknown building names for reservation/availability tools
            if building.startswith("UNKNOWN:") and tool_name in ("libcal_comprehensive_reservation", "libcal_enhanced_availability"):
                unknown_name = building.replace("UNKNOWN:", "").strip()
                if log_callback:
                    log_callback(f"⚠️ [LibCal Agent] Unknown building '{unknown_name}' - listing valid options")
                result = {
                    "agent": self.name,
                    "tool": tool_name,
                    "success": False,
                    "text": (
                        f"'{unknown_name.title()}' is not a recognized Miami University library for room reservations. "
                        f"Study rooms are available at:\n"
                        f"• **King Library** (Oxford main campus)\n"
                        f"• **Wertz Art & Architecture Library** (Oxford)\n"
                        f"• **Rentschler Library** (Hamilton campus)\n"
                        f"• **Gardner-Harvey Library** (Middletown campus)\n\n"
                        f"You can also book directly online:\n"
                        f"• Oxford & Middletown: https://muohio.libcal.com/allspaces\n"
                        f"• Hamilton: https://muohio.libcal.com/reserve/hamilton\n\n"
                        f"Which library would you like to reserve a room at?"
                    ),
                }
                return result
            
            # For unknown buildings on hours queries, default to king
            if building.startswith("UNKNOWN:"):
                building = "king"
            kwargs["building"] = building
        
        # For reservation/availability tools, extract ALL booking params via LLM
        if tool_name in ("libcal_comprehensive_reservation", "libcal_enhanced_availability"):
            booking_params = await self._extract_booking_params(extraction_query, log_callback)
            
            # Merge extracted params into kwargs (don't overwrite already-provided ones)
            param_mapping = {
                "first_name": "first_name",
                "last_name": "last_name",
                "email": "email",
                "date": "date",
                "start_time": "start_time",
                "end_time": "end_time",
                "room_capacity": "room_capacity",
            }
            for src_key, dst_key in param_mapping.items():
                val = booking_params.get(src_key)
                if val is not None and dst_key not in kwargs:
                    kwargs[dst_key] = val
            
            if log_callback:
                filled = [k for k in param_mapping.values() if k in kwargs and kwargs[k] is not None]
                log_callback(f"📝 [LibCal Agent] Booking params ready: {filled}")
        
        # For hours queries, also extract date
        elif tool_name == "libcal_week_hours":
            extracted_date = self._extract_date_from_query(query)
            if extracted_date and "date" not in kwargs:
                kwargs["date"] = extracted_date
                if log_callback:
                    log_callback(f"📅 [LibCal Agent] Extracted date from query: {extracted_date}")
        
        # Call parent execute method
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "agent": self.name,
                "tool": tool_name,
                "success": False,
                "error": f"Tool '{tool_name}' not registered"
            }
        
        # Execute the tool with error handling
        try:
            result = await tool.execute(query, log_callback=log_callback, **kwargs)
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibCal Agent] Tool '{tool_name}' threw exception: {str(e)}")
            # Look up library-specific phone from DB
            phone = await self._get_library_phone(kwargs.get("building", "king"))
            result = {
                "tool": tool_name,
                "success": False,
                "text": f"I'm having trouble with the {tool_name.replace('_', ' ')} service right now. Please visit https://www.lib.miamioh.edu/ or call {phone} for assistance.",
                "error": str(e)
            }
        result["agent"] = self.name
        return result
    
    async def _get_library_phone(self, building: str) -> str:
        """Look up the correct phone number for a library from the database."""
        try:
            from src.services.location_service import get_location_service
            location_service = get_location_service()
            contact_info = await location_service.get_library_contact_info(building)
            if contact_info and contact_info.get("phone"):
                return contact_info["phone"]
        except Exception:
            pass
        # Fallback to King Library main number
        return "(513) 529-4141"
