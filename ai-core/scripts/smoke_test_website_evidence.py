#!/usr/bin/env python3
"""
Smoke test for website evidence search.

Tests the website evidence search functionality with sample queries
to verify that the import and search are working correctly.

Usage:
    python scripts/smoke_test_website_evidence.py
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

sys.path.insert(0, str(root_dir / "ai-core"))

from src.services.website_evidence_search import search_website_evidence, get_collection_name
from src.utils.redirect_resolver import resolve_url


# Test queries
TEST_QUERIES = [
    "How do I borrow a laptop from the library?",
    "What are the library hours?",
    "Can I check out Adobe Creative Cloud?",
    "Where can I find a study room?",
    "Does the library have 3D printing?",
]


async def test_search(query: str, top_k: int = 3):
    """Test a single search query."""
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"{'='*70}")
    
    results = await search_website_evidence(
        query=query,
        top_k=top_k
    )
    
    if not results:
        print("❌ No results found")
        return False
    
    print(f"✅ Found {len(results)} results\n")
    
    for idx, result in enumerate(results, 1):
        title = result.get("title", "N/A")
        score = result.get("score", 0)
        final_url = result.get("final_url", "N/A")
        chunk_text = result.get("chunk_text", "")
        chunk_index = result.get("chunk_index", 0)
        
        # Apply redirect resolution
        resolved_url = resolve_url(final_url)
        redirect_note = " (redirected)" if resolved_url != final_url else ""
        
        print(f"Result {idx}:")
        print(f"  Title: {title}")
        print(f"  Score: {score:.3f}")
        print(f"  URL: {resolved_url}{redirect_note}")
        print(f"  Chunk: {chunk_index}")
        print(f"  Text: {chunk_text[:150]}...")
        print()
    
    return True


async def main():
    """Run smoke tests."""
    print("="*70)
    print("🌐 Website Evidence Search - Smoke Test")
    print("="*70)
    
    # Check environment
    collection_name = get_collection_name()
    print(f"\nCollection: {collection_name}")
    
    weaviate_host = os.getenv("WEAVIATE_HOST", "NOT SET")
    openai_api_key = os.getenv("OPENAI_API_KEY", "NOT SET")
    
    print(f"Weaviate Host: {weaviate_host}")
    print(f"OpenAI API Key: {'SET' if openai_api_key != 'NOT SET' else 'NOT SET'}")
    
    if weaviate_host == "NOT SET" or openai_api_key == "NOT SET":
        print("\n❌ Error: Missing required environment variables")
        print("   Please ensure WEAVIATE_HOST and OPENAI_API_KEY are set in .env")
        sys.exit(1)
    
    # Run tests
    print(f"\n{'='*70}")
    print(f"Running {len(TEST_QUERIES)} test queries")
    print(f"{'='*70}")
    
    success_count = 0
    for query in TEST_QUERIES:
        try:
            success = await test_search(query, top_k=3)
            if success:
                success_count += 1
        except Exception as e:
            print(f"\n❌ Error testing query '{query}': {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*70)
    print("📊 Test Summary")
    print("="*70)
    print(f"Total queries: {len(TEST_QUERIES)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(TEST_QUERIES) - success_count}")
    
    if success_count == len(TEST_QUERIES):
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n⚠️ {len(TEST_QUERIES) - success_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
