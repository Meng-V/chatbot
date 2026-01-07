"""
Reinitialize RAG Vector Store with Updated Examples
Run: python scripts/reinit_rag_store.py
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from project root
env_path = project_root.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from {env_path}")
    print(f"   WEAVIATE_HOST: {os.getenv('WEAVIATE_HOST', 'NOT SET')}")
    print(f"   WEAVIATE_API_KEY: {'SET' if os.getenv('WEAVIATE_API_KEY') else 'NOT SET'}")
else:
    print(f"⚠️ .env file not found at {env_path}")

from src.classification.rag_classifier import RAGQuestionClassifier


async def main():
    """Reinitialize the RAG vector store with updated category examples."""
    print("\n" + "=" * 80)
    print("REINITIALIZING RAG VECTOR STORE")
    print("=" * 80)
    print()
    
    classifier = RAGQuestionClassifier()
    
    print("🔄 Deleting old vector store and creating new one with updated examples...")
    await classifier.initialize_vector_store(force_refresh=True)
    
    print("\n✅ RAG vector store reinitialized successfully!")
    print("=" * 80)
    print()


if __name__ == "__main__":
    asyncio.run(main())
