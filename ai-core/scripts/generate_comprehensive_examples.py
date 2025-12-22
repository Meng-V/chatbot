"""
Generate Comprehensive RAG Examples

This script generates extensive, realistic examples for the RAG classifier based on
actual Miami University Libraries services from lib.miamioh.edu
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

# Based on scraped content from:
# - https://www.lib.miamioh.edu/research/
# - https://www.lib.miamioh.edu/use/
# - https://www.lib.miamioh.edu/about/

COMPREHENSIVE_EXAMPLES = {
    "LIBRARY_EQUIPMENT_CHECKOUT": {
        "additions": [
            # Tech Equipment (from /use/technology/tech-checkout/)
            "Can I borrow a GoPro?",
            "Do you have video cameras?",
            "Can I check out a microphone?",
            "Are there HDMI cables available?",
            "Can I borrow a USB-C adapter?",
            "Do you have phone chargers?",
            "Can I get a laptop charger?",
            "Are there audio recorders?",
            "Can I borrow presentation equipment?",
            "Do you have webcams?",
            "Can I check out a tablet?",
            "Are there drawing tablets?",
            "Can I borrow VR equipment?",
            # Software (from /software/)
            "Can I get Adobe Creative Cloud?",
            "Do you have SPSS?",
            "Can I borrow statistical software?",
            "Is Photoshop available?",
            "Can I get video editing software?",
            "Do you have Microsoft Office?",
            "Can I check out design software?",
        ]
    },
    
    "LIBRARY_HOURS_ROOMS": {
        "additions": [
            # Specific locations (from /about/locations/)
            "What time does Wertz Library close?",
            "Art and Architecture Library hours",
            "When is Special Collections open?",
            "Archives hours",
            "Regional library hours",
            "Is King Library open 24 hours?",
            "Library hours during finals week",
            "Are you open during spring break?",
            "What time do you close on Friday?",
            "Weekend hours",
            "Holiday hours",
            # Spaces (from /use/spaces/)
            "How do I reserve a study room?",
            "Are group study rooms available?",
            "Can I book a room for 3 hours?",
            "Study room availability",
            "Where is the MakerSpace?",
            "Faculty reading room location",
            "Graduate reading room",
            "Where can I study quietly?",
            "Silent study areas",
            "Computer lab locations",
            "How many computers are available?",
            "Where is the Howe Writing Center?",
        ]
    },
    
    "SUBJECT_LIBRARIAN_GUIDES": {
        "additions": [
            # More subjects
            "Who is the art librarian?",
            "Music librarian contact",
            "Political science librarian",
            "Sociology librarian",
            "Anthropology librarian",
            "Philosophy librarian",
            "Economics librarian",
            "Education librarian",
            "Kinesiology librarian",
            "Architecture librarian",
            # Research guides (from /research/find/guides/)
            "Research guide for my major",
            "LibGuide for ENG 111",
            "Do you have a guide for BIO 201?",
            "Subject guide for my class",
            "Research resources for nursing",
            "Engineering research guide",
            "Business LibGuide",
            "Chemistry resources",
        ]
    },
    
    "RESEARCH_HELP_HANDOFF": {
        "additions": [
            # From /research/research-support/
            "I need help with my literature review",
            "Can you help me find peer-reviewed articles?",
            "What database should I use for psychology research?",
            "I need scholarly sources about climate change",
            "Help me develop a search strategy",
            "I'm looking for articles on social media effects",
            "Can you find me sources for my thesis?",
            "I need help narrowing my research topic",
            "What keywords should I use?",
            "How do I find academic journals?",
            "I need sources for my capstone project",
            "Research help for my dissertation",
            "I'm writing about artificial intelligence",
            "Find me articles on mental health",
            "I need help with database searching",
        ]
    },
    
    "LIBRARY_POLICIES_SERVICES": {
        "additions": [
            # Borrowing (from /use/borrow/)
            "How do I request interlibrary loan?",
            "What is ILL?",
            "Can I get books from other universities?",
            "OhioLINK request",
            "SearchOhio",
            "How long does ILL take?",
            "Course reserves access",
            "Are textbooks on reserve?",
            "Can I request curbside pickup?",
            "Do you deliver to dorms?",
            "Home delivery service",
            "Department delivery",
            # Technology services (from /use/technology/)
            "How do I print?",
            "Printing costs",
            "Can I scan documents?",
            "Where are the scanners?",
            "3D printing services",
            "How do I use the 3D printer?",
            "3D printing cost",
            "WiFi password",
            "Audio-video production help",
            # Research support (from /research/research-support/)
            "Citation help",
            "How do I cite in APA?",
            "MLA citation format",
            "Copyright information",
            "Academic integrity resources",
            "Plagiarism help",
            "Research workshops",
            # More food/drink
            "Can I bring my Starbucks?",
            "Are drinks with lids allowed?",
            "Can I eat snacks?",
            "Food policy",
            "Where can I eat?",
        ]
    },
    
    "OUT_OF_SCOPE_TECH_SUPPORT": {
        "additions": [
            # More specific tech issues
            "My Canvas won't load",
            "I can't submit my assignment on Canvas",
            "Blackboard isn't working",
            "My email is down",
            "I can't access Outlook",
            "Microsoft Teams issues",
            "Zoom not working",
            "My VPN won't connect",
            "Two-factor authentication problems",
            "I'm locked out of my account",
            "UniqueID password reset",
            "My laptop screen is black",
            "Computer won't boot",
            "Blue screen of death",
            "My mouse isn't working",
            "Keyboard not responding",
            "Printer driver issues",
            "Software won't install",
            "My phone won't connect to WiFi",
            "Eduroam setup help",
        ]
    },
    
    "OUT_OF_SCOPE_ACADEMICS": {
        "additions": [
            # More academic questions
            "How do I declare my major?",
            "Can I change my major?",
            "What's my class schedule?",
            "How do I add/drop a class?",
            "When is the add/drop deadline?",
            "Can you explain this calculus problem?",
            "What is the Krebs cycle?",
            "Help me understand organic chemistry",
            "Can you solve this equation?",
            "What's the answer to my homework?",
            "Can you write my essay?",
            "Proofread my paper",
            "What should I write about?",
            "How do I calculate my GPA?",
            "Transcript request",
            "Dean's list requirements",
            "Academic probation",
            "Grade appeal",
        ]
    },
    
    "OUT_OF_SCOPE_CAMPUS_LIFE": {
        "additions": [
            # More campus locations
            "Where is Shriver Center?",
            "How do I get to Upham Hall?",
            "Where is Bachelor Hall?",
            "Farmer School of Business location",
            "Where is the bookstore?",
            "Campus bookstore hours",
            # More dining
            "Dining hall menu",
            "What's for breakfast?",
            "Where can I get pizza?",
            "Starbucks on campus",
            "Food delivery on campus",
            # More activities
            "Greek life",
            "How do I join a fraternity?",
            "Club sports",
            "Intramural sports",
            "Student organizations",
            "When is homecoming?",
            "Concert tickets",
            "Theater performances",
            # More services
            "Health center hours",
            "Counseling services",
            "Career center",
            "Where is the post office?",
            "Mailroom hours",
            "Laundry facilities",
        ]
    },
    
    "OUT_OF_SCOPE_FINANCIAL": {
        "additions": [
            # More financial questions
            "Bursar office hours",
            "Payment deadline",
            "Can I set up a payment plan?",
            "Refund check",
            "When will I get my refund?",
            "Financial aid disbursement",
            "Student loan information",
            "How do I accept my financial aid?",
            "Scholarship application",
            "Work-study positions",
            "Student employment",
            "How much do I owe?",
            "Billing statement",
            "1098-T form",
        ]
    }
}

def print_comprehensive_examples():
    """Print all comprehensive examples organized by category."""
    print("=" * 80)
    print("COMPREHENSIVE RAG CLASSIFIER EXAMPLES")
    print("Based on Miami University Libraries Services")
    print("=" * 80)
    
    for category, data in COMPREHENSIVE_EXAMPLES.items():
        print(f"\n## {category}")
        print(f"Additional examples: {len(data['additions'])}")
        print("\nExamples:")
        for i, example in enumerate(data['additions'][:10], 1):
            print(f"  {i}. {example}")
        if len(data['additions']) > 10:
            print(f"  ... and {len(data['additions']) - 10} more")
    
    total = sum(len(data['additions']) for data in COMPREHENSIVE_EXAMPLES.values())
    print(f"\n{'=' * 80}")
    print(f"TOTAL NEW EXAMPLES: {total}")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    print_comprehensive_examples()
