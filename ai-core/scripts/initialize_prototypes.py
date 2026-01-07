"""
Initialize Weaviate Prototypes Collection

This script migrates from the old "many samples per category" approach
to the new "8-12 high-quality prototypes per agent" approach.

Key improvements:
1. Equipment checkout prototypes MUST have action verbs
2. Each prototype is high-distinction (not just synonyms)
3. Prototypes emphasize what makes each agent unique
4. No overlap between similar categories

Usage:
    python scripts/initialize_prototypes.py [--clear]
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "ai-core"))

# Load environment variables from .env file
load_dotenv(dotenv_path=project_root / ".env")

from src.router.weaviate_router import WeaviateRouter


# ============================================================================
# PROTOTYPE DEFINITIONS
# ============================================================================
# Each agent gets 8-12 high-quality, distinctive prototypes
# Equipment checkout prototypes MUST include action verbs

PROTOTYPES = [
    # ========================================================================
    # EQUIPMENT CHECKOUT - Action-verb focused
    # ========================================================================
    {
        "agent_id": "equipment_checkout",
        "category": "Equipment Checkout",
        "prototypes": [
            {"text": "Can I borrow a laptop from the library?", "is_action": True, "priority": 3},
            {"text": "How do I check out a Chromebook?", "is_action": True, "priority": 3},
            {"text": "I need to rent a camera for my project", "is_action": True, "priority": 3},
            {"text": "Do you have laptop chargers available for checkout?", "is_action": True, "priority": 2},
            {"text": "Can I get a calculator to borrow?", "is_action": True, "priority": 2},
            {"text": "Where can I check out equipment?", "is_action": True, "priority": 2},
            {"text": "I want to borrow an iPad", "is_action": True, "priority": 3},
            {"text": "Are there headphones I can check out?", "is_action": True, "priority": 2},
            {"text": "Can I reserve a laptop for tomorrow?", "is_action": True, "priority": 3},
            {"text": "How do I get Adobe Creative Cloud?", "is_action": True, "priority": 2},
            {"text": "Do you loan out tripods?", "is_action": True, "priority": 2},
            {"text": "Can I checkout a MacBook?", "is_action": True, "priority": 3},
        ]
    },
    
    # ========================================================================
    # LIBRARY HOURS
    # ========================================================================
    {
        "agent_id": "libcal_hours",
        "category": "Library Hours",
        "prototypes": [
            {"text": "What time does King Library close today?", "is_action": False, "priority": 3},
            {"text": "When does the Art Library open?", "is_action": False, "priority": 3},
            {"text": "What are the hours for King Library today?", "is_action": False, "priority": 3},
            {"text": "Library hours for tomorrow", "is_action": False, "priority": 3},
            {"text": "Is the library open on Sunday?", "is_action": False, "priority": 2},
            {"text": "What time does King Library open today?", "is_action": False, "priority": 3},
            {"text": "When does King Library close tonight?", "is_action": False, "priority": 3},
            {"text": "What are the Makerspace hours?", "is_action": False, "priority": 2},
            {"text": "When does Rentschler Library close?", "is_action": False, "priority": 2},
            {"text": "Library schedule for finals week", "is_action": False, "priority": 2},
            {"text": "Is King Library open on Martin Luther King Jr. Day?", "is_action": False, "priority": 2},
            {"text": "What are the hours for live chat with librarians?", "is_action": False, "priority": 3},
            {"text": "When is librarian chat available?", "is_action": False, "priority": 3},
            {"text": "Is live chat open right now?", "is_action": False, "priority": 3},
            {"text": "What time does online chat support close?", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # STUDY ROOM RESERVATIONS
    # ========================================================================
    {
        "agent_id": "libcal_spaces",
        "category": "Study Room Reservations",
        "prototypes": [
            {"text": "How do I book a study room?", "is_action": True, "priority": 3},
            {"text": "Reserve a group study space", "is_action": True, "priority": 3},
            {"text": "Can I reserve a room for a meeting?", "is_action": True, "priority": 3},
            {"text": "Where do I reserve group study rooms?", "is_action": True, "priority": 3},
            {"text": "Can I book a study room online?", "is_action": True, "priority": 3},
            {"text": "How do I reserve a study room in Farmer?", "is_action": True, "priority": 2},
            {"text": "Book a private study room", "is_action": True, "priority": 2},
            {"text": "Study room reservation process", "is_action": True, "priority": 2},
        ]
    },
    
    # ========================================================================
    # SUBJECT LIBRARIAN
    # ========================================================================
    {
        "agent_id": "subject_librarian",
        "category": "Subject Librarian",
        "prototypes": [
            {"text": "Who is the biology librarian?", "is_action": False, "priority": 3},
            {"text": "Find the librarian for psychology", "is_action": False, "priority": 3},
            {"text": "Subject librarian for engineering", "is_action": False, "priority": 3},
            {"text": "I need help with chemistry research", "is_action": False, "priority": 2},
            {"text": "Who can help me with business resources?", "is_action": False, "priority": 2},
            {"text": "Librarian for English department", "is_action": False, "priority": 2},
            {"text": "Contact info for the history librarian", "is_action": False, "priority": 2},
            {"text": "Who handles nursing research?", "is_action": False, "priority": 2},
            {"text": "List of all subject librarians", "is_action": False, "priority": 2},
            {"text": "Research guide for my major", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # LIBGUIDE - Course & Research Guides
    # ========================================================================
    {
        "agent_id": "libguide",
        "category": "Course & Research Guides",
        "prototypes": [
            {"text": "LibGuide for ENG 111", "is_action": False, "priority": 3},
            {"text": "What databases should I use for PSY 201?", "is_action": False, "priority": 3},
            {"text": "Research guide for my class", "is_action": False, "priority": 2},
            {"text": "Course resources for BIO 115", "is_action": False, "priority": 2},
            {"text": "Where can I find sources for my paper?", "is_action": False, "priority": 2},
            {"text": "Best databases for history research", "is_action": False, "priority": 2},
            {"text": "Guide for writing a literature review", "is_action": False, "priority": 2},
            {"text": "How do I cite sources in APA?", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # GOOGLE SITE - Policies, Services & Contact Info
    # ========================================================================
    {
        "agent_id": "google_site",
        "category": "Library Policies, Services & Contact Info",
        "prototypes": [
            {"text": "How do I renew a book?", "is_action": False, "priority": 3},
            {"text": "What are the library's printing policies?", "is_action": False, "priority": 3},
            {"text": "What is the address of King Library?", "is_action": False, "priority": 3},
            {"text": "What is the phone number for King Library?", "is_action": False, "priority": 3},
            {"text": "How do I contact King Library?", "is_action": False, "priority": 3},
            {"text": "Where is King Library located?", "is_action": False, "priority": 3},
            {"text": "What is the address of the Art and Architecture Library?", "is_action": False, "priority": 3},
            {"text": "Where is the Wertz Art and Architecture Library?", "is_action": False, "priority": 3},
            {"text": "What is the phone number for the Art and Architecture Library?", "is_action": False, "priority": 2},
            {"text": "Where is the Makerspace located?", "is_action": False, "priority": 2},
            {"text": "What is the address of the Makerspace?", "is_action": False, "priority": 2},
            {"text": "Can I bring food into the library?", "is_action": False, "priority": 2},
            {"text": "How much does it cost to print?", "is_action": False, "priority": 2},
            {"text": "What services does the library offer?", "is_action": False, "priority": 2},
            {"text": "Where is the quiet study area?", "is_action": False, "priority": 2},
            {"text": "Library website URL", "is_action": False, "priority": 2},
            {"text": "How do I access the library remotely?", "is_action": False, "priority": 2},
            {"text": "What is the late fee policy?", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # LIBCHAT - Human Help
    # ========================================================================
    {
        "agent_id": "libchat_handoff",
        "category": "Talk to Librarian",
        "prototypes": [
            {"text": "I want to talk to a librarian", "is_action": True, "priority": 3},
            {"text": "Can I speak with someone?", "is_action": True, "priority": 3},
            {"text": "Connect me to a human", "is_action": True, "priority": 3},
            {"text": "I need help from a real person", "is_action": True, "priority": 2},
            {"text": "Talk to library staff", "is_action": True, "priority": 2},
            {"text": "Can someone help me?", "is_action": True, "priority": 2},
            {"text": "I have a complex question", "is_action": False, "priority": 2},
            {"text": "This bot isn't helping", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # OUT OF SCOPE - Tech Support
    # ========================================================================
    {
        "agent_id": "out_of_scope",
        "category": "Out of Scope - Tech Support",
        "prototypes": [
            {"text": "My computer won't turn on", "is_action": False, "priority": 3},
            {"text": "Canvas isn't working", "is_action": False, "priority": 3},
            {"text": "I can't log into my email", "is_action": False, "priority": 3},
            {"text": "WiFi is down in my dorm", "is_action": False, "priority": 2},
            {"text": "My laptop is broken", "is_action": False, "priority": 2},
            {"text": "Password reset for my account", "is_action": False, "priority": 2},
            {"text": "VPN not connecting", "is_action": False, "priority": 2},
        ]
    },
    
    # ========================================================================
    # OUT OF SCOPE - Homework
    # ========================================================================
    {
        "agent_id": "out_of_scope",
        "category": "Out of Scope - Homework",
        "prototypes": [
            {"text": "What's the answer to question 5?", "is_action": False, "priority": 3},
            {"text": "Help me solve this math problem", "is_action": False, "priority": 3},
            {"text": "Can you do my homework?", "is_action": False, "priority": 3},
            {"text": "I need help with my assignment", "is_action": False, "priority": 2},
        ]
    },
]


async def initialize_prototypes(clear_existing: bool = False):
    """
    Initialize the Weaviate prototypes collection.
    
    Args:
        clear_existing: If True, clear existing prototypes first
    """
    print("🚀 Initializing Weaviate Prototypes Collection")
    print("=" * 60)
    
    router = WeaviateRouter()
    
    if clear_existing:
        print("🗑️  Clearing existing prototypes...")
        await router.clear_collection()
        print("✅ Cleared")
    
    print("📦 Creating collection...")
    await router.ensure_collection()
    print("✅ Collection ready")
    
    print("\n📝 Adding prototypes...")
    
    total_prototypes = 0
    for agent_data in PROTOTYPES:
        agent_id = agent_data["agent_id"]
        category = agent_data["category"]
        prototypes = agent_data["prototypes"]
        
        print(f"\n   {agent_id} ({category}): {len(prototypes)} prototypes")
        
        for proto in prototypes:
            await router.add_prototype(
                agent_id=agent_id,
                prototype_text=proto["text"],
                category=category,
                is_action_based=proto["is_action"],
                priority=proto["priority"]
            )
            total_prototypes += 1
            print(f"      ✓ {proto['text'][:60]}...")
    
    print("\n" + "=" * 60)
    print(f"✅ Successfully initialized {total_prototypes} prototypes")
    print(f"   across {len(PROTOTYPES)} agent categories")
    print("\n💡 Key improvements:")
    print("   - Equipment checkout prototypes have action verbs")
    print("   - 8-12 high-quality prototypes per agent")
    print("   - High distinction between categories")
    print("   - No sample overlap")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Initialize Weaviate prototypes collection"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing prototypes before initializing"
    )
    
    args = parser.parse_args()
    
    try:
        await initialize_prototypes(clear_existing=args.clear)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
