#!/usr/bin/env python3
"""
Delete Weaviate Records by ID

This script allows you to delete specific records from the Weaviate TranscriptQA
collection by providing their UUIDs.

Usage:
    # Interactive mode (prompts for IDs)
    python scripts/delete_weaviate_records.py
    
    # Single ID
    python scripts/delete_weaviate_records.py --ids abc-123-def
    
    # Multiple IDs
    python scripts/delete_weaviate_records.py --ids abc-123 def-456 ghi-789
    
    # From file (one ID per line)
    python scripts/delete_weaviate_records.py --file ids_to_delete.txt
"""

import sys
from pathlib import Path
import argparse
import weaviate
import weaviate.classes as wvc

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
import os

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def connect_to_weaviate():
    """Connect to Weaviate cloud instance."""
    if not WEAVIATE_HOST or not WEAVIATE_API_KEY:
        print("❌ Error: WEAVIATE_HOST or WEAVIATE_API_KEY not set in .env")
        return None
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_HOST,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
            headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
        )
        print(f"✅ Connected to Weaviate: {WEAVIATE_HOST}")
        return client
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


def preview_record(client, record_id: str):
    """Preview a record before deletion."""
    try:
        collection = client.collections.get("TranscriptQA")
        obj = collection.query.fetch_object_by_id(record_id)
        
        if obj:
            print(f"\n   📄 Record Preview (ID: {record_id}):")
            print(f"      Question: {obj.properties.get('question', 'N/A')[:80]}...")
            print(f"      Topic: {obj.properties.get('topic', 'N/A')}")
            return True
        else:
            print(f"   ⚠️  Record not found: {record_id}")
            return False
    except Exception as e:
        print(f"   ⚠️  Could not preview {record_id}: {e}")
        return False


def delete_records(client, record_ids: list, preview: bool = True, confirm: bool = True):
    """
    Delete multiple records from Weaviate.
    
    Args:
        client: Weaviate client
        record_ids: List of UUID strings
        preview: Whether to preview records before deletion
        confirm: Whether to ask for confirmation
    """
    if not record_ids:
        print("⚠️  No record IDs provided")
        return
    
    print(f"\n{'='*80}")
    print(f"DELETING {len(record_ids)} RECORD(S) FROM WEAVIATE")
    print(f"{'='*80}")
    
    # Preview records
    if preview:
        print("\n📋 Previewing records to delete:")
        valid_ids = []
        for record_id in record_ids:
            if preview_record(client, record_id):
                valid_ids.append(record_id)
        
        if not valid_ids:
            print("\n❌ No valid records found. Aborting.")
            return
        
        record_ids = valid_ids
    
    # Confirmation
    if confirm:
        print(f"\n⚠️  You are about to DELETE {len(record_ids)} record(s)")
        print("   This action CANNOT be undone!")
        response = input("\n   Type 'DELETE' to confirm: ")
        
        if response != "DELETE":
            print("\n❌ Deletion cancelled")
            return
    
    # Delete records
    print(f"\n🗑️  Deleting {len(record_ids)} record(s)...")
    collection = client.collections.get("TranscriptQA")
    
    deleted_count = 0
    failed_count = 0
    
    for i, record_id in enumerate(record_ids, 1):
        try:
            collection.data.delete_by_id(record_id)
            print(f"   [{i}/{len(record_ids)}] ✅ Deleted: {record_id}")
            deleted_count += 1
        except Exception as e:
            print(f"   [{i}/{len(record_ids)}] ❌ Failed: {record_id} - {e}")
            failed_count += 1
    
    # Summary
    print(f"\n{'='*80}")
    print(f"DELETION SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Successfully deleted: {deleted_count}")
    print(f"❌ Failed to delete: {failed_count}")
    print(f"📊 Total attempted: {len(record_ids)}")
    print(f"{'='*80}")


def interactive_mode(client):
    """Interactive mode for entering IDs."""
    print("\n" + "="*80)
    print("INTERACTIVE DELETION MODE")
    print("="*80)
    print("\nEnter Weaviate record IDs to delete.")
    print("You can enter:")
    print("  • Single ID: abc-123-def")
    print("  • Multiple IDs (comma-separated): abc-123, def-456, ghi-789")
    print("  • Multiple IDs (space-separated): abc-123 def-456 ghi-789")
    print("  • Type 'quit' to exit")
    print()
    
    ids_input = input("Enter record ID(s): ").strip()
    
    if ids_input.lower() == 'quit':
        print("👋 Exiting")
        return
    
    # Parse IDs (handle both comma and space separated)
    if ',' in ids_input:
        record_ids = [id.strip() for id in ids_input.split(',') if id.strip()]
    else:
        record_ids = [id.strip() for id in ids_input.split() if id.strip()]
    
    if not record_ids:
        print("❌ No valid IDs entered")
        return
    
    delete_records(client, record_ids, preview=True, confirm=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Delete records from Weaviate TranscriptQA collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python scripts/delete_weaviate_records.py
  
  # Delete single record
  python scripts/delete_weaviate_records.py --ids abc-123-def
  
  # Delete multiple records
  python scripts/delete_weaviate_records.py --ids abc-123 def-456 ghi-789
  
  # Delete from file
  python scripts/delete_weaviate_records.py --file ids_to_delete.txt
  
  # Skip preview and confirmation (dangerous!)
  python scripts/delete_weaviate_records.py --ids abc-123 --no-preview --no-confirm
        """
    )
    
    parser.add_argument(
        '--ids',
        nargs='+',
        help='Weaviate record IDs to delete (space-separated)'
    )
    parser.add_argument(
        '--file',
        help='File containing record IDs (one per line)'
    )
    parser.add_argument(
        '--no-preview',
        action='store_true',
        help='Skip record preview'
    )
    parser.add_argument(
        '--no-confirm',
        action='store_true',
        help='Skip confirmation prompt (USE WITH CAUTION!)'
    )
    
    args = parser.parse_args()
    
    # Connect to Weaviate
    print("="*80)
    print("WEAVIATE RECORD DELETION TOOL")
    print("="*80)
    
    client = connect_to_weaviate()
    if not client:
        sys.exit(1)
    
    try:
        # Determine record IDs
        record_ids = []
        
        if args.file:
            # Read from file
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"❌ File not found: {args.file}")
                sys.exit(1)
            
            with open(file_path, 'r') as f:
                record_ids = [line.strip() for line in f if line.strip()]
            
            print(f"📄 Loaded {len(record_ids)} IDs from {args.file}")
        
        elif args.ids:
            # Use provided IDs
            record_ids = args.ids
        
        else:
            # Interactive mode
            interactive_mode(client)
            return
        
        # Delete records
        if record_ids:
            delete_records(
                client, 
                record_ids, 
                preview=not args.no_preview,
                confirm=not args.no_confirm
            )
    
    finally:
        client.close()
        print("\n🔌 Connection closed")


if __name__ == "__main__":
    main()
