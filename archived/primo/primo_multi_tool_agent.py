"""Primo/Alma Agent with multiple tools (search, availability, full-text links)."""
from typing import Dict, Any
from src.agents.base_agent import Agent
from src.tools.primo_tools import PrimoBibliographicSearchTool, PrimoAvailabilityTool

class PrimoAgent(Agent):
    """Agent for discovery search - routes to catalog search or availability check."""
    
    @property
    def name(self) -> str:
        return "Primo"
    
    def _register_tools(self):
        """Register Primo tools."""
        self.register_tool(PrimoBibliographicSearchTool())
        self.register_tool(PrimoAvailabilityTool())
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate Primo tool based on query."""
        q_lower = query.lower()
        
        # Availability check keywords
        availability_keywords = ["available", "in stock", "can i get", "is it available", "check out"]
        if any(keyword in q_lower for keyword in availability_keywords) and len(q_lower.split()) < 15:
            # Short queries about availability
            return "primo_availability"
        
        # Default to bibliographic search
        return "primo_search"
