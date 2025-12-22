"""
Example: Using the RAG-Based Question Classifier

This example shows how to integrate the RAG classifier into your application.
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

# Load .env from project root
env_path = root_dir.parent / ".env"
load_dotenv(dotenv_path=env_path)

from src.classification.rag_classifier import RAGQuestionClassifier, classify_with_rag


async def example_basic_usage():
    """Basic usage example."""
    
    print("=" * 80)
    print("EXAMPLE 1: Basic Classification")
    print("=" * 80)
    
    questions = [
        "Can I borrow a laptop from the library?",
        "My computer is broken, who can fix it?",
        "What time does King Library close?",
        "I need 5 articles about climate change",
    ]
    
    for question in questions:
        print(f"\nQuestion: {question}")
        
        result = await classify_with_rag(question)
        
        print(f"  Category: {result['category']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Agent: {result['agent']}")
        
        if result.get('needs_clarification'):
            print(f"  ⚠️  Clarification needed:")
            print(f"  {result['clarification_question']}")


async def example_with_classifier_instance():
    """Using classifier instance for multiple queries."""
    
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Using Classifier Instance")
    print("=" * 80)
    
    classifier = RAGQuestionClassifier()
    
    await classifier.initialize_vector_store()
    
    questions = [
        "I have a question about computers",
        "Who is the biology librarian?",
        "How do I register for classes?",
    ]
    
    for question in questions:
        result = await classifier.classify_question(question)
        
        print(f"\nQ: {question}")
        print(f"A: Category={result['category']}, Confidence={result['confidence']:.2f}")


async def example_handling_clarification():
    """Example of handling clarification requests."""
    
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Handling Clarification")
    print("=" * 80)
    
    question = "I need help with computer stuff"
    
    result = await classify_with_rag(question)
    
    print(f"Question: {question}")
    print(f"Category: {result['category']}")
    
    if result.get('needs_clarification'):
        print("\n🤖 Bot Response:")
        print(result['clarification_question'])
        
        print("\n📋 Possible categories:")
        for cat in result.get('alternative_categories', []):
            print(f"  - {cat}")
        
        print("\n💡 How to handle:")
        print("  1. Show clarification question to user")
        print("  2. Get user's choice")
        print("  3. Route to appropriate agent based on choice")


async def example_integration_with_router():
    """Example of integrating with your router."""
    
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Integration Pattern")
    print("=" * 80)
    
    async def handle_user_query(user_message: str):
        """Example handler function."""
        
        result = await classify_with_rag(user_message)
        
        category = result['category']
        confidence = result['confidence']
        
        if result.get('needs_clarification'):
            return {
                "type": "clarification",
                "message": result['clarification_question'],
                "alternatives": result.get('alternative_categories', [])
            }
        
        if category.startswith('out_of_scope_'):
            return {
                "type": "out_of_scope",
                "message": "I can only help with library-related questions. For this type of question, please contact..."
            }
        
        agent = result['agent']
        
        return {
            "type": "route_to_agent",
            "agent": agent,
            "category": category,
            "confidence": confidence
        }
    
    test_queries = [
        "Can I borrow a laptop?",
        "I have a computer question",
        "How do I register for classes?",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        response = await handle_user_query(query)
        print(f"Response: {response}")


async def main():
    """Run all examples."""
    
    print("\n🚀 RAG Classifier Usage Examples\n")
    
    try:
        await example_basic_usage()
        await example_with_classifier_instance()
        await example_handling_clarification()
        await example_integration_with_router()
        
        print("\n" + "=" * 80)
        print("✅ All examples completed successfully!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("  1. Weaviate is running (docker ps | grep weaviate)")
        print("  2. Vector store is initialized (python scripts/initialize_rag_classifier.py)")
        print("  3. OPENAI_API_KEY is set in .env")


if __name__ == "__main__":
    asyncio.run(main())
