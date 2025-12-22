#!/usr/bin/env python3
"""
Test RAG Classification
Quick script to test question classification without env loading issues.
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST before any other imports
root_dir = Path(__file__).resolve().parent.parent
env_path = root_dir.parent / ".env"
load_dotenv(dotenv_path=env_path)

# NOW import the classifier
sys.path.insert(0, str(root_dir))
from src.classification.rag_classifier import classify_with_rag


async def test_question(question: str, margin_threshold: float = 0.15):
    """Test a single question classification."""
    print("="*80)
    print(f"Testing: {question}")
    print("="*80)
    
    result = await classify_with_rag(question)
    
    print(f"\n✅ Results:")
    print(f"   Category: {result['category']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Agent: {result.get('agent', 'N/A')}")
    
    # Display margin information
    if result.get('margin') is not None:
        margin = result['margin']
        margin_status = "✅ High" if margin >= margin_threshold else "⚠️ Low"
        print(f"   Margin (Top-1 vs Top-2): {margin:.3f} {margin_status}")
        
        if result.get('alternative_category'):
            print(f"   Alternative Category: {result['alternative_category']}")
    
    # Display LLM decision info
    if result.get('llm_decision'):
        print(f"   🤖 LLM Decision: YES")
        if result.get('llm_reasoning'):
            print(f"   LLM Reasoning: {result['llm_reasoning']}")
    else:
        print(f"   🤖 LLM Decision: NO (used RAG only)")
    
    print(f"   Needs Clarification: {result.get('needs_clarification', False)}")
    
    if result.get('similar_examples'):
        print(f"\n📝 Top matching examples:")
        for i, ex in enumerate(result['similar_examples'][:3], 1):
            print(f"   {i}. {ex}")
    
    print("\n" + "="*80)
    return result


async def main():
    """Main test function."""
    if len(sys.argv) > 1:
        # Test question from command line argument
        question = " ".join(sys.argv[1:])
        await test_question(question)
    else:
        # Test a few default questions including ambiguous ones
        print("\n🎯 Testing Classification with Margin-Based LLM Fallback\n")
        
        test_questions = [
            # Clear cases (should have high margin, no LLM needed)
            "What time does King Library close?",
            "Can I borrow a laptop?",
            "Who is the biology librarian?",
            
            # Potentially ambiguous cases (may trigger LLM fallback)
            "How do I get Adobe",
            "I need help with printing",
            "Computer question",
            "I need a computer",
            
            # Edge cases
            "Library hours at Hamilton",
            "Can I eat in the library?",
        ]
        
        for q in test_questions:
            await test_question(q)
            print()


if __name__ == "__main__":
    asyncio.run(main())
