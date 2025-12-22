#!/usr/bin/env python3
"""
Test Margin-Based Classification with LLM Fallback

This script demonstrates the margin-based classification system by testing
questions with varying levels of ambiguity to show when LLM fallback is triggered.
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


async def test_with_different_thresholds(question: str):
    """Test a question with different margin thresholds."""
    print("=" * 100)
    print(f"Question: {question}")
    print("=" * 100)
    
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.30]
    
    for threshold in thresholds:
        result = await classify_with_rag(question)
        
        margin = result.get('margin', 'N/A')
        margin_str = f"{margin:.3f}" if isinstance(margin, float) else margin
        llm_used = "🤖 YES" if result.get('llm_decision') else "❌ NO"
        
        print(f"\nThreshold: {threshold:.2f} | Margin: {margin_str} | LLM Used: {llm_used}")
        print(f"  → Category: {result['category']} (confidence: {result['confidence']:.2f})")
        
        if result.get('llm_reasoning'):
            print(f"  → LLM Reasoning: {result['llm_reasoning'][:80]}...")
    
    print()


async def main():
    """Main test function."""
    print("\n" + "=" * 100)
    print("MARGIN-BASED CLASSIFICATION TEST SUITE")
    print("Testing how margin thresholds affect LLM fallback decisions")
    print("=" * 100 + "\n")
    
    # Test questions with varying ambiguity levels
    test_cases = [
        {
            "category": "Clear Questions (High Margin Expected)",
            "questions": [
                "What time does King Library close?",
                "Who is the biology librarian?",
                "Can I borrow a laptop?",
            ]
        },
        {
            "category": "Moderately Ambiguous (Medium Margin)",
            "questions": [
                "How do I get Adobe?",
                "I need help with printing",
                "Library hours at Hamilton",
            ]
        },
        {
            "category": "Highly Ambiguous (Low Margin Expected)",
            "questions": [
                "Computer question",
                "I have a question about computers",
                "Help with equipment",
            ]
        }
    ]
    
    for test_category in test_cases:
        print(f"\n{'=' * 100}")
        print(f"TEST CATEGORY: {test_category['category']}")
        print(f"{'=' * 100}\n")
        
        for question in test_category['questions']:
            result = await classify_with_rag(question)
            
            margin = result.get('margin')
            margin_str = f"{margin:.3f}" if margin is not None else "N/A"
            llm_used = "🤖 YES" if result.get('llm_decision') else "❌ NO"
            
            print(f"Question: {question}")
            print(f"  Category: {result['category']}")
            print(f"  Confidence: {result['confidence']:.2f}")
            print(f"  Margin: {margin_str}")
            print(f"  LLM Used: {llm_used}")
            
            if result.get('alternative_category'):
                print(f"  Alternative: {result['alternative_category']}")
            
            if result.get('llm_reasoning'):
                print(f"  LLM Reasoning: {result['llm_reasoning']}")
            
            print()
    
    print("\n" + "=" * 100)
    print("TEST COMPLETE")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
