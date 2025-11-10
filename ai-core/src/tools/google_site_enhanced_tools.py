"""Enhanced Google Site Search with metadata extraction and specialized patterns."""
import os
import httpx
from typing import Dict, Any, Optional
from src.tools.base import Tool

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_LIBRARY_SEARCH_CSE_ID", "")

class GoogleSiteEnhancedSearchTool(Tool):
    """Enhanced Google Site Search with metadata extraction."""
    
    @property
    def name(self) -> str:
        return "google_site_enhanced_search"
    
    @property
    def description(self) -> str:
        return "Search lib.miamioh.edu with metadata extraction for policies, services, how-tos"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        num_results: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """Search library site with enhanced metadata."""
        try:
            if log_callback:
                log_callback(f"🔎 [Google Site Enhanced Search Tool] Searching lib.miamioh.edu", {"query": query})
            
            if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
                if log_callback:
                    log_callback("❌ [Google Site Enhanced Search Tool] API not configured")
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Site search not configured. Browse https://www.lib.miamioh.edu/"
                }
            
            # Ensure num_results is within valid range (1-10)
            num_results = max(1, min(num_results, 10))
            
            async with httpx.AsyncClient(timeout=10) as client:
                if log_callback:
                    log_callback("🌐 [Google Site Enhanced Search Tool] Calling Google CSE API")
                
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": GOOGLE_API_KEY,
                        "cx": GOOGLE_CSE_ID,
                        "q": query,
                        "num": num_results,
                        "safe": "off",
                        "fields": "items(title,link,snippet,pagemap/metatags)"
                    }
                )
                
                # Handle quota/rate limiting
                if response.status_code == 429:
                    if log_callback:
                        log_callback("⚠️ [Google Site Enhanced Search Tool] Quota exceeded")
                    return {
                        "tool": self.name,
                        "success": True,
                        "text": "The search service is temporarily unavailable due to quota limits. Please visit https://www.lib.miamioh.edu/ directly or contact a librarian for assistance.",
                        "fallback": True
                    }
                
                # Handle forbidden
                if response.status_code == 403:
                    if log_callback:
                        log_callback("❌ [Google Site Enhanced Search Tool] Access denied")
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": "Search service access denied. Please check API credentials. Visit https://www.lib.miamioh.edu/"
                    }
                
                # Handle bad request
                if response.status_code == 400:
                    if log_callback:
                        log_callback("❌ [Google Site Enhanced Search Tool] Bad request")
                    return {
                        "tool": self.name,
                        "success": False,
                        "text": "Invalid search parameters. Visit https://www.lib.miamioh.edu/"
                    }
                
                response.raise_for_status()
                data = response.json()
                
                items = data.get("items", [])
                
                if log_callback:
                    log_callback(f"✅ [Google Site Enhanced Search Tool] Found {len(items)} results")
                
                if not items:
                    return {
                        "tool": self.name,
                        "success": True,
                        "text": f"No results found for '{query}' on lib.miamioh.edu"
                    }
                
                # Extract enhanced metadata
                results = []
                for item in items:
                    title = item.get("title", "Page")
                    link = item.get("link", "")
                    snippet = item.get("snippet", "")
                    
                    # Try to get og:description from metatags
                    pagemap = item.get("pagemap", {})
                    metatags = pagemap.get("metatags", [{}])[0] if pagemap.get("metatags") else {}
                    og_description = metatags.get("og:description", "")
                    
                    # Use og:description if available, otherwise use snippet
                    content = og_description if og_description else snippet
                    
                    results.append(f"• **{title}**\n  {content}\n  {link}")
                
                return {
                    "tool": self.name,
                    "success": True,
                    "text": f"Found on lib.miamioh.edu:\n\n" + "\n\n".join(results),
                    "results_count": len(items)
                }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Google Site Enhanced Search Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": f"Error searching site. Visit https://www.lib.miamioh.edu/"
            }

class BorrowingPolicySearchTool(Tool):
    """Specialized tool for borrowing policy questions."""
    
    @property
    def name(self) -> str:
        return "borrowing_policy_search"
    
    @property
    def description(self) -> str:
        return "Search for borrowing policies (renew, ILL, loan periods, fines, delivery)"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Search for borrowing policies."""
        try:
            if log_callback:
                log_callback("📚 [Borrowing Policy Search Tool] Searching policies")
            
            # Enhance query with policy-specific terms
            policy_keywords = {
                "renew": "renew renewal",
                "borrow": "borrow borrowing checkout",
                "loan": "loan period lending",
                "fine": "fine fees overdue",
                "delivery": "delivery mail home",
                "ill": "interlibrary loan ILL",
                "reserve": "course reserve reserves",
                "recall": "recall"
            }
            
            enhanced_query = query
            for keyword, expansion in policy_keywords.items():
                if keyword in query.lower():
                    enhanced_query += f" {expansion}"
                    break
            
            # Use enhanced Google search
            google_tool = GoogleSiteEnhancedSearchTool()
            result = await google_tool.execute(
                query=enhanced_query,
                log_callback=log_callback,
                num_results=3
            )
            
            if result.get("success"):
                # Add policy-specific context
                text = "**Borrowing Policy Information:**\n\n" + result.get("text", "")
                result["text"] = text
            
            return result
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Borrowing Policy Search Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Error searching policies. Visit https://www.lib.miamioh.edu/services/borrowing"
            }
