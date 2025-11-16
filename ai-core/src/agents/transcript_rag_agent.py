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

async def transcript_rag_query(query: str, log_callback=None, filters=None) -> Dict[str, Any]:
    """Query Weaviate for similar Q&A from chat transcripts with enhanced filtering and ranking."""
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
            
            # Build filter conditions (prioritize high-quality answers)
            where_filter = None
            if filters:
                # Filter by minimum rating
                if filters.get('min_rating'):
                    where_filter = wvc.query.Filter.by_property('rating').greater_or_equal(filters['min_rating'])
                
                # Filter by topic
                if filters.get('topic'):
                    topic_filter = wvc.query.Filter.by_property('topic').equal(filters['topic'])
                    where_filter = where_filter & topic_filter if where_filter else topic_filter
            else:
                # Default: only use answers with rating >= 2
                where_filter = wvc.query.Filter.by_property('rating').greater_or_equal(2)
            
            # Query with more results for re-ranking
            response = collection.query.near_text(
                query=query,
                limit=5,  # Get more results for better selection
                where=where_filter,
                return_metadata=wvc.query.MetadataQuery(distance=True)
            )
            
            if not response.objects:
                # Try again without filters if no results
                if where_filter:
                    response = collection.query.near_text(
                        query=query,
                        limit=5,
                        return_metadata=wvc.query.MetadataQuery(distance=True)
                    )
                
                if not response.objects:
                    return {
                        "source": "TranscriptRAG",
                        "success": True,
                        "text": "I don't have a confident answer from our knowledge base. Let me connect you with a librarian.",
                        "needs_human": True
                    }
            
            # Re-rank results by combining distance and quality scores
            scored_results = []
            for obj in response.objects:
                props = obj.properties
                distance = obj.metadata.distance
                confidence = props.get('confidence_score', 0.5)
                rating = props.get('rating', 0)
                
                # Combined score: 60% semantic similarity + 30% confidence + 10% rating
                combined_score = (1 - distance) * 0.6 + confidence * 0.3 + (rating / 4.0) * 0.1
                
                scored_results.append({
                    'question': props.get('question', ''),
                    'answer': props.get('answer', ''),
                    'topic': props.get('topic', ''),
                    'rating': rating,
                    'confidence_score': confidence,
                    'distance': distance,
                    'combined_score': combined_score
                })
            
            # Sort by combined score
            scored_results.sort(key=lambda x: x['combined_score'], reverse=True)
            
            # Take top 3 results
            top_results = scored_results[:3]
            
            # Format output
            answers = []
            for result in top_results:
                answers.append(f"**Q:** {result['question']}\n**A:** {result['answer']}")
            
            # Determine overall confidence
            best_score = top_results[0]['combined_score']
            if best_score >= 0.8:
                overall_confidence = "high"
            elif best_score >= 0.6:
                overall_confidence = "medium"
            else:
                overall_confidence = "low"
            
            return {
                "source": "TranscriptRAG",
                "success": True,
                "text": "Based on similar questions from our knowledge base:\n\n" + "\n\n".join(answers),
                "confidence": overall_confidence,
                "matched_topic": top_results[0]['topic'],
                "num_results": len(top_results)
            }
        except Exception as e:
            return {
                "source": "TranscriptRAG",
                "success": False,
                "error": str(e),
                "text": f"Knowledge base unavailable: {str(e)}"
            }
    
    return await asyncio.to_thread(_search)
