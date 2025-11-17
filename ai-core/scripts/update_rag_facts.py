#!/usr/bin/env python3
"""
Update RAG Database with Correct Facts

This script allows you to add or update Q&A pairs in the Weaviate TranscriptQA collection.
Use this when you discover incorrect information that needs to be corrected.

Usage:
    python scripts/update_rag_facts.py

The script will:
1. Check if similar questions already exist
2. Update existing entries or add new ones
3. Verify the updates were successful
"""

import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment - .env is at repository root
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def connect_to_weaviate():
    """Connect to Weaviate cloud instance."""
    if not WEAVIATE_HOST or not WEAVIATE_API_KEY:
        raise ValueError("WEAVIATE_HOST and WEAVIATE_API_KEY must be set in .env file")
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_HOST,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
            headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
        )
        print("✅ Connected to Weaviate")
        return client
    except Exception as e:
        raise ConnectionError(f"Failed to connect to Weaviate: {e}")


# ========================================
# DEFINE YOUR FACTS TO ADD/UPDATE HERE
# ========================================

CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library was built in 1966 and underwent major renovations in 1973 and 2007.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1966", "construction", "history", "renovations", "1973", "2007"]
    },
    {
        "question": "Where is the makerspace located?",
        "answer": "The makerspace is located on the 3rd floor of King Library, in Room 303.",
        "topic": "location_information",
        "keywords": ["makerspace", "location", "King Library", "3rd floor", "Room 303", "303"]
    },
    {
        "question": "I have questions about MakerSpace, how should I contact?",
        "answer": "To contact the MakerSpace, please email create@miamioh.edu or call 513-529-2871. If you need more help, please check on our website at https://libguides.lib.miamioh.edu/create/makerspace/.",
        "topic": "location_information",
        "keywords": ["makerspace", "location", "King Library", "contact", "email", "phone", "website"]
    },
    # ADD MORE FACTS HERE
    # {
    #     "question": "Your question here",
    #     "answer": "Your answer here",
    #     "topic": "category",
    #     "keywords": ["keyword1", "keyword2", ...]
    # },
]


def add_or_update_fact(collection, fact, similarity_threshold=0.08):
    """
    Add a new fact or update existing one if very similar.
    
    Args:
        collection: Weaviate collection
        fact: Dict with question, answer, topic, keywords
        similarity_threshold: Distance threshold for considering a match (lower = more similar)
    
    Returns:
        (action, message) where action is 'added', 'updated', or 'skipped'
    """
    try:
        # Check if similar question already exists
        results = collection.query.near_text(
            query=fact["question"],
            limit=1,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        # If very similar exists, update it
        if results.objects and results.objects[0].metadata.distance < similarity_threshold:
            uuid = results.objects[0].uuid
            existing_q = results.objects[0].properties.get("question", "")
            distance = results.objects[0].metadata.distance
            
            collection.data.update(
                uuid=uuid,
                properties=fact
            )
            return "updated", f"Updated (distance: {distance:.3f}): '{existing_q}' → '{fact['question']}'"
        else:
            # Add new fact
            uuid = collection.data.insert(properties=fact)
            return "added", f"Added new: '{fact['question']}' (UUID: {uuid})"
    
    except Exception as e:
        return "error", f"Error with '{fact['question']}': {str(e)}"


def verify_fact(collection, question, expected_keywords=None):
    """Verify a fact was added/updated correctly."""
    try:
        results = collection.query.near_text(
            query=question,
            limit=1,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        if results.objects:
            obj = results.objects[0]
            props = obj.properties
            distance = obj.metadata.distance
            
            print(f"\n  📋 Verification:")
            print(f"     Question: {props.get('question', 'N/A')}")
            print(f"     Answer: {props.get('answer', 'N/A')[:100]}...")
            print(f"     Topic: {props.get('topic', 'N/A')}")
            print(f"     Keywords: {', '.join(props.get('keywords', [])[:5])}")
            print(f"     Similarity: {1-distance:.3f} (distance: {distance:.3f})")
            
            if distance < 0.05:
                print(f"     ✅ Excellent match!")
            elif distance < 0.15:
                print(f"     ✅ Good match")
            else:
                print(f"     ⚠️  Match quality could be improved")
            
            return True
        else:
            print(f"  ❌ Could not verify - no results found")
            return False
    
    except Exception as e:
        print(f"  ❌ Verification error: {e}")
        return False


def main():
    """Main function to update RAG facts."""
    print("="*70)
    print("RAG Fact Update Utility")
    print("="*70)
    print(f"\nTotal facts to process: {len(CORRECT_FACTS)}\n")
    
    # Connect to Weaviate
    try:
        client = connect_to_weaviate()
        collection = client.collections.get("TranscriptQA")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    # Track statistics
    stats = {"added": 0, "updated": 0, "error": 0}
    
    # Process each fact
    for i, fact in enumerate(CORRECT_FACTS, 1):
        print(f"\n[{i}/{len(CORRECT_FACTS)}] Processing: {fact['question']}")
        print("-" * 70)
        
        action, message = add_or_update_fact(collection, fact)
        stats[action] += 1
        
        if action == "added":
            print(f"✅ {message}")
        elif action == "updated":
            print(f"🔄 {message}")
        else:
            print(f"❌ {message}")
            continue
        
        # Verify the update
        verify_fact(collection, fact["question"], fact.get("keywords"))
    
    # Print summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"✅ Added: {stats['added']}")
    print(f"🔄 Updated: {stats['updated']}")
    print(f"❌ Errors: {stats['error']}")
    print(f"📊 Total processed: {stats['added'] + stats['updated'] + stats['error']}")
    print("\n✅ All facts updated in RAG database!")
    print("\nNext steps:")
    print("1. Test the queries using: python scripts/test_fact_queries.py")
    print("2. Ask the chatbot the questions to verify end-to-end")
    print("="*70)
    
    # Close connection
    client.close()


if __name__ == "__main__":
    main()
