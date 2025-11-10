"""Primo/Alma tools for discovery search."""
import os
import httpx
from typing import Dict, Any
from src.tools.base import Tool

PRIMO_API_KEY = os.getenv("PRIMO_API_KEY", "")
PRIMO_SEARCH_URL = os.getenv("PRIMO_SEARCH_URL", "")
PRIMO_VID = os.getenv("PRIMO_VID", "")
PRIMO_SCOPE = os.getenv("PRIMO_SCOPE", "")

class PrimoBibliographicSearchTool(Tool):
    """Tool for searching books, articles, e-resources in Primo."""
    
    @property
    def name(self) -> str:
        return "primo_search"
    
    @property
    def description(self) -> str:
        return "Search catalog for books, articles, journals, e-resources"
    
    async def execute(self, query: str, log_callback=None, **kwargs) -> Dict[str, Any]:
        """Search Primo catalog."""
        if log_callback:
            log_callback("🔍 [Primo Search Tool] Searching catalog", {"query": query})
        
        if not PRIMO_API_KEY or not PRIMO_SEARCH_URL:
            if log_callback:
                log_callback("❌ [Primo Search Tool] API not configured")
            return {
                "tool": self.name,
                "success": False,
                "error": "Primo API not configured",
                "text": "I couldn't search the catalog right now. Please try https://libcat.lib.miamioh.edu/"
            }
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                params = {
                    "q": f"any,contains,{query}",
                    "vid": PRIMO_VID,
                    "scope": PRIMO_SCOPE,
                    "apikey": PRIMO_API_KEY,
                    "limit": 5
                }
                
                if log_callback:
                    log_callback("🌐 [Primo Search Tool] Calling Primo API")
                
                response = await client.get(PRIMO_SEARCH_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
                docs = data.get("docs", [])
                
                if log_callback:
                    log_callback(f"✅ [Primo Search Tool] Found {len(docs)} results")
                
                if not docs:
                    return {
                        "tool": self.name,
                        "success": True,
                        "text": f"No results found for '{query}' in the catalog. Try refining your search."
                    }
                
                results = []
                for doc in docs[:3]:
                    title = doc.get("pnx", {}).get("display", {}).get("title", ["Unknown"])[0]
                    author = doc.get("pnx", {}).get("display", {}).get("creator", [""])[0]
                    link = doc.get("pnx", {}).get("links", {}).get("linktorsrc", [""])[0]
                    results.append(f"• **{title}**{' by ' + author if author else ''}\n  {link if link else 'Available in catalog'}")
                
                return {
                    "tool": self.name,
                    "success": True,
                    "text": f"Found these resources:\n\n" + "\n\n".join(results),
                    "count": len(docs)
                }
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Primo Search Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": f"Error searching catalog: {str(e)}"
            }

class PrimoAvailabilityTool(Tool):
    """Tool for checking item availability."""
    
    @property
    def name(self) -> str:
        return "primo_availability"
    
    @property
    def description(self) -> str:
        return "Check availability of a specific item"
    
    async def execute(self, query: str, log_callback=None, item_id: str = None, **kwargs) -> Dict[str, Any]:
        """Check availability (stub - needs specific item ID)."""
        if log_callback:
            log_callback("📦 [Primo Availability Tool] Checking item availability")
        
        return {
            "tool": self.name,
            "success": True,
            "text": "To check availability of a specific item, please provide the item ID or search for it first."
        }
