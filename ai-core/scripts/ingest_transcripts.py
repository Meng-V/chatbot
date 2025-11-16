#!/usr/bin/env python3
"""
⚠️  DEPRECATED - Use ingest_transcripts_optimized.py instead

This script uses the OLD schema with 12 fields including metadata.
For the new optimized vector search approach with simplified schema (4 fields),
use: scripts/ingest_transcripts_optimized.py

This file is kept for reference only.
"""
import os
import json
import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def get_client():
    """Create Weaviate v4 client."""
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_HOST,
        auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
        headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
    )
    return client

def create_schema(client):
    """Create TranscriptQA collection with v4 API - Enhanced Schema."""
    try:
        client.collections.create(
            name="TranscriptQA",
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(),
            properties=[
                # Core content
                wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                
                # Classification
                wvc.config.Property(name="topic", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="keywords", data_type=wvc.config.DataType.TEXT_ARRAY),
                
                # Quality metrics
                wvc.config.Property(name="rating", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="confidence_score", data_type=wvc.config.DataType.NUMBER),
                
                # Context (optional)
                wvc.config.Property(name="context", data_type=wvc.config.DataType.TEXT),
                
                # Metadata
                wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="chat_id", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="timestamp", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="answerer", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="department", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
            ]
        )
        print("✅ Created TranscriptQA collection with enhanced schema")
    except Exception as e:
        print(f"Collection may already exist: {e}")

def ingest(client, path: str):
    """Ingest transcripts using v4 batch API with enhanced data."""
    with open(path, 'r', encoding='utf-8') as f:
        rows = json.load(f)
    
    collection = client.collections.get("TranscriptQA")
    
    print(f"📦 Preparing to ingest {len(rows)} transcripts...")
    
    success_count = 0
    error_count = 0
    
    with collection.batch.dynamic() as batch:
        for idx, r in enumerate(rows):
            try:
                batch.add_object(
                    properties={
                        # Core content
                        "question": r["question"],
                        "answer": r["answer"],
                        
                        # Classification
                        "topic": r.get("topic", "general_question"),
                        "keywords": r.get("keywords", []),
                        
                        # Quality
                        "rating": r.get("rating", 0),
                        "confidence_score": r.get("confidence_score", 0.5),
                        
                        # Context
                        "context": r.get("context", ""),
                        
                        # Metadata
                        "source": r.get("source", "transcripts"),
                        "chat_id": r.get("chat_id", ""),
                        "timestamp": r.get("timestamp", ""),
                        "answerer": r.get("answerer", ""),
                        "department": r.get("department", ""),
                        "tags": r.get("tags", []),
                    }
                )
                success_count += 1
                
                # Progress indicator
                if (idx + 1) % 100 == 0:
                    print(f"   Progress: {idx + 1}/{len(rows)}...")
            
            except Exception as e:
                error_count += 1
                print(f"⚠️  Error ingesting record {idx}: {e}")
    
    print(f"✅ Ingestion complete!")
    print(f"   Success: {success_count}")
    print(f"   Errors: {error_count}")
    print(f"   Total: {len(rows)}")

if __name__ == "__main__":
    client = get_client()
    create_schema(client)
    
    default_path = os.path.join(os.path.dirname(__file__), "..", "data", "transcripts_clean.json")
    path = os.environ.get("TRANSCRIPTS_PATH", os.path.abspath(default_path))
    
    if os.path.exists(path):
        ingest(client, path)
    else:
        print(f"⚠️  No transcripts file found at {path}")
    
    client.close()
    print("✅ Ingestion complete")
