"""LangGraph state schema for Miami University Libraries chatbot."""
from typing import TypedDict, Literal, Optional, List, Dict, Any
from langgraph.graph import MessagesState

class AgentState(MessagesState):
    """State for the library chatbot graph."""
    user_message: str
    conversation_id: Optional[str] = None  # Conversation ID for tracking
    classified_intent: Optional[str] = None
    selected_agents: List[str] = []
    agent_responses: Dict[str, Any] = {}
    final_answer: str = ""
    needs_human: bool = False
    error: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = []  # Previous messages for context
    token_usage: Optional[Dict[str, Any]] = None  # Token usage tracking
    tool_executions: List[Dict[str, Any]] = []  # Detailed tool execution logs
    
    # Query Understanding Layer fields
    original_query: Optional[str] = None  # Original user input before processing
    processed_query: Optional[str] = None  # Translated/simplified query for system
    query_understanding: Optional[Dict[str, Any]] = None  # Full understanding result
    needs_clarification: bool = False  # Flag to request user clarification
    clarifying_question: Optional[str] = None  # Question to ask user if ambiguous
    query_type_hint: Optional[str] = None  # Hint for routing from understanding layer

# Intent types based on screenshot
IntentType = Literal[
    "discovery_search",      # Primo Agent
    "course_subject_help",   # LibGuide/MyGuide Agent
    "booking_or_hours",      # LibCal Agent
    "policy_or_service",     # Google Site Search Agent
    "human_help",            # LibChat Agent
    "general_question"       # Transcript RAG Agent
]
