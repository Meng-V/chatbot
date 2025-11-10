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
# Comprehensive multi-tool agents
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
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

Classify the user's question into ONE of these categories:

1. **discovery_search** - Searching for books, articles, journals, e-resources, call numbers, catalog items
   Examples: "Do you have The Great Gatsby?", "Find articles on climate change", "What's the call number for..."

2. **course_subject_help** - Course guides, subject librarians, recommended databases for a major/class
   Examples: "Who's the librarian for ENG 111?", "What databases for biology?", "Guide for PSY 201"

3. **booking_or_hours** - Building hours, room reservations, library schedule
   Examples: "What time does King Library close?", "Book a study room", "Library hours tomorrow"

4. **policy_or_service** - Policies, services, renewals, printing, fines, access info
   Examples: "How do I renew a book?", "Can I print here?", "What's the late fee?"

5. **human_help** - User explicitly wants to talk to a person
   Examples: "Can I talk to someone?", "Connect me to a librarian", "I need human help"

6. **general_question** - General library questions not fitting above (use RAG)
   Examples: "How can I print in the library?", "Where is the quiet study area?"

Respond with ONLY the category name (e.g., discovery_search). No explanation."""

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
    
    # Map intent to agents (multi-tool agents can handle sub-routing internally)
    agent_mapping = {
        "discovery_search": ["primo"],  # Primo agent will route to search/availability tool
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
    responses = state["agent_responses"]
    intent = state["classified_intent"]
    user_msg = state["user_message"]
    logger = state.get("_logger") or AgentLogger()
    
    logger.log("🤖 [Synthesizer] Generating final answer")
    
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
        state["final_answer"] = "I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian."
        return state
    
    context = "\n\n".join(context_parts)
    
    synthesis_prompt = f"""You are a helpful Miami University Libraries assistant.

User question: {user_msg}

Information from library systems:
{context}

FORMATTING GUIDELINES:
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks
- Use inline bullet points (•) instead of dashes when listing 2-3 items
- For longer lists, use compact formatting with minimal spacing
- Highlight actionable information and links
- Keep paragraphs concise (2-3 sentences max)
- Use natural, conversational language

Provide a clear, helpful answer based on the information above. Be concise, friendly, and cite sources when relevant. If the information doesn't fully answer the question, suggest talking to a librarian."""
    
    messages = [
        SystemMessage(content="You are a Miami University Libraries assistant. Format responses to be compact, modern, and easy to scan. Use bold for key info."),
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
