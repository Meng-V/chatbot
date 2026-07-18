#!/usr/bin/env python3
"""
Migrate TranscriptQA schema to add verification metadata fields.

This script adds new fields to the existing TranscriptQA collection:
- verified: bool (default False)
- source_url: str | None
- evidence_quote: str | None
- source_domain: str | None
- created_at: str (ISO timestamp)

Usage:
    python scripts/migrate_transcript_qa_schema.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

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


def migrate_schema(client):
    """
    Migrate TranscriptQA schema by recreating with new fields.
    
    WARNING: This will delete and recreate the collection.
    All existing data will be lost unless backed up.
    """
    print("=" * 70)
    print("MIGRATE TRANSCRIPTQA SCHEMA")
    print("=" * 70)
    print()
    
    # Check if collection exists
    if client.collections.exists("TranscriptQA"):
        print("⚠️  WARNING: This will DELETE the existing TranscriptQA collection!")
        print("   All data will be lost unless you have a backup.")
        response = input("\nContinue? (yes/no): ").lower()
        if response != "yes":
            print("❌ Migration cancelled")
            return False
        
        # Delete existing collection
        print("\n🗑️  Deleting existing collection...")
        client.collections.delete("TranscriptQA")
        print("✅ Deleted")
    
    # Create new collection with updated schema
    print("\n📦 Creating collection with new schema...")
    
    collection = client.collections.create(
        name="TranscriptQA",
        description="Optimized Q&A pairs with verification metadata",
        vector_config=wvc.config.Configure.Vectors.self_provided(),
        properties=[
            # Original fields
            wvc.config.Property(
                name="question",
                data_type=wvc.config.DataType.TEXT,
                description="The question being asked"
            ),
            wvc.config.Property(
                name="answer",
                data_type=wvc.config.DataType.TEXT,
                description="The answer to the question"
            ),
            wvc.config.Property(
                name="topic",
                data_type=wvc.config.DataType.TEXT,
                description="Topic category (e.g., discovery_search, hours, policy)"
            ),
            wvc.config.Property(
                name="keywords",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="Keywords for better search matching"
            ),
            # NEW VERIFICATION METADATA FIELDS
            wvc.config.Property(
                name="verified",
                data_type=wvc.config.DataType.BOOL,
                description="Whether this entry has been verified against official sources"
            ),
            wvc.config.Property(
                name="source_url",
                data_type=wvc.config.DataType.TEXT,
                description="Official source URL (required for verified=True)"
            ),
            wvc.config.Property(
                name="evidence_quote",
                data_type=wvc.config.DataType.TEXT,
                description="1-3 sentence quote from source page (required for verified=True)"
            ),
            wvc.config.Property(
                name="source_domain",
                data_type=wvc.config.DataType.TEXT,
                description="Domain of source URL (for allowlist filtering)"
            ),
            wvc.config.Property(
                name="created_at",
                data_type=wvc.config.DataType.TEXT,
                description="ISO timestamp when entry was created"
            )
        ]
    )
    
    print("✅ Collection created with new schema!")
    print("\nNew fields added:")
    print("  • verified (BOOL) - Verification status")
    print("  • source_url (TEXT) - Official source URL")
    print("  • evidence_quote (TEXT) - Quote from source")
    print("  • source_domain (TEXT) - Source domain")
    print("  • created_at (TEXT) - Creation timestamp")
    
    return True


def main():
    try:
        client = get_client()
        print("✅ Connected to Weaviate\n")
        
        success = migrate_schema(client)
        
        client.close()
        print("\n✅ Connection closed")
        
        if success:
            print("\n🎉 Schema migration complete!")
            print("\nNext steps:")
            print("1. Re-import your data with the new fields")
            print("2. Use make_transcript_rag_item() helper for new entries")
            print("3. Restart your backend")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
