#!/usr/bin/env python3
"""
Google Site Search Integration Test Suite

Tests Google Site Search functionality end-to-end with:
- Pass A: Cold start (populate cache) - counts external calls
- Pass B: Warm cache (validate cache hits) - should have near-zero external calls

Outputs detailed JSONL with routing, cache hits, external calls, and URLs.
"""

import os
import sys
import csv
import json
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.orchestrator import library_graph
from src.state import AgentState
from src.utils.logger import AgentLogger


def extract_google_metrics_from_logs(log_messages: List[str]) -> Dict[str, Any]:
    """
    Extract Google Site Search metrics from log messages.
    
    Returns:
        Dict with external_call, cache_hit, blocked, urls
    """
    metrics = {
        "external_call": False,
        "cache_hit": False,
        "blocked": False,
        "urls": [],
        "google_tool_invoked": False
    }
    
    for msg in log_messages:
        # Check for Google tool invocation - multiple patterns
        if any(pattern in msg for pattern in [
            "[Google Site Enhanced Search]",
            "[CSE]",
            "Using tool: google_site_enhanced_search",
            "google_site_enhanced_search"
        ]):
            metrics["google_tool_invoked"] = True
        
        # Parse cache and external call indicators (case insensitive)
        if "external_call=true" in msg.lower():
            metrics["external_call"] = True
        if "cache_hit=true" in msg.lower():
            metrics["cache_hit"] = True
        if any(pattern in msg for pattern in ["blocked=disabled", "DISABLED", "CIRCUIT_OPEN"]):
            metrics["blocked"] = True
        
        # Extract URLs from results
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, msg)
        for url in urls:
            if "lib.miamioh.edu" in url and url not in metrics["urls"]:
                metrics["urls"].append(url)
    
    return metrics


async def run_single_query(
    question: str,
    expected_category: str,
    logger: AgentLogger,
    pass_name: str
) -> Dict[str, Any]:
    """
    Run a single query through the production routing pipeline.
    
    Returns:
        Dict with routing, Google metrics, and response information
    """
    import logging
    
    # Set up log capture for Python standard logging
    class LogCapture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages = []
        
        def emit(self, record):
            self.messages.append(self.format(record))
    
    log_capture = LogCapture()
    log_capture.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)
    
    capturing_logger = AgentLogger()
    
    # Initialize state
    initial_state: AgentState = {
        "user_message": question,
        "messages": [{"role": "user", "content": question}],
        "conversation_history": [],
        "_logger": capturing_logger,
    }
    
    try:
        # Invoke production graph
        result = await library_graph.ainvoke(initial_state)
        
        # Remove log handler
        root_logger.removeHandler(log_capture)
        
        # Extract routing information
        category = result.get("category")
        primary_agent_id = result.get("primary_agent_id")
        classification_confidence = result.get("classification_confidence")
        needs_clarification = result.get("needs_clarification", False)
        
        # Extract Google metrics from captured logs
        google_metrics = extract_google_metrics_from_logs(log_capture.messages)
        
        # Get response snippet
        messages = result.get("messages", [])
        response_snippet = ""
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                response_snippet = last_msg.get("content", "")[:300]
            else:
                response_snippet = str(last_msg)[:300]
        
        # Check if routing matches expectation
        category_match = category == expected_category if expected_category else None
        
        return {
            "pass": pass_name,
            "question": question,
            "expected_category": expected_category,
            "category": category,
            "category_match": category_match,
            "primary_agent_id": primary_agent_id,
            "classification_confidence": float(classification_confidence) if classification_confidence is not None else None,
            "needs_clarification": needs_clarification,
            "google_tool_invoked": google_metrics["google_tool_invoked"],
            "google_external_call": google_metrics["external_call"],
            "google_cache_hit": google_metrics["cache_hit"],
            "google_blocked": google_metrics["blocked"],
            "google_urls": google_metrics["urls"],
            "response_snippet": response_snippet,
            "status": "success",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "pass": pass_name,
            "question": question,
            "expected_category": expected_category,
            "category": None,
            "category_match": None,
            "primary_agent_id": None,
            "classification_confidence": None,
            "needs_clarification": None,
            "google_tool_invoked": False,
            "google_external_call": False,
            "google_cache_hit": False,
            "google_blocked": False,
            "google_urls": [],
            "response_snippet": None,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def run_test_pass(
    queries: List[Dict[str, str]],
    pass_name: str,
    output_jsonl: Path
) -> Dict[str, Any]:
    """
    Run a complete test pass (A or B) and return summary metrics.
    """
    print("=" * 80)
    print(f"PASS {pass_name}: {'Cold Start (Populate Cache)' if pass_name == 'A' else 'Warm Cache (Validate Cache Hits)'}")
    print("=" * 80)
    print()
    
    logger = AgentLogger()
    results = []
    
    for i, query_data in enumerate(queries, 1):
        question = query_data["question"]
        expected_category = query_data.get("expected_category", "")
        
        print(f"[{i}/{len(queries)}] {question[:70]}{'...' if len(question) > 70 else ''}")
        
        result = await run_single_query(question, expected_category, logger, pass_name)
        results.append(result)
        
        # Show brief status
        status = "✅" if result["status"] == "success" else "❌"
        agent = result.get("primary_agent_id", "N/A")
        google_call = "🌐" if result.get("google_external_call") else ""
        cache_hit = "💾" if result.get("google_cache_hit") else ""
        clarif = "⚠️" if result.get("needs_clarification") else ""
        
        print(f"  {status} {agent} {google_call}{cache_hit}{clarif}")
        
        # Brief delay to avoid overwhelming services
        await asyncio.sleep(0.5)
    
    # Write results to JSONL
    with open(output_jsonl, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
    
    # Calculate summary statistics
    total = len(results)
    successful = sum(1 for r in results if r["status"] == "success")
    errors = sum(1 for r in results if r["status"] == "error")
    clarifications = sum(1 for r in results if r.get("needs_clarification"))
    
    google_invoked = sum(1 for r in results if r.get("google_tool_invoked"))
    external_calls = sum(1 for r in results if r.get("google_external_call"))
    cache_hits = sum(1 for r in results if r.get("google_cache_hit"))
    blocked = sum(1 for r in results if r.get("google_blocked"))
    
    category_matches = sum(1 for r in results if r.get("category_match") is True)
    category_mismatches = sum(1 for r in results if r.get("category_match") is False)
    
    summary = {
        "pass": pass_name,
        "total_queries": total,
        "successful": successful,
        "errors": errors,
        "clarifications": clarifications,
        "google_tool_invoked": google_invoked,
        "google_external_calls": external_calls,
        "google_cache_hits": cache_hits,
        "google_blocked": blocked,
        "category_matches": category_matches,
        "category_mismatches": category_mismatches,
        "cache_hit_rate": f"{100*cache_hits/google_invoked:.1f}%" if google_invoked > 0 else "N/A"
    }
    
    print()
    print("=" * 80)
    print(f"PASS {pass_name} SUMMARY")
    print("=" * 80)
    print(f"Total queries: {total}")
    print(f"Successful: {successful}")
    print(f"Errors: {errors}")
    print(f"Clarifications: {clarifications}")
    print()
    print(f"Google tool invoked: {google_invoked}")
    print(f"Google external calls: {external_calls}")
    print(f"Google cache hits: {cache_hits}")
    print(f"Google blocked: {blocked}")
    print(f"Cache hit rate: {summary['cache_hit_rate']}")
    print()
    print(f"Category matches: {category_matches}")
    print(f"Category mismatches: {category_mismatches}")
    print()
    print(f"✅ Results saved to: {output_jsonl}")
    print("=" * 80)
    print()
    
    return summary


async def main():
    """Main integration test runner."""
    print("=" * 80)
    print("Google Site Search Integration Test Suite")
    print("=" * 80)
    print()
    
    # Check Google CSE status
    disable_flag = os.getenv("DISABLE_GOOGLE_SITE_SEARCH", "0")
    daily_limit = os.getenv("GOOGLE_SEARCH_DAILY_LIMIT", "0")
    cache_ttl = os.getenv("GOOGLE_SEARCH_CACHE_TTL_SECONDS", "0")
    
    print("📊 Configuration:")
    print(f"   DISABLE_GOOGLE_SITE_SEARCH: {disable_flag}")
    print(f"   GOOGLE_SEARCH_DAILY_LIMIT: {daily_limit}")
    print(f"   GOOGLE_SEARCH_CACHE_TTL_SECONDS: {cache_ttl}")
    print()
    
    if disable_flag == "1":
        print("⚠️  WARNING: Google Site Search is DISABLED")
        print("   Set DISABLE_GOOGLE_SITE_SEARCH=0 to enable for this test")
        print()
    
    # Define paths
    script_dir = Path(__file__).parent
    input_csv = script_dir.parent / "test_data" / "google_integration_queries.csv"
    output_pass_a = script_dir.parent / "test_data" / "google_integration_pass_a.jsonl"
    output_pass_b = script_dir.parent / "test_data" / "google_integration_pass_b.jsonl"
    
    # Check if input exists
    if not input_csv.exists():
        print(f"❌ Error: Input file not found: {input_csv}")
        return 1
    
    # Load queries
    queries: List[Dict[str, str]] = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            question = row.get('question', '').strip()
            expected_category = row.get('expected_category', '').strip()
            if question:
                queries.append({
                    "question": question,
                    "expected_category": expected_category
                })
    
    print(f"📊 Loaded {len(queries)} queries from {input_csv.name}")
    print()
    
    # Run Pass A (Cold Start)
    summary_a = await run_test_pass(queries, "A", output_pass_a)
    
    # Brief pause between passes
    print("⏳ Waiting 3 seconds before Pass B...")
    await asyncio.sleep(3)
    
    # Run Pass B (Warm Cache)
    summary_b = await run_test_pass(queries, "B", output_pass_b)
    
    # Final comparison
    print()
    print("=" * 80)
    print("FINAL COMPARISON: Pass A vs Pass B")
    print("=" * 80)
    print()
    print(f"External calls - Pass A: {summary_a['google_external_calls']}")
    print(f"External calls - Pass B: {summary_b['google_external_calls']}")
    print(f"Reduction: {summary_a['google_external_calls'] - summary_b['google_external_calls']}")
    print()
    print(f"Cache hits - Pass A: {summary_a['google_cache_hits']}")
    print(f"Cache hits - Pass B: {summary_b['google_cache_hits']}")
    print()
    print(f"Cache hit rate - Pass A: {summary_a['cache_hit_rate']}")
    print(f"Cache hit rate - Pass B: {summary_b['cache_hit_rate']}")
    print()
    
    # Go/No-Go assessment
    print("=" * 80)
    print("GO/NO-GO ASSESSMENT")
    print("=" * 80)
    
    checks = []
    
    # Check 1: Pass A completed successfully
    check1 = summary_a['successful'] >= len(queries) * 0.9
    checks.append(("Pass A 90%+ success rate", check1))
    
    # Check 2: Pass B completed successfully
    check2 = summary_b['successful'] >= len(queries) * 0.9
    checks.append(("Pass B 90%+ success rate", check2))
    
    # Check 3: Cache working (Pass B has significantly more cache hits than Pass A)
    check3 = summary_b['google_cache_hits'] > summary_a['google_cache_hits']
    checks.append(("Cache working (Pass B > Pass A hits)", check3))
    
    # Check 4: External calls reduced in Pass B
    check4 = summary_b['google_external_calls'] < summary_a['google_external_calls']
    checks.append(("External calls reduced in Pass B", check4))
    
    # Check 5: No blocking (Google not disabled)
    check5 = summary_a['google_blocked'] == 0 and summary_b['google_blocked'] == 0
    checks.append(("Google not blocked", check5))
    
    # Check 6: Routing consistency (Pass A and B should route similarly)
    check6 = abs(summary_a['category_matches'] - summary_b['category_matches']) <= 2
    checks.append(("Routing consistency between passes", check6))
    
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {check_name}")
    
    all_passed = all(passed for _, passed in checks)
    
    print()
    if all_passed:
        print("✅ GO FOR ALPHA - All checks passed")
    else:
        print("⚠️  NO-GO - Some checks failed, review required")
    
    print("=" * 80)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
