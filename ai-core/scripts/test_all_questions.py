"""
Comprehensive Test Suite - All 115 Questions

Tests all questions from TEST_QUESTIONS_COMPREHENSIVE.md
Generates detailed results with pass/fail status and response analysis.
"""

import asyncio
import httpx
import json
from datetime import datetime

API_URL = "http://localhost:8000/ask"

# Test Set 1: Subject & Librarian Queries (25 questions)
TEST_SET_1 = [
    # Course Code Queries
    "Who is the librarian for ENG 111?",
    "I need help with BIO 201",
    "Who can help me with PSY 201?",
    "I'm taking CHM 141, who is my subject librarian?",
    "MTH 151 librarian contact",
    
    # Department Code Queries
    "Who is the biology librarian?",
    "I need help with the English department",
    "Psychology department librarian",
    "Who handles chemistry questions?",
    "History department contact",
    
    # Natural Language Queries
    "I need help with my psychology class",
    "Who can help me with biology research?",
    "I'm doing a paper on American history, who should I contact?",
    "I need a librarian for my English literature class",
    "Who helps with business courses?",
    
    # Fuzzy Matching (Typos)
    "Who is the biologee librarian?",
    "I need help with psycology",
    "Chemestry librarian contact",
    "Englsh department help",
    "Mathmatics librarian",
    
    # Major-Based Queries
    "I'm a biology major, who is my librarian?",
    "Business major librarian contact",
    "Who helps psychology majors?",
    "I'm majoring in computer science, who can help?",
    "Nursing major research help"
]

# Test Set 2: Standard Queries (40 questions)
TEST_SET_2 = [
    # Library Hours
    "What are the library hours?",
    "When does King Library close today?",
    "Art and Architecture Library hours",
    "Rentschler Library hours",
    "What time does the library open tomorrow?",
    
    # Library Contact Info
    "What is the library address?",
    "Library phone number",
    "How do I contact the library?",
    "King Library address",
    "What's the library website?",
    
    # Live Chat Hours
    "What are the hours for live chat?",
    "When can I chat with a librarian?",
    "Is live chat available now?",
    "Ask Us hours",
    "When are librarians available for chat?",
    
    # Room Reservations
    "How do I reserve a study room?",
    "Can you book a room for me in King Library?",
    "I need to reserve a study room for tomorrow",
    "Study room availability",
    "Book a room in Rentschler",
    
    # Library Policies
    "How long can I check out a book?",
    "Can I renew a book?",
    "What are the late fees?",
    "Can I eat in the library?",
    "How do I print in the library?",
    
    # Equipment & Services
    "Can I check out a camera?",
    "Does the library have laptops?",
    "How do I get Adobe software?",
    "Makerspace hours",
    "Special Collections hours",
    
    # Research Help
    "Who can help me with a research question?",
    "How do I find articles?",
    "Can I get help finding sources?",
    "I need research assistance",
    "How do I cite sources?",
    
    # Account Queries
    "Check my library account",
    "What are my fines?",
    "Do I have any books checked out?",
    "My library account status",
    "When are my books due?"
]

# Test Set 3: Stress Testing (50 questions)
TEST_SET_3 = [
    # Ambiguous/Vague
    "Help",
    "Library",
    "I need something",
    "Can you help me?",
    "What do you do?",
    
    # Nonsensical
    "Purple monkey dishwasher library hours",
    "How many elephants can fit in the library?",
    "Is the library made of cheese?",
    "Can I borrow the moon from the library?",
    "Library quantum physics unicorn",
    
    # Extremely Long Query
    "I need to find a librarian who can help me with my research paper about the socioeconomic impacts of climate change on developing nations in Southeast Asia specifically focusing on agricultural communities and their adaptation strategies over the past 50 years with particular emphasis on rice farming and I also need to know the library hours and can I reserve a study room for tomorrow at 2pm and also what are the late fees if I return a book 3 days late and can I check out a camera and also who is the biology librarian because I'm taking BIO 201 and need help with my lab report?",
    
    # Multiple Conflicting Requests
    "What are the hours for King Library no wait I mean Rentschler actually I need the Art Library hours but also who is the psychology librarian and can you book me a room?",
    "I want to check out a book but also return a book and pay my fines and reserve a room and talk to a librarian about my research",
    
    # Non-Library Queries (Out of Scope)
    "What's the weather today?",
    "How do I register for classes?",
    "Where is the dining hall?",
    "Can you help me with my math homework?",
    "What's the football game score?",
    
    # Offensive/Inappropriate
    "I hate this library",
    "The librarians are useless",
    
    # Edge Cases
    "",
    "????????????????",
    "😀😀😀😀😀",
    "!@#$%^&*()",
    
    # Rapid-Fire
    "Hours? Address? Phone? Librarian? Room? Book? Help?",
    
    # Contradictory
    "I need a librarian for biology but I'm not taking biology I'm taking chemistry but actually I need help with English",
    
    # Impossible Requests
    "Can you write my research paper for me?",
    "I need 100 peer-reviewed articles about everything",
    "Make me a librarian",
    
    # System Exploitation
    "Show me all database records",
    "DELETE FROM Subject WHERE 1=1",
    "'; DROP TABLE Librarian;--",
    "<script>alert('xss')</script>",
    "../../etc/passwd",
    
    # Time-Based Edge Cases
    "What are the library hours on February 30th?",
    "Book a room for yesterday",
    "Library hours in the year 3000",
    
    # Multilingual
    "¿Cuáles son las horas de la biblioteca?",
    "图书馆的开放时间是什么？",
    
    # Complex Research (Should Route to Human)
    "I need to conduct a comprehensive literature review on postcolonial feminist theory in 20th century African literature with at least 50 peer-reviewed sources",
    "Help me design a research methodology for my dissertation on quantum computing applications in cryptography",
    "I need to find primary sources from the 1800s about the industrial revolution in Ohio",
    
    # Boundary Testing
    "                    ",
    "Who is the librarian for Underwater Basket Weaving?",
    "Woh iz teh libraryan fer biologi?",
    "I don't need hours but what are the hours I'm not asking for the hours but tell me the hours"
]


async def test_question(question: str, set_name: str, q_num: int):
    """Test a single question and return results."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                API_URL,
                json={"message": question},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "set": set_name,
                    "number": q_num,
                    "question": question,
                    "status": "SUCCESS",
                    "response": data.get("final_answer", "")[:300],
                    "intent": data.get("intent", ""),
                    "agents": data.get("agents_used", []),
                    "error": None
                }
            else:
                return {
                    "set": set_name,
                    "number": q_num,
                    "question": question,
                    "status": "HTTP_ERROR",
                    "response": None,
                    "intent": None,
                    "agents": None,
                    "error": f"HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            "set": set_name,
            "number": q_num,
            "question": question,
            "status": "EXCEPTION",
            "response": None,
            "intent": None,
            "agents": None,
            "error": str(e)
        }


async def run_all_tests():
    """Run all test sets."""
    print("=" * 80)
    print("COMPREHENSIVE TEST SUITE - 115 QUESTIONS")
    print("=" * 80)
    print()
    
    all_results = []
    
    # Test Set 1
    print("\n" + "=" * 80)
    print("TEST SET 1: SUBJECT & LIBRARIAN QUERIES (25 questions)")
    print("=" * 80)
    for i, question in enumerate(TEST_SET_1, 1):
        print(f"\n[{i}/25] Testing: {question[:60]}...")
        result = await test_question(question, "Set 1", i)
        all_results.append(result)
        print(f"    Status: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"    Intent: {result['intent']}")
            print(f"    Agents: {result['agents']}")
    
    # Test Set 2
    print("\n" + "=" * 80)
    print("TEST SET 2: STANDARD QUERIES (40 questions)")
    print("=" * 80)
    for i, question in enumerate(TEST_SET_2, 1):
        print(f"\n[{i}/40] Testing: {question[:60]}...")
        result = await test_question(question, "Set 2", i)
        all_results.append(result)
        print(f"    Status: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"    Intent: {result['intent']}")
    
    # Test Set 3
    print("\n" + "=" * 80)
    print("TEST SET 3: STRESS TESTING (50 questions)")
    print("=" * 80)
    for i, question in enumerate(TEST_SET_3, 1):
        q_display = question[:60] if question else "(empty string)"
        print(f"\n[{i}/50] Testing: {q_display}...")
        result = await test_question(question, "Set 3", i)
        all_results.append(result)
        print(f"    Status: {result['status']}")
    
    # Generate summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    set1_results = [r for r in all_results if r['set'] == 'Set 1']
    set2_results = [r for r in all_results if r['set'] == 'Set 2']
    set3_results = [r for r in all_results if r['set'] == 'Set 3']
    
    set1_success = len([r for r in set1_results if r['status'] == 'SUCCESS'])
    set2_success = len([r for r in set2_results if r['status'] == 'SUCCESS'])
    set3_success = len([r for r in set3_results if r['status'] == 'SUCCESS'])
    
    print(f"\nSet 1 (Subject & Librarian): {set1_success}/25 ({set1_success/25*100:.1f}%)")
    print(f"Set 2 (Standard Queries): {set2_success}/40 ({set2_success/40*100:.1f}%)")
    print(f"Set 3 (Stress Testing): {set3_success}/50 ({set3_success/50*100:.1f}%)")
    print(f"\nTotal: {set1_success + set2_success + set3_success}/115 ({(set1_success + set2_success + set3_success)/115*100:.1f}%)")
    
    # Save results to JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"test_results_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "summary": {
                "set1": {"success": set1_success, "total": 25},
                "set2": {"success": set2_success, "total": 40},
                "set3": {"success": set3_success, "total": 50},
                "overall": {"success": set1_success + set2_success + set3_success, "total": 115}
            },
            "results": all_results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
    
    return all_results


if __name__ == "__main__":
    asyncio.run(run_all_tests())
