"""
Circulation Policy Tool

Provides URL-only responses for circulation, ILL, and borrowing policy queries.
No explanations, no content excerpts - just direct users to the authoritative page.
"""

from typing import Dict, Any
from src.tools.base import Tool
from src.services.website_evidence_search import search_website_evidence


class CirculationPolicyTool(Tool):
    """Search circulation policies and return URL-only responses."""
    
    @property
    def name(self) -> str:
        return "circulation_policy_lookup"
    
    @property
    def description(self) -> str:
        return "Look up circulation, borrowing, ILL, and OhioLINK policy information - returns authoritative URLs only"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search circulation policies and return URLs only.
        
        Args:
            query: User's policy question
            log_callback: Optional logging callback
            
        Returns:
            Dict with URL-only response
        """
        try:
            if log_callback:
                log_callback(f"📋 [Circulation Policy Tool] Searching policies", {"query": query})
            
            # Search the CirculationPolicies collection
            results = await search_website_evidence(
                query=query,
                top_k=3,
                collection="CirculationPolicies",
                log_callback=log_callback
            )
            
            if not results:
                if log_callback:
                    log_callback("⚠️ [Circulation Policy Tool] No matching policies found")
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "For circulation and borrowing policies, please visit: https://libguides.lib.miamioh.edu/circulation-policies"
                }
            
            # Get the top result (highest relevance)
            top_result = results[0]
            url = top_result.get("final_url", "")
            title = top_result.get("title", "Circulation Policies")
            score = top_result.get("score", 0)
            
            if log_callback:
                log_callback(f"✅ [Circulation Policy Tool] Found policy page (score: {score:.3f})", {"url": url})
            
            # Return URL-only response
            response_text = f"**{title}**\n\n{url}"
            
            return {
                "tool": self.name,
                "success": True,
                "text": response_text,
                "url": url,
                "title": title,
                "response_mode": "url_only"  # Flag for orchestrator
            }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Circulation Policy Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "For circulation and borrowing policies, please visit: https://libguides.lib.miamioh.edu/circulation-policies"
            }
