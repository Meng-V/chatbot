#!/usr/bin/env python3
"""
Ingest Q&A Data into Weaviate

This script ingests Q&A data into Weaviate with a simplified schema:
- Only 4 fields: question, answer, keywords, topic
- Optimized for vector search performance
- No unnecessary metadata

Usage:
    python3 scripts/ingest_transcripts_optimized.py
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


def get_client():
    """Create Weaviate v4 client."""
    # Use centralized client for local Docker
    client = get_weaviate_client()
    if not client:
        raise ValueError("Could not connect to Weaviate local Docker instance")
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


def truncate_text(text: str, max_chars: int = 8000) -> str:
    """Truncate text to avoid token limit issues."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def get_sample_data():
    """Generate sample Q&A data for ingestion."""
    return [
        {
            "question": "How do I renew a book?",
            "answer": "You can renew books through your library account online, by calling the circulation desk at (513) 529-4141, or by visiting the library in person. Most items can be renewed unless they have holds.",
            "keywords": ["renew", "book", "circulation", "library account", "online"],
            "topic": "policy_or_service"
        },
        {
            "question": "What are King Library's hours?",
            "answer": "During regular semesters, King Library is open Monday-Thursday 7:30am-2am, Friday 7:30am-6pm, Saturday 10am-6pm, and Sunday 10am-2am. Hours may vary during breaks and summer.",
            "keywords": ["hours", "King Library", "open", "schedule", "when"],
            "topic": "booking_or_hours"
        },
        {
            "question": "How do I book a study room?",
            "answer": "You can reserve study rooms online through LibCal at https://muohio.libcal.com/reserve/studyrooms or by visiting the circulation desk. You'll need your Miami University ID.",
            "keywords": ["study room", "book", "reserve", "LibCal", "room reservation"],
            "topic": "booking_or_hours"
        },
        {
            "question": "How do I access databases from off-campus?",
            "answer": "To access library databases from off-campus, you'll need to log in with your Miami University UniqueID and password. The system will authenticate you through the library's proxy server.",
            "keywords": ["databases", "off-campus", "remote access", "login", "authentication"],
            "topic": "policy_or_service"
        },
        {
            "question": "What is interlibrary loan?",
            "answer": "Interlibrary Loan (ILL) is a service that allows you to request books and articles from other libraries if Miami doesn't own them. Submit requests through ILLiad, and items typically arrive within 1-2 weeks.",
            "keywords": ["interlibrary loan", "ILL", "ILLiad", "request", "borrow"],
            "topic": "policy_or_service"
        }
    ]


def ingest(client, qa_pairs: list):
    """Ingest Q&A pairs into Weaviate with proper batching."""
    print(f"📦 Preparing to ingest {len(qa_pairs)} Q&A pairs...")
    
    # Get collection
    collection = client.collections.get("TranscriptQA")
    
    # Batch insert with smaller batches to avoid token limits
    success_count = 0
    error_count = 0
    batch_size = 50  # Smaller batches to avoid OpenAI token limits
    
    for batch_start in range(0, len(qa_pairs), batch_size):
        batch_end = min(batch_start + batch_size, len(qa_pairs))
        batch_items = qa_pairs[batch_start:batch_end]
        
        with collection.batch.fixed_size(batch_size=batch_size) as batch:
            for i, qa in enumerate(batch_items):
                try:
                    # Prepare data object with truncation to avoid token limits
                    data_object = {
                        "question": truncate_text(qa.get("question", ""), max_chars=2000),
                        "answer": truncate_text(qa.get("answer", ""), max_chars=6000),
                        "keywords": qa.get("keywords", [])[:20],  # Limit keywords
                        "topic": qa.get("topic", "general_question")
                    }
                    
                    batch.add_object(properties=data_object)
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    print(f"   ⚠️  Error inserting item {batch_start + i}: {e}")
        
        # Progress indicator
        print(f"   Progress: {batch_end}/{len(qa_pairs)}... (Batch {batch_start//batch_size + 1}/{(len(qa_pairs) + batch_size - 1)//batch_size})")
        
        # Check for failed objects in this batch
        failed_objects = collection.batch.failed_objects
        if failed_objects:
            error_count += len(failed_objects)
            print(f"   ⚠️  Batch had {len(failed_objects)} failed objects")
    
    print(f"\n✅ Ingestion complete!")
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
    print("🚀 Ingesting Q&A Data into Weaviate")
    print("="*70)
    print(f"Weaviate host: {WEAVIATE_HOST}")
    
    # Connect to Weaviate
    print(f"\n🔌 Connecting to Weaviate...")
    client = get_client()
    print(f"✅ Connected")
    
    try:
        # Create collection
        print(f"\n📋 Creating optimized schema...")
        create_optimized_collection(client)
        
        # Get sample data
        print(f"\n📦 Generating sample data...")
        qa_pairs = get_sample_data()
        print(f"✅ Generated {len(qa_pairs)} sample Q&A pairs")
        
        # Ingest data
        print(f"\n📥 Ingesting data...")
        ingest(client, qa_pairs)
        
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
