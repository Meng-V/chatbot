"""LangGraph state schema for Miami University Libraries chatbot."""
from typing import TypedDict, Literal, Optional, List, Dict, Any
from langgraph.graph import MessagesState

class AgentState(MessagesState):
    """State for the library chatbot graph."""
    user_message: str
    classified_intent: Optional[str] = None
    selected_agents: List[str] = []
    agent_responses: Dict[str, Any] = {}
    final_answer: str = ""
    needs_human: bool = False
    error: Optional[str] = None

# Intent types based on screenshot
IntentType = Literal[
    "discovery_search",      # Primo Agent
    "course_subject_help",   # LibGuide/MyGuide Agent
    "booking_or_hours",      # LibCal Agent
    "policy_or_service",     # Google Site Search Agent
    "human_help",            # LibChat Agent
    "general_question"       # Transcript RAG Agent
]
