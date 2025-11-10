"""Comprehensive Google Site Search Agent."""
from typing import Dict, Any
from src.agents.base_agent import Agent
from src.tools.google_site_enhanced_tools import (
    GoogleSiteEnhancedSearchTool,
    BorrowingPolicySearchTool
)
from src.tools.citation_tools import CitationAssistTool

class GoogleSiteComprehensiveAgent(Agent):
    """Comprehensive Google Site agent with specialized tools."""
    
    @property
    def name(self) -> str:
        return "GoogleSite"
    
    def _register_tools(self):
        """Register all Google Site Search tools."""
        self.register_tool(GoogleSiteEnhancedSearchTool())
        self.register_tool(BorrowingPolicySearchTool())
        self.register_tool(CitationAssistTool())
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate tool based on query type."""
        q_lower = query.lower()
        
        # Citation keywords → Citation tool
        if any(word in q_lower for word in ["cite", "citation", "apa", "mla", "chicago", "turabian", "ama", "bibliography", "reference"]):
            return "citation_assist"
        
        # Borrowing policy keywords → Borrowing policy tool
        if any(word in q_lower for word in [
            "renew", "renewal",
            "borrow", "checkout", "check out",
            "loan", "loan period",
            "fine", "fee", "overdue",
            "delivery", "mail", "home delivery",
            "ill", "interlibrary", "inter-library",
            "reserve", "course reserve",
            "recall"
        ]):
            return "borrowing_policy_search"
        
        # Default to general site search
        return "google_site_enhanced_search"
