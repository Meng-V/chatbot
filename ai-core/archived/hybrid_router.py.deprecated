"""Hybrid router: decides between function calling and LangGraph orchestration."""
import os
import re
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from src.config.research_question_detection import detect_research_question
from src.config.capability_scope import detect_policy_question

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
    import re
    user_msg_lower = user_message.lower()
    
    # ✅ EQUIPMENT BORROWING - Library offers PC/laptop/chromebook checkout (IN-SCOPE)
    # Check this FIRST to exclude from out-of-scope patterns
    equipment_borrow_patterns = [
        r'\b(borrow|checkout|check\s*out|rent|loan|reserve|get)\b.*\b(laptop|pc|computer|chromebook|charger|equipment|device|camera|tripod|headphone|calculator|adapter|ipad|tablet|macbook)\b',
        r'\b(laptop|pc|computer|chromebook|charger|equipment|device|camera|tripod|headphone|calculator|adapter|ipad|tablet|macbook)\b.*\b(borrow|checkout|check\s*out|rent|loan|available|availability)\b',
        r'\b(can\s*i|do\s*you|does\s*the\s*library)\b.*\b(check\s*out|checkout|borrow|rent|loan)\b.*\b(pc|computer|laptop|chromebook|equipment)\b',
        r'\b(adobe|software|license|photoshop|illustrator|creative\s*cloud)\b',
        r'\b(do\s*you\s*have|can\s*i\s*get|where\s*can\s*i)\b.*\b(laptop|pc|computer|chromebook|charger|equipment)\b',
    ]
    is_equipment_borrow = any(re.search(p, user_msg_lower, re.IGNORECASE) for p in equipment_borrow_patterns)
    
    # Skip out-of-scope check if this is equipment borrowing
    if is_equipment_borrow:
        if logger:
            logger.log(f"✅ [Hybrid Router] Equipment borrowing question detected → allowing through")
    
    # 🚫 OUT-OF-SCOPE queries MUST use LangGraph for proper denial (but NOT equipment borrowing)
    if not is_equipment_borrow:
        out_of_scope_patterns = [
            # Weather
            r'\b(weather|temperature|forecast|rain|snow|sunny|cloudy|cold|hot|warm)\b',
            # Course registration/academics
            r'\b(register|registration|enroll|enrollment|add\s*a?\s*class|drop\s*a?\s*class|course\s*selection)\b',
            r'\b(when\s*is\s*(class|course)\s*registration|how\s*do\s*i\s*register)\b',
            # Dining
            r'\b(dining|food|lunch|dinner|breakfast|cafeteria|restaurant|eat)\b',
            # Sports
            r'\b(football|basketball|soccer|sports?|game|score|schedule)\b.*\b(game|schedule|score)\b',
            # Homework/assignments
            r'\b(homework|assignment|essay|paper|test|quiz|exam)\b.*\b(help|write|do|solve|answer)\b',
            # Campus locations (non-library)
            r'\b(where\s*is|how\s*do\s*i\s*get\s*to)\b.*\b(student\s*center|armstrong|upham|shriver|bachelor)\b',
            # IT/Technology - tech support PROBLEMS (NOT equipment borrowing)
            r'\b(wifi|internet|canvas|email|login|password)\b.*\b(issue|problem|broken|not\s*working|fix|down)\b',
            r'\b(my|a)\s*(computer|laptop|phone|device)\b.*\b(broken|not\s*working|crashed|frozen|slow|virus|issue|problem)\b',
            r'\b(fix|repair|troubleshoot)\s*(my|a)?\s*(computer|laptop|phone|device)\b',
            r'\b(computer|laptop|phone|device)\b.*\b(won\'t|doesn\'t|isn\'t|not)\s*(work|start|turn\s*on|boot|connect)\b',
            # Generic tech help requests (not equipment borrowing)
            r'\bwho\s*(can|could|would)\s*(help|assist)\b.*\b(computer|tech|software|hardware)\b',
            r'\b(help|assist)\b.*\b(computer|tech)\s*question\b',
            r'\b(computer|tech)\s*(help|support|assistance)\b',
            # Financial
            r'\b(tuition|financial\s*aid|scholarship|payment|pay|bursar)\b',
        ]
        
        for pattern in out_of_scope_patterns:
            if re.search(pattern, user_msg_lower, re.IGNORECASE):
                if logger:
                    logger.log(f"🚫 [Hybrid Router] Out-of-scope query detected → FORCING LangGraph for denial")
                return False  # Force LangGraph for proper out-of-scope handling
    
    # 📋 POLICY QUESTIONS MUST use LangGraph for authoritative URL response
    # These are questions about loan periods, circulation policies, etc.
    policy_check = detect_policy_question(user_message)
    if policy_check.get("is_policy_question"):
        if logger:
            policy_type = policy_check.get("policy_type", "unknown")
            logger.log(f"📋 [Hybrid Router] Policy question detected ({policy_type}) → FORCING LangGraph for authoritative URL")
        return False  # Force LangGraph for policy question handling
    
    # 🔬 RESEARCH QUESTIONS MUST use LangGraph for proper handoff to librarians
    # These are questions asking for specific articles, sources, research help
    research_check = detect_research_question(user_message)
    if research_check.get("is_research_question") and research_check.get("should_handoff"):
        if logger:
            pattern_type = research_check.get("pattern_type", "unknown")
            logger.log(f"🔬 [Hybrid Router] Research question detected ({pattern_type}) → FORCING LangGraph for librarian handoff")
        return False  # Force LangGraph for research question handling
    
    # 🔬 Additional research patterns that MUST go to LangGraph
    research_patterns = [
        # Specific article/source requirements
        r'\b(i\s*need|looking\s*for|find|get|want)\s*\d+\s*(articles?|sources?|papers?|publications?|peer[- ]?reviewed)\b',
        r'\b\d+\s*(articles?|sources?|papers?|publications?)\b.*\b(pages?|about|on|regarding|that)\b',
        r'\b(articles?|papers?|sources?)\b.*\b\d+\s*pages?\b',
        # Research help requests
        r'\b(scholarly|academic|peer[- ]?reviewed)\s*(articles?|sources?|papers?|journals?)\b',
        r'\b(research|write|writing)\s*(a\s*)?(paper|essay|thesis|dissertation)\b.*\b(about|on|regarding)\b',
        r'\b(effects?|impacts?|relationship|correlation)\s*(of|between)\b.*\b(on|and)\b',
        # Database/search strategy questions  
        r'\b(which|what|best)\s*(databases?|resources?)\s*(should|can|do|for)\b',
        r'\bhow\s*(do|can|to)\s*(i\s*)?(search|find|locate)\b.*\b(articles?|sources?|research)\b',
    ]
    
    for pattern in research_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            if logger:
                logger.log(f"🔬 [Hybrid Router] Research pattern matched → FORCING LangGraph for librarian handoff")
            return False  # Force LangGraph
    
    # 👤 Personal account queries MUST use LangGraph for direct URL response
    personal_account_patterns = [
        r'\b(my|i\s*have|do\s*i\s*have|check\s*my|view\s*my|see\s*my)\b.*\b(loans?|checkouts?|books?\s*checked\s*out|borrowed|fines?|fees?|owe|owing|requests?|holds?|account|blocks?|messages?)\b',
        r'\b(library|my)\s*account\b',
        r'\bcheck\s*(my\s*)?(library\s*)?account\b',
        r'\bwhat\s*(do\s*i|books?\s*do\s*i)\s*(owe|have\s*(checked\s*out|due|borrowed))\b',
        r'\b(am\s*i|do\s*i\s*have)\s*(blocked|any\s*(fines?|fees?|holds?|blocks?))\b',
        r'\bwhen\s*(is|are)\s*my\s*(books?|items?|loans?)\s*due\b',
        r'\bmy\s*(due\s*dates?|overdue|renewals?)\b',
    ]
    
    for pattern in personal_account_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            if logger:
                logger.log(f"👤 [Hybrid Router] Personal account query → FORCING LangGraph for account URL")
            return False  # Force LangGraph
    
    # 🎯 CRITICAL: Factual queries MUST use LangGraph for fact grounding
    from src.utils.fact_grounding import detect_factual_query_type
    fact_types = detect_factual_query_type(user_message)
    if fact_types:
        if logger:
            logger.log(f"🔒 [Hybrid Router] Factual query detected ({', '.join(fact_types)}) → FORCING LangGraph for fact grounding")
        return False  # Force LangGraph
    
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

async def route_query(user_message: str, logger=None, conversation_history=None, conversation_id=None):
    """
    Route query to either function calling or LangGraph orchestrator.
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
        
        # Debug: Log result type and structure
        if logger:
            logger.log(f"🔍 [Hybrid Router] Result type: {type(result)}, has get: {hasattr(result, 'get')}")
            if result is not None and hasattr(result, '__dict__'):
                logger.log(f"🔍 [Hybrid Router] Result keys: {list(result.keys()) if hasattr(result, 'keys') else 'N/A'}")
        
        # Handle non-dict result
        if not isinstance(result, dict):
            if logger:
                logger.log(f"⚠️ [Hybrid Router] LangGraph returned non-dict type: {type(result)}")
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
