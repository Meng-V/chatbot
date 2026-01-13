#!/usr/bin/env python3
"""
Import Jekyll-derived website evidence into Weaviate.

This script imports the curated, filtered, and chunked website evidence
from weaviate_import.jsonl into a Weaviate collection for RAG fallback.

Usage:
    python scripts/import_weaviate_jsonl.py [options]

Examples:
    # Dry run to preview import
    python scripts/import_weaviate_jsonl.py --dry-run

    # Import with default collection name
    python scripts/import_weaviate_jsonl.py

    # Import with custom collection name
    python scripts/import_weaviate_jsonl.py --collection WebsiteEvidence_2026_01

    # Reset and reimport
    python scripts/import_weaviate_jsonl.py --reset
"""

import os
import sys
import json
import argparse
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import weaviate
import weaviate.classes as wvc
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DEFAULT_INPUT = "ai-core/data/weaviate_import.jsonl"


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


def derive_collection_name(jsonl_path: str) -> str:
    """
    Derive collection name from the first line's last_build_utc field.
    
    Format: WebsiteEvidence_YYYY_MM_DD_HH_MM
    Fallback: WebsiteEvidence
    """
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if first_line:
                data = json.loads(first_line)
                build_utc = data.get("last_build_utc", "")
                if build_utc:
                    # Parse "2026-01-12T22-36-49Z" format
                    build_utc = build_utc.replace("Z", "").replace("T", "_").replace("-", "_").replace(":", "_")
                    return f"WebsiteEvidence_{build_utc}"
    except Exception as e:
        print(f"⚠️ Could not derive collection name from first line: {e}")
    
    return "WebsiteEvidence"


def create_collection(client, collection_name: str, reset: bool = False):
    """Create or reset Weaviate collection for website evidence."""
    if reset and client.collections.exists(collection_name):
        print(f"🗑️ Deleting existing collection: {collection_name}")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ Collection already exists: {collection_name}")
        return
    
    print(f"📦 Creating collection: {collection_name}")
    
    client.collections.create(
        name=collection_name,
        description="Jekyll-derived website evidence for RAG fallback",
        properties=[
            wvc.config.Property(
                name="source_id",
                data_type=wvc.config.DataType.TEXT,
                description="Unique chunk identifier from source"
            ),
            wvc.config.Property(
                name="final_url",
                data_type=wvc.config.DataType.TEXT,
                description="Final URL after redirects"
            ),
            wvc.config.Property(
                name="canonical_url",
                data_type=wvc.config.DataType.TEXT,
                description="Canonical URL"
            ),
            wvc.config.Property(
                name="aliases",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="URL aliases"
            ),
            wvc.config.Property(
                name="title",
                data_type=wvc.config.DataType.TEXT,
                description="Page title"
            ),
            wvc.config.Property(
                name="headings",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="Page headings"
            ),
            wvc.config.Property(
                name="summary",
                data_type=wvc.config.DataType.TEXT,
                description="Page summary"
            ),
            wvc.config.Property(
                name="tags",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="Content tags"
            ),
            wvc.config.Property(
                name="chunk_index",
                data_type=wvc.config.DataType.INT,
                description="Chunk index for this page"
            ),
            wvc.config.Property(
                name="chunk_text",
                data_type=wvc.config.DataType.TEXT,
                description="Chunk text content"
            ),
            wvc.config.Property(
                name="last_build_utc",
                data_type=wvc.config.DataType.TEXT,
                description="Build timestamp"
            ),
            wvc.config.Property(
                name="response_mode",
                data_type=wvc.config.DataType.TEXT,
                description="Response mode: 'url_only' for policies, 'full' for regular content"
            ),
        ]
    )
    
    print(f"✅ Collection created: {collection_name}")


def generate_deterministic_uuid(source_id: str) -> str:
    """Generate deterministic UUID from source ID using UUID5."""
    namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # UUID namespace for URLs
    return str(uuid.uuid5(namespace, source_id))


def import_jsonl(
    client,
    collection_name: str,
    jsonl_path: str,
    batch_size: int = 50,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Import JSONL data into Weaviate collection.
    
    Returns:
        Dict with import statistics
    """
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY in .env file - required for embeddings")
    
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-large",
        api_key=OPENAI_API_KEY
    )
    
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }
    
    collection = client.collections.get(collection_name)
    
    print(f"📖 Reading from: {jsonl_path}")
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            # Show first 3 records as preview
            for i, line in enumerate(lines[:3]):
                data = json.loads(line)
                print(f"\n  Record {i+1}:")
                print(f"    ID: {data.get('id')}")
                print(f"    URL: {data.get('final_url')}")
                print(f"    Title: {data.get('title')}")
                print(f"    Chunk: {data.get('chunk_index')}")
                print(f"    Text preview: {data.get('chunk_text', '')[:100]}...")
            return stats
        
        print(f"🚀 Importing {stats['total']} records in batches of {batch_size}...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    # Generate embedding for chunk_text
                    chunk_text = data.get("chunk_text", "")
                    if not chunk_text:
                        stats["skipped"] += 1
                        continue
                    
                    # Embed the chunk text
                    vector = embeddings.embed_query(chunk_text)
                    
                    # Generate deterministic UUID from source ID
                    source_id = data.get("id", "")
                    obj_uuid = generate_deterministic_uuid(source_id)
                    
                    properties = {
                        "source_id": source_id,
                        "final_url": data.get("final_url", ""),
                        "canonical_url": data.get("canonical_url", ""),
                        "aliases": data.get("aliases", []),
                        "title": data.get("title", ""),
                        "headings": data.get("headings", []),
                        "summary": data.get("summary", ""),
                        "tags": data.get("tags", []),
                        "chunk_index": data.get("chunk_index", 0),
                        "chunk_text": chunk_text,
                        "last_build_utc": data.get("last_build_utc", ""),
                        "response_mode": data.get("response_mode", "full"),
                    }
                    
                    batch.add_object(
                        properties=properties,
                        vector=vector,
                        uuid=obj_uuid
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 100 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    error_msg = f"Line {idx}: {str(e)}"
                    stats["errors"].append(error_msg)
                    if len(stats["errors"]) <= 5:  # Only show first 5 errors
                        print(f"  ❌ {error_msg}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import Jekyll-derived website evidence into Weaviate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to preview import
  python scripts/import_weaviate_jsonl.py --dry-run

  # Import with default collection name
  python scripts/import_weaviate_jsonl.py

  # Import with custom collection name
  python scripts/import_weaviate_jsonl.py --collection WebsiteEvidence_2026_01

  # Reset and reimport
  python scripts/import_weaviate_jsonl.py --reset
        """
    )
    
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Path to JSONL file (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Collection name (default: derived from first line's last_build_utc)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate collection"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for import (default: 50)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without actually inserting data"
    )
    
    args = parser.parse_args()
    
    # Resolve input path
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root_dir / args.input
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    # Derive collection name if not provided
    collection_name = args.collection
    if not collection_name:
        collection_name = derive_collection_name(str(input_path))
        print(f"📋 Derived collection name: {collection_name}")
    
    print("="*70)
    print("🌐 Website Evidence Import Script")
    print("="*70)
    print(f"Input file: {input_path}")
    print(f"Collection: {collection_name}")
    print(f"Reset: {args.reset}")
    print(f"Batch size: {args.batch_size}")
    print(f"Dry run: {args.dry_run}")
    print("="*70)
    
    if not args.dry_run:
        print(f"\n🔌 Connecting to Weaviate: {WEAVIATE_HOST}")
    
    try:
        if args.dry_run:
            # For dry run, we don't need to connect
            client = None
            stats = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "errors": []
            }
            
            with open(input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                stats["total"] = len(lines)
                
                print(f"🔍 DRY RUN: Would import {stats['total']} records into '{collection_name}'")
                print("\nPreview of first 3 records:")
                for i, line in enumerate(lines[:3]):
                    data = json.loads(line)
                    print(f"\n  Record {i+1}:")
                    print(f"    ID: {data.get('id')}")
                    print(f"    URL: {data.get('final_url')}")
                    print(f"    Title: {data.get('title')}")
                    print(f"    Chunk: {data.get('chunk_index')}")
                    print(f"    Text preview: {data.get('chunk_text', '')[:100]}...")
        else:
            client = get_client()
            print("✅ Connected to Weaviate\n")
            
            # Create or reset collection
            create_collection(client, collection_name, reset=args.reset)
            
            # Import data
            stats = import_jsonl(
                client,
                collection_name,
                str(input_path),
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
        
        # Print summary
        print("\n" + "="*70)
        print("📊 Import Summary")
        print("="*70)
        print(f"Total records: {stats['total']}")
        print(f"Successful: {stats['success']}")
        print(f"Failed: {stats['failed']}")
        print(f"Skipped: {stats['skipped']}")
        
        if stats['errors']:
            print(f"\n❌ Sample errors (showing first 5):")
            for error in stats['errors'][:5]:
                print(f"  - {error}")
        
        if not args.dry_run and stats['success'] > 0:
            print(f"\n✅ Import complete! Collection '{collection_name}' now has {stats['success']} records.")
            print(f"\nTo use this collection, set the environment variable:")
            print(f"  export WEBSITE_EVIDENCE_COLLECTION={collection_name}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        if client:
            try:
                client.close()
            except:
                pass


if __name__ == "__main__":
    main()
