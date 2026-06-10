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
    "book_room_action": {
        "description": "Book/reserve a study room on the user's behalf",
        "reason": (
            "v1's LibCal booking flow (libcal_comprehensive_tools.py) is not "
            "yet migrated to v2 -- book_room is an unwired backend, and an "
            "action tool also needs the confirm-before-POST UX the plan "
            "requires. Until that lands, refuse the ACTION but hand the user "
            "the LibCal booking page so they self-serve in two clicks. "
            "Info-style questions (how do I book a room?) are NOT gated -- "
            "the agent answers those with the room-reservations page."
        ),
        "redirect_to": "human_help",
        "response": "I can't book rooms for you yet -- reservations go through LibCal so they're tied to your account. Book yours at https://muohio.libcal.com/spaces (pick your library, room, and time -- takes about a minute). Bookings are capped at 2 hours.",
    },
    "place_holds": {
        "description": "Place holds on books or materials",
        "reason": "No integration with patron account system",
        "redirect_to": "human_help",
        # Copy fixed 2026-06-09 (audit C4): pointed at the bare homepage,
        # which doesn't show how to place a hold. Primo search is where
        # the "Place Hold" button lives.
        "response": "I can't place holds for you -- only you can, signed into your account. Search the item in Primo (https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU), click \"Place Hold\" on the title, and sign in. A librarian can help if you get stuck.",
    },
    "catalog_search": {
        "description": "Search for books, articles, journals, e-resources",
        "reason": "Catalog search is by-design self-service via Primo (the bot does not proxy searches)",
        "redirect_to": "human_help",
        # Copy fixed 2026-06-09 (audit C4): the old text said "Catalog
        # search is currently unavailable", which read as an OUTAGE. It is
        # not an outage -- searching is by-design handed off to Primo. The
        # gold case ref_catalog_search_handoff expects a clean Primo
        # handoff, and cap2_course_reserves_submit was hitting this lie too.
        "response": "I can't run catalog searches for you, but Primo -- the library catalog -- can do it in one box: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU. It covers our books, ebooks, articles, media, and OhioLINK partner libraries. A librarian on Ask Us can also help you find materials.",
    },
    "interlibrary_loan": {
        "description": "Request or check status of interlibrary loans (ILL)",
        "reason": "No integration with ILL system - but can provide ILL portal links",
        "redirect_to": "ill_info",  # Special handling for campus-specific ILL
        # Copy fixed 2026-06-09 (audit C4): promised "I can show you how"
        # without actually showing anything. Now carries the form URL, per
        # the gold contract (refusal + the request-form URL).
        "response": "I can't submit ILL requests for you -- requests go through the official form so they're tied to your account. Submit yours at https://www.lib.miamioh.edu/use/borrow/ill/ (takes a couple of minutes). Pickup is at your campus library.",
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
        # Copy fixed 2026-06-09 (audit C4): also covers the faculty
        # "put my book on reserve FOR me" action request, which previously
        # fell through to the catalog_search "currently unavailable" lie.
        "response": "I can't check or submit course reserves for you. Browse current reserves or find the faculty request process at https://libguides.lib.miamioh.edu/reserves-textbooks/ -- the circulation desk staff can take it from there.",
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
    # Action-gated (see _REQUIRES_ACTION_SIGNAL): only "book it FOR me" /
    # "can you book" / imperative "Book a room..." phrasings refuse here.
    # "How do I book a study room?" carries no action signal and flows to
    # the agent, which answers with the room-reservations page.
    "book_room_action": [
        r'\b(book|reserve)\b.*\b(study\s*|group\s*)?room\b',
        r'\broom\b.*\b(book|booking|reserve|reservation)\b',
    ],
    "renew_books": [
        # Plurals added 2026-06-10: `\bbook\b` does not match "books", so
        # "Can you renew my books for me?" never hit this template and fell
        # through to the agent (pre-existing gap, found by regression probe).
        r'\b(renew|renewal|extend|extension)\b.*\b(books?|items?|materials?|checkouts?|loans?)\b',
        r'\b(books?|items?|materials?)\b.*\b(renew|renewal|due|extend)\b',
        r'\bcan i renew\b',
        r'\bhow (do|can) i renew\b',
        r'\brenewal eligibility\b',
        r'\bcheck.*renewal\b',
    ],
    "check_account": [
        # Tightened 2026-05-23: was `\b(my|check)\s*(library)?\s*(account|fines?|...|checkouts?|loans?|items?)\b`
        # which fired on "my checkout" -- catching `renew_extend`
        # ("How do I extend my checkout?") as a false-positive
        # check_account refusal. The narrower split below keeps
        # `cap_check_my_account` covered (regex 2 + 4) while letting
        # info phrasings about checkouts pass through to the agent loop.
        r'\bmy\s*(library)?\s*(account|fines?|fees?|balance)\b',
        r'\bcheck\s*(library)?\s*(my\s*)?(account|fines?|fees?|balance|checkouts?|loans?|items?)\b',
        r'\bwhat (do i|books|items).*\b(owe|checked out|have out|borrowed)\b',
        r'\bhow much do i owe\b',
        r'\bwhat.*checked out\b',
        r'\bmy (fines?|fees?|balance)\b',
    ],
    "place_holds": [
        r'\b(place|put|request)\s*(a)?\s*hold\b',
        r'\bhold.*on\s*(a|this|the)?\s*(book|item)\b',
        # `\brequest.*book\b` REMOVED 2026-06-09 (audit C4): it hijacked
        # explicit ILL action requests -- "Submit an ILL request for me for
        # the book Foundation" matched HERE first (dict order puts
        # place_holds before interlibrary_loan), so the user got the holds
        # template instead of the ILL one (ill_no_submit_refusal). ILL
        # phrasings match the interlibrary_loan patterns explicitly; a bare
        # "request a book" action falls to the hold/ILL patterns above or
        # through to the agent, which answers with the Primo hold flow.
    ],
    "interlibrary_loan": [
        r'\b(ill|interlibrary\s*loan)\b',
        r'\b(request|get|order)\s*(a)?\s*book.*another\s*library\b',
        r'\bborrow.*other\s*librar',
        r'\b(book|article|item)\s*(not\s*)?(available|held|owned)\b',
        r'\bnot\s*(available|held)\s*(at|by)\s*(miami|the\s*library)\b',
        r'\bget\s*(a\s*)?(book|article)\s*from\s*(another|other|different)\s*library\b',
        r'\bhow\s*(do|can)\s*i\s*(get|borrow|request)\b.*\bnot\s*(at|in|available)\b',
        r'\bborrow\b.*\b(book|article|item)\b.*\bnot\b.*\b(from|at|in|by)\b.*\b(miami|mu|our)\b',
        r'\b(book|article|item)\b.*\bnot\s*(from|at|in|by)\s*(miami|mu|our\s*library)\b',
        r'\bborrow\b.*\b(book|item)\b.*\b(another|other|different|outside|not from)\b',
        r'\b(get|find|access|obtain)\b.*\b(book|article)\b.*\b(not|doesn.t|don.t)\b.*\b(have|own|carry)\b',
        r'\b(book|article)\b.*\b(another|other|different)\s*(university|school|college|institution|library)\b',
        r'\bborrow\b.*\b(book|item|article)\b.*\bfrom\b',
    ],
    # course_reserves MUST be checked before catalog_search: first-match-
    # wins, and catalog's broad `books?\b.*\bon\b` regex matched "put my
    # book ON course reserves", serving the Primo-handoff copy for a
    # reserves request (audit case cap2_course_reserves_submit,
    # 2026-06-09). Specific topic before generic topic.
    "course_reserves": [
        r'\b(course|class)\s*reserves?\b',
        r'\breserves?\s*(for|in)\s*(my|a|the)?\s*(class|course)\b',
        r'\bprofessor.*put.*reserve\b',
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
    "pay_fines": [
        r'\b(pay|paying)\s*(my|library|a)?\s*(fines?|fees?|balance)\b',
        r'\bhow.*pay.*fine\b',
    ],
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Action signals: phrases that mark the user as asking the BOT to perform
# the action (vs asking informationally how to do it themselves). The
# action-vs-info distinction is critical: "How do I renew my book?" should
# get an answer pointing to MyAccount, while "Can you renew my book?"
# should refuse with the same URL but an explicit "I can't do that for
# you" preamble.
#
# Without this gate, the topic regexes below were over-firing on ALL
# 27 ILL/catalog/place_holds/renew gold cases that the eval expects to
# answer (see eval failure analysis 2026-05-23). The intent-capability
# registry (router/intent_capabilities.py) handles the info case via
# READY (agent + synth) or POINT_TO_URL (Primo / A-Z).
_ACTION_SIGNALS: List[str] = [
    # Bot-directive: "can/could/would/will you [do X]"
    r"\b(can|could|would|will)\s+you\b",
    # "for me" / "for us" -- explicit personal request to the bot
    r"\bfor\s+(me|us)\b",
    # Sentence-initial imperative: "Renew my book", "Submit ILL...",
    # "Book a room at Rentschler tomorrow". Allows leading "please ".
    r"^\s*(please\s+)?(renew|submit|file|place|cancel|pay|extend|process|hold|book|reserve|find\s+me|get\s+me|pull\s+up)\b",
    # "please [action verb]" anywhere in the message.
    r"\bplease\s+(renew|submit|file|place|cancel|pay|extend|process|hold|book|reserve)\b",
]

# Limitations gated on action signals -- the bot only refuses these when
# the user phrased it as an action request. Info-style phrasings fall
# through to the intent-capability registry, which routes them to
# POINT_TO_URL (find_resource -> Primo, databases -> A-Z) or to the
# normal agent loop (interlibrary_loan / renew / holds = READY; the
# synthesizer composes a "here's how + here's the URL" answer).
#
# `check_account` and `pay_fines` are NOT gated: their existing topic
# patterns are already personal-account-specific ("my fines", "what do
# I owe") so info-style phrasings don't match them in the first place.
_REQUIRES_ACTION_SIGNAL: Set[str] = {
    "renew_books",
    "place_holds",
    "interlibrary_loan",
    "catalog_search",
    "course_reserves",
    "book_room_action",
}


def _has_action_signal(user_msg_lower: str) -> bool:
    """True if the message contains any bot-directive / for-me / imperative
    marker. Lowercased input expected (cheaper to lowercase once at the
    caller than re-lower in each pattern)."""
    for pattern in _ACTION_SIGNALS:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            return True
    return False


def detect_limitation_request(user_message: str) -> Dict[str, any]:
    """Check if user is asking for something the bot cannot do.

    Action-vs-info gating: for limitation types in `_REQUIRES_ACTION_SIGNAL`,
    we ONLY trigger the refusal when the user's phrasing carries an
    action signal (bot-directive, "for me", or imperative). Info-style
    phrasings ("How do I renew?", "Where do I pick up ILL?") fall
    through so the intent-capability registry can serve them via
    POINT_TO_URL or the agent loop.

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
    has_action = _has_action_signal(user_msg_lower)

    for limitation_type, patterns in LIMITATION_PATTERNS.items():
        # Action-gated limitations: skip if the user asked an info question.
        if limitation_type in _REQUIRES_ACTION_SIGNAL and not has_action:
            continue
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


# ============================================================================
# ILL (INTERLIBRARY LOAN) CAMPUS-SPECIFIC URLS
# ============================================================================

ILL_URLS = {
    "main": {
        "name": "Oxford (Main Campus)",
        "url": "https://www.lib.miamioh.edu/use/borrow/ill/",
        "description": "King Library and main Oxford campus",
    },
    "hamilton": {
        "name": "Hamilton Campus (Rentschler Library)",
        "url": "https://libguides.lib.miamioh.edu/ILL",
        "description": "Hamilton regional campus",
    },
    "middletown": {
        "name": "Middletown Campus (Gardner-Harvey Library)", 
        "url": "https://www.mid.miamioh.edu/library/interlibraryloan.htm",
        "description": "Middletown regional campus",
    },
}

def detect_campus_from_message(user_message: str) -> str:
    """Detect which campus the user is asking about for ILL.
    
    Returns:
        'hamilton', 'middletown', or 'main' (default)
    """
    user_msg_lower = user_message.lower()
    
    # Hamilton campus patterns
    hamilton_patterns = [
        r'\bhamilton\b',
        r'\brentschler\b',
        r'\bham\s*campus\b',
    ]
    
    # Middletown campus patterns  
    middletown_patterns = [
        r'\bmiddletown\b',
        r'\bgardner[\s-]?harvey\b',
        r'\bmid\s*campus\b',
    ]
    
    for pattern in hamilton_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            return "hamilton"
    
    for pattern in middletown_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            return "middletown"
    
    # Default to main campus
    return "main"


def get_ill_response(user_message: str) -> str:
    """Get campus-specific ILL response.
    
    Args:
        user_message: The user's message to detect campus
        
    Returns:
        Formatted ILL response with appropriate campus URL
    """
    campus = detect_campus_from_message(user_message)
    campus_info = ILL_URLS.get(campus, ILL_URLS["main"])
    
    # Build response with all campus options
    response = f"""**Interlibrary Loan (ILL)** lets you borrow items not available at Miami University Libraries.

**Your ILL Portal** ({campus_info['name']}):
🔗 {campus_info['url']}

**How to request:**
1. Sign in with your Miami credentials
2. Choose "Borrowing" and select book or article
3. Fill in the citation details and submit
4. You'll receive email updates when it arrives

**Turnaround time:** 1-2 weeks for books, 2-5 days for articles

"""
    
    # Add other campus links if user might need them
    if campus == "main":
        response += """**Regional Campus ILL:**
• Hamilton: https://libguides.lib.miamioh.edu/ILL
• Middletown: https://www.mid.miamioh.edu/library/interlibraryloan.htm"""
    else:
        response += f"""**Main Campus (Oxford) ILL:**
• {ILL_URLS['main']['url']}"""
    
    return response


# ============================================================================
# POLICY URLS - Authoritative sources for specific policy questions
# ============================================================================

POLICY_URLS = {
    "loan_periods": {
        "url": "https://libguides.lib.miamioh.edu/circulation-policies/loan-periods-fines",
        "description": "Loan periods and fines for different patron types",
        "patterns": [
            r'\b(how\s*long|loan\s*period|checkout\s*period|borrow\s*period)\b',
            r'\b(check\s*out|checkout)\b.*\b(how\s*long|period|time|days?|weeks?)\b',
            r'\bhow\s*(long|many\s*(days?|weeks?))\s*(can\s*i|to)\s*(keep|borrow|check\s*out|have)\b',
            r'\b(loan|lending|borrowing|checkout)\s*(period|policy|policies|time|limit)\b',
            r'\bwhen\s*(is|are)\s*(it|books?|items?)\s*due\b',
            r'\bdue\s*date\s*(policy|policies)?\b',
            r'\b(renewal|renew)\s*(policy|policies|limit|period)\b',
            r'\bfines?\s*(policy|policies|amount|rate)\b',
            r'\b(overdue|late)\s*(fee|fine|charge|policy)\b',
        ],
    },
    "circulation_policies": {
        "url": "https://libguides.lib.miamioh.edu/circulation-policies",
        "description": "General circulation policies",
        "patterns": [
            r'\bcirculation\s*(policy|policies)\b',
            r'\bborrowing\s*(policy|policies|rules?|privileges?)\b',
        ],
    },
}


def detect_policy_question(user_message: str) -> Dict[str, any]:
    """Detect if user is asking about a specific policy with authoritative URL.
    
    Args:
        user_message: The user's message
        
    Returns:
        Dict with:
        - is_policy_question: True if this is a policy question
        - policy_type: The type of policy (e.g., "loan_periods")
        - url: The authoritative URL for this policy
        - description: Description of what the URL covers
    """
    user_msg_lower = user_message.lower()
    
    for policy_type, policy_info in POLICY_URLS.items():
        for pattern in policy_info.get("patterns", []):
            if re.search(pattern, user_msg_lower, re.IGNORECASE):
                return {
                    "is_policy_question": True,
                    "policy_type": policy_type,
                    "url": policy_info["url"],
                    "description": policy_info["description"],
                }
    
    return {"is_policy_question": False}


def get_policy_response(policy_type: str, user_message: str = "") -> str:
    """Get authoritative response for a policy question.
    
    Args:
        policy_type: Type of policy from POLICY_URLS
        user_message: Original user message for context
        
    Returns:
        Formatted response with authoritative URL
    """
    policy_info = POLICY_URLS.get(policy_type, {})
    url = policy_info.get("url", "https://www.lib.miamioh.edu/")
    description = policy_info.get("description", "library policies")
    
    if policy_type == "loan_periods":
        return f"""For accurate and up-to-date information on **loan periods and fines**, please visit our official circulation policies page:

🔗 **{url}**

This page has detailed information on:
• Loan periods for undergraduates, graduates, faculty & staff
• Renewal policies and limits
• Fines and fees for overdue items
• Course reserves loan periods
• DVD and media loan periods

If you have specific questions, feel free to ask a librarian at (513) 529-4141 or chat at https://www.lib.miamioh.edu/research/research-support/ask/"""
    
    return f"""For information on {description}, please visit:

🔗 **{url}**

For additional help, contact a librarian at (513) 529-4141."""


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
