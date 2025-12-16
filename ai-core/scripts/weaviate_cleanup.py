#!/usr/bin/env python3
"""
Weaviate Cleanup Script - Delete All Records

WARNING: This script deletes ALL records in the Weaviate collection.
Use this to clear out old RAG data before starting fresh with correction pool.

Usage:
    cd /Users/qum/Documents/GitHub/chatbot/ai-core
    source venv/bin/activate
    python scripts/weaviate_cleanup.py

Safety: Requires typing "DELETE ALL" to confirm.
"""

import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

WEAVIATE_URL = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
COLLECTION_NAME = "TranscriptQA"

def connect_to_weaviate():
    """Connect to Weaviate Cloud."""
    print(f"🔌 Connecting to Weaviate at {WEAVIATE_URL}...")
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_URL,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY)
        )
        print("✅ Connected successfully\n")
        return client
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)

def count_records(client):
    """Count total records in collection."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        response = collection.aggregate.over_all(total_count=True)
        return response.total_count
    except Exception as e:
        print(f"⚠️ Error counting records: {e}")
        return 0

def delete_all_records(client):
    """Delete all records from Weaviate collection."""
    try:
        collection = client.collections.get(COLLECTION_NAME)
        
        print("🗑️  Deleting all records...")
        
        # Method 1: Try to delete collection entirely and recreate
        # This is the cleanest way to clear all data
        try:
            print("   Attempting to delete entire collection...")
            client.collections.delete(COLLECTION_NAME)
            print("   ✅ Collection deleted")
            
            # Recreate empty collection with same schema
            print("   Recreating collection...")
            client.collections.create(
                name=COLLECTION_NAME,
                properties=[
                    wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="answer", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="topic", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="confidence", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="date_added", data_type=wvc.config.DataType.DATE),
                ]
            )
            print("   ✅ Collection recreated")
            return True
        except Exception as e:
            print(f"   ⚠️  Collection delete/recreate failed: {e}")
            print("   Trying alternative method...")
            
            # Method 2: Fetch all objects and delete individually
            print("   Fetching all objects to delete individually...")
            response = collection.query.fetch_objects(limit=10000)
            objects = response.objects
            
            if not objects:
                print("   No objects found to delete")
                return True
            
            print(f"   Deleting {len(objects)} objects...")
            deleted_count = 0
            for obj in objects:
                try:
                    collection.data.delete_by_id(obj.uuid)
                    deleted_count += 1
                    if deleted_count % 100 == 0:
                        print(f"   Deleted {deleted_count}/{len(objects)}...")
                except Exception as del_err:
                    print(f"   ⚠️  Failed to delete {obj.uuid}: {del_err}")
            
            print(f"   ✅ Deleted {deleted_count} objects")
            return True
        
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        return None

def main():
    print("=" * 70)
    print("🚨 WEAVIATE CLEANUP - DELETE ALL RECORDS 🚨")
    print("=" * 70)
    print()
    print("⚠️  WARNING: This will permanently delete ALL records in Weaviate!")
    print("   This action cannot be undone.")
    print()
    
    # Connect to Weaviate
    client = connect_to_weaviate()
    
    # Count current records
    total_records = count_records(client)
    print(f"📊 Current records in collection: {total_records}")
    print()
    
    if total_records == 0:
        print("✅ Collection is already empty. Nothing to delete.")
        client.close()
        return
    
    # Require confirmation
    print("=" * 70)
    print('To confirm deletion, type exactly: DELETE ALL')
    print("=" * 70)
    confirmation = input("Type here: ").strip()
    
    if confirmation != "DELETE ALL":
        print("\n❌ Deletion cancelled. Confirmation text did not match.")
        client.close()
        return
    
    print()
    print("🗑️  Proceeding with deletion...")
    print()
    
    # Delete all records
    result = delete_all_records(client)
    
    if result:
        print(f"✅ Successfully deleted all records")
        print()
        
        # Verify deletion
        remaining = count_records(client)
        if remaining == 0:
            print("✅ Verification: Collection is now empty")
        else:
            print(f"⚠️  Warning: {remaining} records still remain")
    else:
        print("❌ Deletion may have failed. Check logs.")
    
    # Close connection
    client.close()
    print("\n🔌 Disconnected from Weaviate")
    print()
    print("=" * 70)
    print("✅ CLEANUP COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Use add_correction_to_rag.py to add corrected Q&A pairs")
    print("2. Start with high-priority bot mistakes")
    print("3. Do NOT try to reload all old transcript data")
    print()

if __name__ == "__main__":
    main()
