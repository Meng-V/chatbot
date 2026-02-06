#!/usr/bin/env python3
"""
Verify RAG Correction - Test if Bot Will Use It

This script tests if a correction exists in Weaviate and how well it matches
a given question.

Usage:
    cd /Users/qum/Documents/GitHub/chatbot/ai-core
    source venv/bin/activate
    python scripts/verify_correction.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

COLLECTION_NAME = "TranscriptQA"

def connect_to_weaviate():
    """Connect to Weaviate LOCAL DOCKER."""
    print(f"🔌 Connecting to Weaviate (local Docker)...")
    
    try:
        client = get_weaviate_client()
        if client:
            print("✅ Connected successfully")
        return client
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

def search_correction(client, question):
    """Search for a correction matching the question."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        
        print(f"🔍 Searching for corrections matching:")
        print(f"   \"{question}\"")
        print()
        
        # Search using vector similarity
        response = collection.query.near_text(
            query=question,
            limit=3,  # Show top 3 matches
            return_metadata=wvc.query.MetadataQuery(distance=True),
            return_properties=["question", "answer", "topic", "confidence"]
        )
        
        if not response.objects:
            print("❌ No corrections found matching this question")
            print()
            print("Suggestions:")
            print("1. Add a correction using: python scripts/add_correction_to_rag.py")
            print("2. Check if question wording matches correction")
            print("3. List all corrections: python scripts/list_rag_corrections.py")
            return
        
        print(f"✅ Found {len(response.objects)} matching correction(s)\n")
        
        # Display matches
        for i, obj in enumerate(response.objects, 1):
            props = obj.properties
            distance = obj.metadata.distance if obj.metadata else None
            similarity = 1 - distance if distance else None
            
            print("=" * 70)
            print(f"Match #{i}")
            print("=" * 70)
            print(f"Similarity: {similarity:.3f}" if similarity else "Similarity: N/A")
            
            if similarity:
                if similarity > 0.85:
                    print("✅ EXCELLENT match - Bot will definitely use this")
                elif similarity > 0.70:
                    print("✅ GOOD match - Bot will likely use this")
                elif similarity > 0.50:
                    print("⚠️  MODERATE match - Bot might use this")
                else:
                    print("❌ POOR match - Bot probably won't use this")
            
            print()
            print(f"Topic: {props.get('topic', 'N/A')}")
            print(f"Confidence: {props.get('confidence', 'N/A')}")
            print(f"UUID: {obj.uuid}")
            print()
            print(f"Stored Question: {props.get('question', 'N/A')}")
            print()
            print("Answer:")
            answer = props.get('answer', 'N/A')
            print(answer)
            print()
        
        # Provide recommendations
        best_match = response.objects[0]
        best_similarity = 1 - best_match.metadata.distance if best_match.metadata else None
        
        if best_similarity and best_similarity < 0.70:
            print("💡 RECOMMENDATION:")
            print("   Similarity is below 0.70. Consider:")
            print("   1. Adding more question variations")
            print("   2. Rewording the stored question to match user phrasing")
            print("   3. Using more keywords that users typically use")
            print()
        
    except Exception as e:
        print(f"❌ Error searching: {e}")

def main():
    print("=" * 70)
    print("🔍 VERIFY RAG CORRECTION")
    print("=" * 70)
    print()
    
    # Get question from user
    print("Enter the question you want to test:")
    question = input("❓ ").strip()
    
    if not question:
        print("❌ Question cannot be empty")
        sys.exit(1)
    
    print()
    
    # Connect to Weaviate
    client = connect_to_weaviate()
    
    # Search for correction
    search_correction(client, question)
    
    # Close connection
    client.close()
    print("🔌 Disconnected from Weaviate")

if __name__ == "__main__":
    main()
