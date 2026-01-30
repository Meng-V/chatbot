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
        campus_scope: str = "oxford",
        log_callback=None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search circulation policies and return direct answers or URLs.
        
        Args:
            query: User's policy question
            campus_scope: Campus to search (default: "oxford")
            log_callback: Optional logging callback
            
        Returns:
            Dict with direct answer (if high confidence) or URL-only response
        """
        try:
            if log_callback:
                log_callback(f"📋 [Circulation Policy Tool] Searching policies", {"query": query, "campus": campus_scope})
            
            # PRIORITY 1: Try CirculationPolicyFacts for direct answers
            fact_results = await search_website_evidence(
                query=query,
                top_k=3,
                collection="CirculationPolicyFacts",
                campus_scope=campus_scope,
                log_callback=log_callback
            )
            
            # Check for high-confidence fact hit (score >= 0.78)
            if fact_results:
                top_fact = fact_results[0]
                distance = top_fact.get("distance", 1.0)
                score = 1 - distance  # Convert distance to similarity score
                
                if score >= 0.78:
                    answer = top_fact.get("answer", "")
                    url = top_fact.get("canonical_url", "")
                    
                    if answer and url:
                        if log_callback:
                            log_callback(f"✅ [Circulation Policy Tool] High-confidence fact match (score: {score:.3f})")
                        
                        # Return direct answer with URL
                        response_text = f"{answer}\n\n**Source:** {url}"
                        
                        return {
                            "tool": self.name,
                            "success": True,
                            "text": response_text,
                            "url": url,
                            "response_mode": "fact_answer",
                            "confidence_score": score
                        }
            
            # PRIORITY 2: Search the CirculationPolicies collection for chunks
            results = await search_website_evidence(
                query=query,
                top_k=3,
                collection="CirculationPolicies",
                campus_scope=campus_scope,
                log_callback=log_callback
            )
            
            if not results:
                if log_callback:
                    log_callback("⚠️ [Circulation Policy Tool] No matching policies found")
                # Return Oxford-default fallback URL
                fallback_url = "https://libguides.lib.miamioh.edu/mul-circulation-policies"
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"For circulation and borrowing policies, please visit: {fallback_url}"
                }
            
            # Get the top result (highest relevance)
            top_result = results[0]
            url = top_result.get("final_url", "") or top_result.get("canonical_url", "")
            title = top_result.get("title", "Circulation Policies")
            distance = top_result.get("distance", 1.0)
            score = 1 - distance  # Convert distance to similarity score
            
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
                "text": "For circulation and borrowing policies, please visit: https://libguides.lib.miamioh.edu/mul-circulation-policies"
            }
