"""
RAG-Based Router Node

Replaces pattern-based classification with semantic similarity search.
Uses the RAG classifier to determine question category and routing.
"""

from typing import Dict, Any
from src.state import AgentState
from src.classification.rag_classifier import classify_with_rag
from src.config.scope_definition import get_out_of_scope_response


async def rag_router_node(state: AgentState) -> AgentState:
    """
    Route questions using RAG-based semantic classification.
    
    This replaces the old pattern-based router with a more intelligent
    system that understands context and nuance.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with classification results
    """
    user_msg = state.get("processed_query") or state["user_message"]
    logger = state.get("_logger")
    history = state.get("conversation_history", [])
    
    if logger:
        logger.log("🎯 [RAG Router] Starting semantic classification")
    
    classification = await classify_with_rag(
        user_question=user_msg,
        conversation_history=history,
        logger=logger
    )
    
    category = classification["category"]
    confidence = classification["confidence"]
    agent = classification["agent"]
    needs_clarification = classification.get("needs_clarification", False)
    
    if logger:
        logger.log(f"✅ [RAG Router] Category: {category} (confidence: {confidence:.2f})")
    
    if needs_clarification:
        if logger:
            logger.log(f"⚠️ [RAG Router] Ambiguous query detected, requesting clarification")
        
        state["needs_clarification"] = True
        state["clarifying_question"] = classification.get("clarification_question", "")
        state["classification_result"] = classification
        state["classified_intent"] = category
        state["selected_agents"] = []
        
        clarification_response = f"""I want to make sure I help you with the right thing! 

{classification.get('clarification_question', '')}

Please let me know which one applies to your situation."""
        
        state["final_answer"] = clarification_response
        state["needs_human"] = False
        
        return state
    
    state["classified_intent"] = category
    state["classification_confidence"] = confidence
    state["classification_result"] = classification
    
    if category.startswith("out_of_scope_"):
        if logger:
            logger.log(f"🚫 [RAG Router] Out-of-scope question: {category}")
        
        # Extract subcategory from "out_of_scope_X" format
        # Map RAG categories to scope_definition categories
        category_mapping = {
            "out_of_scope_tech_support": "technical_support",
            "out_of_scope_factual_trivia": "university_general",
            "out_of_scope_inappropriate": "university_general",
            "out_of_scope_nonsensical": "university_general",
        }
        
        topic_category = category_mapping.get(category, "university_general")
        
        if logger:
            logger.log(f"📋 [RAG Router] Mapping {category} → {topic_category}")
        
        out_of_scope_response = get_out_of_scope_response(topic_category)
        state["final_answer"] = out_of_scope_response
        state["needs_human"] = False
        state["selected_agents"] = []
        
        return state
    
    intent_to_agent_mapping = {
        "library_equipment_checkout": ("policy_or_service", ["google_site"]),
        "library_hours_rooms": ("booking_or_hours", ["libcal"]),
        "subject_librarian_guides": ("subject_librarian", ["subject_librarian"]),
        "research_help_handoff": ("human_help", ["libchat"]),
        "library_policies_services": ("policy_or_service", ["google_site"]),
        "ticket_submission_request": ("ticket_request", ["ticket_handler"]),
        "human_librarian_request": ("human_help", ["libchat"]),
    }
    
    # Get intent and agents, fallback to defaults
    if category in intent_to_agent_mapping:
        mapped_intent, agents_list = intent_to_agent_mapping[category]
    else:
        mapped_intent = agent
        agents_list = ["google_site"]  # Default agent
    
    if logger:
        logger.log(f"🎯 [RAG Router] Routing to: {mapped_intent} with agents: {agents_list}")
    
    state["classified_intent"] = mapped_intent
    state["selected_agents"] = agents_list
    state["rag_category"] = category
    
    return state


def should_use_rag_router(state: AgentState) -> bool:
    """
    Determine if we should use RAG-based routing.
    
    For now, this is always True, but we keep this function
    to allow for A/B testing or gradual rollout.
    """
    return True
