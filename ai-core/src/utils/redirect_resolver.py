"""
URL Redirect Resolver

Loads redirect mappings from site_map_redirects.jsonl and provides
URL resolution to ensure citations use final URLs after redirects.

This is used to ensure that when the chatbot cites website evidence,
it provides the correct final URL rather than an old/redirect URL.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Set
from functools import lru_cache


class RedirectResolver:
    """Manages URL redirects and aliases for website citations."""
    
    def __init__(self, redirects_path: Optional[str] = None):
        """
        Initialize redirect resolver.
        
        Args:
            redirects_path: Path to site_map_redirects.jsonl
                           (default: ai-core/data/site_map_redirects.jsonl)
        """
        self.redirects: Dict[str, str] = {}  # from_url -> final_url
        self.aliases: Dict[str, Set[str]] = {}  # final_url -> set of aliases
        self.loaded = False
        
        if redirects_path is None:
            # Default path
            root_dir = Path(__file__).resolve().parent.parent.parent.parent
            redirects_path = root_dir / "ai-core" / "data" / "site_map_redirects.jsonl"
        
        self.redirects_path = Path(redirects_path)
        self._load_redirects()
    
    def _load_redirects(self):
        """Load redirect mappings from JSONL file."""
        if not self.redirects_path.exists():
            # File doesn't exist yet - that's OK, we'll just return URLs as-is
            return
        
        try:
            with open(self.redirects_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    data = json.loads(line)
                    from_url = data.get("from_url", "")
                    final_url = data.get("final_url", "")
                    aliases = data.get("aliases", [])
                    
                    if from_url and final_url:
                        self.redirects[from_url] = final_url
                        
                        # Also map all aliases to the final URL
                        for alias in aliases:
                            if alias:
                                self.redirects[alias] = final_url
                        
                        # Store aliases for reverse lookup
                        if final_url not in self.aliases:
                            self.aliases[final_url] = set()
                        self.aliases[final_url].update(aliases)
            
            self.loaded = True
        
        except Exception as e:
            # If there's an error loading, we'll just work without redirects
            pass
    
    def resolve_url(self, url: str) -> str:
        """
        Resolve a URL to its final destination.
        
        Args:
            url: URL to resolve (may be a redirect or alias)
            
        Returns:
            Final URL after following redirects, or original URL if no mapping exists
        """
        if not url:
            return url
        
        # Normalize URL (remove trailing slash for comparison)
        normalized = url.rstrip('/')
        
        # Check if we have a redirect mapping
        final = self.redirects.get(normalized)
        if final:
            return final
        
        # Check with trailing slash
        final = self.redirects.get(url)
        if final:
            return final
        
        # No mapping found, return original
        return url
    
    def get_aliases(self, url: str) -> Set[str]:
        """
        Get all known aliases for a URL.
        
        Args:
            url: URL to look up
            
        Returns:
            Set of aliases for this URL
        """
        normalized = url.rstrip('/')
        return self.aliases.get(normalized, set())
    
    def is_redirect(self, url: str) -> bool:
        """
        Check if a URL is a redirect (not the final URL).
        
        Args:
            url: URL to check
            
        Returns:
            True if this URL redirects to another URL
        """
        normalized = url.rstrip('/')
        return normalized in self.redirects


# Global instance for efficient reuse
_resolver_instance: Optional[RedirectResolver] = None


def get_resolver() -> RedirectResolver:
    """Get the global redirect resolver instance."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = RedirectResolver()
    return _resolver_instance


def resolve_url(url: str) -> str:
    """
    Convenience function to resolve a URL.
    
    Args:
        url: URL to resolve
        
    Returns:
        Final URL after following redirects
    """
    resolver = get_resolver()
    return resolver.resolve_url(url)


def resolve_urls_in_response(response: str) -> str:
    """
    Resolve all URLs in a response text.
    
    This function finds URLs in the response and replaces them with their
    final URLs after following redirects.
    
    Args:
        response: Response text containing URLs
        
    Returns:
        Response with URLs resolved to their final destinations
    """
    import re
    
    resolver = get_resolver()
    
    # Find all URLs in the response (basic pattern)
    url_pattern = r'https?://[^\s\)\]<>]+'
    
    def replace_url(match):
        url = match.group(0)
        return resolver.resolve_url(url)
    
    return re.sub(url_pattern, replace_url, response)


def apply_redirects_to_citations(citations: list) -> list:
    """
    Apply redirect resolution to a list of citation dictionaries.
    
    Args:
        citations: List of dicts with 'url' or 'final_url' keys
        
    Returns:
        Citations with URLs resolved
    """
    resolver = get_resolver()
    
    resolved = []
    for citation in citations:
        citation_copy = citation.copy()
        
        # Resolve URL field
        if 'url' in citation_copy:
            citation_copy['url'] = resolver.resolve_url(citation_copy['url'])
        
        # Resolve final_url field
        if 'final_url' in citation_copy:
            citation_copy['final_url'] = resolver.resolve_url(citation_copy['final_url'])
        
        resolved.append(citation_copy)
    
    return resolved
