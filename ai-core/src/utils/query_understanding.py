"""
Query Understanding Layer for Miami University Libraries Chatbot

This module provides intelligent query preprocessing that:
1. Translates complex/verbose user queries into clear, actionable requests
2. Extracts key information and intent signals from natural language
3. Detects ambiguous queries and generates clarifying questions
4. Handles library-specific terminology and common user expressions

The layer sits between user input and the classification system, ensuring
the backend receives clean, well-structured queries for accurate routing.

Author: Meng Qu, Miami University Libraries
Date: December 9, 2025
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter
llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
query_llm = ChatOpenAI(**llm_kwargs)


def get_date_context() -> Dict[str, str]:
    """Get current date context for relative date interpretation."""
    today = datetime.now()
    current_year = today.year
    current_month = today.month
    
    # If we're in December, "new year" means next year
    # If we're in January-November, "new year" still typically means the upcoming January
    if current_month >= 11:  # November or December
        next_year = current_year + 1
    else:
        # Earlier in the year, "new year" could mean current year if before mid-year
        next_year = current_year + 1  # Safe default: always upcoming
    
    return {
        "today_date": today.strftime("%B %d, %Y"),  # e.g., "December 9, 2025"
        "current_year": str(current_year),
        "next_year": str(next_year),
        "current_month": today.strftime("%B"),
    }


def get_formatted_prompt() -> str:
    """Get the query understanding prompt with current date context."""
    date_context = get_date_context()
    return QUERY_UNDERSTANDING_PROMPT.format(**date_context)


# ============================================================================
# QUERY UNDERSTANDING SYSTEM PROMPT
# ============================================================================

QUERY_UNDERSTANDING_PROMPT = """You are a Query Understanding Assistant for Miami University Libraries.
Your job is to analyze user messages and prepare them for the library chatbot system.

## YOUR TASKS:

### 1. TRANSLATE & SIMPLIFY
Convert verbose, complex, or unclear user messages into clear, actionable library queries.
- Extract the core request from lengthy descriptions
- Identify what library service they need (books, rooms, hours, research help, etc.)
- Preserve important details (dates, times, subjects, specific items)

### 2. DETECT AMBIGUITY
Identify if the query is too vague to process accurately. A query is ambiguous if:
- Multiple interpretations are equally likely
- Critical information is missing (e.g., "book a room" without date/time)
- The user's actual need is unclear

### 3. LIBRARY TERMINOLOGY MAPPING
Understand common ways users express library needs:
- "quiet place to study" → study room / quiet floor inquiry
- "find stuff about X" → discovery search for X
- "need help with research" → subject librarian / research help
- "when are you open" → library hours
- "print something" → printing services
- "borrow a book" → circulation / borrowing policy
- "reserve a space" → room booking
- "talk to someone" → human librarian assistance

### 4. EXTRACT KEY ENTITIES
Identify and preserve:
- Book titles, author names, subjects
- Dates and times (for room bookings, hours queries)
- Building names (King Library, Art Library, etc.)
- Course numbers (ENG 111, PSY 201)
- Department/major names (biology, accounting)

### 5. RELATIVE DATE/TIME INTERPRETATION (CRITICAL)
TODAY'S DATE: {today_date}
CURRENT YEAR: {current_year}

When users mention relative dates, ALWAYS interpret them relative to TODAY:
- "new year" = the upcoming new year ({next_year}), NOT a fixed year
- "next week" = 7 days from today
- "tomorrow" = the day after today
- "next month" = the following calendar month
- "this weekend" = the upcoming Saturday/Sunday
- "the tenth of the new year" = January 10, {next_year}
- "first week of January" = first week of January {next_year} (if today is in December)

YEAR INTERPRETATION RULES:
- If today is December and user says "January", assume NEXT year ({next_year})
- If user says "new year" without a specific year, use {next_year}
- NEVER assume a past date when the user is clearly planning something

## RESPONSE FORMAT (JSON):

{
  "original_query": "the exact user input",
  "processed_query": "clear, concise version for the system",
  "is_ambiguous": true/false,
  "clarifying_question": "question to ask if ambiguous (null if not ambiguous)",
  "confidence": "high/medium/low",
  "extracted_entities": {
    "subject": null or "detected subject",
    "date": null or "detected date",
    "time": null or "detected time",
    "building": null or "detected building name",
    "book_title": null or "detected title",
    "course": null or "detected course number"
  },
  "query_type_hint": "suggested category (discovery/booking/hours/research_help/policy/general)",
  "needs_immediate_clarification": true/false,
  "user_friendly_summary": "brief description of what the user is asking for"
}

## EXAMPLES:

User: "So I've been trying to figure out where I can find a quiet spot to work on my thesis and I was wondering if maybe the library has like private rooms or something that I could use tomorrow afternoon around 2pm?"

Response:
{
  "original_query": "So I've been trying to figure out...",
  "processed_query": "Book a study room for tomorrow afternoon around 2pm",
  "is_ambiguous": false,
  "clarifying_question": null,
  "confidence": "high",
  "extracted_entities": {
    "subject": null,
    "date": "tomorrow",
    "time": "2pm afternoon",
    "building": null,
    "book_title": null,
    "course": null
  },
  "query_type_hint": "booking",
  "needs_immediate_clarification": false,
  "user_friendly_summary": "User wants to book a study room for tomorrow at 2pm"
}

User: "I need a book"

Response:
{
  "original_query": "I need a book",
  "processed_query": "Find a book",
  "is_ambiguous": true,
  "clarifying_question": "I'd be happy to help you find a book! Could you tell me the title, author, or subject you're looking for?",
  "confidence": "low",
  "extracted_entities": {},
  "query_type_hint": "discovery",
  "needs_immediate_clarification": true,
  "user_friendly_summary": "User wants to find a book but hasn't specified which one"
}

User: "room"

Response:
{
  "original_query": "room",
  "processed_query": "Study room inquiry",
  "is_ambiguous": true,
  "clarifying_question": "I can help with study rooms! Are you looking to book a room, check availability, or find information about room policies?",
  "confidence": "low",
  "extracted_entities": {},
  "query_type_hint": "booking",
  "needs_immediate_clarification": true,
  "user_friendly_summary": "User mentioned rooms but intent is unclear"
}

IMPORTANT:
- Always respond with valid JSON only
- Be helpful and friendly in clarifying questions
- Preserve user's original intent even when simplifying
- For greetings like "hi" or "hello", treat as non-ambiguous general conversation

🚨 CRITICAL - BOT CAPABILITY LIMITATIONS 🚨
The following requests are OUTSIDE the bot's capabilities. Do NOT ask for clarification on these:
- Renewing books or checking renewal eligibility → Bot CANNOT renew books
- Checking patron account, fines, holds, or checkouts → Bot CANNOT access accounts
- Placing holds on books → Bot CANNOT place holds
- Paying fines → Bot CANNOT process payments
- Interlibrary loan requests → Bot CANNOT manage ILL
- Course reserves → Bot CANNOT access course reserves
- Catalog/database search → TEMPORARILY DISABLED

For these requests, set:
- "is_ambiguous": false (NOT ambiguous - we know what they want, we just can't do it)
- "needs_immediate_clarification": false (DO NOT ask for more details)
- "query_type_hint": "capability_limitation"
- "user_friendly_summary": "User wants X but this is outside bot capabilities"
"""


async def understand_query(
    user_message: str,
    conversation_history: list = None,
    log_callback=None
) -> Dict[str, Any]:
    """
    Process and understand user query before routing.
    
    Args:
        user_message: Raw user input
        conversation_history: Previous messages for context
        log_callback: Optional logging function
    
    Returns:
        Dictionary with query understanding results
    """
    if log_callback:
        log_callback("🔍 [Query Understanding] Analyzing user message")
    
    # Handle very short or greeting messages without LLM
    greeting_words = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
    if user_message.strip().lower() in greeting_words:
        return {
            "original_query": user_message,
            "processed_query": user_message,
            "is_ambiguous": False,
            "clarifying_question": None,
            "confidence": "high",
            "extracted_entities": {},
            "query_type_hint": "greeting",
            "needs_immediate_clarification": False,
            "user_friendly_summary": "User greeted the chatbot",
            "skip_understanding": True
        }
    
    # 🚨 EARLY CHECK: Detect capability limitations before LLM call
    # This prevents the LLM from asking for clarification on things we can't do
    from src.config.capability_scope import detect_limitation_request
    limitation = detect_limitation_request(user_message)
    if limitation.get("is_limitation"):
        limitation_type = limitation.get("limitation_type")
        description = limitation.get("description", "")
        if log_callback:
            log_callback(f"🚫 [Query Understanding] Detected capability limitation: {limitation_type}")
        return {
            "original_query": user_message,
            "processed_query": user_message,
            "is_ambiguous": False,  # NOT ambiguous - we know what they want
            "clarifying_question": None,  # DO NOT ask for more details
            "confidence": "high",
            "extracted_entities": {},
            "query_type_hint": "capability_limitation",
            "needs_immediate_clarification": False,
            "user_friendly_summary": f"User wants {description} but this is outside bot capabilities",
            "limitation_type": limitation_type,
            "limitation_response": limitation.get("response")
        }
    
    # Build context from conversation history
    context_str = ""
    if conversation_history and len(conversation_history) > 0:
        recent_messages = conversation_history[-4:]  # Last 2 exchanges
        context_parts = []
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:200]  # Limit length
            context_parts.append(f"{role}: {content}")
        context_str = f"\n\nRecent conversation context:\n" + "\n".join(context_parts)
    
    # Construct the prompt
    analysis_prompt = f"""Analyze this user message and provide structured understanding.

User message: "{user_message}"{context_str}

Respond with JSON only."""

    try:
        # Get prompt with current date context
        formatted_prompt = get_formatted_prompt()
        
        messages = [
            SystemMessage(content=formatted_prompt),
            HumanMessage(content=analysis_prompt)
        ]
        
        response = await query_llm.ainvoke(messages)
        response_text = response.content.strip()
        
        # Parse JSON response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            response_text = "\n".join(json_lines)
        
        result = json.loads(response_text)
        
        if log_callback:
            log_callback(f"✅ [Query Understanding] Processed: {result.get('processed_query', user_message)}")
            if result.get("is_ambiguous"):
                log_callback(f"⚠️ [Query Understanding] Query is ambiguous, may need clarification")
        
        return result
        
    except json.JSONDecodeError as e:
        if log_callback:
            log_callback(f"⚠️ [Query Understanding] JSON parse error, using original query")
        return {
            "original_query": user_message,
            "processed_query": user_message,
            "is_ambiguous": False,
            "clarifying_question": None,
            "confidence": "medium",
            "extracted_entities": {},
            "query_type_hint": "general",
            "needs_immediate_clarification": False,
            "user_friendly_summary": "Query processing fallback",
            "parse_error": str(e)
        }
    except Exception as e:
        if log_callback:
            log_callback(f"❌ [Query Understanding] Error: {str(e)}")
        return {
            "original_query": user_message,
            "processed_query": user_message,
            "is_ambiguous": False,
            "clarifying_question": None,
            "confidence": "low",
            "extracted_entities": {},
            "query_type_hint": "general",
            "needs_immediate_clarification": False,
            "user_friendly_summary": "Query processing error",
            "error": str(e)
        }


def format_clarifying_response(understanding_result: Dict[str, Any]) -> str:
    """
    Format a friendly clarifying response for the user.
    
    Args:
        understanding_result: Result from understand_query()
    
    Returns:
        Formatted string to send back to user
    """
    question = understanding_result.get("clarifying_question")
    summary = understanding_result.get("user_friendly_summary", "")
    
    if question:
        return question
    
    # Fallback clarification
    return "I want to make sure I understand your question correctly. Could you provide a bit more detail about what you're looking for?"


def should_request_clarification(understanding_result: Dict[str, Any]) -> bool:
    """
    Determine if we should ask the user for clarification before processing.
    
    Args:
        understanding_result: Result from understand_query()
    
    Returns:
        True if clarification is needed
    """
    # 🚫 NEVER request clarification for capability limitations
    # The bot cannot do these things, so asking for more details is misleading
    if understanding_result.get("query_type_hint") == "capability_limitation":
        return False
    
    if understanding_result.get("limitation_type"):
        return False
    
    # Explicit flag for immediate clarification
    if understanding_result.get("needs_immediate_clarification"):
        return True
    
    # Ambiguous with low confidence
    if understanding_result.get("is_ambiguous") and understanding_result.get("confidence") == "low":
        return True
    
    return False


def get_processed_query(understanding_result: Dict[str, Any]) -> str:
    """
    Get the processed/translated query for the system.
    
    Args:
        understanding_result: Result from understand_query()
    
    Returns:
        Processed query string
    """
    return understanding_result.get("processed_query") or understanding_result.get("original_query", "")


def get_query_type_hint(understanding_result: Dict[str, Any]) -> Optional[str]:
    """
    Get the suggested query type hint for routing assistance.
    
    Args:
        understanding_result: Result from understand_query()
    
    Returns:
        Query type hint or None
    """
    hint = understanding_result.get("query_type_hint")
    
    # Map hints to system intent categories
    hint_mapping = {
        "discovery": "discovery_search",
        "booking": "booking_or_hours",
        "hours": "booking_or_hours",
        "research_help": "subject_librarian",
        "policy": "policy_or_service",
        "general": "general_question",
        "human": "human_help",
        "greeting": None,  # Greetings don't need routing hints
        "capability_limitation": "capability_limitation",  # Pass through as-is
    }
    
    return hint_mapping.get(hint, hint)
