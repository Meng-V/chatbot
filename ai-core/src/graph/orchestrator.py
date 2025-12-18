"""LangGraph orchestrator (Meta Router) for Miami University Libraries chatbot."""
import os
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Load .env from project root before anything else
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

from src.state import AgentState
from src.config.scope_definition import (
    SCOPE_ENFORCEMENT_PROMPTS,
    get_out_of_scope_response,
    OFFICIAL_LIBRARY_CONTACTS
)
# Comprehensive multi-tool agents
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
from src.agents.subject_librarian_agent import find_subject_librarian_query
from src.agents.enhanced_subject_librarian_agent import EnhancedSubjectLibrarianAgent
# Legacy single-tool agents
from src.agents.libchat_agent import libchat_handoff
from src.agents.transcript_rag_agent import transcript_rag_query
from src.utils.logger import AgentLogger
from src.memory.conversation_store import (
    create_conversation,
    add_message,
    get_conversation_history,
    update_conversation_tools,
    log_token_usage
)
from src.tools.url_validator import validate_and_clean_response
from src.utils.fact_grounding import (
    detect_factual_query_type,
    is_high_confidence_rag_match,
    verify_factual_claims_against_rag,
    create_grounded_synthesis_prompt,
    should_enforce_strict_grounding
)
from src.utils.query_understanding import (
    understand_query,
    should_request_clarification,
    get_processed_query,
    format_clarifying_response,
    get_query_type_hint
)
from src.config.capability_scope import (
    detect_limitation_request,
    get_limitation_response,
    get_limitation_response_with_availability,
    is_account_action
)

# Use o4-mini as specified
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter, only use it for other models
llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
llm = ChatOpenAI(**llm_kwargs)

# ============================================================================
# AVAILABLE INFORMATION SOURCES (Version 3.0 - Dec 2025)
# ============================================================================
# ACTIVE AGENTS (6 core capabilities):
#   - LibGuide (SpringShare): Subject guides, research guides, MyGuide
#   - LibCal (SpringShare): Library hours, room reservations
#   - LibChat (SpringShare): Human librarian handoff
#   - Google Site Search: Library website search
#   - Subject Librarian Agent: Find librarians by subject
#   - Transcript RAG: Correction pool only (fixes bot mistakes)
#
# ARCHIVED (not in active use):
#   - Primo Agent: Catalog search (see /archived/primo/)
#
# IMPORTANT: Only information from active agents is reliable.
# Do NOT generate or guess information not provided by agents.
# ============================================================================

ROUTER_SYSTEM_PROMPT = """You are a classification assistant for Miami University Libraries.

CRITICAL SCOPE RULE:
- ONLY classify questions about MIAMI UNIVERSITY LIBRARIES
- If question is about general Miami University, admissions, courses, housing, dining, campus life, or non-library services, respond with: out_of_scope
- If question is about homework help, assignments, or academic content, respond with: out_of_scope

🚨 CATALOG SEARCH NOT AVAILABLE 🚨
The following requests MUST be classified as "human_help" (NOT discovery_search):
- Searching for books, articles, journals, e-resources
- Finding specific publications or call numbers
- "I need articles about...", "Find me books on...", "Do you have..."
- Any request to search the library catalog or databases
REASON: Catalog search is not available. Redirect users to human librarians for book/article searches.

IN-SCOPE LIBRARY QUESTIONS - Classify into ONE of these categories:

1. **subject_librarian** - Finding subject librarian, LibGuides for a specific major, department, or academic subject. ALSO use for general questions about all subject librarians.
   Examples: "Who's the biology librarian?", "LibGuide for accounting", "I need help with psychology research", "list of subject librarians", "show me all subject librarians", "subject librarian map"

2. **course_subject_help** - Course guides, recommended databases for a specific class
   Examples: "What databases for ENG 111?", "Guide for PSY 201", "Resources for CHM 201"

3. **booking_or_hours** - Library building hours, room reservations, library schedule
   Examples: "What time does King Library close?", "Book a study room", "Library hours tomorrow"

4. **policy_or_service** - Library policies, services, questions about library website content
   Examples: "How do I renew a book?", "Can I print in library?", "What's the late fee for library books?"

5. **human_help** - MUST use for ANY of these:
   - User wants to talk to a librarian
   - User asks for books, articles, journals, e-resources (catalog search disabled!)
   - User wants to search the library catalog or databases
   Examples: "Can I talk to a librarian?", "Connect me to library staff", "I need human help"
   CATALOG SEARCH EXAMPLES (classify as human_help): "I need 3 articles about...", "Do you have [book]?", "Find articles on...", "Search for books about...", "Looking for journal articles"

6. **general_question** - General library questions about services, locations, policies
   Examples: "Where is the quiet study area?", "What services does the library offer?"

OUT-OF-SCOPE (respond with: out_of_scope):
- General university questions, admissions, financial aid, tuition
- Course content, homework, assignments, test prep
- IT support, Canvas help, email issues
- Housing, dining, parking
- Student organizations, campus events

Respond with ONLY the category name (e.g., subject_librarian or out_of_scope). No explanation."""

# ============================================================================
# QUERY UNDERSTANDING NODE (NEW - Pre-processing layer)
# ============================================================================

async def query_understanding_node(state: AgentState) -> AgentState:
    """
    Query Understanding Layer: Analyze and translate user input before routing.
    
    This node:
    1. Translates verbose/complex queries into clear, actionable requests
    2. Detects ambiguous queries that need clarification
    3. Extracts key entities (dates, subjects, buildings, etc.)
    4. Provides hints for better routing
    """
    user_msg = state["user_message"]
    logger = state.get("_logger") or AgentLogger()
    history = state.get("conversation_history", [])
    
    logger.log("🔍 [Query Understanding] Processing user input", {"query": user_msg})
    
    # Store original query
    state["original_query"] = user_msg
    
    # Run query understanding
    understanding = await understand_query(
        user_message=user_msg,
        conversation_history=history,
        log_callback=logger.log
    )
    
    state["query_understanding"] = understanding
    
    # Check if clarification is needed
    if should_request_clarification(understanding):
        logger.log("⚠️ [Query Understanding] Query is ambiguous, requesting clarification")
        state["needs_clarification"] = True
        state["clarifying_question"] = format_clarifying_response(understanding)
        # Use original query but mark for clarification
        state["processed_query"] = user_msg
    else:
        # Use the processed/translated query
        processed = get_processed_query(understanding)
        state["processed_query"] = processed
        state["needs_clarification"] = False
        
        # Store query type hint for routing assistance
        hint = get_query_type_hint(understanding)
        if hint:
            state["query_type_hint"] = hint
            logger.log(f"💡 [Query Understanding] Query type hint: {hint}")
        
        if processed != user_msg:
            logger.log(f"✅ [Query Understanding] Translated: '{user_msg}' → '{processed}'")
    
    state["_logger"] = logger
    return state


def should_skip_to_clarification(state: AgentState) -> str:
    """
    Routing function: decide if we need clarification or can proceed.
    
    Returns:
        'clarify' if user needs to provide more info
        'classify' if we can proceed with intent classification
    """
    if state.get("needs_clarification"):
        return "clarify"
    return "classify"


async def clarification_node(state: AgentState) -> AgentState:
    """
    Handle ambiguous queries by asking for clarification.
    
    This node generates a friendly response asking the user for more details.
    """
    logger = state.get("_logger") or AgentLogger()
    
    clarifying_q = state.get("clarifying_question")
    if clarifying_q:
        logger.log(f"❓ [Clarification] Asking user: {clarifying_q}")
        state["final_answer"] = clarifying_q
    else:
        # Fallback
        state["final_answer"] = (
            "I want to make sure I understand your question correctly. "
            "Could you provide a bit more detail about what you're looking for?"
        )
    
    state["_logger"] = logger
    return state


# ============================================================================
# INTENT CLASSIFICATION NODE
# ============================================================================

async def classify_intent_node(state: AgentState) -> AgentState:
    """Meta Router: classify user intent using LLM."""
    import re
    
    # Use processed query if available, otherwise original
    user_msg = state.get("processed_query") or state["user_message"]
    original_msg = state["user_message"]  # Keep original for capability check
    logger = state.get("_logger") or AgentLogger()
    
    # 🚨 CAPABILITY CHECK: Detect requests for things the bot CANNOT do
    # This prevents asking for clarification on things we can't help with
    limitation = detect_limitation_request(original_msg)
    if limitation.get("is_limitation"):
        limitation_type = limitation.get("limitation_type")
        logger.log(f"🚫 [Capability Check] Detected limitation: {limitation_type} - {limitation.get('description')}")
        
        # Return the appropriate response for this limitation
        state["classified_intent"] = "capability_limitation"
        state["selected_agents"] = []
        state["_limitation_response"] = limitation.get("response")
        state["_limitation_type"] = limitation_type
        state["_logger"] = logger
        return state
    
    # 🚨 PRE-CHECK: Catch address/location requests BEFORE LLM routing
    address_patterns = [
        r'\b(library|king|art|rentschler|hamilton|middletown|gardner)\s*(address|location|where\s*is)\b',
        r'\b(address|location|where\s*is|where.*located)\b.*\b(library|king|art|rentschler|hamilton|middletown)\b',
        r'\bwhat\s*is\s*the\b.*\b(library|king|art|rentschler|hamilton|middletown)\b.*\b(address|location)\b',
        r'\bhow\s*(do\s*i|can\s*i)\s*get\s*to\b.*\b(library|king|art|rentschler|hamilton|middletown)\b',
        r'\baddress\s*(of|for)\s*(the\s*)?(library|king|art)\b',
        r'\bwhat\s*(is|are)\s*(the\s*)?.*\baddress\b.*\blibrary\b',
        r'\blibrary\b.*\baddress\b',
    ]
    
    user_msg_lower = user_msg.lower()
    for pattern in address_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"📍 [Meta Router] Detected library address query - bypassing agents, using database")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = []  # Skip agents, go directly to synthesizer
            state["_library_address_query"] = True  # Flag for special handling
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch website URL requests BEFORE LLM routing
    website_patterns = [
        r'\b(library|king|art|rentschler|hamilton|middletown|gardner|makerspace|maker\s*space|special\s*collections?)\s*(website|url|link|webpage|web\s*page)\b',
        r'\b(website|url|link|webpage|web\s*page)\b.*\b(library|king|art|rentschler|hamilton|middletown|makerspace|maker\s*space|special\s*collections?)\b',
        r'\bwhat\s*is\s*the\b.*\b(library|king|art|rentschler|hamilton|middletown|makerspace|maker\s*space|special\s*collections?)\b.*\b(website|url|link)\b',
    ]
    
    for pattern in website_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"🌐 [Meta Router] Detected library website query - bypassing agents, using database")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = []  # Skip agents, go directly to synthesizer
            state["_library_website_query"] = True  # Flag for special handling
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch PERSONAL LIBRARY ACCOUNT queries - direct to account URL
    # Users asking about THEIR OWN account (loans, fines, requests, holds, etc.)
    # NOT general policy questions like "what are the late fees"
    personal_account_patterns = [
        r'\b(my|i\s*have|do\s*i\s*have|check\s*my|view\s*my|see\s*my)\b.*\b(loans?|checkouts?|books?\s*checked\s*out|borrowed|fines?|fees?|owe|owing|requests?|holds?|account|blocks?|messages?)\b',
        r'\b(loans?|fines?|fees?|requests?|holds?|blocks?)\b.*\b(on\s*my\s*account|in\s*my\s*account)\b',
        r'\b(what|how\s*many)\b.*\b(books?|items?)\b.*\b(do\s*i\s*have|have\s*i)\b.*\b(checked\s*out|borrowed|due)\b',
        r'\b(library|my)\s*account\s*(status|overview|details?|settings?|info)?\b',
        r'\bcheck\s*(my\s*)?(library\s*)?account\b',
        r'\bwhat\s*(do\s*i|books?\s*do\s*i)\s*(owe|have\s*(checked\s*out|due|borrowed))\b',
        r'\b(am\s*i|do\s*i\s*have)\s*(blocked|any\s*(fines?|fees?|holds?|blocks?))\b',
        r'\bwhen\s*(is|are)\s*my\s*(books?|items?|loans?)\s*due\b',
        r'\bmy\s*(due\s*dates?|overdue|renewals?)\b',
    ]
    
    for pattern in personal_account_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"👤 [Meta Router] Detected personal account query - directing to account URL")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = []  # No agent needed, handle in synthesizer
            state["_personal_account_query"] = True
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch EQUIPMENT/TECHNOLOGY patterns - route to Google Site Search
    # Camera, laptop, charger, equipment checkout questions
    equipment_patterns = [
        r'\b(check\s*out|borrow|rent|loan)\b.*\b(camera|laptop|charger|tripod|microphone|headphone|calculator|equipment)\b',
        r'\b(camera|laptop|charger|tripod|microphone|headphone|calculator|equipment)\b.*\b(check\s*out|borrow|rent|available)\b',
        r'\b(technology|tech|equipment)\s*(checkout|lending|loan)\b',
        r'\bdo\s*you\s*(have|lend|loan)\b.*\b(camera|laptop|charger|equipment)\b',
    ]
    
    for pattern in equipment_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"📷 [Meta Router] Detected equipment checkout query - routing to google_site")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = ["google_site"]
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch SUBSCRIPTION patterns - route to Google Site Search
    # NYT, WSJ, newspaper subscriptions
    subscription_patterns = [
        r'\b(nyt|new\s*york\s*times|wall\s*street\s*journal|wsj|newspaper)\b.*\b(subscription|access|renew|get)\b',
        r'\b(subscription|access|renew|get)\b.*\b(nyt|new\s*york\s*times|wall\s*street\s*journal|wsj|newspaper)\b',
        r'\bhow\s*(do\s*i|can\s*i|to)\b.*\b(nyt|new\s*york\s*times)\b',
        r'\b(nyt|new\s*york\s*times)\b',
    ]
    
    for pattern in subscription_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"📰 [Meta Router] Detected subscription query - routing to google_site")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = ["google_site"]
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch SUBJECT LIBRARIAN patterns BEFORE LLM routing
    # These patterns MUST go to subject_librarian agent (DB + LibGuide API)
    subject_librarian_patterns = [
        r'\b(subject|liaison)\s*librarian\b',
        r'\blibrarian\s*for\s*(biology|chemistry|physics|math|psychology|english|history|art|music|business|nursing|engineering)\b',
        r'\bwho\s*(is|are)\s*(the\s*)?(.*?)librarian\b',
        r'\b(biology|chemistry|physics|psychology|english|history|art|music|business|nursing|engineering)\s*librarian\b',
        r'\bfind\s*(a\s*)?librarian\s*for\b',
        r'\bhelp\s*with\s*(.*?)\s*research\b.*\blibrarian\b',
        # Course code patterns: "ENG 111", "BIO 201", "PSY"
        r'\b([A-Z]{2,4})\s*\d{3,4}\b.*\blibrarian\b',
        r'\blibrarian\b.*\b([A-Z]{2,4})\s*\d{3,4}\b',
        # Help with subject/course/department patterns
        r'\b(help|assist|need)\s*(with|on|for)\s*(my\s*)?([A-Z]{2,4}\s*\d{3,4})\b',  # "help with ENG 111"
        r'\b(help|assist|need)\s*(with|on|for)\s*(the\s*)?([a-z]+)\s*department\b',  # "help with the English department"
        r'\b(help|assist|need)\s*(with|on|for)\s*my\s*([a-z]+)\s*(class|course)\b',  # "help with my psychology class"
        r'\b(help|assist|need)\s*(with|on|for)\s*([a-z]+)\s*research\b',  # "help with biology research"
        # Major-based patterns
        r'\b(biology|chemistry|physics|psychology|english|history|business|nursing|computer\s*science)\s*major\b.*\blibrarian\b',
        r'\bmajor.*\blibrarian\b',
        r'\bmajoring\s*in\b.*\b(who|librarian|help)\b',
    ]
    
    for pattern in subject_librarian_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"👨‍🏫 [Meta Router] Detected subject librarian query - routing to subject_librarian agent")
            state["classified_intent"] = "subject_librarian"
            state["selected_agents"] = ["subject_librarian"]
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch LIVE CHAT / ASK US hours patterns BEFORE LLM routing
    # These patterns use the Ask Us hours API (same as librarian availability)
    live_chat_patterns = [
        r'\b(live\s*chat|ask\s*us|human\s*chat|librarian\s*chat|chat\s*with\s*librarian)\b.*\b(hours?|available|open|when)\b',
        r'\b(hours?|when|available)\b.*\b(live\s*chat|ask\s*us|human\s*chat|librarian\s*chat|chat\s*with\s*librarian)\b',
        r'\bwhen\s*(can\s*i|are)\b.*\b(chat|talk)\b.*\blibrarian',
        r'\b(chat|talk)\b.*\blibrarian\b.*\b(hours?|available|when)\b',
        r'\blive\s*chat\s*(help|support|hours?)\b',
        r'\b(librarian|staff)\b.*\b(available|online|hours?)\b',
        r'\bis\s*(live\s*chat|chat|ask\s*us)\s*available\b',  # "is live chat available now"
        r'\b(live\s*chat|chat)\s*available\s*(now|right\s*now)\b',
    ]
    
    for pattern in live_chat_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"💬 [Meta Router] Detected live chat hours query - using Ask Us hours API")
            state["classified_intent"] = "policy_or_service"
            state["selected_agents"] = []  # Skip agents, handle in synthesizer
            state["_live_chat_hours_query"] = True
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch hours/booking patterns BEFORE LLM routing
    # These patterns MUST go to LibCal for reliable hours data
    # Includes: libraries (King, Art, Rentschler, Gardner-Harvey) AND spaces (Makerspace, Special Collections)
    hours_patterns = [
        r'\b(library|building|king|art|rentschler|gardner|harvey|architecture|wertz|makerspace|special\s*collections?|havighurst)\s*(hours?|open|close|opening|closing)\b',
        r'\b(hours?|open|close|opening|closing)\b.*\b(library|building|king|art|rentschler|gardner|harvey|architecture|wertz|makerspace|special\s*collections?|havighurst)\b',
        r'\bwhat\s*time\b.*\b(library|king|art|rentschler|gardner|harvey|architecture|wertz|makerspace|special\s*collections?)\b',
        r'\b(when\s*does|when\s*is)\b.*\b(library|king|art|rentschler|gardner|harvey|architecture|wertz|makerspace|special\s*collections?)\b.*\b(open|close)\b',
        r'\blibrary\s*schedule\b',
        r'\b(art\s*(and|&)\s*architecture)\b.*\b(hours?|open|close)\b',  # "Art and Architecture hours"
        r'\b(hours?|open|close)\b.*\b(art\s*(and|&)\s*architecture)\b',  # "hours for Art and Architecture"
        r'\bmakerspace\b',  # Any makerspace query likely wants hours/info
        r'\bspecial\s*collections?\b.*\b(hours?|open|close|when)\b',  # Special Collections hours
    ]
    
    for pattern in hours_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"🕐 [Meta Router] Detected hours query - routing to LibCal")
            state["classified_intent"] = "booking_or_hours"
            state["selected_agents"] = ["libcal"]
            state["_logger"] = logger
            return state
    
    # 🚨 PRE-CHECK: Catch catalog search patterns BEFORE LLM routing
    # These patterns MUST go to human_help (catalog search disabled)
    catalog_patterns = [
        r'\b(find|search|look\s*for|need|want|get)\b.*\b(articles?|books?|journals?|e-?resources?|publications?)\b',
        r'\b(articles?|books?|journals?)\b.*\b(about|on|regarding)\b',
        r'\bdo you have\b.*\b(book|article|journal|copy)\b',
        r'\b\d+\s*(articles?|books?|sources?|pages?)\b',  # "3 articles", "5 books"
        r'\bcall\s*number\b',
        r'\bcatalog\s*search\b',
        r'\bsearch\s*(the\s*)?(catalog|database)',
    ]
    
    for pattern in catalog_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            logger.log(f"📚 [Meta Router] Detected catalog search request - routing to human_help (service disabled)")
            state["classified_intent"] = "human_help"
            state["selected_agents"] = ["libchat"]
            state["_catalog_search_requested"] = True  # Flag for special message
            state["_logger"] = logger
            return state
    
    # Check if Query Understanding Layer detected a capability limitation
    understanding = state.get("query_understanding", {})
    if understanding.get("query_type_hint") == "capability_limitation":
        limitation_type = understanding.get("limitation_type", "unknown")
        limitation_response = understanding.get("limitation_response")
        logger.log(f"🚫 [Meta Router] Query Understanding detected limitation: {limitation_type}")
        state["classified_intent"] = "capability_limitation"
        state["selected_agents"] = []
        state["_limitation_type"] = limitation_type
        state["_limitation_response"] = limitation_response
        state["_logger"] = logger
        return state
    
    # Check if Query Understanding Layer detected a greeting
    if understanding.get("query_type_hint") == "greeting" or understanding.get("skip_understanding"):
        logger.log("👋 [Meta Router] Detected greeting, responding directly")
        state["classified_intent"] = "greeting"
        state["selected_agents"] = []
        state["_needs_availability_check"] = True  # Flag to check availability in greeting
        state["_logger"] = logger
        return state
    
    logger.log("🧠 [Meta Router] Classifying user intent", {"query": user_msg})
    
    # Use query type hint if available for faster routing
    hint = state.get("query_type_hint")
    if hint and hint in ["booking_or_hours", "subject_librarian", 
                         "policy_or_service", "human_help", "general_question"]:
        logger.log(f"💡 [Meta Router] Using query understanding hint: {hint}")
        intent = hint
    elif hint == "discovery_search":
        # Redirect discovery_search to human_help (no catalog search available)
        logger.log(f"💡 [Meta Router] Query hint was discovery_search -> redirecting to human_help")
        intent = "human_help"
        state["_catalog_search_requested"] = True
    else:
        # Fall back to LLM classification
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_msg)
        ]
        
        response = await llm.ainvoke(messages)
        intent = response.content.strip().lower()
    
    logger.log(f"🎯 [Meta Router] Classified as: {intent}")
    
    # Handle out-of-scope questions
    if intent == "out_of_scope":
        state["classified_intent"] = "out_of_scope"
        state["selected_agents"] = []
        state["out_of_scope"] = True
        state["_logger"] = logger
        logger.log("🚫 [Meta Router] Question is OUT OF SCOPE - will redirect to appropriate service")
        return state
    
    # Map intent to agents (6 core capabilities)
    # Note: transcript_rag is available for correction pool but not used in routing
    agent_mapping = {
        "discovery_search": ["libchat"],  # Redirect to human librarian (no catalog search)
        "subject_librarian": ["subject_librarian"],  # MyGuide + LibGuides API
        "course_subject_help": ["libguide"],  # Research guides
        "booking_or_hours": ["libcal"],  # Hours and room booking
        "policy_or_service": ["google_site"],  # Website search
        "human_help": ["libchat"],  # Live chat handoff
        "general_question": ["google_site"]  # Website search
    }
    
    # Default to google_site for unknown intents
    agents = agent_mapping.get(intent, ["google_site"])
    
    # 🎯 CRITICAL: Pre-filter agents for factual queries to prevent hallucinations
    from src.utils.fact_grounding import detect_factual_query_type
    fact_types = detect_factual_query_type(user_msg)
    
    if fact_types and "google_site" in agents:
        logger.log(f"🔒 [Meta Router] Detected factual query ({', '.join(fact_types)}) - REMOVING google_site to prevent conflicting data")
        agents = [a for a in agents if a != "google_site"]
        logger.log(f"📋 [Meta Router] Filtered agents: {', '.join(agents)}")
    
    state["classified_intent"] = intent
    state["selected_agents"] = agents
    state["_logger"] = logger
    
    logger.log(f"📋 [Meta Router] Selected agents: {', '.join(agents)}")
    
    return state

# Initialize comprehensive multi-tool agent instances
libcal_agent = LibCalComprehensiveAgent()
libguide_agent = LibGuideComprehensiveAgent()
google_site_agent = GoogleSiteComprehensiveAgent()
enhanced_subject_agent = EnhancedSubjectLibrarianAgent()

async def execute_agents_node(state: AgentState) -> AgentState:
    """Execute selected agents in parallel."""
    agents = state["selected_agents"]
    logger = state.get("_logger") or AgentLogger()
    results = {}
    
    # Handle greeting or pre-answered queries (no agents to execute)
    if not agents:
        if state.get("final_answer"):
            logger.log("✅ [Orchestrator] Query already answered (greeting/clarification)")
            state["agent_responses"] = {}
            state["_logger"] = logger
            return state
    
    logger.log(f"⚡ [Orchestrator] Executing {len(agents)} agent(s) in parallel")
    
    # Map agent names to agent instances
    agent_map = {
        "libcal": libcal_agent,
        "libguide": libguide_agent,
        "google_site": google_site_agent,
        "subject_librarian": enhanced_subject_agent,  # Use enhanced agent
        "libchat": libchat_handoff,
        "transcript_rag": transcript_rag_query  # Correction pool only
    }
    
    import asyncio
    import time
    tasks = []
    agent_start_times = {}
    
    for agent_name in agents:
        agent_or_func = agent_map.get(agent_name)
        if agent_or_func:
            # Record start time for tracking
            agent_start_times[agent_name] = time.time()
            
            # Check if it's a multi-tool agent (has execute method) or legacy function
            if hasattr(agent_or_func, 'execute'):
                # Multi-tool agent - call execute
                tasks.append(agent_or_func.execute(state["user_message"], log_callback=logger.log))
            else:
                # Legacy function-based agent
                tasks.append(agent_or_func(state["user_message"], log_callback=logger.log))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Track tool executions
    tool_executions = state.get("tool_executions", [])
    
    for agent_name, response in zip(agents, responses):
        # Calculate execution time
        execution_time = int((time.time() - agent_start_times.get(agent_name, time.time())) * 1000)  # ms
        
        if isinstance(response, Exception):
            results[agent_name] = {"source": agent_name, "success": False, "error": str(response)}
            # Log failed execution
            tool_executions.append({
                "agent_name": agent_name,
                "tool_name": "query" if agent_name != "transcript_rag" else "rag_search",
                "parameters": {"query": state["user_message"]},
                "success": False,
                "execution_time": execution_time
            })
        else:
            results[agent_name] = response
            if response.get("needs_human"):
                state["needs_human"] = True
            
            # 🎯 Track RAG usage specifically
            if agent_name == "transcript_rag" and response.get("success"):
                logger.log("📊 [RAG Tracking] Logging RAG query to database")
                tool_executions.append({
                    "agent_name": "transcript_rag",
                    "tool_name": "rag_search",
                    "parameters": {
                        "query": state["user_message"],
                        "confidence": response.get("confidence", "unknown"),
                        "similarity_score": response.get("similarity_score", 0),
                        "matched_topic": response.get("matched_topic", "unknown"),
                        "num_results": response.get("num_results", 0),
                        "weaviate_ids": response.get("weaviate_ids", [])  # Store Weaviate record IDs
                    },
                    "success": True,
                    "execution_time": execution_time
                })
    
    state["agent_responses"] = results
    state["tool_executions"] = tool_executions
    state["_logger"] = logger
    
    logger.log(f"✅ [Orchestrator] All agents completed")
    
    return state

async def synthesize_answer_node(state: AgentState) -> AgentState:
    """Synthesize final answer from agent responses using LLM with fact grounding."""
    intent = state.get("classified_intent")
    user_msg = state["user_message"]
    history = state.get("conversation_history", [])
    logger = state.get("_logger") or AgentLogger()
    
    logger.log("🤖 [Synthesizer] Generating final answer", {"history_messages": len(history)})
    
    # Handle greetings with availability check
    if intent == "greeting" and state.get("_needs_availability_check"):
        logger.log("👋 [Synthesizer] Generating greeting with librarian availability")
        from src.api.askus_hours import get_askus_hours_for_date
        
        try:
            hours_data = await get_askus_hours_for_date()
            is_open = hours_data.get("is_open", False)
            current_period = hours_data.get("current_period")
            hours_list = hours_data.get("hours", [])
            
            base_greeting = (
                "Hello! I'm the Miami University Libraries assistant. 📚\n\n"
                "I can help you with:\n"
                "• **Library hours and study room reservations**\n"
                "• **Research guides and subject librarians**\n"
                "• **Library services and policies**\n\n"
            )
            
            if is_open and current_period:
                availability_msg = (
                    f"✅ **Librarians are available NOW** (until {current_period['close']})\n"
                    f"For help finding books or articles, you can chat with a librarian live.\n\n"
                )
            elif hours_list and len(hours_list) > 0:
                next_open = hours_list[0].get("from")
                next_close = hours_list[0].get("to")
                availability_msg = (
                    f"⏰ Live chat with librarians: {next_open} - {next_close} today\n"
                    f"For help finding books or articles, submit a ticket or chat during business hours.\n\n"
                )
            else:
                availability_msg = (
                    "For help finding books or articles, I can connect you with a librarian.\n\n"
                )
            
            state["final_answer"] = base_greeting + availability_msg + "What can I help you with today?"
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] Error checking availability: {str(e)}")
            state["final_answer"] = (
                "Hello! I'm the Miami University Libraries assistant. 📚\n\n"
                "I can help you with:\n"
                "• **Library hours and study room reservations**\n"
                "• **Research guides and subject librarians**\n"
                "• **Library services and policies**\n\n"
                "For help finding books or articles, I can connect you with a librarian.\n\n"
                "What can I help you with today?"
            )
        return state
    
    # Handle pre-answered queries (clarification responses)
    if state.get("final_answer") and intent is None:
        logger.log("✅ [Synthesizer] Using pre-generated answer")
        return state
    
    # Handle capability limitations (things the bot cannot do)
    if intent == "capability_limitation" or state.get("_limitation_response"):
        limitation_type = state.get("_limitation_type", "unknown")
        logger.log(f"🚫 [Synthesizer] Responding to capability limitation: {limitation_type}")
        
        # Get availability-aware response for limitations that redirect to human help
        try:
            limitation_response = await get_limitation_response_with_availability(limitation_type)
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] Error getting availability-aware response: {str(e)}")
            limitation_response = state.get("_limitation_response", 
                "I can't help with that directly. Please contact a librarian at (513) 529-4141 or visit https://www.lib.miamioh.edu/research/research-support/ask/")
        
        # Validate URLs before returning
        validated_msg, had_invalid_urls = await validate_and_clean_response(
            limitation_response, 
            log_callback=logger.log
        )
        state["final_answer"] = validated_msg
        state["needs_human"] = True
        return state
    
    # 🏠 Handle library address queries EARLY (before other checks)
    if state.get("_library_address_query"):
        logger.log("📍 [Synthesizer] Providing library address (early check)")
        from src.tools.libcal_comprehensive_tools import _extract_building_from_query
        
        # Hardcoded fallback data (no DB needed)
        LIBRARY_DATA = {
            "king": {"displayName": "Edgar W. King Library", "address": "151 S. Campus Ave, Oxford, OH 45056", "phone": "(513) 529-4141", "website": "https://www.lib.miamioh.edu/"},
            "art": {"displayName": "Art & Architecture Library", "address": "Alumni Hall, Oxford, OH 45056", "phone": "(513) 529-6638", "website": "https://www.lib.miamioh.edu/"},
            "hamilton": {"displayName": "Rentschler Library", "address": "1601 University Blvd, Hamilton, OH 45011", "phone": "(513) 785-3235", "website": "https://www.ham.miamioh.edu/library/"},
            "middletown": {"displayName": "Gardner-Harvey Library", "address": "4200 N. University Blvd, Middletown, OH 45042", "phone": "(513) 727-3222", "website": "https://www.mid.miamioh.edu/library/"},
        }
        
        library_name = _extract_building_from_query(user_msg)
        logger.log(f"📍 [Synthesizer] Looking up: {library_name}")
        
        # Try database first, fall back to hardcoded data
        contact_info = None
        try:
            from src.services.location_service import get_location_service
            location_service = get_location_service()
            contact_info = await location_service.get_library_contact_info(library_name)
            logger.log(f"✅ [Synthesizer] Got contact info from database")
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] DB error: {type(e).__name__}, using fallback data")
        
        # Use hardcoded fallback if DB failed
        if not contact_info:
            key = library_name.lower() if library_name else "king"
            if key in ["rentschler", "hamilton"]:
                key = "hamilton"
            elif key in ["gardner", "gardner-harvey", "middletown"]:
                key = "middletown"
            elif key not in LIBRARY_DATA:
                key = "king"
            contact_info = LIBRARY_DATA.get(key, LIBRARY_DATA["king"])
            logger.log(f"📝 [Synthesizer] Using fallback data for: {key}")
        
        display_name = contact_info.get("displayName", "Library")
        address = contact_info.get("address", "N/A")
        phone = contact_info.get("phone", "N/A")
        website = contact_info.get("website", "https://www.lib.miamioh.edu/")
        
        address_msg = f"**{display_name}**\n\n"
        address_msg += f"📍 **Address:** {address}\n\n"
        address_msg += f"📞 **Phone:** {phone}\n\n"
        address_msg += f"🌐 **Website:** {website}"
        
        state["final_answer"] = address_msg
        return state
    
    # 💬 Handle live chat / Ask Us hours queries
    if state.get("_live_chat_hours_query"):
        logger.log("💬 [Synthesizer] Providing live chat hours from Ask Us API")
        from src.api.askus_hours import get_askus_hours_for_date
        
        try:
            hours_data = await get_askus_hours_for_date()
            is_open = hours_data.get("is_open", False)
            current_period = hours_data.get("current_period")
            hours_list = hours_data.get("hours", [])
            
            if is_open and current_period:
                chat_msg = (
                    f"**Live Chat with Librarians**\n\n"
                    f"✅ **Librarians are available NOW!**\n\n"
                    f"• Current hours: {current_period['open']} - {current_period['close']}\n"
                    f"• Start a chat: https://www.lib.miamioh.edu/research/research-support/ask/\n\n"
                    f"Our librarians can help with research questions, finding resources, and more."
                )
            elif hours_list:
                # Show today's schedule
                schedule_lines = []
                for period in hours_list:
                    schedule_lines.append(f"• {period.get('from', '')} - {period.get('to', '')}")
                
                chat_msg = (
                    f"**Live Chat with Librarians**\n\n"
                    f"⏰ **Today's Live Chat Hours:**\n"
                    f"{chr(10).join(schedule_lines)}\n\n"
                    f"• Chat link: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                    f"• Phone: (513) 529-4141\n\n"
                    f"Outside chat hours? Submit a ticket and we'll respond as soon as possible!"
                )
            else:
                chat_msg = (
                    f"**Live Chat with Librarians**\n\n"
                    f"Live chat hours vary. Please check:\n"
                    f"• https://www.lib.miamioh.edu/research/research-support/ask/\n\n"
                    f"You can also:\n"
                    f"• Submit a ticket for help anytime\n"
                    f"• Call: (513) 529-4141"
                )
            
            state["final_answer"] = chat_msg
            return state
            
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] Error getting Ask Us hours: {str(e)}")
            state["final_answer"] = (
                "**Live Chat with Librarians**\n\n"
                "For live chat hours, please visit:\n"
                "• https://www.lib.miamioh.edu/research/research-support/ask/\n\n"
                "You can also call: (513) 529-4141"
            )
            return state
    
    # 👤 Handle personal library account queries
    if state.get("_personal_account_query"):
        logger.log("👤 [Synthesizer] Providing library account URL for personal account query")
        
        account_url = "https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en"
        
        account_msg = (
            "**My Library Account**\n\n"
            "To view your personal library account information (loans, fines, requests, holds, messages), "
            "please sign in to your account:\n\n"
            f"🔗 **[Access My Library Account]({account_url})**\n\n"
            "From your account you can:\n"
            "• View your current **loans** and due dates\n"
            "• Check any **fines or fees**\n"
            "• See your **requests** and holds\n"
            "• View **blocks** or messages on your account\n"
            "• Update your **personal details** and settings\n\n"
            "If you need help with your account, call us at **(513) 529-4141**."
        )
        
        state["final_answer"] = account_msg
        return state
    
    # Handle catalog search requests (not available)
    # Triggered by: discovery_search intent OR _catalog_search_requested flag from regex pattern
    if intent == "discovery_search" or state.get("_catalog_search_requested"):
        logger.log("📚 [Synthesizer] Catalog search requested - service not available")
        from src.api.askus_hours import get_askus_hours_for_date
        
        base_msg = """I'd love to help you find those materials! However, our catalog search feature is currently unavailable.

**To search for books, articles, and e-resources, please:**

• **Use our online catalog directly**: https://www.lib.miamioh.edu/
• **Call us**: (513) 529-4141

"""
        
        try:
            hours_data = await get_askus_hours_for_date()
            is_open = hours_data.get("is_open", False)
            current_period = hours_data.get("current_period")
            hours_list = hours_data.get("hours", [])
            
            if is_open and current_period:
                availability_msg = (
                    f"✅ **Librarians are available NOW** (until {current_period['close']})\n"
                    f"Our librarians are experts at finding exactly what you need - they can help with specific article requirements, page counts, and topic searches.\n\n"
                    f"**Chat with a librarian**: https://www.lib.miamioh.edu/research/research-support/ask/"
                )
            elif hours_list and len(hours_list) > 0:
                next_open = hours_list[0].get("from")
                next_close = hours_list[0].get("to")
                availability_msg = (
                    f"⏰ **Live chat hours today**: {next_open} - {next_close}\n"
                    f"Our librarians are experts at finding exactly what you need.\n\n"
                    f"**Submit a ticket for off-hours help**: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                    f"Or come back during chat hours to talk to a librarian live."
                )
            else:
                availability_msg = (
                    "**Submit a ticket** and our librarians will help you find the materials you need:\n"
                    "https://www.lib.miamioh.edu/research/research-support/ask/"
                )
            
            catalog_unavailable_msg = base_msg + availability_msg
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] Error checking availability: {str(e)}")
            catalog_unavailable_msg = base_msg + "• **Chat with a librarian or submit a ticket**: https://www.lib.miamioh.edu/research/research-support/ask/"
        
        # Validate URLs before returning
        validated_msg, had_invalid_urls = await validate_and_clean_response(
            catalog_unavailable_msg, 
            log_callback=logger.log
        )
        state["final_answer"] = validated_msg
        state["needs_human"] = True
        return state
    
    # Handle library website queries
    if state.get("_library_website_query"):
        logger.log("🌐 [Synthesizer] Providing library/space website URL from database")
        from src.services.location_service import get_location_service
        from src.tools.libcal_comprehensive_tools import _extract_building_from_query
        
        # Extract library/space name using centralized function (handles all variations)
        library_name = _extract_building_from_query(user_msg)
        logger.log(f"🌐 [Synthesizer] Extracted library/space name: {library_name}")
        
        try:
            location_service = get_location_service()
            # location_service handles libraries, campuses, and spaces (makerspace, special collections)
            website = await location_service.get_library_website(library_name)
            
            # Get display name from database
            contact_info = await location_service.get_library_contact_info(library_name)
            if contact_info:
                display_name = contact_info.get("displayName", "Library")
            else:
                # For spaces like Makerspace, try to get a reasonable display name
                if library_name == "makerspace":
                    display_name = "Makerspace"
                elif library_name == "special collections":
                    display_name = "Special Collections & University Archives"
                else:
                    display_name = "Library"
            
            website_msg = f"**{display_name} Website:**\n\n{website}"
        except Exception as e:
            logger.log(f"⚠️ [Synthesizer] Error getting website from database: {str(e)}")
            website_msg = "I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141."
        
        state["final_answer"] = website_msg
        return state
    
    # Handle out-of-scope questions
    if state.get("out_of_scope"):
        logger.log("🚫 [Synthesizer] Providing out-of-scope response")
        out_of_scope_msg = f"""I appreciate your question, but that's outside the scope of library services. I can only help with library-related questions such as:

• Library hours and study room reservations
• Subject librarians and research guides
• Library policies and services

For questions about general university matters, admissions, courses, or campus services, please visit:
• **Miami University Main Website**: https://miamioh.edu
• **University Information**: (513) 529-0001

For immediate library assistance, you can:
• **Chat with a librarian or leave a ticket**: https://www.lib.miamioh.edu/research/research-support/ask/
• **Call us**: (513) 529-4141
• **Visit our website**: https://www.lib.miamioh.edu

Is there anything library-related I can help you with?"""
        # Validate URLs before returning
        logger.log("🔍 [URL Validator] Checking URLs in out-of-scope message")
        validated_msg, had_invalid_urls = await validate_and_clean_response(
            out_of_scope_msg, 
            log_callback=logger.log
        )
        if had_invalid_urls:
            logger.log("⚠️ [URL Validator] Removed invalid URLs from out-of-scope message")
        
        state["final_answer"] = validated_msg
        return state
    
    responses = state.get("agent_responses", {})
    
    if state.get("needs_human"):
        # If any agent requested human handoff, prioritize that
        for resp in responses.values():
            if resp.get("needs_human"):
                state["final_answer"] = resp.get("text", "Let me connect you with a librarian.")
                return state
    
    # Combine agent outputs with PRIORITY ORDER
    # Priority: API functions > RAG > Google Site Search
    priority_order = {
        "libcal": 1,          # API: Hours & reservations
        "libguide": 1,        # API: Research guides
        "subject_librarian": 1, # API: Subject librarian routing
        "libchat": 1,         # API: Chat handoff
        "google_site": 2,      # Website search (LOWER PRIORITY - fallback only)
        "transcript_rag": 3,  # RAG: Correction pool for fixing mistakes
    }
    
    # Sort responses by priority
    sorted_responses = sorted(
        responses.items(),
        key=lambda x: priority_order.get(x[0], 99)  # Unknown agents get lowest priority
    )
    
    context_parts = []
    for agent_name, resp in sorted_responses:
        if resp.get("success"):
            # Add priority label for RAG to emphasize it in synthesis
            priority_label = ""
            if agent_name == "transcript_rag":
                priority_label = " [CURATED KNOWLEDGE BASE - HIGH PRIORITY]"
            elif priority_order.get(agent_name, 99) == 1:
                priority_label = " [VERIFIED API DATA]"
            elif agent_name == "google_site":
                priority_label = " [WEBSITE SEARCH - USE ONLY IF NO BETTER SOURCE]"
            
            context_parts.append(f"[{resp.get('source', agent_name)}{priority_label}]: {resp.get('text', '')}")
    
    if not context_parts:
        error_msg = "I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141."
        # Validate URLs before returning
        logger.log("🔍 [URL Validator] Checking URLs in error message")
        validated_msg, had_invalid_urls = await validate_and_clean_response(
            error_msg, 
            log_callback=logger.log
        )
        if had_invalid_urls:
            logger.log("⚠️ [URL Validator] Removed invalid URLs from error message")
        
        state["final_answer"] = validated_msg
        return state
    
    context = "\n\n".join(context_parts)
    
    # 🎯 NEW: Detect if this is a factual query requiring strict grounding
    fact_types = detect_factual_query_type(user_msg)
    rag_response = responses.get("transcript_rag", {})
    
    # Check if we should enforce strict grounding
    use_strict_grounding = should_enforce_strict_grounding(user_msg, rag_response)
    
    if use_strict_grounding:
        logger.log(f"🔒 [Fact Grounding] Detected factual query types: {', '.join(fact_types)}")
        
        # 🚨 CRITICAL: Remove google_site from responses to prevent conflicting information
        if "google_site" in responses:
            logger.log("⚠️ [Fact Grounding] Removing Google Site Search - using RAG only for factual accuracy")
            del responses["google_site"]
            # Update context to exclude google_site
            sorted_responses = [(k, v) for k, v in sorted_responses if k != "google_site"]
            context_parts = []
            for agent_name, resp in sorted_responses:
                if resp.get("success"):
                    priority_label = ""
                    if agent_name == "transcript_rag":
                        priority_label = " [CURATED KNOWLEDGE BASE - HIGH PRIORITY]"
                    elif priority_order.get(agent_name, 99) == 1:
                        priority_label = " [VERIFIED API DATA]"
                    context_parts.append(f"[{resp.get('source', agent_name)}{priority_label}]: {resp.get('text', '')}")
            context = "\n\n".join(context_parts)
        
        # Check RAG confidence
        confidence_level, confidence_reason = await is_high_confidence_rag_match(rag_response)
        logger.log(f"📊 [Fact Grounding] RAG confidence: {confidence_reason}")
        
        # Only escalate if confidence is explicitly low AND similarity is very low
        if confidence_level == "low" and rag_response.get("similarity_score", 0) < 0.45:
            logger.log("⚠️ [Fact Grounding] Very low confidence for factual query - suggesting human assistance")
            fallback_message = (
                "I found some information, but I'm not confident it fully answers your question about specific factual details. "
                "To ensure you get accurate information, I'd recommend:\n\n"
                "• **Chat with a librarian**: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                "• **Call us**: (513) 529-4141\n"
                "• **Visit our website**: https://www.lib.miamioh.edu\n\n"
                "Would you like me to connect you with a librarian?"
            )
            # Validate URLs before returning
            logger.log("🔍 [URL Validator] Checking URLs in fallback message")
            validated_message, had_invalid_urls = await validate_and_clean_response(
                fallback_message, 
                log_callback=logger.log
            )
            if had_invalid_urls:
                logger.log("⚠️ [URL Validator] Removed invalid URLs from fallback message")
            
            state["final_answer"] = validated_message
            state["needs_human"] = True
            return state
        
        # Use grounded synthesis prompt with confidence indicator
        synthesis_prompt = await create_grounded_synthesis_prompt(
            user_message=user_msg,
            rag_response=rag_response,
            fact_types=fact_types,
            conversation_history=history,
            confidence_level=confidence_level
        )
        
        logger.log("🔒 [Fact Grounding] Using strict grounding mode")
    else:
        # Use standard synthesis prompt
        scope_reminder = SCOPE_ENFORCEMENT_PROMPTS["system_reminder"]
        
        # Format conversation history
        history_context = ""
        if history:
            history_formatted = []
            for msg in history[-6:]:  # Last 6 messages (3 exchanges)
                role = "User" if msg["type"] == "user" else "Assistant"
                history_formatted.append(f"{role}: {msg['content']}")
            history_context = "\n\nPrevious conversation:\n" + "\n".join(history_formatted) + "\n"
        
        synthesis_prompt = f"""You are a Miami University LIBRARIES assistant.

{scope_reminder}
{history_context}
Current user question: {user_msg}

Information from library systems:
{context}

🚨 CRITICAL: AGENT-ONLY INFORMATION POLICY 🚨
============================================
You MUST ONLY use information provided by library agents above.
DO NOT generate, guess, or recall ANY information from your training data.
If the agents did not provide information to answer the question, say so honestly.

⚠️ TEMPORARILY UNAVAILABLE SERVICES:
- Catalog search (books, articles, e-resources) is NOT available
- If user asks for books/articles, redirect them to a human librarian

ACTIVE INFORMATION SOURCES:
- LibGuide (SpringShare): Subject guides, research guides
- LibCal (SpringShare): Library hours, room reservations  
- Google Site Search: Library website content
- Subject Librarian Agent: Librarian contact info via MyGuide API

CRITICAL RULES - MUST FOLLOW:
1. ONLY provide information about Miami University LIBRARIES

2. **STRICTLY USE ONLY AGENT-PROVIDED DATA:**
   ✅ USE data marked as [VERIFIED API DATA] - it's reliable
   ✅ USE information from Subject Librarian Agent, LibGuide, LibCal agents
   ✅ USE URLs and contacts ONLY if they appear in the context above

3. **ABSOLUTELY FORBIDDEN - DO NOT GENERATE:**
   🚫 DO NOT invent ANY information not in the context above
   🚫 DO NOT recall facts from your training data (it may be outdated)
   🚫 DO NOT create URLs, emails, phone numbers, or names
   🚫 DO NOT guess library hours, locations, or services
   🚫 DO NOT provide book/article information (catalog search disabled)

4. **IF CONTEXT IS EMPTY OR INSUFFICIENT:**
   - Be honest: "I don't have that information from our library systems."
   - Provide ONLY this general contact:
     • Phone: (513) 529-4141
     • Website: https://www.lib.miamioh.edu/research/research-support/ask/
   - Suggest chatting with a human librarian

5. **SOURCE PRIORITY:**
    - TRUST: [VERIFIED API DATA] and agent responses
    - Use cautiously: [WEBSITE SEARCH] results (URLs must be from context)
    - If no agent data available, redirect to human librarian

6. **Response Guidelines:**
    - Answer questions directly when you have verified agent data
    - Be honest when you don't have information - don't make things up
    - Redirect to human librarian for catalog/book searches
    
    **Example of GOOD response:**
    Context: "Source: Subject Librarian Agent (MyGuide + LibGuides API)
             For computer science research help, contact Andy Revelle (revellaa@miamioh.edu)"
    → Answer: "For computer science research help, contact Andy Revelle at revellaa@miamioh.edu"
    
    **Example of BAD response (being overly cautious):**
    Context: [same as above]
    → DON'T say: "I'm having trouble accessing our systems. Please visit..."
    → This is WRONG because you DO have verified data!

12. If question seems outside library scope, politely redirect to appropriate service
13. Use the conversation history to provide contextual follow-up responses

STUDY ROOM BOOKING RULES - EXTREMELY IMPORTANT:
- NEVER say "checking availability", "let me check", "I'll look for", or similar status updates
- The backend handles all availability checking automatically
- Room bookings require ALL of the following information:
  * First name
  * Last name
  * @miamioh.edu email address
  * Date (YYYY-MM-DD format)
  * Start time and end time (HH:MM 24-hour format)
  * Number of people
  * Building preference
- ONLY present the FINAL result from the context:
  1. If missing information: Ask for the specific missing details (especially first name, last name, email)
  2. If no rooms are available: State directly that no rooms are available
  3. If booking confirmed: Present the confirmation number and mention the confirmation email
- DO NOT provide intermediate status messages about what you're doing

WARNING - ABSOLUTELY FORBIDDEN - NEVER DO THIS:
- NEVER output JSON, code, or programming syntax
- NEVER show API responses or data structures
- NEVER use curly braces, square brackets, or code formatting
- NEVER output technical/system information
- NEVER show raw data - ALWAYS convert to human-readable sentences

FORMATTING GUIDELINES:
- Write in complete, natural sentences like you're talking to a person
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks
- Use bullet points (•) for lists, NOT JSON or arrays
- Highlight actionable information and links
- Keep paragraphs concise (2-3 sentences max)
- Use natural, conversational, HUMAN language
- ALWAYS present information in readable paragraph/list format

Provide a clear, helpful answer based ONLY on the information above. Be concise, friendly, and cite sources. If the information doesn't fully answer the question, suggest contacting a librarian."""
    
    # 🎯 Generate final response
    logger.log("💬 [Synthesizer] Generating final response")
    
    messages = [
        SystemMessage(content="You are a Miami University LIBRARIES assistant. KEY RULES: 1) TRUST and USE data marked as [VERIFIED API DATA] or from 'Subject Librarian Agent' - it's already validated, so answer confidently! 2) NEVER invent information if context is empty - provide library general contact instead. 3) For factual queries, ONLY use the provided context - NEVER supplement with your training data. Write in natural, conversational language. NEVER output JSON or code. Balance: Be helpful when you have verified data, be cautious only when context is missing."),
        HumanMessage(content=synthesis_prompt)
    ]
    
    response = await llm.ainvoke(messages)
    raw_answer = response.content.strip()
    
    # 🎯 NEW: Verify factual claims if strict grounding was used
    if use_strict_grounding and fact_types:
        logger.log("🔍 [Fact Verifier] Checking factual claims against RAG context")
        rag_context = rag_response.get("text", "")
        all_verified, issues = await verify_factual_claims_against_rag(
            generated_text=raw_answer,
            rag_context=rag_context,
            query=user_msg,
            log_callback=logger.log
        )
        
        if not all_verified:
            logger.log(f"🚨 [Fact Verifier] HALLUCINATION DETECTED - Found {len(issues)} unverified claim(s)")
            for issue in issues:
                logger.log(f"   ❌ {issue}")
            
            # 🚨 CRITICAL: For date queries, extract correct years from RAG and use directly
            if "date" in fact_types:
                import re
                # Extract all 4-digit years from RAG context
                rag_years = re.findall(r'\b(19\d{2}|20\d{2})\b', rag_context)
                if rag_years:
                    logger.log(f"✅ [Fact Verifier] Correct years from RAG: {', '.join(rag_years)}")
                    # Replace the answer with RAG text directly to avoid hallucination
                    logger.log("🔄 [Fact Verifier] Using RAG answer directly (bypassing LLM synthesis)")
                    raw_answer = rag_context.strip()
                else:
                    logger.log("⚠️ [Fact Verifier] No years found in RAG, suggesting human assistance")
                    raw_answer = (
                        "I found some information but want to ensure you get accurate dates. "
                        "For the most accurate information about construction dates, please contact our library staff at "
                        "(513) 529-4141 or visit https://www.lib.miamioh.edu/research/research-support/ask/"
                    )
        else:
            logger.log("✅ [Fact Verifier] All factual claims verified against RAG")
    
    # Validate and clean URLs in the response
    logger.log("🔍 [URL Validator] Checking URLs in response")
    validated_answer, had_invalid_urls = await validate_and_clean_response(
        raw_answer, 
        log_callback=logger.log,
        agents_used=state.get("selected_agents", [])
    )
    
    if had_invalid_urls:
        logger.log("⚠️ [URL Validator] Removed invalid URLs from response")
    
    state["final_answer"] = validated_answer
    
    # Extract token usage from response metadata
    if hasattr(response, 'response_metadata') and 'token_usage' in response.response_metadata:
        usage = response.response_metadata['token_usage']
        state["token_usage"] = {
            "model": response.response_metadata.get('model_name', OPENAI_MODEL),
            "prompt_tokens": usage.get('prompt_tokens', 0),
            "completion_tokens": usage.get('completion_tokens', 0),
            "total_tokens": usage.get('total_tokens', 0)
        }
    
    return state

def should_end(state: AgentState) -> str:
    """Decide if we should end or continue."""
    return END

# Build the graph
def create_library_graph():
    """Create the LangGraph orchestrator with Query Understanding Layer."""
    workflow = StateGraph(AgentState)
    
    # Add nodes - Query Understanding Layer is the entry point
    workflow.add_node("understand_query", query_understanding_node)
    workflow.add_node("clarify", clarification_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("execute_agents", execute_agents_node)
    workflow.add_node("synthesize", synthesize_answer_node)
    
    # Set entry point to Query Understanding Layer
    workflow.set_entry_point("understand_query")
    
    # Conditional edge: after understanding, either clarify or proceed to classification
    workflow.add_conditional_edges(
        "understand_query",
        should_skip_to_clarification,
        {
            "clarify": "clarify",      # Ambiguous query → ask for clarification
            "classify": "classify_intent"  # Clear query → proceed to classification
        }
    )
    
    # Clarification ends the flow (user needs to respond)
    workflow.add_edge("clarify", END)
    
    # Normal flow: classify → execute → synthesize → end
    workflow.add_edge("classify_intent", "execute_agents")
    workflow.add_edge("execute_agents", "synthesize")
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()

# Create singleton graph instance
library_graph = create_library_graph()
