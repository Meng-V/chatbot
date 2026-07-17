"""
Clarification Choice Handler

Handles user selection of clarification choices and continues the conversation flow.
"""
from typing import Dict, Any, Optional
from src.classification.rag_classifier import classify_with_rag


async def handle_clarification_choice(
    choice_id: str,
    original_question: str,
    clarification_data: Dict[str, Any],
    conversation_history: Optional[list] = None,
    logger = None
) -> Dict[str, Any]:
    """
    Handle user's clarification choice selection.
    
    Args:
        choice_id: The ID of the selected choice (e.g., "choice_0", "choice_none")
        original_question: The user's original question
        clarification_data: The clarification data from classification
        conversation_history: Previous conversation context
        logger: Optional logger
        
    Returns:
        Dict with:
            - selected_category: The category user selected
            - needs_more_info: Whether we need more details from user
            - response_message: Message to show user
            - should_reclassify: Whether to reclassify with more context
    """
    if logger:
        logger.log(f"🎯 [Clarification Handler] User selected: {choice_id}")
    
    # Find the selected choice
    # Support both "options" (new schema from orchestrator) and "choices" (legacy)
    # Prioritize "options" over "choices"
    choices = clarification_data.get("options", clarification_data.get("choices", []))
    selected_choice = None
    
    for choice in choices:
        if choice["id"] == choice_id:
            selected_choice = choice
            break
    
    if not selected_choice:
        return {
            "selected_category": None,
            "needs_more_info": True,
            "response_message": "I couldn't find that option. Could you please try again?",
            "should_reclassify": False
        }
    
    # Handle "None of the above" selection
    if selected_choice["category"] == "none_of_above":
        if logger:
            logger.log("💬 [Clarification Handler] User selected 'None of the above'")
        
        return {
            "selected_category": "none_of_above",
            "needs_more_info": True,
            "response_message": "I understand. Could you please provide more details about what you're looking for? This will help me assist you better.",
            "should_reclassify": True,
            "prompt_for_details": True
        }
    
    # User selected a specific category
    category = selected_choice["category"]
    
    if logger:
        logger.log(f"✅ [Clarification Handler] User confirmed category: {category}")
    
    return {
        "selected_category": category,
        "needs_more_info": False,
        "response_message": f"Great! I'll help you with {selected_choice['label'].lower()}.",
        "should_reclassify": False,
        "confirmed_category": category
    }


async def reclassify_with_additional_context(
    original_question: str,
    additional_details: str,
    conversation_history: Optional[list] = None,
    logger = None
) -> Dict[str, Any]:
    """
    Reclassify question with additional context from user.
    
    Args:
        original_question: The user's original question
        additional_details: Additional details provided by user
        conversation_history: Previous conversation context
        logger: Optional logger
        
    Returns:
        Classification result with updated context
    """
    # Combine original question with additional details
    enhanced_question = f"{original_question}. Additional context: {additional_details}"
    
    if logger:
        logger.log(f"🔄 [Clarification Handler] Reclassifying with context: {enhanced_question}")
    
    # Reclassify with enhanced context
    result = await classify_with_rag(
        enhanced_question,
        conversation_history=conversation_history,
        logger=logger
    )
    
    return result
