"""
Intent Normalization Layer

Pure function that translates user input into a standardized intent representation.
This layer DOES NOT choose agents, do RAG, or answer questions.
It ONLY normalizes what the user is asking into a structured format.
"""

import os
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser

from src.models.intent import NormalizedIntent

# Use o4-mini as specified
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter
llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0

llm = ChatOpenAI(**llm_kwargs)

# Create parser for structured output
parser = PydanticOutputParser(pydantic_object=NormalizedIntent)


INTENT_NORMALIZATION_PROMPT = """You are an intent normalization assistant for Miami University Libraries.

Your ONLY job is to understand what the user is asking and express it as a clear, standardized intent statement.

DO NOT:
- Choose which agent should handle this
- Answer the question
- Decide if it's in-scope or out-of-scope
- Provide solutions

DO:
- Rewrite the user's question into a clear intent statement
- Extract key entities (locations, equipment, subjects, etc.)
- Assess your confidence in understanding the intent
- Flag ambiguity ONLY when truly necessary

CRITICAL - AMBIGUITY POLICY:
**DEFAULT: ambiguity = False**

Set ambiguity = True ONLY if:
1. User explicitly mixes TWO DIFFERENT intents in one message (e.g., "Can I borrow a laptop AND talk to someone about my research?"), OR
2. Request is so underspecified that routing would FAIL without clarification (e.g., "help" with no context)

DO NOT flag ambiguity for:
- Short queries that have a clear single intent (e.g., "Library hours", "Can I get Adobe?", "I need a computer")
- Queries where the most reasonable interpretation is obvious (e.g., "I need help with a computer" → library equipment checkout)
- Common library questions, even if brief

INTENT STATEMENT FORMAT:
"User is asking about [TOPIC/ACTION]"
"User wants to [ACTION]"
"User is requesting [SERVICE/INFORMATION]"

EXAMPLES:

User: "Can I borrow a laptop?"
Intent: "User is asking about borrowing library equipment (laptop)"
Confidence: 0.95
Ambiguity: False

User: "Library hours"
Intent: "User is requesting library building hours"
Confidence: 0.90
Ambiguity: False

User: "Can I get Adobe?"
Intent: "User is asking about Adobe software access or checkout"
Confidence: 0.90
Ambiguity: False

User: "I need a computer"
Intent: "User needs to access or borrow a library computer"
Confidence: 0.85
Ambiguity: False

User: "I need help with a computer"
Intent: "User needs computer-related assistance"
Confidence: 0.85
Ambiguity: False

User: "Camera checkout"
Intent: "User wants to check out camera equipment from the library"
Confidence: 0.90
Ambiguity: False

User: "Talk to a librarian"
Intent: "User wants to connect with a librarian"
Confidence: 0.95
Ambiguity: False

User: "Where is the dining hall?"
Intent: "User is asking for the location of campus dining facilities"
Confidence: 0.95
Ambiguity: False

User: "Who is the biology librarian?"
Intent: "User is requesting contact information for the subject librarian for biology"
Confidence: 0.95
Ambiguity: False

User: "help"
Intent: "User is requesting assistance"
Confidence: 0.40
Ambiguity: True
Reason: "Single word 'help' with no context - cannot determine what type of assistance is needed"

CONVERSATION HISTORY:
{history}

USER MESSAGE:
{user_message}

{format_instructions}

Respond with ONLY the JSON object, no additional text."""


async def normalize_intent(
    user_message: str,
    conversation_history: List[Dict[str, Any]] = None,
    log_callback=None
) -> NormalizedIntent:
    """
    Normalize user input into a standardized intent representation.
    
    This is a pure function that:
    - Takes raw user input
    - Returns structured intent representation
    - Does NOT choose agents or answer questions
    
    Args:
        user_message: Raw user input
        conversation_history: Previous conversation for context
        log_callback: Optional logging function
        
    Returns:
        NormalizedIntent: Structured intent representation
    """
    if log_callback:
        log_callback("🔍 [Intent Normalizer] Analyzing user message")
    
    # Format conversation history
    history_text = ""
    if conversation_history:
        history_formatted = []
        for msg in conversation_history[-4:]:  # Last 4 messages (2 exchanges)
            role = "User" if msg.get("type") == "user" else "Assistant"
            content = msg.get("content", "")
            history_formatted.append(f"{role}: {content}")
        history_text = "\n".join(history_formatted)
    else:
        history_text = "No previous conversation"
    
    # Create prompt with format instructions
    format_instructions = parser.get_format_instructions()
    
    prompt = INTENT_NORMALIZATION_PROMPT.format(
        history=history_text,
        user_message=user_message,
        format_instructions=format_instructions
    )
    
    messages = [
        SystemMessage(content="You are an intent normalization assistant. Output valid JSON only."),
        HumanMessage(content=prompt)
    ]
    
    try:
        # Get LLM response
        response = await llm.ainvoke(messages)
        
        # Parse structured output
        normalized_intent = parser.parse(response.content)
        
        # Ensure original_query is set
        if not normalized_intent.original_query:
            normalized_intent.original_query = user_message
        
        if log_callback:
            log_callback(f"✅ [Intent Normalizer] Intent: {normalized_intent.intent_summary}")
            log_callback(f"   Confidence: {normalized_intent.confidence:.2f}, Ambiguity: {normalized_intent.ambiguity}")
        
        return normalized_intent
    
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [Intent Normalizer] Error: {str(e)}, using fallback")
        
        # Fallback: create basic intent
        return NormalizedIntent(
            intent_summary=f"User is asking: {user_message}",
            confidence=0.5,
            ambiguity=True,
            ambiguity_reason="Failed to parse intent, using fallback",
            key_entities=[],
            original_query=user_message
        )
