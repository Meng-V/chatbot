#!/usr/bin/env python3
"""
List All RAG Corrections

Display all corrections currently in Weaviate database.

Usage:
    cd /Users/qum/Documents/GitHub/chatbot/ai-core
    source venv/bin/activate
    python scripts/list_rag_corrections.py
"""

import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv
import os
import sys
from datetime import datetime

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

WEAVIATE_URL = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
COLLECTION_NAME = "TranscriptQA"

def connect_to_weaviate():
    """Connect to Weaviate Cloud."""
    print(f"🔌 Connecting to Weaviate...")
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_URL,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY)
        )
        print("✅ Connected successfully\n")
        return client
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)

def list_all_corrections(client):
    """List all corrections in Weaviate."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        
        print("📋 Fetching all corrections...")
        print()
        
        # Get all objects
        response = collection.query.fetch_objects(
            limit=1000,  # Adjust if you have more corrections
            return_properties=["question", "answer", "topic", "confidence", "date_added"]
        )
        
        corrections = response.objects
        
        if not corrections:
            print("📭 No corrections found in database")
            return
        
        print(f"📊 Total corrections: {len(corrections)}")
        print("=" * 80)
        print()
        
        # Display each correction
        for i, obj in enumerate(corrections, 1):
            props = obj.properties
            uuid = obj.uuid
            
            question = props.get("question", "N/A")
            answer = props.get("answer", "N/A")
            topic = props.get("topic", "N/A")
            confidence = props.get("confidence", "N/A")
            date_added = props.get("date_added", "N/A")
            
            # Format date if available
            if date_added != "N/A":
                try:
                    dt = datetime.fromisoformat(date_added)
                    date_added = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            print(f"{i}. ID: {uuid}")
            print(f"   Topic: {topic}")
            print(f"   Confidence: {confidence}")
            print(f"   Added: {date_added}")
            print(f"   Question: {question[:80]}..." if len(question) > 80 else f"   Question: {question}")
            print(f"   Answer: {answer[:100]}..." if len(answer) > 100 else f"   Answer: {answer}")
            print()
        
        print("=" * 80)
        print(f"✅ Listed {len(corrections)} corrections")
        
    except Exception as e:
        print(f"❌ Error listing corrections: {e}")

def main():
    print("=" * 80)
    print("📋 LIST ALL RAG CORRECTIONS")
    print("=" * 80)
    print()
    
    # Connect to Weaviate
    client = connect_to_weaviate()
    
    # List corrections
    list_all_corrections(client)
    
    # Close connection
    print()
    client.close()
    print("🔌 Disconnected from Weaviate")

if __name__ == "__main__":
    main()
