#!/usr/bin/env python3
"""Quick smoke test for Google CSE integration with proper metric capture."""
import asyncio
import sys
import logging
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.orchestrator import library_graph
from src.state import AgentState
from src.utils.logger import AgentLogger


class LogCapture(logging.Handler):
    """Custom logging handler to capture log messages."""
    def __init__(self):
        super().__init__()
        self.messages = []
    
    def emit(self, record):
        self.messages.append(self.format(record))


async def test_query(query: str):
    """Test a single query and capture all metrics."""
    print(f"\n{'='*80}")
    print(f"Testing: {query}")
    print(f"{'='*80}")
    
    # Set up log capture
    log_capture = LogCapture()
    log_capture.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)
    
    logger = AgentLogger()
    
    state: AgentState = {
        "user_message": query,
        "conversation_history": [],
        "_logger": logger
    }
    
    result = await library_graph.ainvoke(state)
    
    # Remove handler
    root_logger.removeHandler(log_capture)
    
    # Get all captured log messages
    log_messages = log_capture.messages
    
    # Analyze logs
    google_invoked = False
    cache_hit = False
    external_call = False
    
    for msg in log_messages:
        if "Using tool: google_site_enhanced_search" in msg:
            google_invoked = True
            print(f"✅ Google tool invoked")
        if "cache_hit=true" in msg.lower():
            cache_hit = True
            print(f"💾 Cache hit detected")
        if "external_call=true" in msg.lower():
            external_call = True
            print(f"🌐 External call detected")
    
    print(f"\nMetrics:")
    print(f"  Agent: {result.get('primary_agent_id')}")
    print(f"  Google invoked: {google_invoked}")
    print(f"  Cache hit: {cache_hit}")
    print(f"  External call: {external_call}")
    
    if result.get("final_answer"):
        print(f"\nResponse (first 200 chars):")
        print(f"  {result['final_answer'][:200]}...")
    
    return {
        "query": query,
        "agent": result.get("primary_agent_id"),
        "google_invoked": google_invoked,
        "cache_hit": cache_hit,
        "external_call": external_call
    }


async def main():
    print("\n" + "="*80)
    print("GOOGLE CSE SMOKE TEST")
    print("="*80)
    
    test_queries = [
        "What is the library borrowing policy?",
        "How long can I check out a book?",
        "What are the fines for overdue books?"
    ]
    
    results = []
    for query in test_queries:
        result = await test_query(query)
        results.append(result)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    total_google = sum(1 for r in results if r["google_invoked"])
    total_cache = sum(1 for r in results if r["cache_hit"])
    total_external = sum(1 for r in results if r["external_call"])
    
    print(f"Total queries: {len(results)}")
    print(f"Google invoked: {total_google}/{len(results)}")
    print(f"Cache hits: {total_cache}/{len(results)}")
    print(f"External calls: {total_external}/{len(results)}")
    
    if total_google == len(results):
        print(f"\n✅ SUCCESS: All queries invoked Google CSE")
    else:
        print(f"\n❌ FAIL: Only {total_google}/{len(results)} queries invoked Google CSE")


if __name__ == "__main__":
    asyncio.run(main())
