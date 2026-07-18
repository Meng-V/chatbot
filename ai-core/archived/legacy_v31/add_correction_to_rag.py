#!/usr/bin/env python3
"""
Add Correction to RAG - Interactive Script

This script allows librarians to add corrected question-answer pairs to Weaviate
to fix bot mistakes.

Usage:
    cd /Users/qum/Documents/GitHub/chatbot/ai-core
    source venv/bin/activate
    python scripts/add_correction_to_rag.py

The script will prompt for:
- Question (what user might ask)
- Correct answer
- Topic/category
- Confidence level (high/medium/low)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from langchain_openai import OpenAIEmbeddings

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

def get_user_input():
    """Get correction details from user interactively."""
    print("=" * 70)
    print("📝 ADD CORRECTION TO RAG")
    print("=" * 70)
    print()
    print("Enter the details for the correction:")
    print()
    
    # Get question
    question = input("❓ Question (what users might ask): ").strip()
    if not question:
        print("❌ Question cannot be empty")
        sys.exit(1)
    
    print()
    
    # Get answer
    print("💡 Answer (correct information):")
    print("   (Press Enter twice when done)")
    answer_lines = []
    while True:
        line = input()
        if line == "" and answer_lines and answer_lines[-1] == "":
            break
        answer_lines.append(line)
    
    answer = "\n".join(answer_lines).strip()
    if not answer:
        print("❌ Answer cannot be empty")
        sys.exit(1)
    
    print()
    
    # Get topic
    topic = input("🏷️  Topic/category (e.g., laptop_checkout_policy): ").strip()
    if not topic:
        topic = "general"
    
    print()
    
    # Get confidence
    print("📊 Confidence level:")
    print("   high   - Official policy, well-documented")
    print("   medium - Interpretation, some nuance")
    print("   low    - Edge case, might need verification")
    confidence = input("   Enter (high/medium/low): ").strip().lower()
    
    if confidence not in ["high", "medium", "low"]:
        print("⚠️  Invalid confidence, defaulting to 'medium'")
        confidence = "medium"
    
    print()
    
    # Show summary
    print("=" * 70)
    print("📋 SUMMARY")
    print("=" * 70)
    print(f"Question: {question}")
    print(f"Answer: {answer[:100]}..." if len(answer) > 100 else f"Answer: {answer}")
    print(f"Topic: {topic}")
    print(f"Confidence: {confidence}")
    print()
    
    confirm = input("Add this correction? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("❌ Cancelled")
        sys.exit(0)
    
    return {
        "question": question,
        "answer": answer,
        "topic": topic,
        "confidence": confidence
    }

def add_to_weaviate(client, correction_data):
    """Add correction to Weaviate."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        
        print()
        print("➕ Adding to Weaviate...")
        
        # Prepare data
        data = {
            "question": correction_data["question"],
            "answer": correction_data["answer"],
            "topic": correction_data["topic"],
            "confidence": correction_data["confidence"],
            "date_added": datetime.now().isoformat()
        }
        
        # Add to Weaviate
        uuid = collection.data.insert(data)
        
        print(f"✅ Successfully added correction!")
        print(f"   Weaviate ID: {uuid}")
        print()
        
        return uuid
        
    except Exception as e:
        print(f"❌ Error adding to Weaviate: {e}")
        return None

def verify_correction(client, uuid, question):
    """Verify the correction was added and can be found."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        
        print("🔍 Verifying correction...")
        
        # Search for the question
        response = collection.query.near_text(
            query=question,
            limit=1,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        if response.objects:
            obj = response.objects[0]
            distance = obj.metadata.distance if obj.metadata else None
            similarity = 1 - distance if distance else None
            
            print(f"✅ Correction found via search")
            print(f"   Similarity: {similarity:.3f}" if similarity else "   Similarity: N/A")
            print(f"   Topic: {obj.properties.get('topic', 'N/A')}")
            print()
            return True
        else:
            print("⚠️  Could not find correction via search (might need indexing time)")
            return False
            
    except Exception as e:
        print(f"⚠️  Verification error: {e}")
        return False

def main():
    # Get correction details from user
    correction_data = get_user_input()
    
    # Connect to Weaviate
    client = connect_to_weaviate()
    
    # Add correction
    uuid = add_to_weaviate(client, correction_data)
    
    if uuid:
        # Verify
        verify_correction(client, uuid, correction_data["question"])
        
        print("=" * 70)
        print("✅ CORRECTION ADDED SUCCESSFULLY")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Test the correction using: python scripts/verify_correction.py")
        print("2. Monitor bot responses to ensure correction is working")
        print("3. Document the correction in your maintenance log")
        print()
    else:
        print("❌ Failed to add correction")
    
    # Close connection
    client.close()
    print("🔌 Disconnected from Weaviate")

if __name__ == "__main__":
    main()
