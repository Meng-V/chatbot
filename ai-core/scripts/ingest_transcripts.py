#!/usr/bin/env python3
"""
Ingest chat transcripts into Weaviate for RAG.
"""
import os
import json
import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv

load_dotenv()

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
    """Create TranscriptQA collection with v4 API."""
    try:
        client.collections.create(
            name="TranscriptQA",
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(),
            properties=[
                wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="topic", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
            ]
        )
        print("✅ Created TranscriptQA collection")
    except Exception as e:
        print(f"Collection may already exist: {e}")

def ingest(client, path: str):
    """Ingest transcripts using v4 batch API."""
    with open(path) as f:
        rows = json.load(f)
    
    collection = client.collections.get("TranscriptQA")
    
    with collection.batch.dynamic() as batch:
        for r in rows:
            batch.add_object(
                properties={
                    "question": r["question"],
                    "answer": r["answer"],
                    "topic": r.get("topic", ""),
                    "source": r.get("source", "transcripts")
                }
            )
    print(f"✅ Ingested {len(rows)} transcripts")

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
