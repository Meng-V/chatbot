"""Comprehensive Google Site Search Agent."""
from typing import Dict, Any
from src.agents.base_agent import Agent
from src.tools.google_site_enhanced_tools import (
    GoogleSiteEnhancedSearchTool,
    BorrowingPolicySearchTool
)
from src.tools.citation_tools import CitationAssistTool
from src.tools.circulation_policy_tool import CirculationPolicyTool

class GoogleSiteComprehensiveAgent(Agent):
    """Comprehensive Google Site agent with specialized tools."""
    
    @property
    def name(self) -> str:
        return "GoogleSite"
    
    def _register_tools(self):
        """Register all Google Site Search tools."""
        self.register_tool(GoogleSiteEnhancedSearchTool())
        self.register_tool(CirculationPolicyTool())  # Weaviate-based policy lookup (URL-only)
        self.register_tool(CitationAssistTool())
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate tool based on query type."""
        print(f"🔍 [DEBUG] GoogleSiteComprehensiveAgent.route_to_tool() called with query: {query[:50]}...")
        print(f"🔍 [DEBUG] Available tools: {list(self.tools.keys())}")
        
        q_lower = query.lower()
        
        # Citation keywords → Citation tool
        if any(word in q_lower for word in ["cite", "citation", "apa", "mla", "chicago", "turabian", "ama", "bibliography", "reference"]):
            print(f"🔍 [DEBUG] Routing to citation_assist (citation keywords detected)")
            return "citation_assist"
        
        # ALPHA TESTING: Use Google Site Search for all policy queries
        # (Weaviate collections may not be available, and we want to test Google integration)
        # Circulation/ILL policy keywords → Google site search
        # NOTE: Hours queries go to LibCal agent, not here
        # if any(word in q_lower for word in [
        #     "renew", "renewal",
        #     "borrow", "checkout", "check out",
        #     "loan period",
        #     "fine", "fee", "overdue",
        #     "delivery", "mail", "home delivery",
        #     "ill", "interlibrary", "inter-library",
        #     "reserve", "course reserve",
        #     "recall", "ohiolink", "affiliated patron"
        # ]):
        #     return "circulation_policy_lookup"
        
        # Default to general site search (including policy queries for alpha testing)
        print(f"🔍 [DEBUG] Routing to google_site_enhanced_search (default)")
        return "google_site_enhanced_search"
