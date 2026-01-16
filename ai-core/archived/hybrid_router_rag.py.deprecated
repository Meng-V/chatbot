"""
Hybrid Router with RAG-Based Classification

This is an updated version of hybrid_router.py that uses RAG-based
semantic classification instead of hardcoded regex patterns.

Key improvements:
- Semantic understanding of questions
- Better handling of ambiguous queries
- Automatic clarification requests
- Context-aware classification
"""

import os
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from src.classification.rag_classifier import classify_with_rag

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
llm = ChatOpenAI(**llm_kwargs)

COMPLEXITY_PROMPT = """Analyze the user's question and determine if it's SIMPLE or COMPLEX.

SIMPLE queries:
- Single action: search for something, get hours, book a room, find a guide
- Clear intent: one specific task
- Examples: "Find books about Python", "What time does King Library close?", "Book a study room for tomorrow"

COMPLEX queries:
- Multiple related questions
- Requires combining information from different sources
- Comparison or analysis needed
- Ambiguous intent requiring clarification
- Examples: "I need help with my research paper and also want to book a room", "Compare these two books and tell me which is better"

Respond with ONLY "simple" or "complex". No explanation."""


async def should_use_function_calling_rag(user_message: str, logger=None) -> bool:
    """
    Determine if query should use function calling (simple) or LangGraph (complex).
    
    Uses RAG-based classification to understand the question semantically.
    
    Returns:
        True: Use function calling (simple, single-tool query)
        False: Use LangGraph orchestration (complex, multi-step query)
    """
    
    classification = await classify_with_rag(
        user_question=user_message,
        logger=logger
    )
    
    category = classification["category"]
    confidence = classification["confidence"]
    needs_clarification = classification.get("needs_clarification", False)
    
    if logger:
        logger.log(f"🎯 [Hybrid Router RAG] Category: {category} (confidence: {confidence:.2f})")
    
    if needs_clarification:
        if logger:
            logger.log(f"⚠️ [Hybrid Router RAG] Ambiguous query → FORCING LangGraph for clarification")
        return False
    
    if category.startswith("out_of_scope_"):
        if logger:
            logger.log(f"🚫 [Hybrid Router RAG] Out-of-scope query → FORCING LangGraph for denial")
        return False
    
    if category == "research_help_handoff":
        if logger:
            logger.log(f"🔬 [Hybrid Router RAG] Research question → FORCING LangGraph for librarian handoff")
        return False
    
    if category == "human_librarian_request":
        if logger:
            logger.log(f"👤 [Hybrid Router RAG] Human help request → FORCING LangGraph")
        return False
    
    # 🕐 HOURS QUERIES: Force LangGraph for proper LibCal routing and generic hours handling
    if category == "library_hours_rooms":
        if logger:
            logger.log(f"🕐 [Hybrid Router RAG] Hours query → FORCING LangGraph for LibCal agent routing")
        return False
    
    if len(user_message.split()) <= 5:
        if logger:
            logger.log("🚀 [Hybrid Router RAG] Short query → Function calling")
        return True
    
    try:
        messages = [
            SystemMessage(content=COMPLEXITY_PROMPT),
            HumanMessage(content=user_message)
        ]
        
        response = await llm.ainvoke(messages)
        complexity = response.content.strip().lower()
        
        use_function_calling = complexity == "simple"
        
        if logger:
            mode = "Function calling" if use_function_calling else "LangGraph"
            logger.log(f"🚀 [Hybrid Router RAG] Complexity: {complexity} → {mode}")
        
        return use_function_calling
    
    except Exception as e:
        if logger:
            logger.log(f"⚠️ [Hybrid Router RAG] Error, defaulting to LangGraph: {str(e)}")
        return False


async def route_query_rag(user_message: str, logger=None, conversation_history=None, conversation_id=None):
    """
    Route query to either function calling or LangGraph orchestrator.
    Uses RAG-based classification.
    """
    import re
    
    # 🚨 PRE-CHECK: Catch library address queries BEFORE routing
    address_patterns = [
        r'\b(library|king|art|rentschler|hamilton|middletown|gardner)\s*(address|location|where\s*is)\b',
        r'\b(address|location|where\s*is|where.*located)\b.*\b(library|king|art|rentschler|hamilton|middletown)\b',
        r'\bwhat\s*is\s*the\b.*\b(library|king|art|rentschler|hamilton|middletown)\b.*\b(address|location)\b',
        r'\bhow\s*(do\s*i|can\s*i)\s*get\s*to\b.*\b(library|king|art|rentschler|hamilton|middletown)\b',
        r'\baddress\s*(of|for)\s*(the\s*)?(library|king|art)\b',
        r'\bwhat\s*(is|are)\s*(the\s*)?.*\baddress\b.*\blibrary\b',
        r'\blibrary\b.*\baddress\b',
    ]
    
    user_msg_lower = user_message.lower()
    for pattern in address_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            if logger:
                logger.log(f"📍 [Hybrid Router RAG] Detected library address query - routing to LangGraph with address flag")
            # Force LangGraph mode with address flag
            from src.graph.orchestrator import library_graph
            result = await library_graph.ainvoke({
                "user_message": user_message,
                "messages": [],
                "conversation_history": conversation_history or [],
                "conversation_id": conversation_id,
                "_library_address_query": True,  # Set flag directly
                "_logger": logger
            })
            
            if result is None or not isinstance(result, dict):
                return {
                    "success": False,
                    "final_answer": "I encountered an issue. Please try again or contact a librarian.",
                    "classified_intent": "error",
                    "selected_agents": [],
                    "needs_human": False,
                    "mode": "langgraph"
                }
            
            return {
                "success": True,
                "final_answer": result.get("final_answer", ""),
                "classified_intent": result.get("classified_intent", "policy_or_service"),
                "selected_agents": result.get("selected_agents", []),
                "agent_responses": result.get("agent_responses", {}),
                "needs_human": result.get("needs_human", False),
                "token_usage": result.get("token_usage"),
                "tool_executions": result.get("tool_executions", []),
                "mode": "langgraph"
            }
    
    # Continue with normal routing
    use_function_calling_mode = await should_use_function_calling_rag(user_message, logger)
    
    if use_function_calling_mode:
        from src.graph.function_calling import handle_with_function_calling
        return await handle_with_function_calling(user_message, logger, conversation_history)
    else:
        from src.graph.orchestrator import library_graph
        result = await library_graph.ainvoke({
            "user_message": user_message,
            "messages": [],
            "conversation_history": conversation_history or [],
            "conversation_id": conversation_id,
            "_logger": logger
        })
        
        if result is None:
            if logger:
                logger.log("⚠️ [Hybrid Router RAG] LangGraph returned None, using default response")
            return {
                "success": False,
                "final_answer": "I encountered an issue processing your request. Please try again or contact a librarian.",
                "classified_intent": "error",
                "selected_agents": [],
                "agent_responses": {},
                "needs_human": False,
                "mode": "langgraph"
            }
        
        if not isinstance(result, dict):
            if logger:
                logger.log(f"⚠️ [Hybrid Router RAG] LangGraph returned non-dict type: {type(result)}")
            return {
                "success": False,
                "final_answer": "I encountered an issue processing your request. Please try again or contact a librarian.",
                "classified_intent": "error",
                "selected_agents": [],
                "agent_responses": {},
                "needs_human": False,
                "mode": "langgraph"
            }
        
        return {
            "success": True,
            "final_answer": result.get("final_answer", ""),
            "classified_intent": result.get("classified_intent"),
            "selected_agents": result.get("selected_agents", []),
            "agent_responses": result.get("agent_responses", {}),
            "needs_human": result.get("needs_human", False),
            "token_usage": result.get("token_usage"),
            "tool_executions": result.get("tool_executions", []),
            "mode": "langgraph"
        }
