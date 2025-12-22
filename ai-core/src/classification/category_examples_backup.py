"""
Category Examples for RAG-Based Classification

This module contains rich examples for each question category to enable
semantic similarity-based classification instead of hardcoded regex patterns.

Each category includes:
- Description: What this category covers
- In-scope examples: Questions that belong to this category
- Out-of-scope examples: Similar questions that DON'T belong here
- Boundary cases: Ambiguous examples that need clarification
- Keywords: Important terms (for hybrid search)
"""

from typing import Dict, List, Any

# ============================================================================
# LIBRARY SERVICES CATEGORIES (In-Scope)
# ============================================================================

LIBRARY_EQUIPMENT_CHECKOUT = {
    "category": "library_equipment_checkout",
    "description": "Questions about borrowing library equipment like laptops, computers, chargers, cameras, calculators, or software licenses (Adobe, etc.). The library provides these for checkout.",
    "agent": "policy_or_service",
    "in_scope_examples": [
        "Can I borrow a laptop from the library?",
        "Do you have computers available for checkout?",
        "Can I check out a Chromebook?",
        "Does the library have laptop chargers?",
        "Can I rent a camera from the library?",
        "Do you have calculators to borrow?",
        "Can I get Adobe software from the library?",
        "Does the library loan out headphones?",
        "Can I checkout an iPad?",
        "Are there tripods available?",
        "Can I borrow equipment for my project?",
        "Do you have MacBooks for checkout?",
        "Can I get a laptop adapter?",
        "Does the library have desktop computers I can use?",
        "Can I checkout software licenses?",
        "Do you loan out electronic equipment?",
    ],
    "out_of_scope_examples": [
        "My computer is broken, who can fix it?",
        "I can't connect to WiFi, help!",
        "My laptop won't turn on",
        "Canvas isn't working",
        "I forgot my email password",
    ],
    "boundary_cases": [
        {
            "question": "I have a question about computers",
            "clarification_needed": "Are you asking about: (1) Borrowing/checking out a computer from the library, or (2) Getting help with a computer problem/repair?",
            "possible_categories": ["library_equipment_checkout", "out_of_scope_tech_support"]
        },
        {
            "question": "Who can help me with computer stuff?",
            "clarification_needed": "Are you asking about: (1) Borrowing library computers/equipment, or (2) Technical support for computer problems?",
            "possible_categories": ["library_equipment_checkout", "out_of_scope_tech_support"]
        },
    ],
    "keywords": ["borrow", "checkout", "check out", "rent", "loan", "laptop", "computer", "chromebook", "equipment", "device", "camera", "calculator", "adobe", "software", "charger", "ipad", "macbook"],
}

LIBRARY_HOURS_ROOMS = {
    "category": "library_hours_rooms",
    "description": "Questions about library building hours, schedules, or room reservations/bookings.",
    "agent": "booking_or_hours",
    "in_scope_examples": [
        "What time does King Library close?",
        "When does the library open tomorrow?",
        "Library hours for Saturday?",
        "Is the library open on Sunday?",
        "Book a study room",
        "Reserve a group study room for 4 people",
        "Can I book a room for tomorrow?",
        "Are study rooms available?",
        "How do I reserve a study space?",
        "What are the hours for Amos Music Library?",
    ],
    "out_of_scope_examples": [
        "When is class registration?",
        "What time does the dining hall close?",
        "When is the football game?",
    ],
    "boundary_cases": [],
    "keywords": ["hours", "open", "close", "schedule", "book", "reserve", "room", "study room", "library hours"],
}

SUBJECT_LIBRARIAN_GUIDES = {
    "category": "subject_librarian_guides",
    "description": "Finding subject librarians by discipline, or finding LibGuides/research guides for a specific subject or major.",
    "agent": "subject_librarian",
    "in_scope_examples": [
        "Who is the biology librarian?",
        "Find the business librarian",
        "LibGuide for nursing",
        "Research guide for psychology",
        "I need help with chemistry research",
        "Who can help with history research?",
        "Subject librarian for engineering",
        "Guide for accounting students",
        "Show me all subject librarians",
        "List of subject librarians",
    ],
    "out_of_scope_examples": [
        "I need 5 articles about biology",
        "Find me sources for my paper",
        "What databases should I use?",
    ],
    "boundary_cases": [],
    "keywords": ["subject librarian", "librarian", "libguide", "research guide", "guide", "subject", "major", "department"],
}

RESEARCH_HELP_HANDOFF = {
    "category": "research_help_handoff",
    "description": "Questions asking for specific research help, article searches, database recommendations, or search strategies. These require human librarian expertise.",
    "agent": "human_help",
    "in_scope_examples": [
        "I need 3 articles about climate change",
        "Find me 5 peer-reviewed sources on psychology",
        "I need articles 10 pages or longer about nursing",
        "What databases should I use for my research?",
        "How do I search for scholarly articles?",
        "I need help finding sources for my paper",
        "Can you help me develop a search strategy?",
        "I'm writing a paper about the effects of social media",
        "Looking for articles on the relationship between diet and health",
        "I need peer-reviewed journals about education",
        "Help me find sources about artificial intelligence",
    ],
    "out_of_scope_examples": [
        "LibGuide for computer science",
        "Who is the engineering librarian?",
        "Can you help me write my essay?",
    ],
    "boundary_cases": [],
    "keywords": ["articles", "sources", "research", "peer-reviewed", "scholarly", "database", "search strategy", "find sources", "papers", "journals"],
}

LIBRARY_POLICIES_SERVICES = {
    "category": "library_policies_services",
    "description": "Questions about library policies, services, loan periods, renewals, printing, food/drink policies, noise policies, or general library information from the website.",
    "agent": "policy_or_service",
    "in_scope_examples": [
        "How do I renew a book?",
        "What's the loan period for DVDs?",
        "Can I print in the library?",
        "How much are late fees?",
        "Where is the quiet study area?",
        "What services does the library offer?",
        "How do I get a library card?",
        "Can I scan documents here?",
        "What are the circulation policies?",
        "How long can I keep a book?",
        "Can I eat/drink in the library?",
        "Can I eat in the library?",
        "Can I drink in the library?",
        "Are food and drinks allowed?",
        "Can I bring food into the library?",
        "Can I have coffee in the library?",
        "Is food allowed in the library?",
        "Can I eat at my desk in the library?",
        "Where can I eat in the library?",
        "Library food policy",
        "Can I bring snacks?",
        "Is water allowed in the library?",
    ],
    "out_of_scope_examples": [
        "How do I register for classes?",
        "Where is the student center?",
        "What's for lunch today?",
        "Where can I buy food on campus?",
    ],
    "boundary_cases": [],
    "keywords": ["policy", "service", "renew", "loan period", "print", "scan", "fine", "fee", "circulation", "library card", "food", "drink", "eat", "coffee", "snacks", "water", "beverage"],
}

HUMAN_LIBRARIAN_REQUEST = {
    "category": "human_librarian_request",
    "description": "Direct requests to speak with or connect to a human librarian.",
    "agent": "human_help",
    "in_scope_examples": [
        "Can I talk to a librarian?",
        "Connect me to a human",
        "I need to speak with someone",
        "Is there a real person I can talk to?",
        "Can I chat with a librarian?",
        "I want human help",
    ],
    "out_of_scope_examples": [],
    "boundary_cases": [],
    "keywords": ["talk", "speak", "human", "librarian", "person", "chat", "connect"],
}

# ============================================================================
# OUT-OF-SCOPE CATEGORIES (University but not Library)
# ============================================================================

OUT_OF_SCOPE_TECH_SUPPORT = {
    "category": "out_of_scope_tech_support",
    "description": "Technical problems with computers, devices, WiFi, Canvas, email, passwords. These are IT support issues, not library services.",
    "agent": "out_of_scope",
    "in_scope_examples": [
        "My computer is broken",
        "I can't connect to WiFi",
        "Canvas isn't working",
        "I forgot my password",
        "My laptop won't turn on",
        "Email isn't working",
        "How do I fix my computer?",
        "My phone won't connect",
        "I need tech support",
        "Who can fix my laptop?",
        "My computer crashed",
        "I have a virus on my computer",
        "My device is frozen",
    ],
    "out_of_scope_examples": [
        "Can I borrow a laptop?",
        "Do you have computers for checkout?",
    ],
    "boundary_cases": [
        {
            "question": "My computer has a problem, who should I contact?",
            "clarification_needed": "Are you asking about: (1) IT support to fix your personal computer, or (2) Borrowing a library computer while yours is being fixed?",
            "possible_categories": ["out_of_scope_tech_support", "library_equipment_checkout"]
        },
    ],
    "keywords": ["broken", "fix", "repair", "problem", "issue", "not working", "wifi", "internet", "canvas", "email", "password", "crashed", "frozen", "virus"],
}

OUT_OF_SCOPE_ACADEMICS = {
    "category": "out_of_scope_academics",
    "description": "Course registration, enrollment, class schedules, homework help, or academic content questions.",
    "agent": "out_of_scope",
    "in_scope_examples": [
        "How do I register for classes?",
        "When is course registration?",
        "Can you help me with my homework?",
        "What's the answer to this math problem?",
        "How do I drop a class?",
        "When do I enroll?",
        "Help me write my essay",
        "What classes should I take?",
    ],
    "out_of_scope_examples": [
        "What databases for ENG 111?",
        "LibGuide for my class",
    ],
    "boundary_cases": [],
    "keywords": ["register", "registration", "enroll", "enrollment", "homework", "assignment", "essay", "class", "course", "drop class", "add class"],
}

OUT_OF_SCOPE_CAMPUS_LIFE = {
    "category": "out_of_scope_campus_life",
    "description": "Questions about dining, housing, parking, sports, weather, campus events, or non-library campus locations.",
    "agent": "out_of_scope",
    "in_scope_examples": [
        "What's the weather today?",
        "Where can I eat lunch?",
        "When is the football game?",
        "Where is the student center?",
        "How do I get parking?",
        "What's for dinner?",
        "When is homecoming?",
        "Where is Armstrong Hall?",
    ],
    "out_of_scope_examples": [
        "Where is King Library?",
        "What time does the library close?",
    ],
    "boundary_cases": [],
    "keywords": ["weather", "dining", "food", "lunch", "dinner", "sports", "football", "basketball", "parking", "housing", "student center", "campus event"],
}

OUT_OF_SCOPE_FINANCIAL = {
    "category": "out_of_scope_financial",
    "description": "Questions about tuition, financial aid, scholarships, or payments (not library fines).",
    "agent": "out_of_scope",
    "in_scope_examples": [
        "How much is tuition?",
        "How do I apply for financial aid?",
        "Are there scholarships available?",
        "When is tuition due?",
        "How do I pay my bill?",
    ],
    "out_of_scope_examples": [
        "How much are library late fees?",
        "Do I owe library fines?",
    ],
    "boundary_cases": [],
    "keywords": ["tuition", "financial aid", "scholarship", "payment", "bursar", "bill"],
}

# ============================================================================
# ALL CATEGORIES REGISTRY
# ============================================================================

ALL_CATEGORIES = [
    LIBRARY_EQUIPMENT_CHECKOUT,
    LIBRARY_HOURS_ROOMS,
    SUBJECT_LIBRARIAN_GUIDES,
    RESEARCH_HELP_HANDOFF,
    LIBRARY_POLICIES_SERVICES,
    HUMAN_LIBRARIAN_REQUEST,
    OUT_OF_SCOPE_TECH_SUPPORT,
    OUT_OF_SCOPE_ACADEMICS,
    OUT_OF_SCOPE_CAMPUS_LIFE,
    OUT_OF_SCOPE_FINANCIAL,
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_all_examples_for_embedding() -> List[Dict[str, Any]]:
    """
    Get all examples formatted for embedding into vector store.
    
    Returns:
        List of dicts with: category, question, is_in_scope, metadata
    """
    examples = []
    
    for category_data in ALL_CATEGORIES:
        category = category_data["category"]
        description = category_data["description"]
        agent = category_data["agent"]
        
        # Add in-scope examples
        for question in category_data["in_scope_examples"]:
            examples.append({
                "category": category,
                "question": question,
                "is_in_scope": True,
                "description": description,
                "agent": agent,
                "keywords": category_data.get("keywords", []),
            })
        
        # Add out-of-scope examples (negative examples)
        for question in category_data["out_of_scope_examples"]:
            examples.append({
                "category": category,
                "question": question,
                "is_in_scope": False,
                "description": description,
                "agent": agent,
                "keywords": category_data.get("keywords", []),
            })
    
    return examples


def get_boundary_cases() -> List[Dict[str, Any]]:
    """
    Get all boundary cases that require clarification.
    
    Returns:
        List of dicts with: question, clarification_needed, possible_categories
    """
    boundary_cases = []
    
    for category_data in ALL_CATEGORIES:
        for case in category_data.get("boundary_cases", []):
            boundary_cases.append(case)
    
    return boundary_cases


def get_category_description(category: str) -> str:
    """Get description for a specific category."""
    for cat_data in ALL_CATEGORIES:
        if cat_data["category"] == category:
            return cat_data["description"]
    return ""


def get_category_agent(category: str) -> str:
    """Get the agent that should handle this category."""
    for cat_data in ALL_CATEGORIES:
        if cat_data["category"] == category:
            return cat_data["agent"]
    return "general_question"
