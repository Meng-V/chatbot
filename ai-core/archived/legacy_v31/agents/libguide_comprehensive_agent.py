"""Comprehensive LibGuide Agent with subject and course lookup."""
from typing import Dict, Any
from src.agents.base_agent import Agent
from src.tools.libguide_comprehensive_tools import (
    LibGuideSubjectLookupTool,
    LibGuideCourseLookupTool
)

class LibGuideComprehensiveAgent(Agent):
    """Comprehensive LibGuide agent with subject and course lookup."""
    
    @property
    def name(self) -> str:
        return "LibGuide"
    
    def _register_tools(self):
        """Register all LibGuide tools."""
        self.register_tool(LibGuideSubjectLookupTool())
        self.register_tool(LibGuideCourseLookupTool())
    
    async def route_to_tool(self, query: str) -> str:
        """Route to appropriate LibGuide tool."""
        import re
        q_lower = query.lower()
        
        # Check for course code pattern (e.g., "ENG 111", "BIO 201")
        course_pattern = r'\b[A-Z]{2,4}\s*\d{3,4}\b'
        if re.search(course_pattern, query.upper()):
            return "libguide_course_lookup"
        
        # Check for course-related keywords
        if any(word in q_lower for word in ["course", "class", "eng 111", "bio 201"]):
            return "libguide_course_lookup"
        
        # Default to subject lookup
        return "libguide_subject_lookup"
