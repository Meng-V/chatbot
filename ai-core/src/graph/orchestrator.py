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
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
from src.agents.subject_librarian_agent import find_subject_librarian_query
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

# Use o4-mini as specified
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter, only use it for other models
llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
llm = ChatOpenAI(**llm_kwargs)

ROUTER_SYSTEM_PROMPT = """You are a classification assistant for Miami University Libraries.

CRITICAL SCOPE RULE:
- ONLY classify questions about MIAMI UNIVERSITY LIBRARIES
- If question is about general Miami University, admissions, courses, housing, dining, campus life, or non-library services, respond with: out_of_scope
- If question is about homework help, assignments, or academic content, respond with: out_of_scope

IN-SCOPE LIBRARY QUESTIONS - Classify into ONE of these categories:

1. **discovery_search** - Searching for books, articles, journals, e-resources, call numbers, catalog items
   Examples: "Do you have The Great Gatsby?", "Find articles on climate change", "What's the call number for..."

2. **subject_librarian** - Finding subject librarian, LibGuides for a specific major, department, or academic subject. ALSO use for general questions about all subject librarians.
   Examples: "Who's the biology librarian?", "LibGuide for accounting", "I need help with psychology research", "list of subject librarians", "show me all subject librarians", "subject librarian map"

3. **course_subject_help** - Course guides, recommended databases for a specific class
   Examples: "What databases for ENG 111?", "Guide for PSY 201", "Resources for CHM 201"

4. **booking_or_hours** - Library building hours, room reservations, library schedule
   Examples: "What time does King Library close?", "Book a study room", "Library hours tomorrow"

5. **policy_or_service** - Library policies, services, renewals, printing, fines, access info
   Examples: "How do I renew a book?", "Can I print in library?", "What's the late fee for library books?"

6. **human_help** - User explicitly wants to talk to a librarian
   Examples: "Can I talk to a librarian?", "Connect me to library staff", "I need human help"

7. **general_question** - General library questions not fitting above (use RAG)
   Examples: "How can I print in the library?", "Where is the quiet study area?"

OUT-OF-SCOPE (respond with: out_of_scope):
- General university questions, admissions, financial aid, tuition
- Course content, homework, assignments, test prep
- IT support, Canvas help, email issues
- Housing, dining, parking
- Student organizations, campus events

Respond with ONLY the category name (e.g., discovery_search or out_of_scope). No explanation."""

async def classify_intent_node(state: AgentState) -> AgentState:
    """Meta Router: classify user intent using LLM."""
    user_msg = state["user_message"]
    logger = state.get("_logger") or AgentLogger()
    
    logger.log("🧠 [Meta Router] Classifying user intent", {"query": user_msg})
    
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
    
    # Map intent to agents (multi-tool agents can handle sub-routing internally)
    agent_mapping = {
        "discovery_search": ["primo"],  # Primo agent will route to search/availability tool
        "subject_librarian": ["subject_librarian"],  # MuGuide + LibGuides API for subject-to-librarian routing
        "course_subject_help": ["libguide", "transcript_rag"],
        "booking_or_hours": ["libcal"],  # LibCal agent will route to hours/rooms/reservation tool
        "policy_or_service": ["google_site", "transcript_rag"],  # Google agent handles site search
        "human_help": ["libchat"],
        "general_question": ["transcript_rag", "google_site"]
    }
    
    agents = agent_mapping.get(intent, ["transcript_rag"])
    
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
primo_agent = PrimoAgent()
libcal_agent = LibCalComprehensiveAgent()
libguide_agent = LibGuideComprehensiveAgent()
google_site_agent = GoogleSiteComprehensiveAgent()

async def execute_agents_node(state: AgentState) -> AgentState:
    """Execute selected agents in parallel."""
    agents = state["selected_agents"]
    logger = state.get("_logger") or AgentLogger()
    results = {}
    
    logger.log(f"⚡ [Orchestrator] Executing {len(agents)} agent(s) in parallel")
    
    # Map agent names to agent instances (comprehensive multi-tool) or functions (legacy)
    agent_map = {
        "primo": primo_agent,
        "libcal": libcal_agent,
        "libguide": libguide_agent,
        "google_site": google_site_agent,
        # Subject-to-librarian routing agent
        "subject_librarian": find_subject_librarian_query,
        # Legacy function-based agents
        "libchat": libchat_handoff,
        "transcript_rag": transcript_rag_query
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
    intent = state["classified_intent"]
    user_msg = state["user_message"]
    history = state.get("conversation_history", [])
    logger = state.get("_logger") or AgentLogger()
    
    logger.log("🤖 [Synthesizer] Generating final answer", {"history_messages": len(history)})
    
    # Handle out-of-scope questions
    if state.get("out_of_scope"):
        logger.log("🚫 [Synthesizer] Providing out-of-scope response")
        out_of_scope_msg = f"""I appreciate your question, but that's outside the scope of library services. I can only help with library-related questions such as:

• Finding books, articles, and research materials
• Library hours and study room reservations
• Subject librarians and research guides
• Library policies and services

For questions about general university matters, admissions, courses, or campus services, please visit:
• **Miami University Main Website**: https://miamioh.edu
• **University Information**: (513) 529-1809

For immediate library assistance, you can:
• **Chat with a librarian**: https://www.lib.miamioh.edu/research/research-support/ask/
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
        "primo": 1,           # API: Catalog search
        "libcal": 1,          # API: Hours & reservations
        "libguide": 1,        # API: Research guides
        "subject_librarian": 1, # API: Subject librarian routing
        "libchat": 1,         # API: Chat handoff
        "transcript_rag": 2,  # RAG: Curated knowledge base (HIGHER PRIORITY)
        "google_site": 3      # Website search (LOWER PRIORITY - fallback only)
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
        is_confident, confidence_reason = await is_high_confidence_rag_match(rag_response)
        logger.log(f"📊 [Fact Grounding] RAG confidence: {confidence_reason}")
        
        # If RAG has low confidence for factual query, escalate to human
        if not is_confident and rag_response.get("similarity_score", 0) < 0.70:
            logger.log("⚠️ [Fact Grounding] Low confidence for factual query - suggesting human assistance")
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
        
        # Use grounded synthesis prompt
        synthesis_prompt = await create_grounded_synthesis_prompt(
            user_message=user_msg,
            rag_response=rag_response,
            fact_types=fact_types,
            conversation_history=history
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

CRITICAL RULES - MUST FOLLOW:
1. ONLY provide information about Miami University LIBRARIES

2. **WHEN TO TRUST DATA:**
   ✅ ALWAYS TRUST data marked as [VERIFIED API DATA] or from "Subject Librarian Agent (MyGuide + LibGuides API)"
   ✅ Use librarian names, emails, and links from these verified sources CONFIDENTLY
   ✅ These sources have already been validated - use them without hesitation

3. **WHAT YOU MUST NEVER MAKE UP (only if NOT in context):**
   🚫 DO NOT invent email addresses if none are provided
   🚫 DO NOT create fake librarian names like "Dr. John Smith" if not in context
   🚫 DO NOT generate phone numbers (except library main: 513-529-4141)
   🚫 DO NOT make up URLs if none are provided

4. **How to Use Context:**
   - If context contains librarian names/emails → USE THEM (they're verified!)
   - If context is empty or doesn't answer the question → Provide general library contact
   - NEVER supplement context with made-up information from your training data

5. ONLY use URLs that appear EXACTLY in the context above
6. Allowed URL domains ONLY:
   - lib.miamioh.edu
   - libguides.lib.miamioh.edu
   - digital.lib.miamioh.edu
7. NEVER create URLs even if they look correct - only use URLs from context
8. If the context says "verified from LibGuides API" - use that data EXACTLY as provided
9. If contact info is not in the context, provide ONLY this general library contact:
   - Phone: (513) 529-4141
   - Website: https://www.lib.miamioh.edu/research/research-support/ask/
10. **SOURCE PRIORITY:**
    - TRUST and USE: [VERIFIED API DATA] and "Subject Librarian Agent" responses
    - TRUST and USE: [CURATED KNOWLEDGE BASE - HIGH PRIORITY] (TranscriptRAG)
    - Use cautiously: [WEBSITE SEARCH] (verify URLs match allowed domains)
    - If sources conflict, prefer API data over other sources

11. **Response Guidelines:**
    - Answer questions directly and helpfully when you have verified data
    - Only redirect to general contact if context truly doesn't have the answer
    - Don't be overly cautious - if data is marked as verified, USE IT!
    
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
  2. If no rooms available: State directly that no rooms are available
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
        log_callback=logger.log
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
    """Create the LangGraph orchestrator."""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("execute_agents", execute_agents_node)
    workflow.add_node("synthesize", synthesize_answer_node)
    
    # Add edges
    workflow.set_entry_point("classify_intent")
    workflow.add_edge("classify_intent", "execute_agents")
    workflow.add_edge("execute_agents", "synthesize")
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()

# Create singleton graph instance
library_graph = create_library_graph()
