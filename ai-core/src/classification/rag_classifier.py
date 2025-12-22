"""
RAG-Based Question Classifier

Uses semantic similarity search with a vector store to classify questions
instead of hardcoded regex patterns. This provides better handling of:
- Nuanced questions
- Ambiguous queries
- Context-aware classification
- Natural language variations

Architecture:
1. Embed category examples into vector store (Weaviate)
2. For incoming question, search for similar examples
3. Use similarity scores + LLM to determine category
4. Request clarification for ambiguous cases
"""

import os
import weaviate
import weaviate.classes as wvc
from typing import Dict, List, Any, Optional, Tuple
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage

from src.classification.category_examples import (
    get_all_examples_for_embedding,
    get_boundary_cases,
    get_category_description,
    get_category_agent,
    ALL_CATEGORIES
)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_SCHEME = os.getenv("WEAVIATE_SCHEME", "http")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY", "")

llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
llm = ChatOpenAI(**llm_kwargs)

embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)


class RAGQuestionClassifier:
    """RAG-based question classifier using semantic similarity."""
    
    def __init__(self):
        """Initialize classifier with Weaviate connection."""
        self.client = None
        self.collection_name = "QuestionCategory"
        self.embeddings = embeddings
        self.llm = llm
    
    def _connect(self):
        """Connect to Weaviate if not already connected."""
        if self.client is None:
            # Read env vars at connection time, not module load time
            scheme = os.getenv("WEAVIATE_SCHEME", "http")
            api_key = os.getenv("WEAVIATE_API_KEY", "")
            host = os.getenv("WEAVIATE_HOST", "localhost")
            
            if scheme == "https" and api_key:
                # Connect to cloud Weaviate
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=f"https://{host}",
                    auth_credentials=weaviate.auth.AuthApiKey(api_key)
                )
            else:
                # Connect to local Weaviate
                self.client = weaviate.connect_to_local()
    
    def _disconnect(self):
        """Disconnect from Weaviate."""
        if self.client is not None:
            try:
                self.client.close()
            except:
                pass
            self.client = None
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self._disconnect()
        
    def _ensure_collection(self):
        """Ensure Weaviate collection exists for question categories."""
        self._connect()
        
        if not self.client.collections.exists(self.collection_name):
            self.client.collections.create(
                name=self.collection_name,
                description="Question category examples for classification",
                vectorizer_config=wvc.config.Configure.Vectorizer.none(),
                properties=[
                    wvc.config.Property(name="category", data_type=wvc.config.DataType.TEXT, description="Category name"),
                    wvc.config.Property(name="question", data_type=wvc.config.DataType.TEXT, description="Example question"),
                    wvc.config.Property(name="is_in_scope", data_type=wvc.config.DataType.BOOL, description="Whether this is an in-scope example"),
                    wvc.config.Property(name="description", data_type=wvc.config.DataType.TEXT, description="Category description"),
                    wvc.config.Property(name="agent", data_type=wvc.config.DataType.TEXT, description="Agent to handle this category"),
                    wvc.config.Property(name="keywords", data_type=wvc.config.DataType.TEXT_ARRAY, description="Keywords for hybrid search"),
                ]
            )
    
    async def initialize_vector_store(self, force_refresh: bool = False):
        """
        Initialize vector store with category examples.
        
        Args:
            force_refresh: If True, delete and recreate the collection
        """
        self._connect()
        
        if force_refresh:
            try:
                self.client.collections.delete(self.collection_name)
            except Exception:
                pass
        
        self._ensure_collection()
        
        collection = self.client.collections.get(self.collection_name)
        
        # Check if collection already has data
        try:
            count = len(collection)
            if count > 0 and not force_refresh:
                return
        except:
            pass
        
        examples = get_all_examples_for_embedding()
        
        # Batch insert using v4 API
        with collection.batch.dynamic() as batch:
            for example in examples:
                question_text = example["question"]
                embedding = await self._embed_text(question_text)
                
                properties = {
                    "category": example["category"],
                    "question": question_text,
                    "is_in_scope": example["is_in_scope"],
                    "description": example["description"],
                    "agent": example["agent"],
                    "keywords": example["keywords"],
                }
                
                batch.add_object(
                    properties=properties,
                    vector=embedding
                )
    
    async def _embed_text(self, text: str) -> List[float]:
        """Embed text using OpenAI embeddings."""
        result = await self.embeddings.aembed_query(text)
        return result
    
    async def classify_question(
        self, 
        user_question: str,
        conversation_history: Optional[List[Dict]] = None,
        logger = None
    ) -> Dict[str, Any]:
        """
        Classify a question using RAG-based semantic search.
        
        Args:
            user_question: The user's question
            conversation_history: Previous conversation for context
            logger: Optional logger
            
        Returns:
            Dict with:
            - category: Predicted category
            - confidence: Confidence score (0-1)
            - agent: Agent to handle this
            - needs_clarification: Whether clarification is needed
            - clarification_question: Question to ask user
            - similar_examples: Top matching examples
        """
        self._connect()
        
        if logger:
            logger.log(f"🔍 [RAG Classifier] Classifying: {user_question}")
        
        question_embedding = await self._embed_text(user_question)
        
        collection = self.client.collections.get(self.collection_name)
        
        response = collection.query.near_vector(
            near_vector=question_embedding,
            limit=10,
            return_metadata=wvc.query.MetadataQuery(distance=True, certainty=True)
        )
        
        matches = []
        for obj in response.objects:
            matches.append({
                "category": obj.properties["category"],
                "question": obj.properties["question"],
                "is_in_scope": obj.properties["is_in_scope"],
                "description": obj.properties["description"],
                "agent": obj.properties["agent"],
                "keywords": obj.properties.get("keywords", []),
                "_additional": {
                    "certainty": obj.metadata.certainty if obj.metadata.certainty else 0.0,
                    "distance": obj.metadata.distance if obj.metadata.distance else 1.0
                }
            })
        
        if not matches:
            if logger:
                logger.log("⚠️ [RAG Classifier] No matches found, defaulting to general_question")
            return {
                "category": "general_question",
                "confidence": 0.0,
                "agent": "general_question",
                "needs_clarification": False,
                "similar_examples": []
            }
        
        top_matches = matches[:5]
        
        # CRITICAL: Check if TOP match is out-of-scope FIRST
        # Out-of-scope questions should NEVER trigger clarification, even if there are in-scope alternatives
        if top_matches:
            top_match = top_matches[0]
            if not top_match["is_in_scope"]:
                top_category = top_match["category"]
                confidence = top_match["_additional"]["certainty"]
                
                if logger:
                    logger.log(f"🚫 [RAG Classifier] Top match is out-of-scope: {top_category} (confidence: {confidence:.2f})")
                
                return {
                    "category": top_category,
                    "confidence": confidence,
                    "agent": get_category_agent(top_category),
                    "needs_clarification": False,
                    "similar_examples": [m["question"] for m in top_matches[:3]]
                }
        
        # Build category scores from in-scope matches only
        category_scores = {}
        for match in top_matches:
            category = match["category"]
            certainty = match["_additional"]["certainty"]
            is_in_scope = match["is_in_scope"]
            
            if is_in_scope:
                category_scores[category] = category_scores.get(category, 0) + certainty
        
        if not category_scores:
            if logger:
                logger.log("⚠️ [RAG Classifier] No in-scope matches found")
            return {
                "category": "out_of_scope",
                "confidence": 0.8,
                "agent": "out_of_scope",
                "needs_clarification": False,
                "similar_examples": [m["question"] for m in top_matches[:3]]
            }
        
        sorted_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        top_category, top_score = sorted_categories[0]
        
        confidence = top_score / len(top_matches)
        
        # CRITICAL: Out-of-scope categories should NEVER trigger clarification
        # They should always be directly rejected with appropriate redirect
        is_out_of_scope = top_category.startswith("out_of_scope_")
        
        if is_out_of_scope:
            if logger:
                logger.log(f"🚫 [RAG Classifier] Out-of-scope category detected: {top_category} - skipping clarification")
            return {
                "category": top_category,
                "confidence": confidence,
                "agent": get_category_agent(top_category),
                "needs_clarification": False,
                "similar_examples": [m["question"] for m in top_matches[:3]]
            }
        
        # Only check ambiguity and boundary cases for IN-SCOPE questions
        if len(sorted_categories) > 1:
            second_score = sorted_categories[1][1]
            score_diff = top_score - second_score
            
            if score_diff < 0.3:
                if logger:
                    logger.log(f"⚠️ [RAG Classifier] Ambiguous: {top_category} ({top_score:.2f}) vs {sorted_categories[1][0]} ({second_score:.2f})")
                
                clarification = await self._generate_clarification(
                    user_question,
                    [sorted_categories[0][0], sorted_categories[1][0]],
                    top_matches
                )
                
                return {
                    "category": top_category,
                    "confidence": confidence,
                    "agent": get_category_agent(top_category),
                    "needs_clarification": True,
                    "clarification_question": clarification,
                    "similar_examples": [m["question"] for m in top_matches[:3]],
                    "alternative_categories": [c[0] for c in sorted_categories[:2]]
                }
        
        boundary_match = self._check_boundary_cases(user_question)
        if boundary_match:
            if logger:
                logger.log(f"⚠️ [RAG Classifier] Boundary case detected")
            return {
                "category": top_category,
                "confidence": confidence,
                "agent": get_category_agent(top_category),
                "needs_clarification": True,
                "clarification_question": boundary_match["clarification_needed"],
                "similar_examples": [m["question"] for m in top_matches[:3]],
                "alternative_categories": boundary_match["possible_categories"]
            }
        
        if logger:
            logger.log(f"✅ [RAG Classifier] Classified as: {top_category} (confidence: {confidence:.2f})")
        
        return {
            "category": top_category,
            "confidence": confidence,
            "agent": get_category_agent(top_category),
            "needs_clarification": False,
            "similar_examples": [m["question"] for m in top_matches[:3]]
        }
    
    def _check_boundary_cases(self, user_question: str) -> Optional[Dict[str, Any]]:
        """Check if question matches known boundary cases."""
        boundary_cases = get_boundary_cases()
        user_lower = user_question.lower()
        
        for case in boundary_cases:
            case_lower = case["question"].lower()
            
            if self._fuzzy_match(user_lower, case_lower):
                return case
        
        return None
    
    def _fuzzy_match(self, text1: str, text2: str, threshold: float = 0.6) -> bool:
        """Simple fuzzy matching based on word overlap."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return False
        
        overlap = len(words1 & words2)
        similarity = overlap / max(len(words1), len(words2))
        
        return similarity >= threshold
    
    async def _generate_clarification(
        self,
        user_question: str,
        possible_categories: List[str],
        similar_examples: List[Dict]
    ) -> str:
        """Generate a clarification question using LLM."""
        
        category_descriptions = "\n".join([
            f"- {cat}: {get_category_description(cat)}"
            for cat in possible_categories
        ])
        
        examples_text = "\n".join([
            f"- {ex['question']} (category: {ex['category']})"
            for ex in similar_examples[:3]
        ])
        
        prompt = f"""The user asked: "{user_question}"

This question is ambiguous and could belong to multiple categories:
{category_descriptions}

Similar questions we've seen:
{examples_text}

Generate a brief, friendly clarification question to help determine which category this belongs to.
The clarification should offer 2-3 specific options for the user to choose from.

Example format:
"I can help with that! Just to clarify, are you asking about:
1) [Option 1]
2) [Option 2]"

Generate the clarification question:"""

        messages = [
            SystemMessage(content="You are a helpful assistant that generates clarification questions."),
            HumanMessage(content=prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        return response.content.strip()


# Global classifier instance to reuse cloud Weaviate connection
_classifier_instance = None

async def classify_with_rag(
    user_question: str,
    conversation_history: Optional[List[Dict]] = None,
    logger = None
) -> Dict[str, Any]:
    """
    Convenience function to classify a question using RAG.
    
    Args:
        user_question: The user's question
        conversation_history: Previous conversation for context
        logger: Optional logger
        
    Returns:
        Classification result dictionary
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = RAGQuestionClassifier()
    return await _classifier_instance.classify_question(user_question, conversation_history, logger)
