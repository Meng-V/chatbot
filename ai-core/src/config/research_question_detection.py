"""
Research Question Detection - Identifies when users are asking for research help
that should be handled by a human librarian, not the bot.

The bot should NOT:
- Suggest specific databases or search strategies
- Provide detailed research guidance
- Act as a research consultant

The bot SHOULD:
- Direct users to subject librarians for research help
- Offer to connect them with human librarians
- Provide contact information for research support
"""

import re
from typing import Dict, Any

# ============================================================================
# RESEARCH QUESTION PATTERNS
# ============================================================================

RESEARCH_QUESTION_PATTERNS = {
    "article_search_with_specifics": [
        # Looking for specific number of articles with detailed requirements
        r'\b(i\s*need|looking\s*for|find|get|want)\s*\d+\s*(articles?|sources?|papers?|publications?)\b.*\b(pages?|longer|about|on|regarding)\b',
        r'\b\d+\s*(articles?|sources?|papers?)\b.*\b\d+\s*pages?\b',
        r'\b(articles?|papers?)\b.*\b\d+\s*pages?\s*(or\s*more|or\s*longer|minimum)\b',
        # "I need 3 articles 19 pages or more that talk about..."
        r'\b(need|want|looking\s*for)\b.*\b\d+.*\b(articles?|sources?)\b.*\b(about|on|regarding|that\s*(talk|discuss|cover))\b',
    ],
    
    "research_topic_help": [
        # Asking for help finding sources on a specific topic
        r'\b(help|assist|guide)\s*(me\s*)?(find|finding|locate|locating|search|searching)\b.*\b(articles?|sources?|papers?|research|information)\b.*\b(about|on|regarding|for)\b',
        r'\b(where|how)\s*(can\s*i|do\s*i|to)\s*(find|get|locate|search)\b.*\b(articles?|sources?|papers?|research)\b.*\b(about|on|regarding|for)\b',
        r'\b(research|paper|project|assignment)\b.*\b(about|on|regarding)\b.*\b(need|want|looking\s*for)\b.*\b(help|sources?|articles?)\b',
    ],
    
    "database_recommendation": [
        # Asking which databases to use for research
        r'\b(which|what)\s*(databases?|resources?)\b.*\b(should|can|do)\s*(i\s*)?(use|search|look)\b.*\b(for|to\s*find)\b',
        r'\b(best|good|recommended)\s*(databases?|resources?)\b.*\b(for|to\s*find)\b.*\b(articles?|research|sources?)\b',
        r'\b(databases?)\b.*\b(for|about)\b.*\b(research|topic|subject)\b',
    ],
    
    "search_strategy": [
        # Asking how to search or construct searches
        r'\b(how|what)\s*(do\s*i|can\s*i|to)\s*(search|find|look)\b.*\b(for|about)\b.*\b(articles?|sources?|research)\b',
        r'\b(search\s*strategy|search\s*terms|keywords?)\b.*\b(for|about)\b',
        r'\b(construct|build|create)\b.*\b(search|query)\b',
    ],
    
    "topic_specific_research": [
        # Very specific research topics that need librarian expertise
        r'\b(effects?|impacts?|influence|relationship|correlation)\b.*\b(of|between)\b.*\b(on|and)\b',
        r'\b(articles?|research|sources?|papers?)\b.*\b(about|on|regarding)\b.*\b(effects?|impacts?|influence|causes?|factors?)\b',
        # Multiple complex concepts in one query
        r'\b(and|or)\b.*\b(and|or)\b.*\b(articles?|research|sources?)\b',
    ],
}

# ============================================================================
# DETECTION FUNCTION
# ============================================================================

def detect_research_question(user_message: str) -> Dict[str, Any]:
    """
    Detect if the user is asking a research question that requires librarian help.
    
    Args:
        user_message: The user's message
        
    Returns:
        Dict with:
        - is_research_question: True if this is a research question
        - pattern_type: The type of research question detected
        - confidence: "high" or "medium"
        - should_handoff: True if should hand off to librarian
    """
    user_msg_lower = user_message.lower()
    
    # Check each pattern category
    for pattern_type, patterns in RESEARCH_QUESTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, user_msg_lower, re.IGNORECASE):
                # High confidence patterns
                high_confidence_types = [
                    "article_search_with_specifics",
                    "research_topic_help",
                ]
                
                confidence = "high" if pattern_type in high_confidence_types else "medium"
                
                return {
                    "is_research_question": True,
                    "pattern_type": pattern_type,
                    "confidence": confidence,
                    "should_handoff": True,
                    "reason": f"Detected {pattern_type.replace('_', ' ')} - requires librarian expertise"
                }
    
    return {
        "is_research_question": False,
        "should_handoff": False
    }


def get_research_handoff_response(pattern_type: str = None) -> str:
    """
    Get appropriate handoff response for research questions.
    
    Args:
        pattern_type: The type of research question detected
        
    Returns:
        str: Handoff message directing to librarian
    """
    base_response = """I can see you're working on a research project that requires finding specific sources. This is exactly the kind of detailed research help our librarians specialize in!

**I recommend:**

• **Chat with a research librarian** who can help you:
  - Find the right databases for your topic
  - Develop effective search strategies  
  - Locate articles that meet your specific requirements
  - Navigate complex research topics

• **Contact your subject librarian** who specializes in your area

**Get help now:**
- Chat: https://www.lib.miamioh.edu/research/research-support/ask/
- Call: (513) 529-4141
- Submit a ticket for detailed research help

Our librarians are experts at helping with research projects and can provide personalized guidance for your specific needs."""

    return base_response


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_simple_guide_request(user_message: str) -> bool:
    """
    Check if user is simply asking for a research guide (LibGuide), not research help.
    
    These should go to LibGuide agent, not handoff:
    - "LibGuide for nursing"
    - "Research guide for biology"
    - "Guide for ENG 111"
    """
    simple_guide_patterns = [
        r'^(libguide|research\s*guide|guide)\s*(for|about)\s*[a-z0-9\s]+$',
        r'^(find|show|get)\s*(me\s*)?(the\s*)?(libguide|research\s*guide|guide)\s*(for|about)\s*[a-z0-9\s]+$',
        r'^[a-z0-9\s]+\s*(libguide|research\s*guide|guide)$',
    ]
    
    user_msg_lower = user_message.lower().strip()
    
    for pattern in simple_guide_patterns:
        if re.search(pattern, user_msg_lower, re.IGNORECASE):
            return True
    
    return False
