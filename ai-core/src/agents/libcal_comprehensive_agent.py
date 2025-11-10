"""Comprehensive LibCal Agent with all tools."""
from typing import Dict, Any
from src.agents.base_agent import Agent
from src.tools.libcal_comprehensive_tools import (
    LibCalWeekHoursTool,
    LibCalEnhancedAvailabilityTool,
    LibCalComprehensiveReservationTool,
    LibCalCancelReservationTool
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
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate LibCal tool based on query keywords."""
        q_lower = query.lower()
        
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
