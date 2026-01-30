#!/usr/bin/env python3
"""
Weaviate Connection Debug Script

Tests Weaviate connection and provides diagnostic information.
Use this on the server to troubleshoot Weaviate issues.

Usage:
    python3 scripts/debug_weaviate.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
env_file = root_dir / ".env"
load_dotenv(dotenv_path=env_file)

print("="*80)
print("WEAVIATE CONNECTION DIAGNOSTICS")
print("="*80)

# Step 1: Check environment file
print(f"\n[1] Environment File")
print("-"*80)
print(f"Location: {env_file}")
print(f"Exists: {env_file.exists()}")

# Step 2: Check environment variables
print(f"\n[2] Environment Variables")
print("-"*80)

required_vars = {
    "WEAVIATE_ENABLED": os.getenv("WEAVIATE_ENABLED"),
    "WEAVIATE_HOST": os.getenv("WEAVIATE_HOST"),
    "WEAVIATE_SCHEME": os.getenv("WEAVIATE_SCHEME"),
    "WEAVIATE_HTTP_PORT": os.getenv("WEAVIATE_HTTP_PORT"),
    "WEAVIATE_GRPC_PORT": os.getenv("WEAVIATE_GRPC_PORT"),
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
}

for var_name, var_value in required_vars.items():
    if var_value:
        # Mask API key
        if "KEY" in var_name:
            display_value = var_value[:8] + "..." if len(var_value) > 8 else "***"
        else:
            display_value = var_value
        print(f"✅ {var_name}: {display_value}")
    else:
        print(f"❌ {var_name}: NOT SET")

# Step 3: Test Weaviate import
print(f"\n[3] Import Weaviate Client")
print("-"*80)

try:
    from src.utils.weaviate_client import get_weaviate_client
    print("✅ Successfully imported get_weaviate_client")
except Exception as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)

# Step 4: Test connection
print(f"\n[4] Connect to Weaviate")
print("-"*80)

try:
    client = get_weaviate_client()
    if not client:
        print("❌ get_weaviate_client() returned None")
        print("\nTroubleshooting:")
        print("  1. Check if Weaviate Docker container is running: docker ps | grep weaviate")
        print("  2. Check if ports are accessible: curl http://127.0.0.1:8080/v1/.well-known/ready")
        print("  3. Verify WEAVIATE_HOST and ports in .env")
        sys.exit(1)
    
    print("✅ Client created successfully")
    
    # Test if client is ready
    if client.is_ready():
        print("✅ Weaviate is ready")
    else:
        print("❌ Weaviate is not ready")
        sys.exit(1)
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 5: Get metadata
print(f"\n[5] Weaviate Metadata")
print("-"*80)

try:
    meta = client.get_meta()
    print(f"✅ Version: {meta.get('version', 'Unknown')}")
    print(f"   Modules: {', '.join(meta.get('modules', {}).keys()) if meta.get('modules') else 'None'}")
except Exception as e:
    print(f"❌ Failed to get metadata: {e}")

# Step 6: List collections
print(f"\n[6] Collections")
print("-"*80)

try:
    collections = client.collections.list_all()
    collection_names = [str(c) for c in collections]
    
    if collection_names:
        print(f"✅ Found {len(collection_names)} collections:")
        for name in collection_names:
            try:
                col = client.collections.get(name)
                result = col.aggregate.over_all(total_count=True)
                count = result.total_count
                print(f"   • {name}: {count} records")
            except Exception as e:
                print(f"   • {name}: Error counting records ({str(e)})")
    else:
        print("⚠️  No collections found")
        print("   This is expected if Weaviate was just set up.")
        print("   Run: python3 scripts/deploy_to_weaviate.py")
    
except Exception as e:
    print(f"❌ Failed to list collections: {e}")
    import traceback
    traceback.print_exc()

# Step 7: Test basic query (if collections exist)
print(f"\n[7] Test Query")
print("-"*80)

try:
    collections = client.collections.list_all()
    collection_names = [str(c) for c in collections]
    
    if collection_names:
        test_collection = collection_names[0]
        print(f"Testing with collection: {test_collection}")
        
        col = client.collections.get(test_collection)
        result = col.query.fetch_objects(limit=1)
        
        if result.objects:
            print(f"✅ Successfully queried {test_collection}")
            print(f"   Sample record ID: {result.objects[0].uuid}")
        else:
            print(f"⚠️  Collection {test_collection} is empty")
    else:
        print("⏭️  Skipped (no collections)")
    
except Exception as e:
    print(f"❌ Query failed: {e}")

# Step 8: Test embeddings
print(f"\n[8] Test OpenAI Embeddings")
print("-"*80)

try:
    from langchain_openai import OpenAIEmbeddings
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ OPENAI_API_KEY not set")
    else:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=openai_api_key
        )
        
        test_text = "test embedding"
        vector = embeddings.embed_query(test_text)
        
        print(f"✅ Embeddings working")
        print(f"   Vector dimensions: {len(vector)}")
        print(f"   First 3 values: {vector[:3]}")
    
except Exception as e:
    print(f"❌ Embedding test failed: {e}")
    import traceback
    traceback.print_exc()

# Step 9: Test LLM
print(f"\n[9] Test OpenAI Chat Model")
print("-"*80)

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "o4-mini")
    
    if not openai_api_key:
        print("❌ OPENAI_API_KEY not set")
    else:
        print(f"Testing with model: {openai_model}")
        
        llm_kwargs = {"model": openai_model, "api_key": openai_api_key}
        if not openai_model.startswith("o"):
            llm_kwargs["temperature"] = 0
        
        llm = ChatOpenAI(**llm_kwargs)
        
        response = llm.invoke([HumanMessage(content="Say 'test successful' if you can read this.")])
        
        print(f"✅ LLM working")
        print(f"   Model: {openai_model}")
        print(f"   Response: {response.content[:100]}")
    
except Exception as e:
    print(f"❌ LLM test failed: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "="*80)
print("DIAGNOSTIC SUMMARY")
print("="*80)

if client:
    print("\n✅ Weaviate connection is working!")
    print("\nNext steps:")
    print("  1. If collections are empty, run: python3 scripts/deploy_to_weaviate.py")
    print("  2. If collections exist with data, your setup is complete")
    print("  3. Test the chatbot application")
    
    client.close()
    print("\n🔌 Connection closed")
else:
    print("\n❌ Weaviate connection failed - see errors above")
    sys.exit(1)
