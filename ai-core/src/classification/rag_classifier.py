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

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=OPENAI_API_KEY
)


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
            
            # Always prefer cloud if API key is present
            # if api_key and host != "localhost":
            if api_key and scheme == "https":
                # Connect to cloud Weaviate
                cluster_url = f"https://{host}" if not host.startswith("http") else host
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=cluster_url,
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
        logger = None,
        margin_threshold: float = 0.15,
        use_llm_fallback: bool = True
    ) -> Dict[str, Any]:
        """
        Classify a question using RAG-based semantic search with margin-based LLM fallback.
        
        Args:
            user_question: The user's question
            conversation_history: Previous conversation for context
            logger: Optional logger
            margin_threshold: Minimum margin between top-1 and top-2 scores (default: 0.15)
            use_llm_fallback: Whether to use LLM when margin is low (default: True)
            
        Returns:
            Dict with:
            - category: Predicted category
            - confidence: Confidence score (0-1)
            - agent: Agent to handle this
            - needs_clarification: Whether clarification is needed
            - clarification_question: Question to ask user
            - similar_examples: Top matching examples
            - margin: Confidence margin between top-1 and top-2 (if applicable)
            - llm_decision: Whether LLM was used for final decision
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
                "similar_examples": [],
                "llm_decision": False
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
                    logger.log(f"🚫 [RAG Classifier] Top match is out-of-scope: {top_category} (confidence: {float(confidence):.2f})")
                
                return {
                    "category": top_category,
                    "confidence": confidence,
                    "agent": get_category_agent(top_category),
                    "needs_clarification": False,
                    "similar_examples": [m["question"] for m in top_matches[:3]],
                    "llm_decision": False
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
                "similar_examples": [m["question"] for m in top_matches[:3]],
                "llm_decision": False
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
                "similar_examples": [m["question"] for m in top_matches[:3]],
                "llm_decision": False
            }
        
        # ============================================================================
        # MARGIN-BASED LLM FALLBACK
        # ============================================================================
        # Calculate margin between top-1 and top-2 categories
        # If margin is too small, use LLM to make final decision
        
        margin = None
        second_category = None
        
        if len(sorted_categories) > 1:
            second_category, second_score = sorted_categories[1]
            margin = (top_score - second_score) / top_score  # Normalized margin
            
            # Convert to float for safe formatting (handles Decimal types)
            margin = float(margin) if margin is not None else 0.0
            top_score_float = float(top_score)
            second_score_float = float(second_score)
            
            if logger:
                logger.log(f"📊 [RAG Classifier] Top-1: {top_category} ({top_score_float:.3f}) | Top-2: {second_category} ({second_score_float:.3f}) | Margin: {margin:.3f}")
            
            # If margin is below threshold, use LLM to decide
            if use_llm_fallback and margin < margin_threshold:
                if logger:
                    logger.log(f"🤖 [RAG Classifier] Low margin ({margin:.3f} < {margin_threshold}) - using LLM fallback")
                
                llm_result = await self._llm_classify(
                    user_question,
                    sorted_categories[:2],
                    top_matches,
                    logger
                )
                
                return {
                    "category": llm_result["category"],
                    "confidence": llm_result["confidence"],
                    "agent": get_category_agent(llm_result["category"]),
                    "needs_clarification": False,
                    "similar_examples": [m["question"] for m in top_matches[:3]],
                    "margin": margin,
                    "llm_decision": True,
                    "llm_reasoning": llm_result.get("reasoning", ""),
                    "alternative_category": second_category
                }
        
        # Check for ambiguity requiring clarification (legacy behavior)
        if len(sorted_categories) > 1:
            second_score = sorted_categories[1][1]
            score_diff = top_score - second_score
            
            if score_diff < 0.3:
                if logger:
                    logger.log(f"⚠️ [RAG Classifier] Ambiguous: {top_category} ({float(top_score):.2f}) vs {sorted_categories[1][0]} ({float(second_score):.2f})")
                
                clarification_data = await self._generate_clarification_choices(
                    user_question,
                    [sorted_categories[0][0], sorted_categories[1][0]],
                    top_matches
                )
                
                return {
                    "category": top_category,
                    "confidence": confidence,
                    "agent": get_category_agent(top_category),
                    "needs_clarification": True,
                    "clarification_choices": clarification_data,
                    "similar_examples": [m["question"] for m in top_matches[:3]],
                    "alternative_categories": [c[0] for c in sorted_categories[:2]],
                    "margin": margin,
                    "llm_decision": False
                }
        
        boundary_match = self._check_boundary_cases(user_question)
        if boundary_match:
            if logger:
                logger.log(f"⚠️ [RAG Classifier] Boundary case detected")
            
            # Generate choices for boundary case
            clarification_data = await self._generate_clarification_choices(
                user_question,
                boundary_match["possible_categories"],
                top_matches
            )
            
            return {
                "category": top_category,
                "confidence": confidence,
                "agent": get_category_agent(top_category),
                "needs_clarification": True,
                "clarification_choices": clarification_data,
                "similar_examples": [m["question"] for m in top_matches[:3]],
                "alternative_categories": boundary_match["possible_categories"],
                "margin": margin,
                "llm_decision": False
            }
        
        if logger:
            margin_str = f"{float(margin):.3f}" if margin is not None else "N/A"
            logger.log(f"✅ [RAG Classifier] Classified as: {top_category} (confidence: {float(confidence):.2f}, margin: {margin_str})")
        
        return {
            "category": top_category,
            "confidence": confidence,
            "agent": get_category_agent(top_category),
            "needs_clarification": False,
            "similar_examples": [m["question"] for m in top_matches[:3]],
            "margin": margin,
            "llm_decision": False
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
    
    async def _llm_classify(
        self,
        user_question: str,
        top_categories: List[Tuple[str, float]],
        similar_examples: List[Dict],
        logger = None
    ) -> Dict[str, Any]:
        """
        Use LLM to classify when margin between top categories is too small.
        
        Args:
            user_question: The user's question
            top_categories: List of (category_name, score) tuples for top 2 categories
            similar_examples: Top matching examples from vector search
            logger: Optional logger
            
        Returns:
            Dict with category, confidence, and reasoning
        """
        category1, score1 = top_categories[0]
        category2, score2 = top_categories[1]
        
        # Get descriptions and examples for both categories
        desc1 = get_category_description(category1)
        desc2 = get_category_description(category2)
        
        # Get relevant examples for each category
        examples1 = [ex["question"] for ex in similar_examples if ex["category"] == category1][:3]
        examples2 = [ex["question"] for ex in similar_examples if ex["category"] == category2][:3]
        
        examples1_text = "\n".join([f"  - {ex}" for ex in examples1]) if examples1 else "  (no examples)"
        examples2_text = "\n".join([f"  - {ex}" for ex in examples2]) if examples2 else "  (no examples)"
        
        prompt = f"""You are a question classifier for Miami University Libraries.

User's question: "{user_question}"

The semantic search found two very similar categories:

**Category 1: {category1}**
Description: {desc1}
Score: {score1:.3f}
Example questions:
{examples1_text}

**Category 2: {category2}**
Description: {desc2}
Score: {score2:.3f}
Example questions:
{examples2_text}

Based on the user's question and the category descriptions, which category is the BEST fit?

Respond in this exact format:
CATEGORY: [category1 or category2]
CONFIDENCE: [0.0-1.0]
REASONING: [brief explanation of why this category is the best fit]

Be decisive. Choose the category that best matches the user's intent."""

        messages = [
            SystemMessage(content="You are an expert question classifier for a university library system."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # Parse the response
            lines = content.split("\n")
            result = {
                "category": category1,  # Default to top category
                "confidence": 0.7,
                "reasoning": "LLM classification"
            }
            
            for line in lines:
                if line.startswith("CATEGORY:"):
                    chosen = line.replace("CATEGORY:", "").strip()
                    if category1.lower() in chosen.lower():
                        result["category"] = category1
                    elif category2.lower() in chosen.lower():
                        result["category"] = category2
                elif line.startswith("CONFIDENCE:"):
                    try:
                        conf = float(line.replace("CONFIDENCE:", "").strip())
                        result["confidence"] = max(0.0, min(1.0, conf))
                    except:
                        pass
                elif line.startswith("REASONING:"):
                    result["reasoning"] = line.replace("REASONING:", "").strip()
            
            if logger:
                logger.log(f"🤖 [LLM Classifier] Chose: {result['category']} (confidence: {float(result['confidence']):.2f})")
                logger.log(f"   Reasoning: {result['reasoning']}")
            
            return result
            
        except Exception as e:
            if logger:
                logger.log(f"⚠️ [LLM Classifier] Error: {str(e)} - defaulting to top category")
            return {
                "category": category1,
                "confidence": 0.7,
                "reasoning": f"LLM error, defaulted to top category"
            }
    
    async def _generate_clarification_choices(
        self,
        user_question: str,
        ambiguous_categories: List[str],
        similar_examples: List[Dict]
    ) -> Dict[str, Any]:
        """Generate structured clarification choices when categories are ambiguous.
        
        Returns:
            Dict with:
                - prompt: Brief question text
                - choices: List of choice objects with id, label, description, category
        """
        # Get descriptions and examples for ambiguous categories
        choices = []
        
        for i, cat in enumerate(ambiguous_categories[:3]):  # Max 3 choices + "None of the above"
            desc = get_category_description(cat)
            examples = [ex["question"] for ex in similar_examples if ex["category"] == cat][:2]
            
            # Generate a user-friendly label
            label = self._generate_choice_label(cat, examples)
            
            choices.append({
                "id": f"choice_{i}",
                "label": label,
                "description": desc[:100] + "..." if len(desc) > 100 else desc,
                "category": cat,
                "examples": examples
            })
        
        # Add "None of the above" option
        choices.append({
            "id": "choice_none",
            "label": "None of the above",
            "description": "My question is about something else",
            "category": "none_of_above",
            "examples": []
        })
        
        # Generate a brief prompt
        prompt = "I want to make sure I understand your question correctly. Which of these best describes what you're looking for?"
        
        return {
            "prompt": prompt,
            "choices": choices,
            "original_question": user_question
        }
    
    def _generate_choice_label(self, category: str, examples: List[str]) -> str:
        """Generate a user-friendly label for a category choice."""
        # Map category names to user-friendly labels
        label_map = {
            "library_equipment_checkout": "Borrow equipment (laptops, chargers, etc.)",
            "library_hours_rooms": "Library hours or room reservations",
            "subject_librarian_guides": "Find a subject librarian or research guide",
            "research_help_handoff": "Get research help from a librarian",
            "library_policies_services": "Library policies or services",
            "human_librarian_request": "Talk to a librarian",
        }
        
        # Return mapped label or use first example as label
        if category in label_map:
            return label_map[category]
        elif examples:
            return examples[0]
        else:
            # Fallback: convert category name to readable format
            return category.replace("_", " ").title()

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
