"""Bot Capability Scope - Defines what the chatbot CAN and CANNOT do.

This module prevents the bot from:
1. Asking clarifying questions about things it cannot do
2. Promising services it cannot provide
3. Misleading users about its capabilities

Updated: December 2025
"""

from typing import Dict, List, Set
import re

# ============================================================================
# CAPABILITIES - Things the bot CAN do
# ============================================================================

CAPABILITIES = {
    "library_hours": {
        "description": "Check library building hours and schedules",
        "agent": "libcal",
        "examples": ["When does King Library close?", "Library hours tomorrow"],
        "can_do": True,
    },
    "room_reservations": {
        "description": "Book study rooms and check room availability",
        "agent": "libcal",
        "examples": ["Book a study room", "Reserve a room for 3 people"],
        "can_do": True,
    },
    "subject_librarians": {
        "description": "Find subject librarians and their contact info",
        "agent": "subject_librarian",
        "examples": ["Who is the business librarian?", "Find librarian for psychology"],
        "can_do": True,
    },
    "research_guides": {
        "description": "Find LibGuides and research guides by subject",
        "agent": "libguide",
        "examples": ["LibGuide for nursing", "Research guide for history"],
        "can_do": True,
    },
    "library_website_info": {
        "description": "Answer questions about library services from website",
        "agent": "google_site",
        "examples": ["How do I get a library card?", "Where is the quiet study area?"],
        "can_do": True,
    },
    "human_handoff": {
        "description": "Connect users with human librarians",
        "agent": "libchat",
        "examples": ["Talk to a librarian", "I need human help"],
        "can_do": True,
    },
}

# ============================================================================
# LIMITATIONS - Things the bot CANNOT do
# ============================================================================

LIMITATIONS = {
    "renew_books": {
        "description": "Renew library books or check renewal eligibility",
        "reason": "No integration with patron account system (Alma/ILS)",
        "redirect_to": "human_help",
        "response": "I can't renew books or check renewal status directly. Please renew online at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact a librarian for help.",
    },
    "check_account": {
        "description": "Check patron account, fines, holds, or checkouts",
        "reason": "No integration with patron account system",
        "redirect_to": "human_help",
        "response": "I don't have access to your library account. Please check your account at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact us at (513) 529-4141.",
    },
    "place_holds": {
        "description": "Place holds on books or materials",
        "reason": "No integration with patron account system",
        "redirect_to": "human_help",
        "response": "I can't place holds on items. Please place holds through your library account at https://www.lib.miamioh.edu/ or ask a librarian for help.",
    },
    "catalog_search": {
        "description": "Search for books, articles, journals, e-resources",
        "reason": "Primo agent temporarily disabled",
        "redirect_to": "human_help",
        "response": "Catalog search is currently unavailable. Please search directly at https://www.lib.miamioh.edu/ or chat with a librarian who can help find materials.",
    },
    "interlibrary_loan": {
        "description": "Request or check status of interlibrary loans (ILL)",
        "reason": "No integration with ILL system",
        "redirect_to": "human_help",
        "response": "I can't manage ILL requests. Please visit https://lib.miamioh.edu/use/borrow/ill/ or contact a librarian for ILL help.",
    },
    "pay_fines": {
        "description": "Pay library fines or fees",
        "reason": "No payment processing capability",
        "redirect_to": "human_help",
        "response": "I can't process payments. Please pay fines through your library account at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or at a library service desk.",
    },
    "course_reserves": {
        "description": "Access or check course reserves",
        "reason": "No integration with course reserves system",
        "redirect_to": "human_help",
        "response": "I can't check course reserves. Please visit https://libguides.lib.miamioh.edu/reserves-textbooks/ or ask a librarian.",
    },
    "print_scan_copy": {
        "description": "Help with printing, scanning, or copying (beyond general info)",
        "reason": "Cannot control physical equipment",
        "redirect_to": "google_site",  # Can provide general info
        "response": "For printing help, visit a library service desk or check https://www.lib.miamioh.edu/use/technology/printing/",
    },
}

# ============================================================================
# DETECTION PATTERNS - Regex patterns to detect capability requests
# ============================================================================

LIMITATION_PATTERNS = {
    "renew_books": [
        r'\b(renew|renewal|extend|extension)\b.*\b(book|item|material|checkout|loan)\b',
        r'\b(book|item|material)\b.*\b(renew|renewal|due|extend)\b',
        r'\bcan i renew\b',
        r'\bhow (do|can) i renew\b',
        r'\brenewal eligibility\b',
        r'\bcheck.*renewal\b',
    ],
    "check_account": [
        r'\b(my|check)\s*(library)?\s*(account|fines?|fees?|balance|checkouts?|loans?|items?)\b',
        r'\bwhat (do i|books|items).*\b(owe|checked out|have out|borrowed)\b',
        r'\bhow much do i owe\b',
        r'\bwhat.*checked out\b',
        r'\bmy (fines?|fees?|balance)\b',
    ],
    "place_holds": [
        r'\b(place|put|request)\s*(a)?\s*hold\b',
        r'\bhold.*on\s*(a|this|the)?\s*(book|item)\b',
        r'\brequest.*book\b',
    ],
    "catalog_search": [
        r'\b(find|search|look\s*for|need|want|get)\b.*\b(articles?|books?|journals?|e-?resources?|publications?)\b',
        r'\b(articles?|books?|journals?)\b.*\b(about|on|regarding)\b',
        r'\bdo you have\b.*\b(book|article|journal|copy)\b',
        r'\b\d+\s*(articles?|books?|sources?)\b',
        r'\bcall\s*number\b',
        r'\bcatalog\s*search\b',
        r'\bsearch\s*(the\s*)?(catalog|database)',
    ],
    "interlibrary_loan": [
        r'\b(ill|interlibrary\s*loan)\b',
        r'\b(request|get|order)\s*(a)?\s*book.*another\s*library\b',
        r'\bborrow.*other\s*librar',
    ],
    "pay_fines": [
        r'\b(pay|paying)\s*(my|library|a)?\s*(fines?|fees?|balance)\b',
        r'\bhow.*pay.*fine\b',
    ],
    "course_reserves": [
        r'\b(course|class)\s*reserves?\b',
        r'\breserves?\s*(for|in)\s*(my|a|the)?\s*(class|course)\b',
        r'\bprofessor.*put.*reserve\b',
    ],
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def detect_limitation_request(user_message: str) -> Dict[str, any]:
    """Check if user is asking for something the bot cannot do.
    
    Args:
        user_message: The user's message
        
    Returns:
        Dict with:
        - is_limitation: True if this is something bot cannot do
        - limitation_type: The type of limitation (e.g., "renew_books")
        - response: The response to give the user
        - redirect_to: Where to redirect the user
    """
    user_msg_lower = user_message.lower()
    
    for limitation_type, patterns in LIMITATION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, user_msg_lower, re.IGNORECASE):
                limitation = LIMITATIONS.get(limitation_type, {})
                return {
                    "is_limitation": True,
                    "limitation_type": limitation_type,
                    "description": limitation.get("description", ""),
                    "reason": limitation.get("reason", ""),
                    "response": limitation.get("response", "I can't help with that directly. Please contact a librarian."),
                    "redirect_to": limitation.get("redirect_to", "human_help"),
                }
    
    return {"is_limitation": False}


def get_capability_summary() -> str:
    """Get a summary of bot capabilities for prompts."""
    can_do = []
    cannot_do = []
    
    for name, cap in CAPABILITIES.items():
        if cap.get("can_do"):
            can_do.append(f"- {cap['description']}")
    
    for name, lim in LIMITATIONS.items():
        cannot_do.append(f"- {lim['description']}: {lim['reason']}")
    
    return f"""BOT CAPABILITIES:
What I CAN do:
{chr(10).join(can_do)}

What I CANNOT do (must redirect to human):
{chr(10).join(cannot_do)}
"""


def get_limitation_response(limitation_type: str) -> str:
    """Get the appropriate response for a limitation."""
    limitation = LIMITATIONS.get(limitation_type, {})
    return limitation.get("response", "I can't help with that directly. Please contact a librarian at (513) 529-4141.")


async def get_limitation_response_with_availability(limitation_type: str) -> str:
    """Get the appropriate response with real-time librarian availability check.
    
    For limitations that redirect to human help, this will check if librarians
    are currently available and provide specific guidance on when/how to get help.
    """
    from src.api.askus_hours import get_askus_hours_for_date
    
    limitation = LIMITATIONS.get(limitation_type, {})
    base_response = limitation.get("response", "I can't help with that directly.")
    redirect_to = limitation.get("redirect_to", "")
    
    # Only check availability for human_help redirects
    if redirect_to != "human_help":
        return base_response
    
    try:
        hours_data = await get_askus_hours_for_date()
        is_open = hours_data.get("is_open", False)
        current_period = hours_data.get("current_period")
        hours_list = hours_data.get("hours", [])
        
        if is_open and current_period:
            availability_info = (
                f"\n\n✅ **Librarians are available NOW** (until {current_period['close']})\n"
                f"Chat with a librarian: https://www.lib.miamioh.edu/research/research-support/ask/"
            )
        elif hours_list and len(hours_list) > 0:
            next_open = hours_list[0].get("from")
            next_close = hours_list[0].get("to")
            availability_info = (
                f"\n\n⏰ **Live chat is currently closed**\n"
                f"Chat hours today: {next_open} - {next_close}\n"
                f"Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/"
            )
        else:
            availability_info = (
                f"\n\n⏰ **Live chat is not available today**\n"
                f"Submit a ticket: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                f"Or call us at (513) 529-4141"
            )
        
        return base_response + availability_info
    
    except Exception as e:
        return base_response + "\n\nContact us at (513) 529-4141 for assistance."


# Quick check for common limitations
def is_account_action(message: str) -> bool:
    """Check if message is about patron account actions (renew, holds, fines)."""
    account_patterns = (
        LIMITATION_PATTERNS.get("renew_books", []) +
        LIMITATION_PATTERNS.get("check_account", []) +
        LIMITATION_PATTERNS.get("place_holds", []) +
        LIMITATION_PATTERNS.get("pay_fines", [])
    )
    msg_lower = message.lower()
    return any(re.search(p, msg_lower, re.IGNORECASE) for p in account_patterns)
