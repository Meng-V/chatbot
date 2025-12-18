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
    
    # Special handling flags
    _library_address_query: bool = False  # Flag for address query handling
    _library_website_query: bool = False  # Flag for website query handling
    _catalog_search_requested: bool = False  # Flag for catalog search handling
    _limitation_response: Optional[str] = None  # Pre-built limitation response
    _limitation_type: Optional[str] = None  # Type of capability limitation
    _needs_availability_check: bool = False  # Flag for availability check in greeting
    _live_chat_hours_query: bool = False
    _personal_account_query: bool = False  # Flag for live chat/Ask Us hours query
    out_of_scope: bool = False  # Flag for out-of-scope questions
    _policy_type: Optional[str] = None  # Type of policy question (loan_periods, etc.)
    _policy_url: Optional[str] = None  # Authoritative URL for policy question
    _research_handoff_response: Optional[str] = None  # Pre-built research handoff response
    _research_pattern_type: Optional[str] = None  # Type of research question pattern

# Intent types based on screenshot
IntentType = Literal[
    "discovery_search",      # Primo Agent
    "course_subject_help",   # LibGuide/MyGuide Agent
    "booking_or_hours",      # LibCal Agent
    "policy_or_service",     # Google Site Search Agent
    "human_help",            # LibChat Agent
    "general_question"       # Transcript RAG Agent
]
