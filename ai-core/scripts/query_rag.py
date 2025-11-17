#!/usr/bin/env python3
"""
Query RAG Database Directly

Simple utility to query the Weaviate RAG database and see results.
Useful for debugging and verifying database contents.

Usage:
    python scripts/query_rag.py "Your question here"
    
Example:
    python scripts/query_rag.py "When was King Library built?"
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.transcript_rag_agent import transcript_rag_query


async def query_rag(question: str, num_results: int = 5):
    """Query RAG database and display results."""
    print("="*80)
    print("RAG DATABASE QUERY")
    print("="*80)
    print(f"\nQuestion: {question}\n")
    print("-"*80)
    
    result = await transcript_rag_query(question)
    
    print("\n📊 QUERY RESULTS:")
    print(f"   Success: {result.get('success', False)}")
    print(f"   Confidence: {result.get('confidence', 'unknown')}")
    print(f"   Similarity Score: {result.get('similarity_score', 0):.3f}")
    print(f"   Matched Topic: {result.get('matched_topic', 'N/A')}")
    print(f"   Number of Results: {result.get('num_results', 0)}")
    
    if result.get('top_keywords'):
        print(f"   Top Keywords: {', '.join(result['top_keywords'])}")
    
    print(f"\n📝 ANSWER:")
    print("-"*80)
    print(result.get('text', 'No answer found'))
    print("-"*80)
    
    if result.get('error'):
        print(f"\n❌ Error: {result['error']}")
    
    # Provide recommendation
    similarity = result.get('similarity_score', 0)
    print(f"\n💡 RECOMMENDATION:")
    if similarity >= 0.85:
        print("   ✅ Excellent match - use this answer confidently")
    elif similarity >= 0.75:
        print("   ✅ Good match - answer is likely relevant")
    elif similarity >= 0.65:
        print("   ⚠️  Fair match - verify answer accuracy")
    elif similarity >= 0.50:
        print("   ⚠️  Low confidence - consider adding more specific Q&A pair")
    else:
        print("   ❌ Poor match - add this Q&A pair to RAG database")
        print("   Action: Use scripts/update_rag_facts.py to add correct answer")
    
    print("="*80)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/query_rag.py \"Your question here\"")
        print("\nExample:")
        print('  python scripts/query_rag.py "When was King Library built?"')
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    
    try:
        asyncio.run(query_rag(question))
    except KeyboardInterrupt:
        print("\n\n⚠️  Query interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
