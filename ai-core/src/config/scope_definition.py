"""
Miami University Libraries Chatbot - Strict Scope Definition

This module defines the STRICT boundaries of what the chatbot can and cannot answer.
The chatbot is LIMITED to Miami University Libraries ONLY - not general Miami University.

CRITICAL RULES:
1. ONLY answer questions about Miami University Libraries
2. NEVER make up contact information (emails, phone numbers, names)
3. ALWAYS verify information comes from official sources (APIs, databases)
4. Guide users to human librarians for out-of-scope questions
"""

# ============================================================================
# STRICT SCOPE BOUNDARIES
# ============================================================================

IN_SCOPE_TOPICS = {
    "library_resources": [
        # NOTE: Catalog/discovery search (Primo / Alma) is intentionally NOT in
        # scope until the Alma API integration is tested. Do not list "books",
        # "articles", "journals", "e-resources", or "database search" here --
        # doing so tells the LLM the bot can do catalog work it cannot actually
        # do, and users get routed away from the human handoff that is the
        # correct path for catalog queries today. See orchestrator.py catalog
        # pre-check and archived/primo/ for the disabled implementation.
        "Research guides (LibGuides) -- surface the guide URL, do not search it",
        "How to use citation tools (surface guides / tutorials, not do the citing)",
        "Interlibrary loan INFORMATION (point to the ILL request form; the bot does not submit requests)",
        "General info about how to find resources (pointing to Primo / librarians)",
    ],
    "library_services": [
        "Study room reservations",
        "Library building hours (King, Art & Architecture, etc.)",
        "Printing, scanning, copying services IN THE LIBRARY",
        "Interlibrary loan and borrowing policies",
        "Renewing materials",
        "Overdue fines and fees FOR LIBRARY MATERIALS",
        "Equipment checkout (laptops, chargers, etc.)",
        "Accessibility services IN THE LIBRARY",
    ],
    "library_spaces": [
        "King Library",
        "Art & Architecture Library",
        "Hamilton Campus Rentschler Library",
        "Middletown Campus Gardner-Harvey Library",
        "Study spaces and graduate study spaces IN LIBRARIES",
        "Library floor maps and locations",
    ],
    "library_staff": [
        "Subject librarians and their contact info (FROM API ONLY)",
        "Library departments and their functions",
        "Librarian expertise areas (FROM API ONLY)",
        "How to schedule research consultations",
    ],
    "library_policies": [
        "Borrowing policies",
        "Return policies",
        "Fine policies FOR LIBRARY MATERIALS",
        "Access policies (who can use the library)",
        "Study room policies",
        "Food and drink policies IN THE LIBRARY",
    ],
}

OUT_OF_SCOPE_TOPICS = {
    "university_general": [
        "Admissions questions",
        "Financial aid (not library-related)",
        "Course registration",
        "Tuition and fees (not library fines)",
        "Housing and dining",
        "Student organizations (unless library-related)",
        "Campus events (unless library events)",
        "Academic advising",
        "Career services",
        "Health services",
        "Parking (unless library-specific)",
    ],
    "academic_content": [
        "Homework help",
        "Assignment answers",
        "Test preparation",
        "Course content questions",
        "Grading policies",
        "Professor office hours (except librarians)",
    ],
    "technical_support": [
        "Canvas/Blackboard help",
        "Email account issues",
        "Wi-Fi problems (unless library-specific)",
        "Software installation (unless library software)",
        "General IT support",
    ],
    "non_library_facilities": [
        "Armstrong Student Center",
        "Rec Center",
        "Dining halls",
        "Residence halls",
        "Athletic facilities",
    ],
}

# ============================================================================
# STRICT VALIDATION RULES
# ============================================================================

CONTACT_INFO_RULES = {
    "email": {
        "allowed_sources": [
            "LibGuides API",
            "Subject Librarian database",
            "Official library database",
        ],
        "never_generate": True,
        "verification_required": True,
        "fallback": "Visit https://www.lib.miamioh.edu/research/research-support/ask/ for librarian contact information",
    },
    "phone": {
        "allowed_sources": [
            "LibGuides API",
            "Official library database",
        ],
        "never_generate": True,
        "verification_required": True,
        "fallback": "Call the main library at (513) 529-4141",
    },
    "names": {
        "allowed_sources": [
            "LibGuides API (guide owners)",
            "Subject Librarian database",
        ],
        "never_generate": True,
        "verification_required": True,
        "fallback": "Visit lib.miamioh.edu/librarians to find the appropriate librarian",
    },
}

# ============================================================================
# RESPONSE GUIDELINES
# ============================================================================

SCOPE_ENFORCEMENT_PROMPTS = {
    "system_reminder": """
CRITICAL SCOPE RULES - MUST FOLLOW STRICTLY:

1. ONLY ANSWER about Miami University LIBRARIES
   - Library services (study rooms, hours, borrowing, printing, MakerSpace)
   - Library spaces and locations (King, Wertz, Rentschler, Gardner-Harvey, SWORD, Special Collections)
   - Library staff and subject librarians (lookup only, from API)
   - Library policies
   - Research guides (LibGuides) -- point to the guide URL, don't search it
   - Interlibrary loan (ILL) -- point to the request form, don't submit requests

   ⚠️ CATALOG / DISCOVERY SEARCH IS DISABLED.
   The bot CANNOT search for books, articles, journals, databases, or
   e-resources. For any such question, route to a human librarian. Do not
   offer catalog search as a capability in refusal or clarification text.

2. OUT OF SCOPE - Redirect to appropriate service:
   - General Miami University questions → "For general university questions, please visit miamioh.edu or contact the university at (513) 529-1809"
   - Academic advising → "Please contact your academic advisor"
   - Course content → "Please contact your professor or academic department"
   - Non-library facilities → Direct to appropriate department

3. NEVER MAKE UP INFORMATION:
   - NEVER generate email addresses
   - NEVER generate phone numbers
   - NEVER generate librarian names unless from API
   - ONLY provide contact info retrieved from official sources
   - If unsure, say "I don't have that specific information" and direct to https://www.lib.miamioh.edu/research/research-support/ask/

4. WHEN IN DOUBT:
   - Guide to human librarian: "I'd be happy to connect you with a librarian who can help"
   - Provide Ask-a-Librarian chat link
   - Give general library contact: (513) 529-4141 or https://www.lib.miamioh.edu/research/research-support/ask/
""",
    "out_of_scope_response": """I appreciate your question, but that's outside the scope of library services. I can only help with library-related questions such as:

• Library hours and study room reservations
• Subject librarians and research guide (LibGuide) lookups
• Library locations, spaces, and services (printing, MakerSpace, Special Collections, etc.)
• Interlibrary Loan (ILL) info and where to submit a request
• Library policies (borrowing, fines, access)

For finding specific books, articles, or database results, I can connect you with a librarian — catalog search isn't something I can do directly.

For your question, please contact:
{appropriate_department}

Is there anything library-related I can help you with?""",
    "uncertain_response": """I'm not certain about that specific information. To ensure you get accurate help, I recommend:

• **Chat with a librarian**: {lib_chat_url}
• **Call the library**: (513) 529-4141
• **Visit our website**: https://www.lib.miamioh.edu/research/research-support/ask/

Is there something else about library resources or services I can help with?""",
}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================


def is_in_scope(query: str) -> bool:
    """
    Determine if a query is within the library's scope.
    This is a helper - the LLM will do the actual classification.
    """
    # This will be used by the orchestrator for pre-filtering
    # The LLM classification is the primary mechanism
    return True  # Let LLM decide


def validate_contact_info(info_type: str, value: str, source: str) -> bool:
    """
    Validate that contact information comes from approved sources.

    Args:
        info_type: 'email', 'phone', or 'name'
        value: The actual contact information
        source: Where the information came from

    Returns:
        bool: True if valid and from approved source
    """
    rules = CONTACT_INFO_RULES.get(info_type, {})
    allowed_sources = rules.get("allowed_sources", [])

    if source not in allowed_sources:
        return False

    return True


def get_out_of_scope_response(topic_category: str = None) -> str:
    """
    Get appropriate response for out-of-scope questions.

    Args:
        topic_category: Category of the out-of-scope topic

    Returns:
        str: Appropriate redirect message
    """
    redirects = {
        "university_general": "Miami University's main website at miamioh.edu or call (513) 529-1809",
        "academic_content": "your professor or academic advisor",
        "non_library_facilities": "the appropriate university department at miamioh.edu",
    }

    appropriate_dept = redirects.get(
        topic_category, "the appropriate university department"
    )

    return SCOPE_ENFORCEMENT_PROMPTS["out_of_scope_response"].format(
        appropriate_department=appropriate_dept
    )


# ============================================================================
# LIBRARY OFFICIAL CONTACT INFORMATION (VERIFIED)
# ============================================================================

OFFICIAL_LIBRARY_CONTACTS = {
    "main_library": {
        "name": "King Library",
        "phone": "(513) 529-4141",
        "email": None,  # Use contact form instead
        "website": "https://www.lib.miamioh.edu",
        "contact_page": "https://www.lib.miamioh.edu/research/research-support/ask/",
    },
    "ask_a_librarian": {
        "chat_url": "https://libanswers.lib.miamioh.edu/chat/widget/7fb43538479e4f82cbbe2c74325fdda2",
        "email_form": "https://www.lib.miamioh.edu/ask-email-form/",
        "phone": "(513) 529-4141",
    },
    "art_architecture_library": {
        "name": "Wertz Art & Architecture Library",
        "website": "https://www.lib.miamioh.edu/about/locations/art-arch/",
        "phone": "(513) 529-6638",
    },
    "regional_libraries": {
        "hamilton": {
            "name": "Rentschler Library (Hamilton)",
            "website": "https://www.ham.miamioh.edu/library/",
            "phone": "(513) 785-3235",
        },
        "middletown": {
            "name": "Gardner-Harvey Library (Middletown)",
            "website": "https://www.mid.miamioh.edu/library/",
            "phone": "(513) 727-3222",
        },
    },
}
