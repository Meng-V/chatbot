#!/usr/bin/env python3
"""
Policy Routing Smoke Tests

Tests that policy queries route correctly:
- Oxford-default for general queries
- Direct answers for high-confidence facts
- No regional BorrowingPolicy URLs
- Proper regional handling when explicitly requested

Usage:
    python -m scripts.test_policy_routing
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment
repo_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=repo_root / ".env")

sys.path.insert(0, str(repo_root / "ai-core"))

from src.tools.circulation_policy_tool import CirculationPolicyTool
from src.tools.google_site_enhanced_tools import BorrowingPolicySearchTool
from src.utils.campus_scope import detect_campus_scope


# Test cases
TEST_CASES = [
    {
        "query": "how long can I borrow a book",
        "expected_campus": "oxford",
        "expected_url_pattern": "mul-circulation-policies",
        "should_avoid": "BorrowingPolicy",
        "description": "Generic book loan period → Oxford default, avoid regional BorrowingPolicy"
    },
    {
        "query": "what are the fines for overdue books",
        "expected_campus": "oxford",
        "expected_url_pattern": "mul-circulation-policies",
        "should_avoid": "BorrowingPolicy",
        "description": "Fines query → Oxford fines page"
    },
    {
        "query": "ohiolink loan period",
        "expected_campus": "oxford",
        "expected_url_pattern": "ohiolink",
        "should_avoid": None,
        "description": "OhioLINK query → Oxford OhioLINK/ILL page"
    },
    {
        "query": "how do I recall a book",
        "expected_campus": "oxford",
        "expected_url_pattern": "recall",
        "should_avoid": None,
        "description": "Recall query → Oxford recall-request page"
    },
    {
        "query": "textbook reserves",
        "expected_campus": "oxford",
        "expected_url_pattern": "reserves-textbooks",
        "should_avoid": None,
        "description": "Textbook reserves → Oxford reserves page"
    },
    {
        "query": "course reserves",
        "expected_campus": "oxford",
        "expected_url_pattern": "reserves",
        "should_avoid": None,
        "description": "Course reserves → Oxford reserves/coursematerial page"
    },
    {
        "query": "streaming video for my class",
        "expected_campus": "oxford",
        "expected_url_pattern": "StreamingVideo",
        "should_avoid": None,
        "description": "Streaming video → Oxford StreamingVideoAndRemoteInstruction page"
    },
    {
        "query": "electronic reserves",
        "expected_campus": "oxford",
        "expected_url_pattern": "electronicreserves",
        "should_avoid": None,
        "description": "Electronic reserves → Oxford electronicreserves page"
    },
    {
        "query": "Hamilton campus borrowing policy",
        "expected_campus": "hamilton",
        "expected_url_pattern": None,  # May still use regional or fallback
        "should_avoid": None,
        "description": "Explicit Hamilton request → Hamilton campus scope"
    },
]


async def test_campus_detection():
    """Test campus scope detection."""
    print("=" * 80)
    print("CAMPUS SCOPE DETECTION TESTS")
    print("=" * 80)
    
    test_queries = [
        ("how long can I borrow a book", "oxford"),
        ("King Library hours", "oxford"),
        ("Hamilton campus policy", "hamilton"),
        ("Rentschler Library fines", "hamilton"),
        ("Middletown borrowing rules", "middletown"),
        ("Gardner-Harvey reserves", "middletown"),
    ]
    
    passed = 0
    failed = 0
    
    for query, expected in test_queries:
        detected = detect_campus_scope(query)
        status = "✅" if detected == expected else "❌"
        
        if detected == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} '{query}' → {detected} (expected: {expected})")
    
    print(f"\nResults: {passed} passed, {failed} failed\n")
    return failed == 0


async def test_circulation_policy_tool():
    """Test CirculationPolicyTool routing."""
    print("=" * 80)
    print("CIRCULATION POLICY TOOL TESTS")
    print("=" * 80)
    
    tool = CirculationPolicyTool()
    passed = 0
    failed = 0
    
    for test_case in TEST_CASES[:8]:  # Skip Hamilton test (needs Google)
        query = test_case["query"]
        campus = test_case["expected_campus"]
        expected_pattern = test_case["expected_url_pattern"]
        should_avoid = test_case["should_avoid"]
        desc = test_case["description"]
        
        print(f"\n📝 Test: {desc}")
        print(f"   Query: '{query}'")
        print(f"   Campus: {campus}")
        
        try:
            result = await tool.execute(query=query, campus_scope=campus, log_callback=None)
            
            success = result.get("success", False)
            text = result.get("text", "")
            url = result.get("url", "")
            response_mode = result.get("response_mode", "")
            
            # Check success
            test_passed = success
            
            # Check URL pattern if specified
            if expected_pattern and test_passed:
                if expected_pattern not in url.lower() and expected_pattern not in text.lower():
                    print(f"   ❌ Expected pattern '{expected_pattern}' not found")
                    test_passed = False
                else:
                    print(f"   ✅ Pattern '{expected_pattern}' found")
            
            # Check avoid pattern if specified
            if should_avoid and test_passed:
                if should_avoid in url or should_avoid in text:
                    print(f"   ❌ Should avoid '{should_avoid}' but it appeared")
                    test_passed = False
                else:
                    print(f"   ✅ Successfully avoided '{should_avoid}'")
            
            # Show response mode
            print(f"   Response mode: {response_mode}")
            print(f"   URL: {url[:80]}...")
            
            if test_passed:
                print(f"   ✅ PASSED")
                passed += 1
            else:
                print(f"   ❌ FAILED")
                failed += 1
        
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            failed += 1
    
    print(f"\n{'=' * 80}")
    print(f"Results: {passed} passed, {failed} failed\n")
    return failed == 0


async def test_borrowing_policy_search_tool():
    """Test BorrowingPolicySearchTool with Weaviate priority."""
    print("=" * 80)
    print("BORROWING POLICY SEARCH TOOL TESTS")
    print("=" * 80)
    
    tool = BorrowingPolicySearchTool()
    passed = 0
    failed = 0
    
    for test_case in TEST_CASES[:3]:  # Test first 3 cases
        query = test_case["query"]
        campus = test_case["expected_campus"]
        should_avoid = test_case["should_avoid"]
        desc = test_case["description"]
        
        print(f"\n📝 Test: {desc}")
        print(f"   Query: '{query}'")
        
        try:
            result = await tool.execute(query=query, campus_scope=campus, log_callback=print)
            
            success = result.get("success", False)
            text = result.get("text", "")
            response_mode = result.get("response_mode", "")
            
            test_passed = success
            
            # Check that we avoid BorrowingPolicy if specified
            if should_avoid and test_passed:
                if should_avoid in text:
                    print(f"   ❌ Should avoid '{should_avoid}' but it appeared")
                    test_passed = False
                else:
                    print(f"   ✅ Successfully avoided '{should_avoid}'")
            
            print(f"   Response mode: {response_mode}")
            print(f"   Text preview: {text[:150]}...")
            
            if test_passed:
                print(f"   ✅ PASSED")
                passed += 1
            else:
                print(f"   ❌ FAILED")
                failed += 1
        
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            failed += 1
    
    print(f"\n{'=' * 80}")
    print(f"Results: {passed} passed, {failed} failed\n")
    return failed == 0


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("OXFORD POLICY ROUTING SMOKE TESTS")
    print("=" * 80)
    print("\nNOTE: These tests require:")
    print("1. Weaviate running with CirculationPolicies and CirculationPolicyFacts collections")
    print("2. Data ingested via scripts/ingest_libguides_policies_oxford.py")
    print("3. Data upserted via scripts/upsert_policies_to_weaviate.py")
    print("\n" + "=" * 80 + "\n")
    
    # Run tests
    results = []
    
    print("Starting tests...\n")
    
    # Test 1: Campus detection
    result1 = await test_campus_detection()
    results.append(("Campus Detection", result1))
    
    # Test 2: Circulation policy tool
    result2 = await test_circulation_policy_tool()
    results.append(("Circulation Policy Tool", result2))
    
    # Test 3: Borrowing policy search tool
    result3 = await test_borrowing_policy_search_tool()
    results.append(("Borrowing Policy Search Tool", result3))
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n🎉 All tests passed!\n")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review output above.\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
