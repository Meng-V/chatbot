"""
Category Classifier (Pure RAG-based)

This module ONLY classifies NormalizedIntent into categories.
It does NOT:
- Choose agents (that's done by category_to_agent_map)
- Answer questions (that's done by agents)
- Handle clarifications (that's done by orchestrator)

It ONLY:
- Takes NormalizedIntent
- Uses RAG embeddings against category_examples
- Returns CategoryClassification
"""

from typing import Dict, Any
from src.state import AgentState
from src.models.intent import NormalizedIntent, CategoryClassification
from src.classification.rag_classifier import classify_with_rag

# Confidence thresholds
CONFIDENCE_THRESHOLD_IN_SCOPE = 0.45  # For in-scope categories
CONFIDENCE_THRESHOLD_OUT_OF_SCOPE = 0.45  # For out-of-scope categories (lower threshold)


async def classify_category(
    normalized_intent: NormalizedIntent,
    logger=None
) -> CategoryClassification:
    """
    Pure category classification function.
    
    Takes NormalizedIntent and returns CategoryClassification.
    Does NOT choose agents or answer questions.
    
    Args:
        normalized_intent: Normalized intent from intent normalization layer
        logger: Optional AgentLogger instance
        
    Returns:
        CategoryClassification: Category classification result
    """
    if logger and hasattr(logger, 'log'):
        logger.log(f"🎯 [Category Classifier] Classifying intent: {normalized_intent.intent_summary}")
    
    # Use the intent summary for classification
    classification = await classify_with_rag(
        user_question=normalized_intent.intent_summary,
        conversation_history=[],  # Intent already has context
        logger=logger
    )
    
    category = classification["category"]
    
    # Robust confidence handling
    raw_conf = classification.get("confidence")
    confidence = float(raw_conf) if raw_conf is not None else 0.0
    
    is_out_of_scope = (category == "out_of_scope") or category.startswith("out_of_scope_")
    
    # Determine if clarification is needed based on differentiated thresholds
    threshold = CONFIDENCE_THRESHOLD_OUT_OF_SCOPE if is_out_of_scope else CONFIDENCE_THRESHOLD_IN_SCOPE
    
    needs_clarification = False
    clarification_reason = None
    
    if raw_conf is None:
        # Missing confidence from classifier
        needs_clarification = True
        clarification_reason = "Missing confidence from classifier"
    elif normalized_intent.ambiguity:
        # Intent normalizer flagged ambiguity
        needs_clarification = True
        clarification_reason = normalized_intent.ambiguity_reason
    elif confidence < threshold:
        # Low confidence for this category type
        needs_clarification = True
        clarification_reason = f"Low confidence ({confidence:.2f} < {threshold:.2f}) for category: {category}"
    
    if logger and hasattr(logger, 'log'):
        logger.log(f"✅ [Category Classifier] Category: {category}, Confidence: {confidence:.2f}, Needs clarification: {needs_clarification}")
    
    return CategoryClassification(
        category=category,
        confidence=confidence,
        is_out_of_scope=is_out_of_scope,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason
    )


async def rag_router_node(state: AgentState) -> AgentState:
    """
    DEPRECATED: Legacy router node for backward compatibility.
    
    New code should use the two-step process:
    1. normalize_intent() -> NormalizedIntent
    2. classify_category() -> CategoryClassification
    
    This node is kept for gradual migration only.
    """
    user_msg = state.get("processed_query") or state["user_message"]
    logger = state.get("_logger")
    history = state.get("conversation_history", [])
    
    if logger:
        logger.log("⚠️ [RAG Router] Using legacy router node - should migrate to two-step process")
    
    # Run RAG classification
    classification = await classify_with_rag(
        user_question=user_msg,
        conversation_history=history,
        logger=logger
    )
    
    category = classification["category"]
    confidence = float(classification["confidence"])
    needs_clarification = classification.get("needs_clarification", False)
    
    # Store classification metadata
    state["classified_intent"] = category
    state["classification_confidence"] = confidence
    state["classification_result"] = classification
    
    # DIFFERENTIATED THRESHOLD POLICY
    is_out_of_scope_category = (category == "out_of_scope") or category.startswith("out_of_scope_")
    threshold = CONFIDENCE_THRESHOLD_OUT_OF_SCOPE if is_out_of_scope_category else CONFIDENCE_THRESHOLD_IN_SCOPE
    
    if is_out_of_scope_category and confidence >= CONFIDENCE_THRESHOLD_OUT_OF_SCOPE:
        # Out-of-scope with moderate confidence - route directly
        if logger:
            logger.log(f"🚫 [RAG Router] Out-of-scope with moderate confidence ({confidence:.2f}) - routing directly")
    elif needs_clarification or confidence < threshold:
        if logger:
            reason = "RAG classifier flagged ambiguity" if needs_clarification else f"Low confidence ({confidence:.2f} < {threshold:.2f})"
            logger.log(f"⚠️ [RAG Router] Triggering clarification: {reason}")
        
        # Build clarification payload - NORMALIZE SCHEMA
        raw_clarification = classification.get("clarification_choices", {})
        
        # Normalize: convert 'choices' to 'options' if present
        if raw_clarification and raw_clarification.get("choices"):
            clarification_data = {
                "question": raw_clarification.get("question", "I want to make sure I understand your question correctly."),
                "options": raw_clarification["choices"]  # Convert 'choices' to 'options'
            }
        elif raw_clarification and raw_clarification.get("options"):
            # Already in correct format
            clarification_data = raw_clarification
        else:
            # No structured clarification from RAG, create a simple one
            clarification_data = {
                "question": "I want to make sure I understand your question correctly. Could you provide more details about what you're looking for?",
                "options": [
                    {"id": "libchat", "label": "Talk to a librarian"},
                    {"id": "none", "label": "Let me rephrase my question"}
                ]
            }
        
        # Set clarification state (do NOT set final_answer here)
        state["needs_clarification"] = True
        state["clarification"] = clarification_data
        state["primary_agent_id"] = None
        state["secondary_agent_ids"] = []
        
        return state
    
    # Map category to agent_id
    primary_agent_id = CATEGORY_TO_AGENT.get(category)
    
    # Log category trace for evaluation
    if logger:
        logger.log(f"📊 [RAG Router] Category trace", {
            "processed_query": user_msg,
            "category": category,
            "confidence": confidence,
            "primary_agent_id": primary_agent_id,
            "is_out_of_scope": category.startswith("out_of_scope_")
        })
    
    # Handle unknown categories
    if not primary_agent_id:
        if logger:
            logger.log(f"⚠️ [RAG Router] Unknown category '{category}' - triggering clarification")
        
        state["needs_clarification"] = True
        state["clarification"] = {
            "question": "I'm not sure how to help with that. Would you like to talk to a librarian?",
            "options": [
                {"id": "libchat", "label": "Yes, connect me to a librarian"},
                {"id": "none", "label": "No, let me rephrase"}
            ]
        }
        state["primary_agent_id"] = None
        state["secondary_agent_ids"] = []
        
        return state
    
    # Set routing decision
    state["primary_agent_id"] = primary_agent_id
    state["secondary_agent_ids"] = []  # Can be extended for multi-agent queries
    state["needs_clarification"] = False
    
    # CRITICAL: Set out_of_scope flag for correct termination path
    if primary_agent_id == "out_of_scope":
        state["out_of_scope"] = True
        state["rag_category"] = category
        if logger:
            logger.log(f"🚫 [RAG Router] Out-of-scope detected: {category}")
    
    if logger:
        logger.log(f"✅ [RAG Router] Routed to primary_agent_id: {primary_agent_id}")
    
    return state
