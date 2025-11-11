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

2. **subject_librarian** - Finding subject librarian, LibGuides for a specific major, department, or academic subject
   Examples: "Who's the biology librarian?", "LibGuide for accounting", "I need help with psychology research"

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
- IT support, Canvas help, email issues (unless library-specific)
- Housing, dining, parking (unless library-specific)
- Student organizations, campus events (unless library events)

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
    tasks = []
    for agent_name in agents:
        agent_or_func = agent_map.get(agent_name)
        if agent_or_func:
            # Check if it's a multi-tool agent (has execute method) or legacy function
            if hasattr(agent_or_func, 'execute'):
                # Multi-tool agent - call execute
                tasks.append(agent_or_func.execute(state["user_message"], log_callback=logger.log))
            else:
                # Legacy function-based agent
                tasks.append(agent_or_func(state["user_message"], log_callback=logger.log))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    for agent_name, response in zip(agents, responses):
        if isinstance(response, Exception):
            results[agent_name] = {"source": agent_name, "success": False, "error": str(response)}
        else:
            results[agent_name] = response
            if response.get("needs_human"):
                state["needs_human"] = True
    
    state["agent_responses"] = results
    state["_logger"] = logger
    
    logger.log(f"✅ [Orchestrator] All agents completed")
    
    return state

async def synthesize_answer_node(state: AgentState) -> AgentState:
    """Synthesize final answer from agent responses using LLM."""
    intent = state["classified_intent"]
    user_msg = state["user_message"]
    logger = state.get("_logger") or AgentLogger()
    
    logger.log("🤖 [Synthesizer] Generating final answer")
    
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
• **Chat with a librarian**: https://www.lib.miamioh.edu/contact
• **Call us**: (513) 529-4141
• **Visit our website**: https://www.lib.miamioh.edu

Is there anything library-related I can help you with?"""
        state["final_answer"] = out_of_scope_msg
        return state
    
    responses = state.get("agent_responses", {})
    
    if state.get("needs_human"):
        # If any agent requested human handoff, prioritize that
        for resp in responses.values():
            if resp.get("needs_human"):
                state["final_answer"] = resp.get("text", "Let me connect you with a librarian.")
                return state
    
    # Combine agent outputs
    context_parts = []
    for agent_name, resp in responses.items():
        if resp.get("success"):
            context_parts.append(f"[{resp.get('source', agent_name)}]: {resp.get('text', '')}")
    
    if not context_parts:
        state["final_answer"] = "I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141."
        return state
    
    context = "\n\n".join(context_parts)
    
    scope_reminder = SCOPE_ENFORCEMENT_PROMPTS["system_reminder"]
    
    synthesis_prompt = f"""You are a Miami University LIBRARIES assistant.

{scope_reminder}

User question: {user_msg}

Information from library systems:
{context}

CRITICAL RULES - MUST FOLLOW:
1. ONLY provide information about Miami University LIBRARIES
2. NEVER make up or generate:
   - Email addresses
   - Phone numbers
   - Librarian names (unless from the provided context/API)
   - Building names or locations
3. ONLY use contact information that appears in the context above
4. If contact info is not in the context, provide general library contact:
   - Phone: (513) 529-4141
   - Website: https://www.lib.miamioh.edu/contact
5. If question seems outside library scope, politely redirect to appropriate service

FORMATTING GUIDELINES:
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks
- Use inline bullet points (•) instead of dashes when listing 2-3 items
- For longer lists, use compact formatting with minimal spacing
- Highlight actionable information and links
- Keep paragraphs concise (2-3 sentences max)
- Use natural, conversational language

Provide a clear, helpful answer based ONLY on the information above. Be concise, friendly, and cite sources. If the information doesn't fully answer the question, suggest contacting a librarian."""
    
    messages = [
        SystemMessage(content="You are a Miami University LIBRARIES assistant. ONLY answer library questions. NEVER make up contact information. Format responses to be compact, modern, and easy to scan."),
        HumanMessage(content=synthesis_prompt)
    ]
    
    response = await llm.ainvoke(messages)
    state["final_answer"] = response.content.strip()
    
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
