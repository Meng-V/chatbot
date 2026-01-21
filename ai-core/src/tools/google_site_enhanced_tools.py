"""Enhanced Google Site Search with cost controls, caching, and circuit breaker."""
import os
import hashlib
import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from src.tools.base import Tool


def _get_google_credentials():
    """Get Google API credentials from environment at runtime."""
    return {
        "api_key": os.getenv("GOOGLE_API_KEY", ""),
        "cse_id": os.getenv("GOOGLE_LIBRARY_SEARCH_CSE_ID", "")
    }


def _normalize_query(query: str) -> str:
    """Normalize query for cache key: lowercase, strip, collapse whitespace."""
    return " ".join(query.lower().strip().split())


def _get_cache_key(cx: str, num_results: int, query: str) -> str:
    """Generate SHA256 cache key from cx, num_results, and normalized query."""
    normalized = _normalize_query(query)
    key_input = f"{cx}|{num_results}|{normalized}"
    return hashlib.sha256(key_input.encode()).hexdigest()


def _get_db_path() -> Path:
    """Get path to SQLite cache database."""
    repo_root = Path(__file__).parent.parent.parent
    db_dir = repo_root / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "google_cse_cache.sqlite"


def _init_cache_db():
    """Initialize SQLite cache database with required tables."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Cache table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cse_cache (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    
    # Daily usage table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cse_daily (
            date TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            tripped INTEGER NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


def _get_from_cache(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached result if not expired."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    now = int(time.time())
    cursor.execute(
        "SELECT value_json FROM cse_cache WHERE key = ? AND expires_at > ?",
        (key, now)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row[0])
    return None


def _put_in_cache(key: str, value: Dict[str, Any], ttl_seconds: int):
    """Store result in cache with TTL."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    now = int(time.time())
    expires_at = now + ttl_seconds
    value_json = json.dumps(value)
    
    cursor.execute(
        "INSERT OR REPLACE INTO cse_cache (key, value_json, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (key, value_json, expires_at, now)
    )
    conn.commit()
    conn.close()


def _get_daily_usage(date: str) -> Dict[str, Any]:
    """Get daily usage stats for given date."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT count, tripped FROM cse_daily WHERE date = ?",
        (date,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"count": row[0], "tripped": row[1]}
    return {"count": 0, "tripped": 0}


def _increment_daily_usage(date: str):
    """Increment daily usage count."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO cse_daily (date, count, tripped) VALUES (?, 1, 0) "
        "ON CONFLICT(date) DO UPDATE SET count = count + 1",
        (date,)
    )
    conn.commit()
    conn.close()


def _trip_circuit(date: str):
    """Trip circuit breaker for given date."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO cse_daily (date, count, tripped) VALUES (?, 0, 1) "
        "ON CONFLICT(date) DO UPDATE SET tripped = 1",
        (date,)
    )
    conn.commit()
    conn.close()


class GoogleSiteEnhancedSearchTool(Tool):
    """Enhanced Google Site Search with cost controls and caching."""
    
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
        """Search library site with cost controls, caching, and circuit breaker."""
        try:
            # Initialize cache DB
            _init_cache_db()
            
            # Get config
            disabled = os.getenv("DISABLE_GOOGLE_SITE_SEARCH", "0") == "1"
            cache_ttl = int(os.getenv("GOOGLE_SEARCH_CACHE_TTL_SECONDS", "604800"))  # 7 days
            daily_limit = int(os.getenv("GOOGLE_SEARCH_DAILY_LIMIT", "900"))
            
            creds = _get_google_credentials()
            GOOGLE_API_KEY = creds["api_key"]
            GOOGLE_CSE_ID = creds["cse_id"]
            
            # Generate cache key
            cache_key = _get_cache_key(GOOGLE_CSE_ID, num_results, query)
            query_hash = cache_key[:8]
            today = time.strftime("%Y-%m-%d")
            
            # Check daily usage
            usage = _get_daily_usage(today)
            daily_count = usage["count"]
            is_tripped = usage["tripped"] == 1
            
            # 1) Hard disable switch (highest priority)
            if disabled:
                if log_callback:
                    log_callback(
                        f"🚫 [CSE] DISABLED query_hash={query_hash} cache_hit=false external_call=false "
                        f"daily_count={daily_count}/{daily_limit} blocked=disabled"
                    )
                return {
                    "tool": self.name,
                    "success": True,
                    "fallback": True,
                    "blocked": True,
                    "reason": "disabled",
                    "cache_hit": False,
                    "external_call": False,
                    "text": "Site search is temporarily disabled for testing. Please browse https://www.lib.miamioh.edu/ directly."
                }
            
            # Check API config
            if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
                if log_callback:
                    log_callback(
                        f"❌ [CSE] NOT_CONFIGURED query_hash={query_hash} cache_hit=false external_call=false "
                        f"daily_count={daily_count}/{daily_limit}"
                    )
                return {
                    "tool": self.name,
                    "success": False,
                    "cache_hit": False,
                    "external_call": False,
                    "text": "Site search not configured. Browse https://www.lib.miamioh.edu/"
                }
            
            # 2) Check cache first
            cached_result = _get_from_cache(cache_key)
            if cached_result:
                if log_callback:
                    log_callback(
                        f"💾 [CSE] CACHE_HIT query_hash={query_hash} cache_hit=true external_call=false "
                        f"daily_count={daily_count}/{daily_limit}"
                    )
                cached_result["cache_hit"] = True
                cached_result["external_call"] = False
                return cached_result
            
            # 3) Check circuit breaker
            if is_tripped:
                if log_callback:
                    log_callback(
                        f"⚠️ [CSE] CIRCUIT_OPEN query_hash={query_hash} cache_hit=false external_call=false "
                        f"daily_count={daily_count}/{daily_limit} blocked=circuit_open"
                    )
                return {
                    "tool": self.name,
                    "success": True,
                    "fallback": True,
                    "blocked": True,
                    "reason": "circuit_open",
                    "cache_hit": False,
                    "external_call": False,
                    "text": "The search service is temporarily unavailable due to quota limits. Please visit https://www.lib.miamioh.edu/ directly."
                }
            
            # 4) Check daily limit
            if daily_count >= daily_limit:
                if log_callback:
                    log_callback(
                        f"⚠️ [CSE] DAILY_LIMIT query_hash={query_hash} cache_hit=false external_call=false "
                        f"daily_count={daily_count}/{daily_limit} blocked=daily_limit"
                    )
                return {
                    "tool": self.name,
                    "success": True,
                    "fallback": True,
                    "blocked": True,
                    "reason": "daily_limit",
                    "cache_hit": False,
                    "external_call": False,
                    "text": "Daily search limit reached. Please visit https://www.lib.miamioh.edu/ directly."
                }
            
            # 5) Make external call
            num_results = max(1, min(num_results, 10))
            
            if log_callback:
                log_callback(
                    f"🌐 [CSE] EXTERNAL_CALL query_hash={query_hash} cache_hit=false external_call=true "
                    f"daily_count={daily_count}/{daily_limit}"
                )
            
            async with httpx.AsyncClient(timeout=10) as client:
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
                
                # Increment daily count (success or failure)
                _increment_daily_usage(today)
                daily_count += 1
                
                # Check for quota/rate errors and trip circuit
                response_text = response.text if hasattr(response, 'text') else ""
                is_quota_error = (
                    response.status_code in [429, 403] or
                    any(keyword in response_text.lower() for keyword in [
                        "quota", "ratelimitexceeded", "dailylimitexceeded", "quota exceeded"
                    ])
                )
                
                if is_quota_error:
                    _trip_circuit(today)
                    if log_callback:
                        log_callback(
                            f"🚨 [CSE] QUOTA_EXCEEDED query_hash={query_hash} cache_hit=false external_call=true "
                            f"daily_count={daily_count}/{daily_limit} blocked=quota_exceeded status={response.status_code}"
                        )
                    return {
                        "tool": self.name,
                        "success": True,
                        "fallback": True,
                        "blocked": True,
                        "reason": "quota_exceeded",
                        "cache_hit": False,
                        "external_call": True,
                        "text": "The search service has exceeded its quota. Please visit https://www.lib.miamioh.edu/ directly."
                    }
                
                # Handle other errors
                if response.status_code == 400:
                    if log_callback:
                        log_callback(
                            f"❌ [CSE] BAD_REQUEST query_hash={query_hash} cache_hit=false external_call=true "
                            f"daily_count={daily_count}/{daily_limit}"
                        )
                    return {
                        "tool": self.name,
                        "success": False,
                        "cache_hit": False,
                        "external_call": True,
                        "text": "Invalid search parameters. Visit https://www.lib.miamioh.edu/"
                    }
                
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                
                # Build result
                if not items:
                    result = {
                        "tool": self.name,
                        "success": True,
                        "cache_hit": False,
                        "external_call": True,
                        "text": f"No results found for '{query}' on lib.miamioh.edu"
                    }
                else:
                    # Extract enhanced metadata
                    results = []
                    for item in items:
                        title = item.get("title", "Page")
                        link = item.get("link", "")
                        snippet = item.get("snippet", "")
                        
                        pagemap = item.get("pagemap", {})
                        metatags = pagemap.get("metatags", [{}])[0] if pagemap.get("metatags") else {}
                        og_description = metatags.get("og:description", "")
                        content = og_description if og_description else snippet
                        
                        results.append(f"• **{title}**\n  {content}\n  {link}")
                    
                    result = {
                        "tool": self.name,
                        "success": True,
                        "cache_hit": False,
                        "external_call": True,
                        "text": f"Found on lib.miamioh.edu:\n\n" + "\n\n".join(results),
                        "results_count": len(items)
                    }
                
                # Cache the result
                _put_in_cache(cache_key, result, cache_ttl)
                
                if log_callback:
                    log_callback(
                        f"✅ [CSE] SUCCESS query_hash={query_hash} cache_hit=false external_call=true "
                        f"daily_count={daily_count}/{daily_limit} results={len(items)}"
                    )
                
                return result
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [CSE] ERROR: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "cache_hit": False,
                "external_call": False,
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
        """Execute borrowing policy search with filtering."""
        try:
            if log_callback:
                log_callback(f"📚 [Borrowing Policy Search Tool] Searching borrowing policies", {"query": query})
            
            # Get credentials at runtime
            creds = _get_google_credentials()
            GOOGLE_API_KEY = creds["api_key"]
            GOOGLE_CSE_ID = creds["cse_id"]
            
            if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
                if log_callback:
                    log_callback("❌ [Borrowing Policy Search Tool] API not configured")
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Site search not configured. Browse https://www.lib.miamioh.edu/"
                }
            
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
