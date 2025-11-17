#!/usr/bin/env python3
"""
Weaviate Database Setup Script

This script helps you:
1. Test connection to your new Weaviate database
2. Create the TranscriptQA collection with proper schema
3. Optionally load initial data

Usage:
    python scripts/setup_weaviate.py
"""

import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv
import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment - .env is at repository root (one level up from ai-core)
root_dir = Path(__file__).resolve().parent.parent.parent  # Go up to chatbot/ directory
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def print_header(text):
    """Print a formatted header."""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)


def print_step(number, text):
    """Print a step number."""
    print(f"\n[STEP {number}] {text}")
    print("-"*80)


def check_env_variables():
    """Check if required environment variables are set."""
    print_step(1, "Checking Environment Variables")
    
    required_vars = {
        "WEAVIATE_HOST": WEAVIATE_HOST,
        "WEAVIATE_API_KEY": WEAVIATE_API_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY
    }
    
    all_set = True
    for var_name, var_value in required_vars.items():
        if not var_value or var_value == f"YOUR_NEW_{var_name}_HERE":
            print(f"❌ {var_name}: NOT SET")
            all_set = False
        else:
            # Mask sensitive values
            masked = var_value[:8] + "..." if len(var_value) > 8 else "***"
            print(f"✅ {var_name}: {masked}")
    
    if not all_set:
        print("\n⚠️  ERROR: Please update your .env file with Weaviate credentials")
        print("\nTo get your credentials:")
        print("1. Go to: https://console.weaviate.cloud/")
        print("2. Select your cluster")
        print("3. Click 'Details' tab")
        print("4. Copy:")
        print("   - API Key → WEAVIATE_API_KEY")
        print("   - Cluster URL → WEAVIATE_HOST (without https://)")
        print("\nExample .env configuration:")
        print("  WEAVIATE_API_KEY=abcd1234efgh5678ijkl9012...")
        print("  WEAVIATE_HOST=xyz123.c0.us-east1.gcp.weaviate.cloud")
        print("  WEAVIATE_SCHEME=https")
        return False
    
    return True


def test_connection():
    """Test connection to Weaviate."""
    print_step(2, "Testing Connection to Weaviate")
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_HOST,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
            headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
        )
        
        # Test if connection works
        meta = client.get_meta()
        
        print(f"✅ Connected successfully!")
        print(f"   Weaviate Version: {meta.get('version', 'Unknown')}")
        print(f"   Host: {WEAVIATE_HOST}")
        
        return client
    
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Verify WEAVIATE_HOST is correct (without https://)")
        print("2. Verify WEAVIATE_API_KEY is correct")
        print("3. Check if cluster is running in Weaviate Cloud Console")
        print("4. Verify your IP is allowed (if using IP whitelist)")
        return None


def check_collection_exists(client):
    """Check if TranscriptQA collection already exists."""
    print_step(3, "Checking Existing Collections")
    
    try:
        collections = client.collections.list_all()
        collection_names = [str(c) for c in collections]
        
        print(f"Found {len(collection_names)} collection(s):")
        for name in collection_names:
            print(f"  • {name}")
        
        if "TranscriptQA" in collection_names:
            print(f"\n⚠️  TranscriptQA collection already exists")
            
            # Get collection info
            collection = client.collections.get("TranscriptQA")
            config = collection.config.get()
            
            print(f"\nExisting collection details:")
            print(f"  • Vectorizer: {config.vectorizer}")
            print(f"  • Properties: {len(config.properties)} fields")
            
            response = input("\nDelete and recreate? (yes/no): ").lower()
            if response == "yes":
                collection.delete()
                print("✅ Deleted existing collection")
                return False
            else:
                print("⏭️  Keeping existing collection")
                return True
        else:
            print("\n✅ No existing TranscriptQA collection found")
            return False
    
    except Exception as e:
        print(f"❌ Error checking collections: {e}")
        return False


def create_collection(client):
    """Create the TranscriptQA collection with proper schema."""
    print_step(4, "Creating TranscriptQA Collection")
    
    try:
        # Define collection schema
        collection = client.collections.create(
            name="TranscriptQA",
            description="Optimized Q&A pairs from library transcripts for RAG",
            vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(
                model="text-embedding-3-small"
            ),
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
                    description="Topic category (e.g., discovery_search, hours, policy)"
                ),
                wvc.config.Property(
                    name="keywords",
                    data_type=wvc.config.DataType.TEXT_ARRAY,
                    description="Keywords for better search matching"
                )
            ]
        )
        
        print("✅ Collection 'TranscriptQA' created successfully!")
        print("\nSchema:")
        print("  • question (TEXT) - The question")
        print("  • answer (TEXT) - The answer")
        print("  • topic (TEXT) - Category")
        print("  • keywords (TEXT_ARRAY) - Search keywords")
        print("  • Vectorizer: OpenAI text-embedding-3-small")
        
        return True
    
    except Exception as e:
        print(f"❌ Error creating collection: {e}")
        return False


def load_sample_data(client):
    """Load sample Q&A pairs into the collection."""
    print_step(5, "Loading Sample Data (Optional)")
    
    response = input("\nLoad sample data? (yes/no): ").lower()
    if response != "yes":
        print("⏭️  Skipping sample data")
        return True
    
    try:
        collection = client.collections.get("TranscriptQA")
        
        # Sample Q&A pairs
        sample_data = [
            {
                "question": "How do I renew a book?",
                "answer": "You can renew books through your library account online, by calling the circulation desk at (513) 529-4141, or by visiting the library in person. Most items can be renewed unless they have holds.",
                "topic": "policy_or_service",
                "keywords": ["renew", "book", "circulation", "library account", "online"]
            },
            {
                "question": "What are King Library's hours?",
                "answer": "During regular semesters, King Library is open Monday-Thursday 7:30am-2am, Friday 7:30am-6pm, Saturday 10am-6pm, and Sunday 10am-2am. Hours may vary during breaks and summer.",
                "topic": "booking_or_hours",
                "keywords": ["hours", "King Library", "open", "schedule", "when"]
            },
            {
                "question": "How do I book a study room?",
                "answer": "You can reserve study rooms online through LibCal at https://muohio.libcal.com/reserve/studyrooms or by visiting the circulation desk. You'll need your Miami University ID.",
                "topic": "booking_or_hours",
                "keywords": ["study room", "book", "reserve", "LibCal", "room reservation"]
            },
            {
                "question": "How do I access databases from off-campus?",
                "answer": "To access library databases from off-campus, you'll need to log in with your Miami University UniqueID and password. The system will authenticate you through the library's proxy server.",
                "topic": "policy_or_service",
                "keywords": ["databases", "off-campus", "remote access", "login", "authentication"]
            },
            {
                "question": "What is interlibrary loan?",
                "answer": "Interlibrary Loan (ILL) is a service that allows you to request books and articles from other libraries if Miami doesn't own them. Submit requests through ILLiad, and items typically arrive within 1-2 weeks.",
                "topic": "policy_or_service",
                "keywords": ["interlibrary loan", "ILL", "ILLiad", "request", "borrow"]
            }
        ]
        
        # Insert data
        print(f"\nInserting {len(sample_data)} sample Q&A pairs...")
        
        for i, item in enumerate(sample_data, 1):
            collection.data.insert(properties=item)
            print(f"  {i}. {item['question']}")
        
        print(f"\n✅ Successfully loaded {len(sample_data)} sample Q&A pairs!")
        
        return True
    
    except Exception as e:
        print(f"❌ Error loading sample data: {e}")
        return False


def load_existing_data(client):
    """Load existing Q&A data from JSON file if available."""
    print_step(6, "Loading Existing Q&A Data (Optional)")
    
    # Check if data file exists
    data_file = root_dir / "data" / "optimized_for_weaviate.json"
    
    if not data_file.exists():
        print(f"⏭️  No existing data file found at: {data_file}")
        return True
    
    print(f"Found existing data file: {data_file}")
    response = input("\nLoad this data? (yes/no): ").lower()
    if response != "yes":
        print("⏭️  Skipping existing data")
        return True
    
    try:
        # Load JSON data
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        collection = client.collections.get("TranscriptQA")
        
        print(f"\nLoading {len(data)} Q&A pairs from file...")
        
        # Batch insert for efficiency
        with collection.batch.dynamic() as batch:
            for i, item in enumerate(data, 1):
                batch.add_object(properties=item)
                if i % 10 == 0:
                    print(f"  Loaded {i}/{len(data)}...")
        
        print(f"\n✅ Successfully loaded {len(data)} Q&A pairs from file!")
        
        return True
    
    except Exception as e:
        print(f"❌ Error loading data file: {e}")
        return False


def verify_setup(client):
    """Verify the setup by querying the collection."""
    print_step(7, "Verifying Setup")
    
    try:
        collection = client.collections.get("TranscriptQA")
        
        # Get object count
        response = collection.aggregate.over_all(total_count=True)
        count = response.total_count
        
        print(f"✅ Collection contains {count} objects")
        
        if count > 0:
            # Test a query
            print("\nTesting query: 'How do I renew a book?'")
            results = collection.query.near_text(
                query="How do I renew a book?",
                limit=1,
                return_metadata=wvc.query.MetadataQuery(distance=True)
            )
            
            if results.objects:
                obj = results.objects[0]
                print(f"\n📝 Top result:")
                print(f"   Question: {obj.properties.get('question', 'N/A')}")
                print(f"   Answer: {obj.properties.get('answer', 'N/A')[:100]}...")
                print(f"   Distance: {obj.metadata.distance:.3f}")
                print(f"   Similarity: {1-obj.metadata.distance:.3f}")
        
        return True
    
    except Exception as e:
        print(f"❌ Error verifying setup: {e}")
        return False


def print_next_steps():
    """Print next steps for the user."""
    print_header("Setup Complete! 🎉")
    
    print("\n✅ Your Weaviate database is ready to use!")
    print("\nNext steps:")
    print("\n1. Add your factual data:")
    print("   • Edit: scripts/update_rag_facts.py")
    print("   • Add your correct facts to CORRECT_FACTS list")
    print("   • Run: python scripts/update_rag_facts.py")
    
    print("\n2. Test RAG retrieval:")
    print("   • Run: python scripts/query_rag.py \"your question\"")
    print("   • Verify similarity scores and answers")
    
    print("\n3. Run test suite:")
    print("   • Edit: scripts/test_fact_queries.py (add test cases)")
    print("   • Run: python scripts/test_fact_queries.py")
    
    print("\n4. Test in chatbot:")
    print("   • Start your chatbot application")
    print("   • Ask factual questions")
    print("   • Check logs for [Fact Grounding] messages")
    
    print("\n📚 Documentation:")
    print("   • Quick Start: FACT_GROUNDING_QUICKSTART.md")
    print("   • Complete Guide: docs/FACT_GROUNDING_GUIDE.md")
    print("   • Summary: docs/FACT_CORRECTION_SUMMARY.md")
    
    print("\n" + "="*80)


def main():
    """Main setup workflow."""
    print_header("Weaviate Database Setup")
    print("\nThis script will help you set up your new Weaviate database.")
    
    # Step 1: Check environment variables
    if not check_env_variables():
        return 1
    
    # Step 2: Test connection
    client = test_connection()
    if not client:
        return 1
    
    try:
        # Step 3: Check existing collections
        exists = check_collection_exists(client)
        
        # Step 4: Create collection if needed
        if not exists:
            if not create_collection(client):
                return 1
        
        # Step 5: Load sample data
        load_sample_data(client)
        
        # Step 6: Load existing data file
        load_existing_data(client)
        
        # Step 7: Verify setup
        verify_setup(client)
        
        # Print next steps
        print_next_steps()
        
        return 0
    
    finally:
        client.close()
        print("\n🔌 Connection closed")


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
