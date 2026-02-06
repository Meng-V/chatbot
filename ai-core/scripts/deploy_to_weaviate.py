#!/usr/bin/env python3
"""
Master Weaviate Deployment Script

This script deploys ALL data collections to Weaviate (local or server).
Use this for admin deployment to push everything that's actively used.

Collections deployed:
1. TranscriptQA - Q&A pairs from library transcripts
2. WebsiteEvidence - Jekyll-derived website evidence chunks
3. CirculationPolicies - Oxford policy content chunks
4. CirculationPolicyFacts - Policy fact cards

Usage:
    # Deploy all collections to server
    python scripts/deploy_to_weaviate.py
    
    # Deploy with reset (recreate collections)
    python scripts/deploy_to_weaviate.py --reset
    
    # Deploy specific collections only
    python scripts/deploy_to_weaviate.py --collections TranscriptQA WebsiteEvidence
    
    # Dry run to preview
    python scripts/deploy_to_weaviate.py --dry-run
"""

import os
import sys
import json
import uuid
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
import weaviate.classes as wvc

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ALL_COLLECTIONS = ["TranscriptQA", "WebsiteEvidence", "CirculationPolicies", "CirculationPolicyFacts", "QuestionCategory", "AgentPrototypes"]


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)


def print_step(number: int, text: str):
    """Print step with number."""
    print(f"\n[STEP {number}] {text}")
    print("-"*80)


def get_client():
    """Get Weaviate client."""
    client = get_weaviate_client()
    if not client:
        raise ValueError("Could not connect to Weaviate - check WEAVIATE_HOST in .env")
    return client


def generate_deterministic_uuid(source_id: str) -> str:
    """Generate deterministic UUID from source ID."""
    namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
    return str(uuid.uuid5(namespace, source_id))


def create_transcript_qa_collection(client, reset: bool = False):
    """Create TranscriptQA collection."""
    collection_name = "TranscriptQA"
    
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="Optimized Q&A pairs from library transcripts for RAG",
        properties=[
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
                description="Topic category"
            ),
            wvc.config.Property(
                name="keywords",
                data_type=wvc.config.DataType.TEXT_ARRAY,
                description="Keywords for better search matching"
            )
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def create_website_evidence_collection(client, collection_name: str = "WebsiteEvidence", reset: bool = False):
    """Create WebsiteEvidence collection."""
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="Jekyll-derived website evidence for RAG fallback",
        properties=[
            wvc.config.Property(
                name="source_id",
                data_type=wvc.config.DataType.TEXT,
                description="Unique chunk identifier"
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
                description="Response mode: url_only or full"
            ),
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def create_circulation_policies_collection(client, reset: bool = False):
    """Create CirculationPolicies collection."""
    collection_name = "CirculationPolicies"
    
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="Oxford circulation and borrowing policy content chunks",
        properties=[
            wvc.config.Property(name="canonical_url", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="source_url", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="section_path", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="campus_scope", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="topic", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="audience", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="keywords", data_type=wvc.config.DataType.TEXT_ARRAY),
            wvc.config.Property(name="chunk_text", data_type=wvc.config.DataType.TEXT),
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def create_circulation_policy_facts_collection(client, reset: bool = False):
    """Create CirculationPolicyFacts collection."""
    collection_name = "CirculationPolicyFacts"
    
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="Oxford policy fact cards for direct Q&A",
        properties=[
            wvc.config.Property(name="campus_scope", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="fact_type", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="question_patterns", data_type=wvc.config.DataType.TEXT_ARRAY),
            wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="canonical_url", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="source_url", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="anchor_hint", data_type=wvc.config.DataType.TEXT),
            wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def create_question_category_collection(client, reset: bool = False):
    """Create QuestionCategory collection."""
    collection_name = "QuestionCategory"
    
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="Question category examples for classification",
        properties=[
            wvc.config.Property(name="category", data_type=wvc.config.DataType.TEXT, description="Category name"),
            wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT, description="Example question"),
            wvc.config.Property(name="is_in_scope", data_type=wvc.config.DataType.BOOL, description="Whether this is an in-scope example"),
            wvc.config.Property(name="description", data_type=wvc.config.DataType.TEXT, description="Category description"),
            wvc.config.Property(name="agent", data_type=wvc.config.DataType.TEXT, description="Agent to handle this category"),
            wvc.config.Property(name="keywords", data_type=wvc.config.DataType.TEXT_ARRAY, description="Keywords for hybrid search"),
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def create_agent_prototypes_collection(client, reset: bool = False):
    """Create AgentPrototypes collection."""
    collection_name = "AgentPrototypes"
    
    if reset and client.collections.exists(collection_name):
        print(f"🗑️  Deleting existing {collection_name} collection")
        client.collections.delete(collection_name)
    
    if client.collections.exists(collection_name):
        print(f"✅ {collection_name} collection already exists")
        return True
    
    print(f"📦 Creating {collection_name} collection...")
    
    client.collections.create(
        name=collection_name,
        description="High-quality prototypes for agent routing (8-12 per agent)",
        properties=[
            wvc.config.Property(name="agent_id", data_type=wvc.config.DataType.TEXT, description="Agent identifier"),
            wvc.config.Property(name="prototype_text", data_type=wvc.config.DataType.TEXT, description="Prototype question/phrase"),
            wvc.config.Property(name="category", data_type=wvc.config.DataType.TEXT, description="Category name"),
            wvc.config.Property(name="is_action_based", data_type=wvc.config.DataType.BOOL, description="Whether this prototype emphasizes action verbs"),
            wvc.config.Property(name="priority", data_type=wvc.config.DataType.INT, description="Priority level (higher = more important)"),
        ]
    )
    
    print(f"✅ {collection_name} collection created")
    return True


def import_transcript_qa(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import TranscriptQA data from circulation_policies.jsonl."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    # Try multiple possible data sources
    data_sources = [
        DATA_DIR / "circulation_policies.jsonl",
        DATA_DIR / "policies" / "circulation_policies_oxford_facts.jsonl",
    ]
    
    data_file = None
    for source in data_sources:
        if source.exists():
            data_file = source
            break
    
    if not data_file:
        print(f"⚠️  No TranscriptQA data file found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("TranscriptQA")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    # Extract Q&A structure from policy data
                    # This is a simplified version - adjust based on your actual data structure
                    properties = {
                        "question": data.get("question_patterns", [""])[0] if "question_patterns" in data else data.get("question", ""),
                        "answer": data.get("answer", ""),
                        "topic": data.get("fact_type", data.get("topic", "policy")),
                        "keywords": data.get("tags", data.get("keywords", []))
                    }
                    
                    # Generate embedding
                    text_to_embed = f"{properties['question']} {properties['answer']}"
                    vector = embeddings.embed_query(text_to_embed)
                    
                    batch.add_object(
                        properties=properties,
                        vector=vector
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 50 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def import_website_evidence(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import WebsiteEvidence data from weaviate_import.jsonl."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    data_file = DATA_DIR / "weaviate_import.jsonl"
    
    if not data_file.exists():
        print(f"⚠️  {data_file} not found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("WebsiteEvidence")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    chunk_text = data.get("chunk_text", "")
                    if not chunk_text:
                        continue
                    
                    # Generate embedding
                    vector = embeddings.embed_query(chunk_text)
                    
                    # Generate deterministic UUID
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
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def import_circulation_policies(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import CirculationPolicies data."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    data_file = DATA_DIR / "policies" / "circulation_policies_oxford_chunks.jsonl"
    
    if not data_file.exists():
        print(f"⚠️  {data_file} not found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("CirculationPolicies")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    chunk_text = data.get("chunk_text", "")
                    if not chunk_text:
                        continue
                    
                    # Generate embedding
                    vector = embeddings.embed_query(chunk_text)
                    
                    chunk_id = data.get("id", "")
                    # Convert non-UUID IDs to valid UUIDs
                    try:
                        uuid.UUID(chunk_id)
                        valid_uuid = chunk_id
                    except (ValueError, AttributeError):
                        valid_uuid = generate_deterministic_uuid(chunk_id)
                    
                    properties = {k: v for k, v in data.items() if k != "id"}
                    
                    batch.add_object(
                        properties=properties,
                        uuid=valid_uuid,
                        vector=vector
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 50 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def import_circulation_policy_facts(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import CirculationPolicyFacts data."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    data_file = DATA_DIR / "policies" / "circulation_policies_oxford_facts.jsonl"
    
    if not data_file.exists():
        print(f"⚠️  {data_file} not found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("CirculationPolicyFacts")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    # Generate embedding from question + answer
                    patterns = data.get("question_patterns", [])
                    question = patterns[0] if patterns else ""
                    answer = data.get("answer", "")
                    text_to_embed = f"{question} {answer}".strip()
                    if not text_to_embed:
                        stats["failed"] += 1
                        print(f"  ⚠️  Line {idx}: Empty content, skipping")
                        continue
                    vector = embeddings.embed_query(text_to_embed)
                    
                    fact_id = data.get("id", "")
                    # Convert non-UUID IDs to valid UUIDs
                    try:
                        uuid.UUID(fact_id)
                        valid_uuid = fact_id
                    except (ValueError, AttributeError):
                        valid_uuid = generate_deterministic_uuid(fact_id)
                    
                    properties = {k: v for k, v in data.items() if k != "id"}
                    
                    batch.add_object(
                        properties=properties,
                        uuid=valid_uuid,
                        vector=vector
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 50 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def import_question_category(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import QuestionCategory data from exported JSONL."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    data_file = DATA_DIR / "weaviate_export" / "QuestionCategory.jsonl"
    
    if not data_file.exists():
        print(f"⚠️  {data_file} not found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("QuestionCategory")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    batch.add_object(
                        properties=data["properties"],
                        uuid=data["id"],
                        vector=data.get("vector")
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 100 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def import_agent_prototypes(client, embeddings, dry_run: bool = False) -> Dict[str, int]:
    """Import AgentPrototypes data from exported JSONL."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    data_file = DATA_DIR / "weaviate_export" / "AgentPrototypes.jsonl"
    
    if not data_file.exists():
        print(f"⚠️  {data_file} not found, skipping...")
        return stats
    
    print(f"📖 Reading from: {data_file}")
    
    collection = client.collections.get("AgentPrototypes")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would import {stats['total']} records")
            return stats
        
        print(f"🚀 Importing {stats['total']} records...")
        
        with collection.batch.dynamic() as batch:
            for idx, line in enumerate(lines, 1):
                try:
                    data = json.loads(line)
                    
                    batch.add_object(
                        properties=data["properties"],
                        uuid=data["id"],
                        vector=data.get("vector")
                    )
                    
                    stats["success"] += 1
                    
                    if idx % 100 == 0:
                        print(f"  Progress: {idx}/{stats['total']} ({idx/stats['total']*100:.1f}%)")
                
                except Exception as e:
                    stats["failed"] += 1
                    print(f"  ❌ Line {idx}: {str(e)}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Deploy all data collections to Weaviate (local or server)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--collections",
        nargs="+",
        choices=ALL_COLLECTIONS,
        default=ALL_COLLECTIONS,
        help="Collections to deploy (default: all)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate collections"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deployment without actually inserting data"
    )
    
    args = parser.parse_args()
    
    print_header("Weaviate Master Deployment Script")
    print(f"\nDeploying collections: {', '.join(args.collections)}")
    print(f"Reset: {args.reset}")
    print(f"Dry run: {args.dry_run}")
    
    if not OPENAI_API_KEY:
        print("\n❌ OPENAI_API_KEY not set in .env")
        sys.exit(1)
    
    try:
        # Connect to Weaviate
        print_step(1, "Connecting to Weaviate")
        client = get_client()
        meta = client.get_meta()
        print(f"✅ Connected to Weaviate v{meta.get('version', 'Unknown')}")
        print(f"   Host: {os.getenv('WEAVIATE_HOST', 'localhost')}")
        
        # Initialize embeddings
        print_step(2, "Initializing OpenAI Embeddings")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=OPENAI_API_KEY
        )
        print("✅ Embeddings ready")
        
        # Create collections
        print_step(3, "Creating Collections")
        
        if "TranscriptQA" in args.collections:
            create_transcript_qa_collection(client, reset=args.reset)
        
        if "WebsiteEvidence" in args.collections:
            create_website_evidence_collection(client, reset=args.reset)
        
        if "CirculationPolicies" in args.collections:
            create_circulation_policies_collection(client, reset=args.reset)
        
        if "CirculationPolicyFacts" in args.collections:
            create_circulation_policy_facts_collection(client, reset=args.reset)
        
        if "QuestionCategory" in args.collections:
            create_question_category_collection(client, reset=args.reset)
        
        if "AgentPrototypes" in args.collections:
            create_agent_prototypes_collection(client, reset=args.reset)
        
        # Import data
        print_step(4, "Importing Data")
        
        all_stats = {}
        
        if "TranscriptQA" in args.collections:
            print("\n📦 TranscriptQA Collection")
            all_stats["TranscriptQA"] = import_transcript_qa(client, embeddings, dry_run=args.dry_run)
        
        if "WebsiteEvidence" in args.collections:
            print("\n📦 WebsiteEvidence Collection")
            all_stats["WebsiteEvidence"] = import_website_evidence(client, embeddings, dry_run=args.dry_run)
        
        if "CirculationPolicies" in args.collections:
            print("\n📦 CirculationPolicies Collection")
            all_stats["CirculationPolicies"] = import_circulation_policies(client, embeddings, dry_run=args.dry_run)
        
        if "CirculationPolicyFacts" in args.collections:
            print("\n📦 CirculationPolicyFacts Collection")
            all_stats["CirculationPolicyFacts"] = import_circulation_policy_facts(client, embeddings, dry_run=args.dry_run)
        
        if "QuestionCategory" in args.collections:
            print("\n📦 QuestionCategory Collection")
            all_stats["QuestionCategory"] = import_question_category(client, embeddings, dry_run=args.dry_run)
        
        if "AgentPrototypes" in args.collections:
            print("\n📦 AgentPrototypes Collection")
            all_stats["AgentPrototypes"] = import_agent_prototypes(client, embeddings, dry_run=args.dry_run)
        
        # Print summary
        print_header("Deployment Summary")
        
        total_success = 0
        total_failed = 0
        
        for collection_name, stats in all_stats.items():
            print(f"\n{collection_name}:")
            print(f"  Total: {stats['total']}")
            print(f"  Success: {stats['success']}")
            print(f"  Failed: {stats['failed']}")
            total_success += stats['success']
            total_failed += stats['failed']
        
        print(f"\n{'='*80}")
        print(f"GRAND TOTAL: {total_success} records imported, {total_failed} failed")
        print(f"{'='*80}")
        
        if not args.dry_run and total_success > 0:
            print("\n✅ Deployment complete!")
            print("\nCollections are now ready on:")
            print(f"  {os.getenv('WEAVIATE_SCHEME', 'http')}://{os.getenv('WEAVIATE_HOST', 'localhost')}:{os.getenv('WEAVIATE_HTTP_PORT', '8080')}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        if 'client' in locals():
            client.close()
            print("\n🔌 Connection closed")


if __name__ == "__main__":
    main()
