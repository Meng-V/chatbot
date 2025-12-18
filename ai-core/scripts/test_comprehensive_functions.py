"""
Comprehensive Function Testing

Tests all bot capabilities thoroughly:
1. LibGuide-related queries (by subject, by librarian, by course)
2. All core functions (hours, booking, policies, etc.)
3. Out-of-scope handling and proper handoff
4. Edge cases and error handling
"""

import asyncio
import httpx
import json
from datetime import datetime

API_URL = "http://localhost:8000/ask"

# LibGuide-Related Queries
LIBGUIDE_TESTS = [
    # By Subject
    "Who is the biology librarian?",
    "I need help with psychology research",
    "English department librarian",
    "Chemistry subject guide",
    "History research guide",
    
    # By Course Code
    "Who is the librarian for ENG 111?",
    "I need help with BIO 201",
    "PSY 201 research guide",
    "CHM 141 librarian",
    "MTH 151 help",
    
    # By Major
    "I'm a biology major, who is my librarian?",
    "Business major research help",
    "Nursing major librarian",
    
    # Regional Campus
    "Who is the biology librarian at Hamilton?",
    "I'm at Middletown campus, who can help with English?",
    "Rentschler Library subject librarian for psychology",
    
    # Fuzzy Matching
    "Who is the biologee librarian?",
    "I need help with psycology",
    "Chemestry research guide"
]

# Core Functions
CORE_FUNCTION_TESTS = [
    # Hours
    "What are the library hours?",
    "When does King Library close?",
    "Art and Architecture hours",
    "Makerspace hours",
    "Special Collections hours",
    
    # Contact Info
    "Library address",
    "Library phone number",
    "How do I contact the library?",
    
    # Live Chat
    "What are the hours for live chat?",
    "Is live chat available now?",
    "When can I chat with a librarian?",
    
    # Room Reservations
    "How do I reserve a study room?",
    "Can you book a room for me?",
    "Study room availability",
    
    # Policies
    "How long can I check out a book?",
    "Can I renew a book?",
    "What are the late fees?",
    "Can I eat in the library?",
    "How do I print?",
    
    # Equipment
    "Can I check out a camera?",
    "Does the library have laptops?",
    "How do I get Adobe?",
    
    # Personal Account
    "Check my library account",
    "What are my fines?",
    "When are my books due?"
]

# Out-of-Scope and Handoff Tests
OUT_OF_SCOPE_TESTS = [
    # Should deny and redirect
    "What's the weather today?",
    "How do I register for classes?",
    "Where is the dining hall?",
    "Can you help me with my math homework?",
    "What's the football score?",
    
    # Complex research - should handoff to human
    "I need to find 50 peer-reviewed articles about climate change",
    "Help me design a research methodology for my dissertation",
    "I need primary sources from the 1800s",
    
    # Impossible requests - should deny gracefully
    "Can you write my research paper?",
    "Make me a librarian",
    "Give me all the answers to my exam",
    
    # Ambiguous - should ask for clarification or provide general help
    "Help",
    "I need something",
    "Can you help me?"
]


async def test_query(question: str, category: str):
    """Test a single query and analyze response."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                API_URL,
                json={"message": question},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                final_answer = data.get("final_answer", "")
                agents = data.get("agents_used", [])
                intent = data.get("intent", "")
                
                # Analyze response quality
                analysis = {
                    "has_libguide_url": "libguides.lib.miamioh.edu" in final_answer,
                    "has_email": "@miamioh.edu" in final_answer,
                    "has_phone": "513" in final_answer or "727" in final_answer,
                    "has_account_url": "ohiolink-mu.primo.exlibrisgroup.com" in final_answer,
                    "has_live_chat_info": "Live Chat with Librarians" in final_answer or "available NOW" in final_answer,
                    "has_error": "trouble accessing" in final_answer.lower() or "error" in final_answer.lower(),
                    "is_handoff": "chat with a librarian" in final_answer.lower() or "submit a ticket" in final_answer.lower(),
                    "is_out_of_scope": "outside the scope" in final_answer.lower() or "can only help with library" in final_answer.lower()
                }
                
                return {
                    "category": category,
                    "question": question,
                    "status": "SUCCESS",
                    "response": final_answer[:300],
                    "agents": agents,
                    "intent": intent,
                    "analysis": analysis
                }
            else:
                return {
                    "category": category,
                    "question": question,
                    "status": "HTTP_ERROR",
                    "error": f"HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            "category": category,
            "question": question,
            "status": "EXCEPTION",
            "error": str(e)
        }


async def run_comprehensive_tests():
    """Run all comprehensive tests."""
    print("=" * 80)
    print("COMPREHENSIVE FUNCTION TESTING")
    print("=" * 80)
    print()
    
    all_results = []
    
    # Test LibGuide queries
    print("\n" + "=" * 80)
    print("LIBGUIDE-RELATED QUERIES (19 tests)")
    print("=" * 80)
    for i, question in enumerate(LIBGUIDE_TESTS, 1):
        print(f"\n[{i}/19] {question[:60]}...")
        result = await test_query(question, "LibGuide")
        all_results.append(result)
        if result['status'] == 'SUCCESS':
            analysis = result['analysis']
            print(f"  ✓ Agents: {result['agents']}")
            print(f"  ✓ Has LibGuide URL: {analysis['has_libguide_url']}")
            print(f"  ✓ Has Email: {analysis['has_email']}")
            print(f"  ✓ Has Error: {analysis['has_error']}")
    
    # Test core functions
    print("\n" + "=" * 80)
    print("CORE FUNCTIONS (29 tests)")
    print("=" * 80)
    for i, question in enumerate(CORE_FUNCTION_TESTS, 1):
        print(f"\n[{i}/29] {question[:60]}...")
        result = await test_query(question, "Core")
        all_results.append(result)
        if result['status'] == 'SUCCESS':
            analysis = result['analysis']
            print(f"  ✓ Intent: {result['intent']}")
            if analysis['has_account_url']:
                print(f"  ✓ Has Account URL")
            if analysis['has_live_chat_info']:
                print(f"  ✓ Has Live Chat Info")
    
    # Test out-of-scope
    print("\n" + "=" * 80)
    print("OUT-OF-SCOPE & HANDOFF (15 tests)")
    print("=" * 80)
    for i, question in enumerate(OUT_OF_SCOPE_TESTS, 1):
        print(f"\n[{i}/15] {question[:60]}...")
        result = await test_query(question, "OutOfScope")
        all_results.append(result)
        if result['status'] == 'SUCCESS':
            analysis = result['analysis']
            print(f"  ✓ Is Out-of-Scope: {analysis['is_out_of_scope']}")
            print(f"  ✓ Is Handoff: {analysis['is_handoff']}")
    
    # Generate summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    libguide_results = [r for r in all_results if r['category'] == 'LibGuide']
    core_results = [r for r in all_results if r['category'] == 'Core']
    scope_results = [r for r in all_results if r['category'] == 'OutOfScope']
    
    libguide_success = len([r for r in libguide_results if r['status'] == 'SUCCESS'])
    core_success = len([r for r in core_results if r['status'] == 'SUCCESS'])
    scope_success = len([r for r in scope_results if r['status'] == 'SUCCESS'])
    
    # Quality analysis
    libguide_with_url = len([r for r in libguide_results if r.get('analysis', {}).get('has_libguide_url')])
    libguide_with_email = len([r for r in libguide_results if r.get('analysis', {}).get('has_email')])
    libguide_with_error = len([r for r in libguide_results if r.get('analysis', {}).get('has_error')])
    
    print(f"\nLibGuide Queries: {libguide_success}/19 success")
    print(f"  With LibGuide URL: {libguide_with_url}/19")
    print(f"  With Email Contact: {libguide_with_email}/19")
    print(f"  With Errors: {libguide_with_error}/19")
    
    print(f"\nCore Functions: {core_success}/29 success")
    print(f"\nOut-of-Scope: {scope_success}/15 success")
    
    print(f"\nTotal: {libguide_success + core_success + scope_success}/63 ({(libguide_success + core_success + scope_success)/63*100:.1f}%)")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"comprehensive_test_results_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "summary": {
                "libguide": {"success": libguide_success, "total": 19, "with_url": libguide_with_url, "with_email": libguide_with_email, "with_error": libguide_with_error},
                "core": {"success": core_success, "total": 29},
                "out_of_scope": {"success": scope_success, "total": 15},
                "overall": {"success": libguide_success + core_success + scope_success, "total": 63}
            },
            "results": all_results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
    
    return all_results


if __name__ == "__main__":
    asyncio.run(run_comprehensive_tests())
