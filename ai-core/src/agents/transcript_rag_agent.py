"""
Optimized Transcript RAG Agent for Vector Search

This agent queries the optimized TranscriptQA collection with:
- Simplified schema (question, answer, keywords, topic)
- Better vector search performance
- More generalizable Q&A pairs
"""

import os
import weaviate
import weaviate.classes as wvc
import asyncio
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def _make_client():
    """Create Weaviate v4 client with cloud auth."""
    if not WEAVIATE_HOST or not WEAVIATE_API_KEY:
        return None
    
    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=WEAVIATE_HOST,
            auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
            headers={"X-OpenAI-Api-Key": OPENAI_API_KEY} if OPENAI_API_KEY else None
        )
        return client
    except Exception as e:
        print(f"Weaviate connection error: {e}")
        return None

client = _make_client()

async def transcript_rag_query(query: str, log_callback=None, topic_filter: str = None) -> Dict[str, Any]:
    """
    Query optimized Weaviate collection for generalized Q&A pairs.
    
    Args:
        query: User's question
        log_callback: Optional logging function
        topic_filter: Optional topic filter (e.g., "discovery_search")
    
    Returns:
        Dict with success, text, confidence, and metadata
    """
    def _search():
        if log_callback:
            log_callback("🔮 [Transcript RAG Agent] Querying optimized knowledge base")
        
        if not client:
            return {
                "source": "TranscriptRAG",
                "success": False,
                "error": "Weaviate not configured",
                "text": "Knowledge base is not available. Please contact a librarian for assistance."
            }
        
        try:
            # Get collection
            collection = client.collections.get("TranscriptQA")
            
            # Build query parameters
            query_params = {
                "query": query,
                "limit": 5,  # Get top 5 results for better selection
                "return_metadata": wvc.query.MetadataQuery(distance=True)
            }
            
            # Add topic filter if specified
            if topic_filter:
                query_params["where"] = wvc.query.Filter.by_property("topic").equal(topic_filter)
            
            # Execute semantic search
            response = collection.query.near_text(**query_params)
            
            if not response.objects:
                return {
                    "source": "TranscriptRAG",
                    "success": True,
                    "text": "I don't have a confident answer from our knowledge base. Let me connect you with a librarian who can help.",
                    "needs_human": True,
                    "confidence": "none"
                }
            
            # Score results based on distance (lower is better)
            results = []
            for obj in response.objects:
                props = obj.properties
                distance = obj.metadata.distance
                
                # Convert distance to similarity score (0-1, higher is better)
                similarity = 1 - distance
                
                results.append({
                    'question': props.get('question', ''),
                    'answer': props.get('answer', ''),
                    'topic': props.get('topic', ''),
                    'keywords': props.get('keywords', []),
                    'similarity': similarity,
                    'distance': distance
                })
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Determine confidence based on top result
            top_similarity = results[0]['similarity']
            if top_similarity >= 0.85:
                confidence = "high"
            elif top_similarity >= 0.75:
                confidence = "medium"
            else:
                confidence = "low"
            
            # Format response
            if confidence == "high" and len(results) == 1:
                # Single very relevant result - return directly
                text = f"**Q:** {results[0]['question']}\n\n**A:** {results[0]['answer']}"
            else:
                # Multiple results or lower confidence - show top results
                answer_parts = []
                for i, result in enumerate(results[:3], 1):
                    answer_parts.append(f"**{i}. {result['question']}**\n{result['answer']}")
                
                text = "Here are relevant answers from our knowledge base:\n\n" + "\n\n".join(answer_parts)
            
            return {
                "source": "TranscriptRAG",
                "success": True,
                "text": text,
                "confidence": confidence,
                "matched_topic": results[0]['topic'],
                "num_results": len(results),
                "top_keywords": results[0]['keywords'][:5],
                "similarity_score": top_similarity
            }
        
        except Exception as e:
            return {
                "source": "TranscriptRAG",
                "success": False,
                "error": str(e),
                "text": f"Knowledge base unavailable: {str(e)}"
            }
    
    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _search)
    return result


async def test_rag_agent():
    """Test function for development."""
    test_queries = [
        "How do I renew a book?",
        "What is interlibrary loan?",
        "How can I access databases from home?",
        "What are the library hours?",
        "How do I cite sources?"
    ]
    
    print("="*70)
    print("Testing Optimized Transcript RAG Agent")
    print("="*70)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*70}")
        print(f"Test {i}: {query}")
        print(f"{'='*70}")
        
        result = await transcript_rag_query(query)
        
        print(f"✅ Success: {result.get('success', False)}")
        print(f"📊 Confidence: {result.get('confidence', 'N/A')}")
        print(f"📋 Topic: {result.get('matched_topic', 'N/A')}")
        print(f"📝 Results: {result.get('num_results', 0)}")
        if result.get('similarity_score'):
            print(f"🎯 Similarity: {result['similarity_score']:.3f}")
        print(f"\nAnswer:\n{result.get('text', '')[:300]}...")


if __name__ == "__main__":
    asyncio.run(test_rag_agent())
