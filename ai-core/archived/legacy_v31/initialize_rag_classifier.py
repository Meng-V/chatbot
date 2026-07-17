"""
Initialize RAG-based Question Classifier

This script:
1. Creates the Weaviate schema for question categories
2. Embeds all category examples into the vector store
3. Tests the classifier with sample questions

Run this after setting up Weaviate to enable RAG-based classification.
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST before any other imports
root_dir = Path(__file__).resolve().parent.parent
env_path = root_dir.parent / ".env"
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, str(root_dir))

from src.classification.rag_classifier import RAGQuestionClassifier
from src.classification.category_examples import get_all_examples_for_embedding


async def main():
    """Initialize the RAG classifier vector store."""
    
    print("=" * 80)
    print("RAG Question Classifier Initialization")
    print("=" * 80)
    
    classifier = RAGQuestionClassifier()
    
    print("\n📦 Step 1: Creating Weaviate schema...")
    await classifier.initialize_vector_store(force_refresh=True)
    print("✅ Schema created and examples embedded")
    
    examples = get_all_examples_for_embedding()
    in_scope_count = sum(1 for ex in examples if ex["is_in_scope"])
    out_of_scope_count = sum(1 for ex in examples if not ex["is_in_scope"])
    
    print(f"\n📊 Statistics:")
    print(f"   Total examples: {len(examples)}")
    print(f"   In-scope examples: {in_scope_count}")
    print(f"   Out-of-scope examples: {out_of_scope_count}")
    
    print("\n🧪 Step 2: Testing classifier with sample questions...")
    
    test_questions = [
        "Can I borrow a laptop from the library?",
        "My computer is broken, who can fix it?",
        "I have a question about computers",
        "What time does King Library close?",
        "I need 5 articles about climate change",
        "Who is the biology librarian?",
        "How do I register for classes?",
        "Can I talk to a librarian?",
    ]
    
    for question in test_questions:
        print(f"\n❓ Question: {question}")
        result = await classifier.classify_question(question)
        
        print(f"   Category: {result['category']}")
        print(f"   Confidence: {result['confidence']:.2f}")
        print(f"   Agent: {result['agent']}")
        
        if result.get('needs_clarification'):
            print(f"   ⚠️  Needs clarification:")
            print(f"   {result['clarification_question']}")
        
        if result.get('similar_examples'):
            print(f"   Similar examples:")
            for ex in result['similar_examples'][:2]:
                print(f"      - {ex}")
    
    print("\n" + "=" * 80)
    print("✅ Initialization complete!")
    print("=" * 80)
    print("\nThe RAG classifier is now ready to use.")
    print("You can now update your orchestrator to use classify_with_rag()")


if __name__ == "__main__":
    asyncio.run(main())
