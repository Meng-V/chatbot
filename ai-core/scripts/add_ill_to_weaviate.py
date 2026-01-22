#!/usr/bin/env python3
"""
Add ILL data to Weaviate collection.

This script adds the ILL (Interlibrary Loan) Q&A data to the existing
TranscriptQA collection without deleting existing data.

Usage:
    python scripts/add_ill_to_weaviate.py
"""

import os
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client
from pathlib import Path
from dotenv import load_dotenv

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# No API keys needed for local Docker
ILL_DATA_PATH = "data/ill_rag_data.json"


def get_client():
    """Create Weaviate v4 client."""
    # Use centralized client for local Docker
    client = get_weaviate_client()
    if not client:
        raise ValueError("Could not connect to Weaviate local Docker instance")
    return client


def add_ill_data(client):
    """Add ILL data to TranscriptQA collection."""
    
    # Load ILL data
    ill_path = Path(__file__).parent.parent / ILL_DATA_PATH
    with open(ill_path, 'r', encoding='utf-8') as f:
        ill_data = json.load(f)
    
    print(f"📚 Loaded {len(ill_data)} ILL Q&A pairs")
    
    # Get the collection
    collection = client.collections.get("TranscriptQA")
    
    # Add objects
    success_count = 0
    error_count = 0
    
    for item in ill_data:
        try:
            collection.data.insert({
                "question": item.get("question", ""),
                "answer": item.get("answer", ""),
                "topic": item.get("topic", "interlibrary_loan"),
                "keywords": ["ILL", "interlibrary loan", "borrow", "request"]
            })
            success_count += 1
            print(f"  ✅ Added: {item.get('question', '')[:50]}...")
        except Exception as e:
            error_count += 1
            print(f"  ❌ Error: {e}")
    
    print(f"\n📊 Results: {success_count} added, {error_count} errors")
    return success_count, error_count


def main():
    print("=" * 60)
    print("ADD ILL DATA TO WEAVIATE")
    print("=" * 60)
    
    try:
        client = get_client()
        print("✅ Connected to Weaviate")
        
        success, errors = add_ill_data(client)
        
        client.close()
        print("✅ Connection closed")
        
        if errors == 0:
            print("\n🎉 All ILL data added successfully!")
        else:
            print(f"\n⚠️  Some errors occurred: {errors} failures")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
