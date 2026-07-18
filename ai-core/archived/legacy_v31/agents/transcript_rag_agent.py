"""
Optimized Transcript RAG Agent for Vector Search

This agent queries the optimized TranscriptQA collection with:
- Simplified schema (question, answer, keywords, topic)
- Better vector search performance
- More generalizable Q&A pairs
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urlparse

# Add src to path for utils import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.weaviate_client import get_weaviate_client
import weaviate.classes as wvc

# Load .env file from project root
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Use centralized client factory
client = get_weaviate_client()

# ALLOWLIST: Only trust these domains for verified content
ALLOWED_SOURCE_DOMAINS = {
    "www.lib.miamioh.edu",
    "lib.miamioh.edu",
    "libguides.lib.miamioh.edu",
    "muohio.libcal.com"
}


def _is_verified_result(result: Dict[str, Any]) -> bool:
    """
    Check if a RAG result meets verification requirements.
    
    Requirements for verified result:
    1. verified field must be True
    2. source_url must be present and non-empty
    3. evidence_quote must be present and non-empty
    4. source_domain must be in ALLOWED_SOURCE_DOMAINS
    
    Args:
        result: Result dict with properties from Weaviate
    
    Returns:
        True if result is verified and trustworthy, False otherwise
    """
    # Check verified flag
    if not result.get('verified', False):
        return False
    
    # Check required fields
    source_url = result.get('source_url', '').strip()
    evidence_quote = result.get('evidence_quote', '').strip()
    source_domain = result.get('source_domain', '').strip()
    
    if not source_url or not evidence_quote:
        return False
    
    # Check domain allowlist
    if source_domain not in ALLOWED_SOURCE_DOMAINS:
        return False
    
    return True


def make_transcript_rag_item(
    question: str,
    answer: str,
    topic: str = "policy_or_service",
    keywords: list = None,
    verified: bool = False,
    source_url: Optional[str] = None,
    evidence_quote: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a properly formatted transcript RAG item with verification metadata.
    
    IMPORTANT: If verified=True, source_url and evidence_quote are REQUIRED.
    
    Args:
        question: The question text
        answer: The answer text
        topic: Topic category (default: "policy_or_service")
        keywords: List of keywords (default: [])
        verified: Whether this is verified against official sources (default: False)
        source_url: Official source URL (REQUIRED if verified=True)
        evidence_quote: 1-3 sentence quote from source (REQUIRED if verified=True)
    
    Returns:
        Dict ready for Weaviate insertion
    
    Raises:
        ValueError: If verified=True but source_url or evidence_quote missing
    """
    # Validation for verified items
    if verified:
        if not source_url or not source_url.strip():
            raise ValueError("source_url is REQUIRED when verified=True")
        if not evidence_quote or not evidence_quote.strip():
            raise ValueError("evidence_quote is REQUIRED when verified=True")
        
        # Extract and validate domain
        parsed = urlparse(source_url)
        source_domain = parsed.netloc.lower()
        
        if source_domain not in ALLOWED_SOURCE_DOMAINS:
            raise ValueError(
                f"source_domain '{source_domain}' not in allowlist. "
                f"Allowed: {ALLOWED_SOURCE_DOMAINS}"
            )
    else:
        source_domain = None
    
    return {
        "question": question,
        "answer": answer,
        "topic": topic,
        "keywords": keywords or [],
        "verified": verified,
        "source_url": source_url or "",
        "evidence_quote": evidence_quote or "",
        "source_domain": source_domain or "",
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

# Embeddings instance for transcript RAG queries (BYOV - Bring Your Own Vectors)
_transcript_embeddings = None

def _get_transcript_embeddings():
    """Lazy-init embeddings for transcript RAG."""
    global _transcript_embeddings
    if _transcript_embeddings is None:
        from langchain_openai import OpenAIEmbeddings
        _transcript_embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=os.getenv("OPENAI_API_KEY", "")
        )
    return _transcript_embeddings


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
    # Pre-compute embedding async (Weaviate has no built-in vectorizer)
    try:
        emb = _get_transcript_embeddings()
        query_vector = await emb.aembed_query(query)
    except Exception as e:
        return {
            "source": "TranscriptRAG",
            "success": False,
            "error": f"Embedding error: {str(e)}",
            "text": "Knowledge base is not available. Please contact a librarian for assistance."
        }

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
            
            # Build query parameters using near_vector (BYOV - no Weaviate vectorizer)
            query_params = {
                "near_vector": query_vector,
                "limit": 5,  # Get top 5 results for better selection
                "return_metadata": ['distance']
            }
            
            # Add topic filter if specified
            if topic_filter:
                query_params["filters"] = wvc.query.Filter.by_property("topic").equal(topic_filter)
            
            # Execute semantic search
            response = collection.query.near_vector(**query_params)
            
            if not response.objects:
                return {
                    "source": "TranscriptRAG",
                    "success": True,
                    "text": "I don't have a confident answer from our knowledge base. Let me connect you with a librarian who can help.",
                    "needs_human": True,
                    "confidence": "none"
                }
            
            # Score results based on distance (lower is better)
            # CRITICAL: Filter out unverified results
            results = []
            verified_results = []
            unverified_results = []
            
            for obj in response.objects:
                props = obj.properties
                distance = obj.metadata.distance
                
                # Convert distance to similarity score (0-1, higher is better)
                similarity = 1 - distance
                
                result_dict = {
                    'question': props.get('question', ''),
                    'answer': props.get('answer', ''),
                    'topic': props.get('topic', ''),
                    'keywords': props.get('keywords', []),
                    'similarity': similarity,
                    'distance': distance,
                    'weaviate_id': str(obj.uuid),
                    # Verification metadata
                    'verified': props.get('verified', False),
                    'source_url': props.get('source_url', ''),
                    'evidence_quote': props.get('evidence_quote', ''),
                    'source_domain': props.get('source_domain', '')
                }
                
                # Separate verified from unverified
                if _is_verified_result(result_dict):
                    verified_results.append(result_dict)
                else:
                    unverified_results.append(result_dict)
            
            # PRIORITY: Use verified results if available, otherwise use unverified
            if verified_results:
                results = verified_results
                if log_callback:
                    log_callback(f"✅ [Transcript RAG] Found {len(verified_results)} VERIFIED results (filtered out {len(unverified_results)} unverified)")
            else:
                results = unverified_results
                if log_callback:
                    log_callback(f"⚠️ [Transcript RAG] No verified results found, using {len(unverified_results)} UNVERIFIED results")
            
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
            
            # Include verification status in response
            has_verified = len(verified_results) > 0
            
            return {
                "source": "TranscriptRAG",
                "success": True,
                "text": text,
                "confidence": confidence,
                "matched_topic": results[0]['topic'],
                "num_results": len(results),
                "top_keywords": results[0]['keywords'][:5],
                "similarity_score": top_similarity,
                "weaviate_ids": [r['weaviate_id'] for r in results],
                # VERIFICATION METADATA
                "has_verified_results": has_verified,
                "verified_count": len(verified_results),
                "unverified_count": len(unverified_results),
                "top_result_verified": results[0].get('verified', False),
                "top_result_source_url": results[0].get('source_url', ''),
                "top_result_evidence": results[0].get('evidence_quote', '')
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
