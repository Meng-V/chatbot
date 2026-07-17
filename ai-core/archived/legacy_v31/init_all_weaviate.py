#!/usr/bin/env python3
"""
Initialize ALL Weaviate collections needed for the chatbot.
1. QuestionCategory (RAG classifier)
2. AgentPrototypes (Weaviate router)
3. TranscriptQA (Transcript RAG agent - sample data)

Run: python scripts/init_all_weaviate.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
env_root = project_root.parent
load_dotenv(dotenv_path=env_root / ".env")

from src.utils.weaviate_client import get_weaviate_client


async def init_question_category():
    """Initialize QuestionCategory collection with RAG classifier data."""
    print("\n" + "=" * 60)
    print("1. Initializing QuestionCategory collection")
    print("=" * 60)

    from src.classification.rag_classifier import RAGQuestionClassifier

    classifier = RAGQuestionClassifier()
    await classifier.initialize_vector_store(force_refresh=True)

    # Verify
    client = get_weaviate_client()
    collection = client.collections.get("QuestionCategory")
    result = collection.aggregate.over_all(total_count=True)
    count = result.total_count
    print(f"✅ QuestionCategory: {count} examples loaded")
    client.close()


async def init_agent_prototypes():
    """Initialize AgentPrototypes collection."""
    print("\n" + "=" * 60)
    print("2. Initializing AgentPrototypes collection")
    print("=" * 60)

    from src.router.weaviate_router import WeaviateRouter
    from scripts.initialize_prototypes import PROTOTYPES

    router = WeaviateRouter()

    # Clear and recreate
    await router.clear_collection()
    print("   Cleared existing prototypes")

    total = 0
    for agent_data in PROTOTYPES:
        agent_id = agent_data["agent_id"]
        category = agent_data["category"]
        prototypes = agent_data["prototypes"]

        for proto in prototypes:
            await router.add_prototype(
                agent_id=agent_id,
                prototype_text=proto["text"],
                category=category,
                is_action_based=proto["is_action"],
                priority=proto["priority"]
            )
            total += 1

        print(f"   {agent_id} ({category}): {len(prototypes)} prototypes")

    print(f"✅ AgentPrototypes: {total} prototypes loaded")


async def init_transcript_qa():
    """Initialize TranscriptQA collection with sample data."""
    print("\n" + "=" * 60)
    print("3. Initializing TranscriptQA collection (sample data)")
    print("=" * 60)

    import weaviate.classes.config as wvc_config
    from langchain_openai import OpenAIEmbeddings

    client = get_weaviate_client()

    # Delete if exists
    if client.collections.exists("TranscriptQA"):
        client.collections.delete("TranscriptQA")
        print("   Deleted existing TranscriptQA")

    # Create with self-provided vectors (BYOV)
    import weaviate.classes as wvc
    client.collections.create(
        name="TranscriptQA",
        description="Optimized Q&A pairs from library transcripts for RAG",
        vector_config=wvc.config.Configure.Vectors.self_provided(),
        properties=[
            wvc_config.Property(name="question", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="answer", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="topic", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="keywords", data_type=wvc_config.DataType.TEXT_ARRAY),
            wvc_config.Property(name="verified", data_type=wvc_config.DataType.BOOL),
            wvc_config.Property(name="source_url", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="evidence_quote", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="source_domain", data_type=wvc_config.DataType.TEXT),
            wvc_config.Property(name="created_at", data_type=wvc_config.DataType.TEXT),
        ]
    )

    # Add sample data with embeddings
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-large",
        api_key=os.getenv("OPENAI_API_KEY", "")
    )

    sample_data = [
        {
            "question": "How do I renew a book?",
            "answer": "You can renew books through your library account online, by calling the circulation desk at (513) 529-4141, or by visiting the library in person. Most items can be renewed unless they have holds.",
            "topic": "policy_or_service",
            "keywords": ["renew", "book", "circulation", "library account", "online"],
        },
        {
            "question": "What is interlibrary loan?",
            "answer": "Interlibrary Loan (ILL) is a service that allows you to request books and articles from other libraries if Miami doesn't own them. Submit requests through ILLiad, and items typically arrive within 1-2 weeks.",
            "topic": "policy_or_service",
            "keywords": ["interlibrary loan", "ILL", "ILLiad", "request", "borrow"],
        },
        {
            "question": "How do I access databases from off-campus?",
            "answer": "To access library databases from off-campus, you'll need to log in with your Miami University UniqueID and password. The system will authenticate you through the library's proxy server.",
            "topic": "policy_or_service",
            "keywords": ["databases", "off-campus", "remote access", "login", "authentication"],
        },
        {
            "question": "How do I book a study room?",
            "answer": "You can reserve study rooms online through LibCal at https://muohio.libcal.com/reserve/studyrooms or by visiting the circulation desk. You'll need your Miami University ID.",
            "topic": "booking_or_hours",
            "keywords": ["study room", "book", "reserve", "LibCal", "room reservation"],
        },
        {
            "question": "What are King Library's hours?",
            "answer": "During regular semesters, King Library is open Monday-Thursday 7:30am-2am, Friday 7:30am-6pm, Saturday 10am-6pm, and Sunday 10am-2am. Hours may vary during breaks and summer.",
            "topic": "booking_or_hours",
            "keywords": ["hours", "King Library", "open", "schedule", "when"],
        },
    ]

    collection = client.collections.get("TranscriptQA")
    with collection.batch.dynamic() as batch:
        for item in sample_data:
            embedding = await embeddings.aembed_query(item["question"])
            batch.add_object(
                properties={
                    **item,
                    "verified": False,
                    "source_url": "",
                    "evidence_quote": "",
                    "source_domain": "",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                vector=embedding,
            )

    print(f"✅ TranscriptQA: {len(sample_data)} sample Q&A pairs loaded")
    client.close()


async def verify_all():
    """Verify all collections are ready."""
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    client = get_weaviate_client()
    collections = client.collections.list_all()
    print(f"\nTotal collections: {len(collections)}")
    for name in collections:
        coll = client.collections.get(name)
        count = coll.aggregate.over_all(total_count=True).total_count
        print(f"  • {name}: {count} objects")
    client.close()
    print("\n✅ All collections initialized successfully!")


async def main():
    print("🚀 Initializing ALL Weaviate Collections")
    print("=" * 60)

    await init_question_category()
    await init_agent_prototypes()
    await init_transcript_qa()
    await verify_all()


if __name__ == "__main__":
    asyncio.run(main())
