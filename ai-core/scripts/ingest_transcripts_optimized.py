#!/usr/bin/env python3
"""
Ingest Optimized Transcripts into Weaviate

This script ingests the optimized Q&A dataset with a simplified schema:
- Only 4 fields: question, answer, keywords, topic
- Optimized for vector search performance
- No unnecessary metadata

Usage:
    python3 scripts/ingest_transcripts_optimized.py
    
    # Or specify custom file
    TRANSCRIPTS_PATH=data/custom.json python3 scripts/ingest_transcripts_optimized.py
"""

import os
import json
import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TRANSCRIPTS_PATH = os.getenv("TRANSCRIPTS_PATH", "data/optimized_for_weaviate.json")


def get_client():
    """Create Weaviate v4 client."""
    if not WEAVIATE_HOST or not WEAVIATE_API_KEY:
        raise ValueError("Missing WEAVIATE_HOST or WEAVIATE_API_KEY in .env file")
    
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_HOST,
        auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
        headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
    )
    return client


def create_optimized_collection(client):
    """
    Create optimized TranscriptQA collection with minimal schema.
    
    Schema:
    - question (text): The generalized question
    - answer (text): The comprehensive answer
    - keywords (text[]): Key concepts for retrieval
    - topic (text): Classified topic category
    """
    # Delete old collection if exists
    try:
        client.collections.delete("TranscriptQA")
        print("🗑️  Deleted existing TranscriptQA collection")
    except:
        pass
    
    # Create new collection with simplified schema
    client.collections.create(
        name="TranscriptQA",
        vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(
            model="text-embedding-3-small"
        ),
        properties=[
            wvc.config.Property(
                name="question",
                data_type=wvc.config.DataType.TEXT,
                description="Generalized question for broad applicability"
            ),
            wvc.config.Property(
                name="answer",
                data_type=wvc.config.DataType.TEXT,
                description="Comprehensive, objective answer"
            ),
            wvc.config.Property(
                name="keywords",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="Key concepts and terms"
            ),
            wvc.config.Property(
                name="topic",
                data_type=wvc.config.DataType.TEXT,
                description="Topic category (discovery_search, policy_or_service, etc.)"
            )
        ]
    )
    print("✅ Created optimized TranscriptQA collection")
    print("   Schema: question, answer, keywords, topic")


def ingest(client, transcripts_path: str):
    """Ingest optimized Q&A pairs into Weaviate."""
    # Load data
    with open(transcripts_path, 'r', encoding='utf-8') as f:
        qa_pairs = json.load(f)
    
    print(f"📦 Preparing to ingest {len(qa_pairs)} optimized Q&A pairs...")
    
    # Get collection
    collection = client.collections.get("TranscriptQA")
    
    # Batch insert
    success_count = 0
    error_count = 0
    
    with collection.batch.dynamic() as batch:
        for i, qa in enumerate(qa_pairs):
            try:
                # Prepare data object (only required fields)
                data_object = {
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", ""),
                    "keywords": qa.get("keywords", []),
                    "topic": qa.get("topic", "general_question")
                }
                
                batch.add_object(properties=data_object)
                success_count += 1
                
                # Progress indicator
                if (i + 1) % 100 == 0:
                    print(f"   Progress: {i + 1}/{len(qa_pairs)}...")
                
            except Exception as e:
                error_count += 1
                print(f"   ⚠️  Error inserting item {i}: {e}")
    
    print(f"✅ Ingestion complete!")
    print(f"   Success: {success_count}")
    print(f"   Errors: {error_count}")
    print(f"   Total: {len(qa_pairs)}")


def verify_ingestion(client):
    """Verify data was ingested correctly."""
    collection = client.collections.get("TranscriptQA")
    
    # Get a sample item
    response = collection.query.fetch_objects(limit=3)
    
    if response.objects:
        print(f"\n📊 Verification - Sample Items:")
        for i, obj in enumerate(response.objects, 1):
            print(f"\n   Sample {i}:")
            print(f"   Question: {obj.properties['question'][:80]}...")
            print(f"   Answer: {obj.properties['answer'][:80]}...")
            print(f"   Keywords: {', '.join(obj.properties.get('keywords', [])[:5])}")
            print(f"   Topic: {obj.properties['topic']}")
    
    # Get total count
    agg = collection.aggregate.over_all(total_count=True)
    print(f"\n✅ Total items in collection: {agg.total_count}")


def main():
    print("="*70)
    print("🚀 Ingesting Optimized Transcripts into Weaviate")
    print("="*70)
    print(f"Data file: {TRANSCRIPTS_PATH}")
    print(f"Weaviate host: {WEAVIATE_HOST}")
    
    # Validate file exists
    if not Path(TRANSCRIPTS_PATH).exists():
        print(f"❌ Error: File not found: {TRANSCRIPTS_PATH}")
        return
    
    # Connect to Weaviate
    print(f"\n🔌 Connecting to Weaviate...")
    client = get_client()
    print(f"✅ Connected")
    
    try:
        # Create collection
        print(f"\n📋 Creating optimized schema...")
        create_optimized_collection(client)
        
        # Ingest data
        print(f"\n📥 Ingesting data...")
        ingest(client, TRANSCRIPTS_PATH)
        
        # Verify
        print(f"\n🔍 Verifying ingestion...")
        verify_ingestion(client)
        
        print(f"\n{'='*70}")
        print("✅ Ingestion complete")
        print(f"{'='*70}")
    
    finally:
        client.close()


if __name__ == "__main__":
    main()
