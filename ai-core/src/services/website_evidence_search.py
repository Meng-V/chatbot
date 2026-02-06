"""
Website Evidence Search Service

Provides semantic search over Jekyll-derived website evidence stored in Weaviate.
This service is used for RAG fallback when API agents don't have sufficient information.
"""

import os
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
from langchain_openai import OpenAIEmbeddings

# Import centralized Weaviate client
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.weaviate_client import get_weaviate_client


def get_collection_name() -> str:
    """Get collection name from environment or use default."""
    return os.getenv("WEBSITE_EVIDENCE_COLLECTION", "WebsiteEvidence")


def _get_weaviate_client():
    """Get Weaviate client using centralized factory."""
    return get_weaviate_client()


async def search_website_evidence(
    query: str, 
    top_k: int = 5, 
    collection: Optional[str] = None, 
    campus_scope: Optional[str] = None,
    log_callback=None
) -> List[Dict[str, Any]]:
    """
    Search website evidence using semantic similarity.

    Args:
        query: Search query
        top_k: Number of results to return (default: 5)
        collection: Collection name (default: from env or "WebsiteEvidence")
        campus_scope: Filter by campus (e.g., "oxford", "hamilton", "middletown")
        log_callback: Optional logging callback

    Returns:
        List of results with:
            - final_url: URL to cite
            - title: Page title
            - chunk_text: Relevant text chunk
            - chunk_index: Chunk position in page
            - score: Relevance score (0-1)
            - tags: Content tags
            - summary: Page summary
    """
    collection_name = collection or get_collection_name()

    if log_callback:
        filter_info = f", campus_scope={campus_scope}" if campus_scope else ""
        log_callback(
            f"🔍 [Website Evidence Search] Querying collection: {collection_name}{filter_info}",
            {"query": query, "top_k": top_k},
        )

    client = None
    try:
        # Get OpenAI API key for embeddings
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if not openai_api_key:
            if log_callback:
                log_callback("❌ [Website Evidence Search] OPENAI_API_KEY not set")
            return []

        # Create embeddings
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large", api_key=openai_api_key
        )

        # Connect to Weaviate
        client = _get_weaviate_client()

        # V4 API: Check if collection exists
        exists = client.collections.exists(collection_name)
        if not exists:
            if log_callback:
                log_callback(
                    f"⚠️ [Website Evidence Search] Collection not found: {collection_name}"
                )
            return []

        # Generate query embedding
        query_vector = await embeddings.aembed_query(query)

        # V4 API: Query with near vector and optional campus filter
        collection = client.collections.get(collection_name)
        
        # Build filter if campus_scope specified
        query_kwargs = {
            "near_vector": query_vector,
            "limit": top_k,
            "return_metadata": ['distance']
        }
        
        if campus_scope:
            import weaviate.classes as wvc
            query_kwargs["filters"] = wvc.query.Filter.by_property("campus_scope").equal(campus_scope)
            if log_callback:
                log_callback(f"   🔍 Filtering by campus_scope: {campus_scope}")
        
        response = collection.query.near_vector(**query_kwargs)

        results = []
        for obj in response.objects:
            distance = obj.metadata.distance if obj.metadata else 1.0
            results.append({
                "final_url": obj.properties.get("final_url", ""),
                "title": obj.properties.get("title", ""),
                "chunk_text": obj.properties.get("chunk_text", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "tags": obj.properties.get("tags", []),
                "summary": obj.properties.get("summary", ""),
                "canonical_url": obj.properties.get("canonical_url", ""),
                "aliases": obj.properties.get("aliases", []),
                "distance": distance
            })

        if log_callback:
            log_callback(f"✅ [Website Evidence Search] Found {len(results)} results")
            if results:
                top_result = results[0]
                log_callback(
                    f"   Top result: {top_result['title']} (distance: {top_result['distance']:.3f})"
                )

        return results

    except Exception as e:
        if log_callback:
            log_callback(f"❌ [Website Evidence Search] Error: {str(e)}")
        return []


async def get_evidence_for_url(
    url: str, collection: Optional[str] = None, log_callback=None
) -> List[Dict[str, Any]]:
    """
    Get all evidence chunks for a specific URL.

    Args:
        url: URL to search for
        collection: Collection name (default: from env or "WebsiteEvidence")
        log_callback: Optional logging callback

    Returns:
        List of all chunks for the URL, ordered by chunk_index
    """
    collection_name = collection or get_collection_name()

    if log_callback:
        log_callback(f"🔍 [Website Evidence Search] Getting chunks for URL: {url}")

    client = None
    try:
        client = _get_weaviate_client()

        if not client.collections.exists(collection_name):
            if log_callback:
                log_callback(
                    f"⚠️ [Website Evidence Search] Collection not found: {collection_name}"
                )
            return []

        collection_obj = client.collections.get(collection_name)

        # Query by URL
        response = collection_obj.query.fetch_objects(
            filters=wvc.query.Filter.by_property("final_url").equal(url),
            limit=100,  # Should be enough for most pages
        )

        results = []
        for obj in response.objects:
            props = obj.properties
            results.append(
                {
                    "final_url": props.get("final_url", ""),
                    "title": props.get("title", ""),
                    "chunk_text": props.get("chunk_text", ""),
                    "chunk_index": props.get("chunk_index", 0),
                    "tags": props.get("tags", []),
                    "summary": props.get("summary", ""),
                }
            )

        # Sort by chunk_index
        results.sort(key=lambda x: x["chunk_index"])

        if log_callback:
            log_callback(
                f"✅ [Website Evidence Search] Found {len(results)} chunks for URL"
            )

        return results

    except Exception as e:
        if log_callback:
            log_callback(f"❌ [Website Evidence Search] Error: {str(e)}")
        return []
