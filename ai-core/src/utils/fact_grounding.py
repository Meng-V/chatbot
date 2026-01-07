"""
Fact Grounding System for RAG-based Chatbot

This module ensures factual information (dates, locations, names, etc.) 
is retrieved from RAG rather than LLM's training data.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0
llm = ChatOpenAI(**llm_kwargs)


# Patterns for detecting factual queries
FACTUAL_PATTERNS = {
    "date": [
        r"\b(when|what year|what date|built|opened|established|founded|created)\b",
        r"\b(year|date|time)\b.*\b(built|opened|established|founded)\b"
    ],
    "location": [
        r"\b(where|what floor|which building|what room|located|location)\b",
        r"\b(address|room number|floor)\b"
    ],
    "person": [
        r"\b(who|who is|who's|name of|contact)\b.*\b(librarian|director|staff)\b",
        r"\b(email|phone).*\b(librarian|staff)\b"
    ],
    "quantity": [
        r"\b(how many|how much|number of|total)\b",
        r"\b(capacity|size|hours|count)\b"
    ],
    "policy": [
        r"\b(can I|how do I|how to|allowed|policy|rule)\b",
        r"\b(renew|borrow|fine|fee|checkout|check out)\b"
    ]
}


def detect_factual_query_type(query: str) -> List[str]:
    """
    Detect what types of factual information are being requested.
    
    Returns:
        List of fact types: ["date", "location", "person", etc.]
    """
    query_lower = query.lower()
    detected_types = []
    
    for fact_type, patterns in FACTUAL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                if fact_type not in detected_types:
                    detected_types.append(fact_type)
                break
    
    return detected_types


async def is_high_confidence_rag_match(
    rag_response: Dict[str, Any],
    confidence_threshold: float = 0.80
) -> Tuple[str, str]:
    """
    Check RAG response confidence level.
    
    Args:
        rag_response: Response from transcript_rag_query
        confidence_threshold: Minimum similarity score for high confidence (default 0.80)
    
    Returns:
        (confidence_level, reason) where confidence_level is "high", "medium", or "low"
    """
    if not rag_response.get("success"):
        return "low", "RAG query failed"
    
    confidence = rag_response.get("confidence", "none")
    similarity = rag_response.get("similarity_score", 0)
    
    # Check confidence levels - now more lenient
    if confidence == "high" and similarity >= confidence_threshold:
        return "high", f"High confidence match (similarity: {similarity:.2f})"
    elif confidence == "medium" and similarity >= 0.65:  # Lowered from 0.75
        return "medium", f"Medium confidence match (similarity: {similarity:.2f})"
    elif similarity >= 0.50:  # New: moderate confidence range
        return "moderate", f"Moderate confidence (similarity: {similarity:.2f})"
    else:
        return "low", f"Low confidence (similarity: {similarity:.2f})"


def extract_factual_claims(text: str) -> Dict[str, List[str]]:
    """
    Extract potential factual claims from text for verification.
    
    Returns:
        Dictionary with fact types and extracted values
    """
    claims = {
        "dates": [],
        "locations": [],
        "people": [],
        "urls": [],
        "phone_numbers": [],
        "emails": []
    }
    
    # Extract years (4 digits)
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
    claims["dates"].extend(years)
    
    # Extract building/room references
    locations = re.findall(
        r'\b(King Library|Rentschler Library|Wertz Art & Architecture Library|'
        r'Gardner-Harvey Library|Amos Music Library|room \d+|floor \d+)\b',
        text,
        re.IGNORECASE
    )
    claims["locations"].extend(locations)
    
    # Extract names (capitalized words, 2-3 words)
    # This is a simple heuristic - could be improved
    potential_names = re.findall(r'\b([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b', text)
    claims["people"].extend(potential_names)
    
    # Extract URLs
    urls = re.findall(r'https?://[^\s]+', text)
    claims["urls"].extend(urls)
    
    # Extract phone numbers
    phones = re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    claims["phone_numbers"].extend(phones)
    
    # Extract emails
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    claims["emails"].extend(emails)
    
    return claims


async def verify_factual_claims_against_rag(
    generated_text: str,
    rag_context: str,
    query: str,
    log_callback=None
) -> Tuple[bool, List[str]]:
    """
    Verify that factual claims in generated text match RAG context.
    
    Returns:
        (all_verified, list_of_issues)
    """
    issues = []
    
    # Extract claims from generated text
    claims = extract_factual_claims(generated_text)
    
    # Check each type of claim
    for claim_type, values in claims.items():
        if not values:
            continue
        
        for value in values:
            # Check if claim appears in RAG context
            if value not in rag_context:
                # Special handling for dates - check if year is mentioned
                if claim_type == "dates" and any(year in rag_context for year in values):
                    continue
                
                issue = f"Unverified {claim_type}: '{value}' not found in RAG context"
                issues.append(issue)
                if log_callback:
                    log_callback(f"⚠️ [Fact Verifier] {issue}")
    
    all_verified = len(issues) == 0
    return all_verified, issues


GROUNDED_SYNTHESIS_INSTRUCTIONS = """
🎯 CRITICAL GROUNDING RULES - MUST FOLLOW EXACTLY:

This query contains FACTUAL information that MUST come from the provided context ONLY.

DETECTED FACT TYPES: {fact_types}

ABSOLUTE RULES FOR FACTUAL INFORMATION:
1. **DATES/YEARS**: ONLY use dates/years that appear EXACTLY in the context below
   - If context says "built in 1972", use 1972
   - NEVER use your training data for dates
   - If date not in context, say "I don't have that specific information"

2. **LOCATIONS**: ONLY use locations that appear EXACTLY in the context
   - Building names, room numbers, floor numbers MUST be from context
   - NEVER guess or infer locations
   - If location not in context, say "I don't have that specific location information"

3. **PEOPLE/CONTACTS**: ONLY use names/contacts that appear EXACTLY in the context
   - Names, email addresses, phone numbers MUST be from context
   - NEVER generate or make up contact information
   - If contact not in context, provide general library contact: (513) 529-4141

4. **POLICIES/PROCEDURES**: ONLY describe policies mentioned in the context
   - Don't add details from your training data
   - If policy details missing, suggest contacting librarian

5. **QUANTITIES/NUMBERS/HOURS**: ONLY use numbers that appear in the context
   - Capacities, counts, hours MUST be from context
   - **NEVER GENERATE LIBRARY HOURS** - must come from LibCal API data in context
   - **NEVER USE HARDCODED HOURS** like "Monday-Friday 8:30 AM - 4:30 PM"
   - If hours not in context, say "I'm unable to retrieve current hours. Please check https://www.lib.miamioh.edu/hours"
   - Don't estimate or approximate

VERIFICATION CHECKLIST (before responding):
✓ Every factual claim is directly quoted or paraphrased from context
✓ No dates/years from your training data
✓ No locations not mentioned in context
✓ No generated contact information
✓ No assumed policies
✓ No hardcoded or generated hours

IF FACTUAL INFORMATION IS MISSING FROM CONTEXT:
- Say "I don't have that specific information in our knowledge base"
- Offer to connect user with a librarian
- DO NOT fill in gaps with your training data

RESPONSE FORMAT:
- Start with the factual answer from context
- Cite your source if possible: "According to our records..." or "Based on our knowledge base..."
- Keep response clear and concise
- Add helpful follow-up information only if it's also from context
"""


async def create_grounded_synthesis_prompt(
    user_message: str,
    rag_response: Dict[str, Any],
    fact_types: List[str],
    conversation_history: List[Dict] = None,
    confidence_level: str = "high"
) -> str:
    """
    Create a synthesis prompt with strong grounding instructions.
    
    Args:
        user_message: Original user query
        rag_response: Response from RAG system
        fact_types: Detected factual query types
        conversation_history: Previous messages
        confidence_level: Confidence level ("high", "medium", "moderate", or "low")
    
    Returns:
        Grounding-enhanced synthesis prompt
    """
    # Format fact types for display
    fact_types_str = ", ".join(fact_types) if fact_types else "general information"
    
    # Get RAG context
    rag_text = rag_response.get("text", "")
    confidence = rag_response.get("confidence", "unknown")
    similarity = rag_response.get("similarity_score", 0)
    
    # Format conversation history
    history_context = ""
    if conversation_history:
        history_formatted = []
        for msg in conversation_history[-4:]:  # Last 4 messages
            role = "User" if msg["type"] == "user" else "Assistant"
            history_formatted.append(f"{role}: {msg['content']}")
        history_context = "\n\nPrevious conversation:\n" + "\n".join(history_formatted) + "\n"
    
    # Add uncertainty instructions based on confidence level
    uncertainty_instruction = ""
    if confidence_level in ["medium", "moderate"]:
        uncertainty_instruction = """

⚠️ CONFIDENCE LEVEL GUIDANCE:
Your knowledge base search returned medium confidence results. You should:
1. Start your answer with a visual uncertainty marker: "⚠️ **Based on available information** (this may not be completely accurate):"
2. Provide the best answer you can from the context
3. At the end, add: "\\n\\nIf you need more specific information, I recommend contacting a librarian at (513) 529-4141 or via https://www.lib.miamioh.edu/research/research-support/ask/"
4. Be helpful and try to answer - don't refuse to respond just because confidence isn't perfect
"""
    
    prompt = f"""
{GROUNDED_SYNTHESIS_INSTRUCTIONS.format(fact_types=fact_types_str)}
{uncertainty_instruction}
{history_context}

USER QUERY: {user_message}

RAG KNOWLEDGE BASE INFORMATION:
(Confidence: {confidence}, Similarity: {similarity:.2f})
---
{rag_text}
---

REMINDER: Use ONLY the information above. If specific factual details are missing, acknowledge it and offer to connect with a librarian.

Generate a helpful, accurate response using ONLY the knowledge base information above. If confidence is medium/moderate, use uncertainty markers as instructed.
"""
    
    return prompt


def should_enforce_strict_grounding(query: str, rag_response: Dict[str, Any]) -> bool:
    """
    Determine if strict grounding should be enforced for this query.
    
    Strict grounding is enforced when:
    - Query contains factual patterns (dates, locations, etc.)
    - RAG has a response (even low confidence)
    """
    fact_types = detect_factual_query_type(query)
    has_rag_data = rag_response.get("success") and rag_response.get("text")
    
    return len(fact_types) > 0 and has_rag_data
