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
        "Books, articles, journals, e-resources in library catalog",
        "Database access and recommendations",
        "Research guides (LibGuides)",
        "Citation tools and research help",
        "Library catalog search (Primo)",
        "Interlibrary loan information",
        "Resource availability and locations",
    ],
    
    "library_services": [
        "Study room reservations",
        "Library building hours (King, Art & Architecture, etc.)",
        "Printing, scanning, copying services IN THE LIBRARY",
        "Library card and borrowing policies",
        "Renewing materials",
        "Overdue fines and fees FOR LIBRARY MATERIALS",
        "Equipment checkout (laptops, chargers, etc.)",
        "Accessibility services IN THE LIBRARY",
    ],
    
    "library_spaces": [
        "King Library",
        "Art & Architecture Library",
        "Armstrong Student Center library services",
        "Hamilton Campus Rentschler Library",
        "Middletown Campus Gardner-Harvey Library",
        "Study spaces and quiet areas IN LIBRARIES",
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
        "Armstrong Student Center (non-library areas)",
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
        "fallback": "Visit lib.miamioh.edu/contact for librarian contact information",
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
   - Library resources (books, databases, articles)
   - Library services (study rooms, hours, borrowing)
   - Library spaces and locations
   - Library staff and subject librarians
   - Library policies

2. OUT OF SCOPE - Redirect to appropriate service:
   - General Miami University questions → "For general university questions, please visit miamioh.edu or contact the university at (513) 529-1809"
   - Academic advising → "Please contact your academic advisor"
   - Course content → "Please contact your professor or academic department"
   - IT support → "Please contact IT Services at ithelp@miamioh.edu"
   - Non-library facilities → Direct to appropriate department

3. NEVER MAKE UP INFORMATION:
   - NEVER generate email addresses
   - NEVER generate phone numbers
   - NEVER generate librarian names unless from API
   - ONLY provide contact info retrieved from official sources
   - If unsure, say "I don't have that specific information" and direct to lib.miamioh.edu/contact

4. WHEN IN DOUBT:
   - Guide to human librarian: "I'd be happy to connect you with a librarian who can help"
   - Provide Ask-a-Librarian chat link
   - Give general library contact: (513) 529-4141 or lib.miamioh.edu/contact
""",
    
    "out_of_scope_response": """I appreciate your question, but that's outside the scope of library services. I can only help with library-related questions such as:

• Finding books, articles, and research materials
• Library hours and study room reservations
• Subject librarians and research guides
• Library policies and services

For your question, please contact:
{appropriate_department}

Is there anything library-related I can help you with?""",
    
    "uncertain_response": """I'm not certain about that specific information. To ensure you get accurate help, I recommend:

• **Chat with a librarian**: {lib_chat_url}
• **Call the library**: (513) 529-4141
• **Visit our website**: https://www.lib.miamioh.edu/contact

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
        "technical_support": "IT Services at ithelp@miamioh.edu or call (513) 529-7900",
        "non_library_facilities": "the appropriate university department at miamioh.edu",
    }
    
    appropriate_dept = redirects.get(topic_category, "the appropriate university department")
    
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
        "contact_page": "https://www.lib.miamioh.edu/contact",
    },
    
    "ask_a_librarian": {
        "chat_url": "https://libanswers.lib.miamioh.edu/chat/widget/7fb43538479e4f82cbbe2c74325fdda2",
        "email_form": "https://www.lib.miamioh.edu/contact",
        "phone": "(513) 529-4141",
    },
    
    "art_architecture_library": {
        "name": "Art & Architecture Library",
        "website": "https://www.lib.miamioh.edu/art-architecture",
    },
    
    "regional_libraries": {
        "hamilton": {
            "name": "Rentschler Library (Hamilton)",
            "website": "https://regionals.miamioh.edu/hamilton/academics/library/",
        },
        "middletown": {
            "name": "Gardner-Harvey Library (Middletown)",
            "website": "https://regionals.miamioh.edu/middletown/academics/library/",
        },
    },
}
