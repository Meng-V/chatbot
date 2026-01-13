"""
Website Evidence RAG Tool

Provides semantic search over curated website evidence as a fallback
when API agents don't have sufficient information.
"""

from typing import Dict, Any
from src.tools.base import Tool
from src.services.website_evidence_search import search_website_evidence
from src.utils.redirect_resolver import resolve_url


class WebsiteEvidenceTool(Tool):
    """Search curated website evidence for RAG fallback."""
    
    @property
    def name(self) -> str:
        return "website_evidence_search"
    
    @property
    def description(self) -> str:
        return "Search curated library website content for accurate information with citations"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        top_k: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search website evidence and return results with citations.
        
        Args:
            query: Search query
            log_callback: Optional logging callback
            top_k: Number of results to return (default: 5)
            
        Returns:
            Dict with:
                - tool: Tool name
                - success: Whether search succeeded
                - text: Formatted results with citations
                - results: Raw results list
                - has_citations: Whether results include valid URLs
        """
        try:
            if log_callback:
                log_callback(f"📚 [Website Evidence Tool] Searching website evidence", {"query": query})
            
            # Search website evidence
            results = await search_website_evidence(
                query=query,
                top_k=top_k,
                log_callback=log_callback
            )
            
            if not results:
                if log_callback:
                    log_callback("⚠️ [Website Evidence Tool] No results found")
                return {
                    "tool": self.name,
                    "success": True,
                    "text": f"No relevant information found in website evidence for: {query}",
                    "results": [],
                    "has_citations": False
                }
            
            # Filter for high-confidence results (score > 0.7)
            high_confidence = [r for r in results if r.get("score", 0) > 0.7]
            
            if not high_confidence:
                if log_callback:
                    log_callback(f"⚠️ [Website Evidence Tool] No high-confidence results (best score: {results[0].get('score', 0):.3f})")
                return {
                    "tool": self.name,
                    "success": True,
                    "text": f"Found low-confidence matches for '{query}'. Consider using Google site search instead.",
                    "results": results,
                    "has_citations": False
                }
            
            # Format results with citations
            formatted_results = []
            for idx, result in enumerate(high_confidence[:3], 1):  # Top 3 high-confidence
                title = result.get("title", "Page")
                chunk_text = result.get("chunk_text", "")
                final_url = result.get("final_url", "")
                score = result.get("score", 0)
                
                # Apply redirect resolution
                resolved_url = resolve_url(final_url)
                
                # Format result
                formatted_results.append(
                    f"**{title}**\n"
                    f"{chunk_text[:300]}...\n"
                    f"Source: {resolved_url}\n"
                    f"(Relevance: {score:.2f})"
                )
            
            text = "Found in library website evidence:\n\n" + "\n\n".join(formatted_results)
            
            # Check if we have valid citations
            has_citations = any(r.get("final_url") for r in high_confidence)
            
            if log_callback:
                log_callback(f"✅ [Website Evidence Tool] Returning {len(high_confidence)} high-confidence results")
            
            return {
                "tool": self.name,
                "success": True,
                "text": text,
                "results": high_confidence,
                "has_citations": has_citations
            }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Website Evidence Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Error searching website evidence. Please try Google site search or contact a librarian.",
                "has_citations": False
            }
