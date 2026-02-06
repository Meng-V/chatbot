#!/usr/bin/env python3
"""
Export Weaviate Data to JSONL

Exports all collections from local Weaviate to JSONL files
that can be imported on the server.

Usage:
    python scripts/export_weaviate_data.py
    python scripts/export_weaviate_data.py --output-dir /tmp/weaviate_export
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils.weaviate_client import get_weaviate_client
from dotenv import load_dotenv

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "weaviate_export"


def export_collection(client, collection_name: str, output_file: Path) -> int:
    """Export a collection to JSONL file."""
    print(f"\n📦 Exporting {collection_name}...")
    
    try:
        collection = client.collections.get(collection_name)
        
        # Get all objects
        response = collection.query.fetch_objects(limit=10000)
        
        if not response.objects:
            print(f"⚠️  Collection {collection_name} is empty")
            return 0
        
        # Write to JSONL
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for obj in response.objects:
                data = {
                    "id": str(obj.uuid),
                    "properties": obj.properties,
                    "vector": obj.vector.get("default") if obj.vector else None
                }
                f.write(json.dumps(data) + "\n")
                count += 1
        
        print(f"✅ Exported {count} records to {output_file}")
        return count
    
    except Exception as e:
        print(f"❌ Error exporting {collection_name}: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Export Weaviate data to JSONL")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for JSONL files"
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        help="Specific collections to export (default: all)"
    )
    
    args = parser.parse_args()
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*80)
    print("Weaviate Data Export")
    print("="*80)
    print(f"Output directory: {args.output_dir}")
    
    try:
        # Connect to Weaviate
        print("\n🔌 Connecting to Weaviate...")
        client = get_weaviate_client()
        if not client:
            print("❌ Could not connect to Weaviate")
            sys.exit(1)
        
        print("✅ Connected")
        
        # Get all collections
        all_collections = [str(c) for c in client.collections.list_all()]
        print(f"\nFound {len(all_collections)} collections:")
        for name in all_collections:
            print(f"  • {name}")
        
        # Filter collections if specified
        collections_to_export = args.collections if args.collections else all_collections
        
        # Export each collection
        total_records = 0
        for collection_name in collections_to_export:
            if collection_name not in all_collections:
                print(f"\n⚠️  Collection {collection_name} not found, skipping...")
                continue
            
            output_file = args.output_dir / f"{collection_name}.jsonl"
            count = export_collection(client, collection_name, output_file)
            total_records += count
        
        # Print summary
        print("\n" + "="*80)
        print("Export Summary")
        print("="*80)
        print(f"Total records exported: {total_records}")
        print(f"Output directory: {args.output_dir}")
        print("\nTo copy to server:")
        print(f"  scp {args.output_dir}/*.jsonl user@server:/path/to/data/")
        
        client.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
