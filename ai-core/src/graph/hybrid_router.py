"""Hybrid router: decides between function calling and LangGraph orchestration."""
import os
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter
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

async def should_use_function_calling(user_message: str, logger=None) -> bool:
    """
    Determine if query should use function calling (simple) or LangGraph (complex).
    
    Returns:
        True: Use function calling (simple, single-tool query)
        False: Use LangGraph orchestration (complex, multi-step query)
    """
    # For very short queries, use function calling
    if len(user_message.split()) <= 5:
        if logger:
            logger.log("🚀 [Hybrid Router] Short query → Function calling")
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
            logger.log(f"🚀 [Hybrid Router] Complexity: {complexity} → {mode}")
        
        return use_function_calling
    
    except Exception as e:
        if logger:
            logger.log(f"⚠️ [Hybrid Router] Error, defaulting to LangGraph: {str(e)}")
        # On error, default to LangGraph (more robust)
        return False

async def route_query(user_message: str, logger=None, conversation_history=None, conversation_id=None) -> Dict[str, Any]:
    """
    Route query to appropriate handler (function calling or LangGraph).
    
    Args:
        user_message: Current user query
        logger: Logger instance
        conversation_history: List of previous messages for context
        conversation_id: Conversation ID for tracking (optional)
    
    Returns result from selected handler.
    """
    use_function_calling_mode = await should_use_function_calling(user_message, logger)
    
    if use_function_calling_mode:
        # Import here to avoid circular dependency
        from src.graph.function_calling import handle_with_function_calling
        return await handle_with_function_calling(user_message, logger, conversation_history)
    else:
        # Import here to avoid circular dependency
        from src.graph.orchestrator import library_graph
        result = await library_graph.ainvoke({
            "user_message": user_message,
            "messages": [],
            "conversation_history": conversation_history or [],
            "conversation_id": conversation_id,
            "_logger": logger
        })
        
        # Handle None result
        if result is None:
            if logger:
                logger.log("⚠️ [Hybrid Router] LangGraph returned None, using default response")
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
