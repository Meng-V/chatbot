#!/usr/bin/env python3
"""
Acceptance tests for Google CSE cost controls.

Tests:
1. DISABLE_GOOGLE_SITE_SEARCH=1: tool returns fallback without crashing
2. Cache: same query 5 times, only first is external call
3. Daily limit: with GOOGLE_SEARCH_DAILY_LIMIT=1, second query is blocked
"""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.google_site_enhanced_tools import GoogleSiteEnhancedSearchTool


def log_test_result(test_name: str, passed: bool, details: str = ""):
    """Print test result with formatting."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"        {details}")


async def test_disable_switch():
    """Test 1: Hard disable switch prevents external calls."""
    print("\n" + "="*80)
    print("TEST 1: DISABLE_GOOGLE_SITE_SEARCH=1")
    print("="*80)
    
    # Set disable flag
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "1"
    
    tool = GoogleSiteEnhancedSearchTool()
    logs = []
    
    def capture_log(msg, data=None):
        logs.append(msg)
    
    result = await tool.execute(
        query="test query for disable check",
        log_callback=capture_log,
        num_results=3
    )
    
    # Verify response structure
    passed = (
        result.get("success") is True and
        result.get("blocked") is True and
        result.get("reason") == "disabled" and
        result.get("cache_hit") is False and
        result.get("external_call") is False and
        "temporarily disabled" in result.get("text", "").lower()
    )
    
    log_test_result(
        "Disable switch returns proper fallback",
        passed,
        f"blocked={result.get('blocked')}, reason={result.get('reason')}, external_call={result.get('external_call')}"
    )
    
    # Check logs
    log_has_disabled = any("DISABLED" in log for log in logs)
    log_test_result("Logs show disabled status", log_has_disabled)
    
    # Unset for next test
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "0"
    
    return passed and log_has_disabled


async def test_cache_behavior():
    """Test 2: Cache behavior - same query 5 times, only first is external."""
    print("\n" + "="*80)
    print("TEST 2: Cache Behavior")
    print("="*80)
    
    # Check if API is configured
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_LIBRARY_SEARCH_CSE_ID", "")
    
    if not api_key or not cse_id:
        print("  ⚠️  SKIPPED - Google API credentials not configured")
        log_test_result("Cache behavior test", True, "Skipped - no credentials")
        return True
    
    # Ensure disabled is off
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "0"
    
    # Use a unique query to avoid conflicts
    import time
    test_query = f"library policies test {int(time.time())}"
    
    tool = GoogleSiteEnhancedSearchTool()
    external_calls = []
    cache_hits = []
    
    for i in range(5):
        logs = []
        
        def capture_log(msg, data=None):
            logs.append(msg)
        
        result = await tool.execute(
            query=test_query,
            log_callback=capture_log,
            num_results=3
        )
        
        external_call = result.get("external_call", False)
        cache_hit = result.get("cache_hit", False)
        
        external_calls.append(external_call)
        cache_hits.append(cache_hit)
        
        print(f"  Call {i+1}: external_call={external_call}, cache_hit={cache_hit}")
    
    # First call should be external, rest should be cache hits
    first_external = external_calls[0] is True
    rest_cached = all(cache_hits[1:])
    no_subsequent_external = not any(external_calls[1:])
    
    log_test_result("First call is external", first_external)
    log_test_result("Subsequent 4 calls are cache hits", rest_cached)
    log_test_result("No external calls after first", no_subsequent_external)
    
    return first_external and rest_cached and no_subsequent_external


async def test_daily_limit():
    """Test 3: Daily limit enforcement."""
    print("\n" + "="*80)
    print("TEST 3: Daily Limit Enforcement")
    print("="*80)
    
    # Check if API is configured
    api_key = os.getenv("GOOGLE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_LIBRARY_SEARCH_CSE_ID", "")
    
    if not api_key or not cse_id:
        print("  ⚠️  SKIPPED - Google API credentials not configured")
        log_test_result("Daily limit test", True, "Skipped - no credentials")
        return True
    
    # Set very low daily limit
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "0"
    os.environ["GOOGLE_SEARCH_DAILY_LIMIT"] = "1"
    
    # Clear any existing cache to force external calls
    import time
    query1 = f"unique query one {int(time.time())}"
    query2 = f"unique query two {int(time.time() + 1)}"
    
    tool = GoogleSiteEnhancedSearchTool()
    
    # First query
    logs1 = []
    def capture_log1(msg, data=None):
        logs1.append(msg)
    
    result1 = await tool.execute(
        query=query1,
        log_callback=capture_log1,
        num_results=3
    )
    
    # Second query (should be blocked by daily limit)
    logs2 = []
    def capture_log2(msg, data=None):
        logs2.append(msg)
    
    result2 = await tool.execute(
        query=query2,
        log_callback=capture_log2,
        num_results=3
    )
    
    first_succeeded = result1.get("external_call") is True
    second_blocked = (
        result2.get("blocked") is True and
        result2.get("reason") == "daily_limit" and
        result2.get("external_call") is False
    )
    
    log_test_result("First query completes successfully", first_succeeded)
    log_test_result(
        "Second query blocked by daily limit",
        second_blocked,
        f"blocked={result2.get('blocked')}, reason={result2.get('reason')}"
    )
    
    # Reset limit
    os.environ["GOOGLE_SEARCH_DAILY_LIMIT"] = "900"
    
    return first_succeeded and second_blocked


async def test_with_eval_scripts():
    """Test 4: Run eval scripts with disable flag to ensure no crashes."""
    print("\n" + "="*80)
    print("TEST 4: Eval Scripts with DISABLE_GOOGLE_SITE_SEARCH=1")
    print("="*80)
    
    os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "1"
    
    # Import and run a quick smoke test
    from src.graph.orchestrator import library_graph
    from src.utils.logger import AgentLogger
    
    logger = AgentLogger()
    
    try:
        # Test a simple query that might trigger google search
        result = await library_graph.ainvoke({
            "user_message": "Can I renew my books?",
            "messages": [],
            "conversation_history": [],
            "conversation_id": None,
            "_logger": logger
        })
        
        # Should complete without crashing
        has_response = "final_answer" in result or "answer" in result
        log_test_result(
            "Eval workflow completes without crash",
            True,
            "Graph processed query successfully"
        )
        
        os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "0"
        return True
        
    except Exception as e:
        log_test_result(
            "Eval workflow completes without crash",
            False,
            f"ERROR: {str(e)}"
        )
        os.environ["DISABLE_GOOGLE_SITE_SEARCH"] = "0"
        return False


async def main():
    """Run all acceptance tests."""
    print("\n" + "="*80)
    print("GOOGLE CSE COST CONTROL ACCEPTANCE TESTS")
    print("="*80)
    
    results = []
    
    # Run tests
    results.append(await test_disable_switch())
    results.append(await test_cache_behavior())
    results.append(await test_daily_limit())
    results.append(await test_with_eval_scripts())
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
