#!/usr/bin/env python3
"""
Import Exported Weaviate Data

Imports JSONL files exported by export_weaviate_data.py
Preserves UUIDs and vectors from the export.

Usage:
    python scripts/import_exported_weaviate.py --input-dir data/weaviate_export
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")


def import_collection(client, collection_name: str, jsonl_file: Path) -> Dict[str, int]:
    """Import a collection from JSONL file."""
    stats = {"total": 0, "success": 0, "failed": 0}
    
    print(f"\n📦 Importing {collection_name} from {jsonl_file}...")
    
    if not jsonl_file.exists():
        print(f"⚠️  File not found: {jsonl_file}")
        return stats
    
    if not client.collections.exists(collection_name):
        print(f"⚠️  Collection {collection_name} does not exist - create it first")
        return stats
    
    collection = client.collections.get(collection_name)
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        stats["total"] = len(lines)
        
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
    
    print(f"✅ Imported {stats['success']}/{stats['total']} records")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Import exported Weaviate data")
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Input directory containing JSONL files"
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        help="Specific collections to import (default: all .jsonl files)"
    )
    
    args = parser.parse_args()
    
    if not args.input_dir.exists():
        print(f"❌ Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    print("="*80)
    print("Weaviate Data Import")
    print("="*80)
    print(f"Input directory: {args.input_dir}")
    
    try:
        # Connect to Weaviate
        print("\n🔌 Connecting to Weaviate...")
        client = get_weaviate_client()
        if not client:
            print("❌ Could not connect to Weaviate")
            sys.exit(1)
        
        print("✅ Connected")
        
        # Find JSONL files
        jsonl_files = list(args.input_dir.glob("*.jsonl"))
        print(f"\nFound {len(jsonl_files)} JSONL files")
        
        # Import each collection
        all_stats = {}
        for jsonl_file in jsonl_files:
            collection_name = jsonl_file.stem
            
            # Skip if not in specified collections
            if args.collections and collection_name not in args.collections:
                continue
            
            stats = import_collection(client, collection_name, jsonl_file)
            all_stats[collection_name] = stats
        
        # Print summary
        print("\n" + "="*80)
        print("Import Summary")
        print("="*80)
        
        total_success = 0
        total_failed = 0
        
        for collection_name, stats in all_stats.items():
            print(f"\n{collection_name}:")
            print(f"  Total: {stats['total']}")
            print(f"  Success: {stats['success']}")
            print(f"  Failed: {stats['failed']}")
            total_success += stats['success']
            total_failed += stats['failed']
        
        print(f"\nGRAND TOTAL: {total_success} records imported, {total_failed} failed")
        
        client.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
