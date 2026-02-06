#!/usr/bin/env python3
"""
Weaviate Smoke Test - LOCAL DOCKER ONLY
Tests connectivity, schema operations, and basic CRUD against local Weaviate.
Uses centralized client factory with connect_to_custom.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Add src to path
sys.path.insert(0, str(root_dir / "ai-core" / "src"))
from utils.weaviate_client import get_weaviate_client, get_weaviate_url


def print_config():
    """Print configuration (mask any secrets)."""
    print("=" * 80)
    print("WEAVIATE SMOKE TEST - LOCAL DOCKER")
    print("=" * 80)
    print("\n📋 Configuration:")
    print(f"  WEAVIATE_ENABLED: {os.getenv('WEAVIATE_ENABLED', 'not set')}")
    print(f"  WEAVIATE_SCHEME: {os.getenv('WEAVIATE_SCHEME', 'not set')}")
    print(f"  WEAVIATE_HOST: {os.getenv('WEAVIATE_HOST', 'not set')}")
    print(f"  WEAVIATE_HTTP_PORT: {os.getenv('WEAVIATE_HTTP_PORT', 'not set')}")
    print(f"  WEAVIATE_GRPC_PORT: {os.getenv('WEAVIATE_GRPC_PORT', 'not set')}")
    print(f"  URL: {get_weaviate_url()}")
    print()


def create_client():
    """Create Weaviate client using centralized factory."""
    print(f"🔗 Connecting via centralized client factory...")
    
    try:
        client = get_weaviate_client()
        if client:
            print(f"✅ Client created successfully")
        return client
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return None


def test_ready(client):
    """Test /v1/.well-known/ready endpoint."""
    print("\n🔍 Test 1: Ready Check")
    try:
        is_ready = client.is_ready()
        if is_ready:
            print("  ✅ Weaviate is ready")
            return True
        else:
            print("  ❌ Weaviate not ready")
            return False
    except Exception as e:
        print(f"  ❌ Ready check failed: {e}")
        return False


def test_meta(client):
    """Test /v1/meta endpoint."""
    print("\n🔍 Test 2: Meta Information")
    try:
        meta = client.get_meta()
        version = meta.get("version", "unknown")
        print(f"  ✅ Version: {version}")
        print(f"  ✅ Hostname: {meta.get('hostname', 'unknown')}")
        return True
    except Exception as e:
        print(f"  ❌ Meta query failed: {e}")
        return False


def test_schema(client):
    """Test schema retrieval (v4 API)."""
    print("\n🔍 Test 3: Schema Access")
    try:
        # V4 API uses collections
        all_collections = client.collections.list_all()
        print(f"  ✅ Found {len(all_collections)} collections:")
        for collection_name in all_collections:
            print(f"     - {collection_name}")
        return True
    except Exception as e:
        print(f"  ❌ Schema query failed: {e}")
        return False


def test_crud(client):
    """Test create, insert, query, delete on temporary collection (v4 API)."""
    print("\n🔍 Test 4: CRUD Operations")
    collection_name = "SmokeTest"
    
    try:
        # 1. Create temporary collection (v4 API)
        print(f"  Creating collection: {collection_name}")
        
        # Delete if exists
        if client.collections.exists(collection_name):
            client.collections.delete(collection_name)
        
        # Create collection
        from weaviate.classes.config import Property, DataType
        client.collections.create(
            name=collection_name,
            description="Temporary collection for smoke test",
            properties=[
                Property(name="content", data_type=DataType.TEXT, description="Test content")
            ]
        )
        print(f"  ✅ Collection created")
        
        # 2. Insert test object (v4 API)
        print(f"  Inserting test object...")
        collection = client.collections.get(collection_name)
        uuid = collection.data.insert(
            properties={"content": "smoke test object"}
        )
        print(f"  ✅ Object inserted: {uuid}")
        
        # 3. Query object (v4 API)
        print(f"  Querying object...")
        obj = collection.query.fetch_object_by_id(uuid)
        if obj and obj.properties.get("content") == "smoke test object":
            print(f"  ✅ Object retrieved successfully")
        else:
            print(f"  ❌ Object mismatch")
            return False
        
        # 4. Delete collection
        print(f"  Deleting collection...")
        client.collections.delete(collection_name)
        print(f"  ✅ Collection deleted")
        
        return True
        
    except Exception as e:
        print(f"  ❌ CRUD test failed: {e}")
        import traceback
        traceback.print_exc()
        # Clean up on failure
        try:
            if client.collections.exists(collection_name):
                client.collections.delete(collection_name)
        except:
            pass
        return False


def main():
    """Run all smoke tests."""
    print_config()
    
    # Create client
    client = create_client()
    if not client:
        print("\n❌ SMOKE TEST FAILED: Could not create client")
        return 1
    
    # Run tests
    tests = [
        ("Ready Check", lambda: test_ready(client)),
        ("Meta Info", lambda: test_meta(client)),
        ("Schema Access", lambda: test_schema(client)),
        ("CRUD Operations", lambda: test_crud(client))
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Close client
    client.close()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print()
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED - Weaviate LOCAL DOCKER is healthy!")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED - Check configuration and Docker container")
        return 1


if __name__ == "__main__":
    sys.exit(main())
