"""Transcript RAG Agent for answering from historical chat logs using Weaviate."""
import os
import weaviate
import weaviate.classes as wvc
import asyncio
from typing import Dict, Any

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def _make_client():
    """Create Weaviate v4 client with cloud auth."""
    if not WEAVIATE_HOST or not WEAVIATE_API_KEY:
        return None
    
    try:
        # Weaviate v4 API
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

async def transcript_rag_query(query: str, log_callback=None) -> Dict[str, Any]:
    """Query Weaviate for similar Q&A from chat transcripts."""
    def _search():
        if log_callback:
            log_callback("🔮 [Transcript RAG Agent] Querying knowledge base")
        
        if not client:
            return {
                "source": "TranscriptRAG",
                "success": False,
                "error": "Weaviate not configured",
                "text": "Knowledge base is not available. Please contact a librarian for assistance."
            }
        
        try:
            # Weaviate v4 collection-based API
            collection = client.collections.get("TranscriptQA")
            
            response = collection.query.near_text(
                query=query,
                limit=3,
                return_metadata=wvc.query.MetadataQuery(distance=True)
            )
            
            if not response.objects:
                return {
                    "source": "TranscriptRAG",
                    "success": True,
                    "text": "I don't have a confident answer from our knowledge base. Let me connect you with a librarian.",
                    "needs_human": True
                }
            
            answers = []
            for obj in response.objects:
                props = obj.properties
                q = props.get("question", "")
                a = props.get("answer", "")
                if a:
                    answers.append(f"**Q:** {q}\n**A:** {a}")
            
            return {
                "source": "TranscriptRAG",
                "success": True,
                "text": "Based on similar questions:\n\n" + "\n\n".join(answers),
                "confidence": "medium" if len(response.objects) < 2 else "high"
            }
        except Exception as e:
            return {
                "source": "TranscriptRAG",
                "success": False,
                "error": str(e),
                "text": f"Knowledge base unavailable: {str(e)}"
            }
    
    return await asyncio.to_thread(_search)
