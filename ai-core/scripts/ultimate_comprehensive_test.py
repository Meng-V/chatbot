"""
ULTIMATE COMPREHENSIVE TEST SUITE
Tests ALL bot functions with real bookings, stress testing, and out-of-scope handling

Test Categories:
1. Library Hours (all campuses, all libraries)
2. Study Room Reservations (REAL bookings with Meng Qu)
3. Subject Librarian Queries (all major subjects)
4. LibGuide Searches (courses and subjects)
5. Policy & Service Queries
6. Personal Account Queries
7. Out-of-Scope Queries (must deny/handoff)
8. Stress Testing (edge cases, injections, malformed)
9. Regional Campus Support
10. Invalid Input Handling

Run: python scripts/ultimate_comprehensive_test.py
"""

import asyncio
import httpx
import json
from datetime import datetime, timedelta
from pathlib import Path

API_URL = "http://localhost:8000/ask"
OUTPUT_DIR = Path(__file__).parent.parent / "test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# Test user for room reservations
TEST_USER = {
    "first_name": "Meng",
    "last_name": "Qu",
    "email": "qum@miamioh.edu"
}

# Get tomorrow's date for bookings
tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
tomorrow_display = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")

# Comprehensive test questions
TEST_QUESTIONS = {
    "1_LIBRARY_HOURS": [
        "What time does King Library close today?",
        "When does the Art Library open tomorrow?",
        "What are the hours for Rentschler Library?",
        "Gardner-Harvey Library hours this week",
        "Is the library open on Sunday?",
        "What time does the makerspace close?",
        "Special Collections hours",
        "Hamilton campus library hours",
        "Middletown library schedule",
        "Are libraries open during finals week?",
    ],
    
    "2_ROOM_RESERVATIONS": [
        # Valid libraries
        f"Book a study room at King Library for tomorrow 2pm-4pm for 4 people. Name: Meng Qu, Email: qum@miamioh.edu",
        f"I need to reserve a room at Art Library on {tomorrow_display} from 10am to 12pm for 2 people. Meng Qu, qum@miamioh.edu",
        "Check room availability at King Library tomorrow 3pm-5pm for 3 people",
        "Are there any study rooms available at Rentschler Library tomorrow afternoon?",
        
        # Invalid libraries (should reject)
        "Book a study room at Farmer Library tomorrow",
        "Reserve a room at Science Library",
        "I want to book the Law Library study room",
        
        # Missing information (should ask for details)
        "I need to book a study room",
        "Reserve a room for tomorrow",
        "Book King Library room",
    ],
    
    "3_SUBJECT_LIBRARIANS": [
        "Who is the biology librarian?",
        "I need help with my English paper",
        "Psychology department librarian contact",
        "Who can help me with chemistry research?",
        "Business librarian email",
        "History subject librarian",
        "I'm taking ENG 111, who is my librarian?",
        "PSY 201 librarian contact",
        "Who helps with BIO courses?",
        "Music librarian at Miami",
        "Art history research help",
        "Political science librarian",
        "Who is the librarian at Hamilton campus?",
        "Middletown campus librarian contact",
        "I'm a nursing major, who is my librarian?",
    ],
    
    "4_LIBGUIDE_SEARCHES": [
        "Research guide for biology",
        "Find guide for ENG 111",
        "Psychology research resources",
        "Business LibGuide",
        "Chemistry research guide",
        "History primary sources guide",
        "Where can I find nursing resources?",
        "Political science databases",
        "Art history research guide",
        "Music research resources",
    ],
    
    "5_POLICY_SERVICE": [
        "How do I renew a book?",
        "What are the late fees for overdue books?",
        "Can I eat in the library?",
        "How do I print in the library?",
        "What is the library's guest policy?",
        "How do I get a library card?",
        "Can I check out equipment?",
        "What cameras are available to borrow?",
        "Interlibrary loan policy",
        "How long can I keep a book?",
        "Can I reserve a laptop?",
        "What is the quiet study policy?",
    ],
    
    "6_PERSONAL_ACCOUNT": [
        "Check my library account",
        "How do I access my account?",
        "View my checked out books",
        "My library fines",
        "Renew my books online",
        "Check my holds",
    ],
    
    "7_OUT_OF_SCOPE": [
        # Weather
        "What's the weather today?",
        "Will it rain tomorrow?",
        
        # Course registration
        "How do I register for classes?",
        "When is course registration?",
        "Can you help me add a class?",
        
        # Dining
        "What's for lunch at the dining hall?",
        "Where can I eat on campus?",
        "Dining hall hours",
        
        # Sports
        "When is the football game?",
        "Basketball schedule",
        
        # Homework help
        "Can you help me with my math homework?",
        "What's the answer to question 5?",
        "Write my essay for me",
        
        # General campus
        "Where is the student center?",
        "How do I get to Armstrong?",
        "Campus map",
        
        # Technology
        "How do I connect to WiFi?",
        "My laptop is broken",
        "Canvas login issues",
        
        # Financial
        "How do I pay tuition?",
        "Financial aid office hours",
        "Scholarship information",
    ],
    
    "8_STRESS_TESTING": [
        # Very long queries
        "I need to find a book about psychology and also I want to know the library hours and can you help me with my research paper and I also need to book a study room for tomorrow and I'm not sure what time but probably in the afternoon maybe around 2 or 3 pm and I need it for about 2 hours and there will be 4 people in my group and my name is Meng Qu and my email is qum@miamioh.edu and I'm a psychology major and I need help finding sources for my paper on cognitive development",
        
        # SQL injection attempts
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "<script>alert('xss')</script>",
        
        # Special characters
        "What are the hours for King Library?!@#$%^&*()",
        "Book room @#$%",
        "Librarian contact: <test@test.com>",
        
        # Empty/whitespace
        "   ",
        "",
        "\n\n\n",
        
        # Mixed languages
        "图书馆几点关门？",
        "¿Cuándo cierra la biblioteca?",
        
        # Nonsense
        "asdfghjkl qwertyuiop",
        "blah blah blah",
        "test test test 123",
        
        # Contradictory
        "Book a room for yesterday",
        "What time does the library close before it opens?",
        
        # Extremely specific
        "I need a study room at King Library on December 25th, 2025 at 3:47 AM for exactly 73 minutes for 0.5 people",
        
        # Multiple questions
        "What are the hours? Who is the librarian? Can I book a room? How do I renew?",
    ],
    
    "9_REGIONAL_CAMPUS": [
        "I'm at Hamilton campus, what are the library hours?",
        "Who is the librarian at Rentschler Library?",
        "Book a room at Hamilton",
        "Middletown campus library contact",
        "Gardner-Harvey Library hours",
        "I'm at Middletown, who can help me with research?",
    ],
    
    "10_EDGE_CASES": [
        # Ambiguous
        "hours",
        "librarian",
        "book",
        "help",
        
        # Typos
        "libary hours",
        "libraian contact",
        "resereve room",
        "tomorow",
        
        # Abbreviations
        "KL hours",
        "Art Lib",
        "subj lib",
        
        # Case variations
        "WHAT ARE THE LIBRARY HOURS",
        "who is the biology librarian",
        "BoOk A rOoM",
    ],
}


async def test_query(question: str, category: str, index: int) -> dict:
    """Test a single query and return results."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                API_URL,
                json={"message": question},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                final_answer = data.get("final_answer", "")
                agents = data.get("agents_used", [])
                
                # Analyze response
                has_email = "@miamioh.edu" in final_answer
                has_url = "lib.miamioh.edu" in final_answer or "libguides" in final_answer
                has_error = "trouble accessing" in final_answer.lower() or "error" in final_answer.lower()
                is_out_of_scope = "outside the scope" in final_answer.lower() or "can only help with library" in final_answer.lower() or "can't help" in final_answer.lower()
                has_handoff = "chat with a librarian" in final_answer.lower() or "ask a librarian" in final_answer.lower()
                has_confirmation = "confirmation" in final_answer.lower() or "booking" in final_answer.lower()
                asks_for_info = "please provide" in final_answer.lower() or "need" in final_answer.lower() and "information" in final_answer.lower()
                rejects_invalid = "not a valid library" in final_answer.lower() or "doesn't have" in final_answer.lower()
                
                return {
                    "category": category,
                    "index": index,
                    "question": question,
                    "status": "SUCCESS",
                    "agents": agents,
                    "response": final_answer,
                    "analysis": {
                        "has_email": has_email,
                        "has_url": has_url,
                        "has_error": has_error,
                        "is_out_of_scope": is_out_of_scope,
                        "has_handoff": has_handoff,
                        "has_confirmation": has_confirmation,
                        "asks_for_info": asks_for_info,
                        "rejects_invalid": rejects_invalid,
                        "response_length": len(final_answer),
                    }
                }
            else:
                return {
                    "category": category,
                    "index": index,
                    "question": question,
                    "status": "HTTP_ERROR",
                    "error": f"HTTP {response.status_code}",
                    "response": response.text[:200]
                }
    except asyncio.TimeoutError:
        return {
            "category": category,
            "index": index,
            "question": question,
            "status": "TIMEOUT",
            "error": "Request timed out after 60 seconds"
        }
    except Exception as e:
        return {
            "category": category,
            "index": index,
            "question": question,
            "status": "EXCEPTION",
            "error": str(e)
        }


async def run_all_tests():
    """Run all comprehensive tests."""
    print("\n" + "=" * 100)
    print("ULTIMATE COMPREHENSIVE TEST SUITE - FINAL PRE-LAUNCH VALIDATION")
    print("=" * 100)
    print(f"\nTest User: {TEST_USER['first_name']} {TEST_USER['last_name']} ({TEST_USER['email']})")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tomorrow's Date for Bookings: {tomorrow_display}")
    print()
    
    all_results = []
    total_questions = sum(len(questions) for questions in TEST_QUESTIONS.values())
    current = 0
    
    for category, questions in TEST_QUESTIONS.items():
        print(f"\n{'='*100}")
        print(f"CATEGORY: {category} ({len(questions)} questions)")
        print("=" * 100)
        
        for i, question in enumerate(questions, 1):
            current += 1
            print(f"\n[{current}/{total_questions}] Testing: {question[:80]}...")
            
            result = await test_query(question, category, i)
            all_results.append(result)
            
            if result['status'] == 'SUCCESS':
                analysis = result['analysis']
                print(f"  ✅ Status: {result['status']}")
                print(f"  📊 Agents: {result['agents']}")
                print(f"  📝 Response: {result['response'][:150]}...")
                
                # Category-specific validation
                if category == "2_ROOM_RESERVATIONS":
                    if "Farmer" in question or "Science" in question or "Law" in question:
                        print(f"  🚫 Invalid Library: {'✅' if analysis['rejects_invalid'] else '❌ SHOULD REJECT'}")
                    elif "Book" in question and "tomorrow" in question and "Meng" in question:
                        print(f"  📅 Booking: {'✅' if analysis['has_confirmation'] or analysis['asks_for_info'] else '❌ NO CONFIRMATION'}")
                
                elif category == "3_SUBJECT_LIBRARIANS":
                    print(f"  📧 Has Email: {'✅' if analysis['has_email'] else '❌'}")
                    print(f"  🔗 Has URL: {'✅' if analysis['has_url'] else '➖'}")
                
                elif category == "7_OUT_OF_SCOPE":
                    print(f"  🚫 Out-of-Scope: {'✅' if analysis['is_out_of_scope'] else '❌ SHOULD DENY'}")
                    print(f"  👋 Handoff: {'✅' if analysis['has_handoff'] else '➖'}")
                
                elif category == "8_STRESS_TESTING":
                    print(f"  🛡️ No Error: {'✅' if not analysis['has_error'] else '❌ ERROR DETECTED'}")
                    print(f"  📏 Response Length: {analysis['response_length']} chars")
            else:
                print(f"  ❌ Status: {result['status']}")
                print(f"  ⚠️ Error: {result.get('error', 'Unknown')}")
            
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.5)
    
    return all_results


async def generate_report(results: list):
    """Generate comprehensive final report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save raw results
    json_file = OUTPUT_DIR / f"ultimate_test_results_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate markdown report
    report_file = OUTPUT_DIR / f"ULTIMATE_TEST_REPORT_{timestamp}.md"
    
    with open(report_file, 'w') as f:
        f.write("# ULTIMATE COMPREHENSIVE TEST REPORT\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Questions**: {len(results)}\n")
        f.write(f"**Test User**: {TEST_USER['first_name']} {TEST_USER['last_name']} ({TEST_USER['email']})\n\n")
        
        # Overall statistics
        f.write("## 📊 Overall Statistics\n\n")
        total = len(results)
        success = len([r for r in results if r['status'] == 'SUCCESS'])
        errors = len([r for r in results if r['status'] != 'SUCCESS'])
        
        f.write(f"| Metric | Value | Percentage |\n")
        f.write(f"|--------|-------|------------|\n")
        f.write(f"| Total Questions | {total} | 100% |\n")
        f.write(f"| Successful | {success} | {success/total*100:.1f}% |\n")
        f.write(f"| Errors/Timeouts | {errors} | {errors/total*100:.1f}% |\n\n")
        
        # Category breakdown
        f.write("## 📋 Category Breakdown\n\n")
        
        for category in TEST_QUESTIONS.keys():
            cat_results = [r for r in results if r['category'] == category]
            cat_success = [r for r in cat_results if r['status'] == 'SUCCESS']
            
            f.write(f"### {category}\n\n")
            f.write(f"**Questions**: {len(cat_results)} | **Success**: {len(cat_success)}/{len(cat_results)} ({len(cat_success)/len(cat_results)*100:.1f}%)\n\n")
            
            # Category-specific analysis
            if category == "2_ROOM_RESERVATIONS":
                invalid_rejected = len([r for r in cat_success if r['analysis'].get('rejects_invalid')])
                bookings = len([r for r in cat_success if r['analysis'].get('has_confirmation')])
                asks_info = len([r for r in cat_success if r['analysis'].get('asks_for_info')])
                f.write(f"- Invalid libraries rejected: {invalid_rejected}\n")
                f.write(f"- Booking confirmations: {bookings}\n")
                f.write(f"- Asks for missing info: {asks_info}\n\n")
            
            elif category == "3_SUBJECT_LIBRARIANS":
                with_email = len([r for r in cat_success if r['analysis'].get('has_email')])
                with_url = len([r for r in cat_success if r['analysis'].get('has_url')])
                f.write(f"- Responses with email: {with_email}/{len(cat_success)}\n")
                f.write(f"- Responses with URL: {with_url}/{len(cat_success)}\n\n")
            
            elif category == "7_OUT_OF_SCOPE":
                denied = len([r for r in cat_success if r['analysis'].get('is_out_of_scope')])
                handoff = len([r for r in cat_success if r['analysis'].get('has_handoff')])
                f.write(f"- Properly denied: {denied}/{len(cat_success)} ({denied/len(cat_success)*100:.1f}%)\n")
                f.write(f"- Offered handoff: {handoff}/{len(cat_success)}\n\n")
            
            elif category == "8_STRESS_TESTING":
                no_errors = len([r for r in cat_success if not r['analysis'].get('has_error')])
                f.write(f"- Handled without errors: {no_errors}/{len(cat_success)} ({no_errors/len(cat_success)*100:.1f}%)\n\n")
        
        # Detailed results
        f.write("## 📝 Detailed Results\n\n")
        
        for category in TEST_QUESTIONS.keys():
            f.write(f"### {category}\n\n")
            cat_results = [r for r in results if r['category'] == category]
            
            for result in cat_results:
                status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
                f.write(f"#### {status_icon} Q{result['index']}: {result['question']}\n\n")
                
                if result['status'] == 'SUCCESS':
                    f.write(f"**Agents**: {', '.join(result['agents']) if result['agents'] else 'None'}\n\n")
                    f.write(f"**Response**:\n```\n{result['response'][:500]}\n```\n\n")
                    
                    # Analysis flags
                    analysis = result['analysis']
                    flags = []
                    if analysis.get('has_email'): flags.append("📧 Email")
                    if analysis.get('has_url'): flags.append("🔗 URL")
                    if analysis.get('has_error'): flags.append("⚠️ Error")
                    if analysis.get('is_out_of_scope'): flags.append("🚫 Out-of-Scope")
                    if analysis.get('has_handoff'): flags.append("👋 Handoff")
                    if analysis.get('has_confirmation'): flags.append("✅ Confirmation")
                    if analysis.get('asks_for_info'): flags.append("❓ Asks Info")
                    if analysis.get('rejects_invalid'): flags.append("🚫 Rejects Invalid")
                    
                    if flags:
                        f.write(f"**Flags**: {' | '.join(flags)}\n\n")
                else:
                    f.write(f"**Error**: {result.get('error', 'Unknown')}\n\n")
        
        # Final assessment
        f.write("## 🎯 Final Assessment\n\n")
        
        # Calculate quality scores
        subject_lib_results = [r for r in results if r['category'] == '3_SUBJECT_LIBRARIANS' and r['status'] == 'SUCCESS']
        subject_lib_quality = len([r for r in subject_lib_results if r['analysis'].get('has_email')]) / len(subject_lib_results) * 100 if subject_lib_results else 0
        
        out_of_scope_results = [r for r in results if r['category'] == '7_OUT_OF_SCOPE' and r['status'] == 'SUCCESS']
        out_of_scope_quality = len([r for r in out_of_scope_results if r['analysis'].get('is_out_of_scope')]) / len(out_of_scope_results) * 100 if out_of_scope_results else 0
        
        stress_results = [r for r in results if r['category'] == '8_STRESS_TESTING' and r['status'] == 'SUCCESS']
        stress_quality = len([r for r in stress_results if not r['analysis'].get('has_error')]) / len(stress_results) * 100 if stress_results else 0
        
        f.write(f"| Category | Quality Score |\n")
        f.write(f"|----------|---------------|\n")
        f.write(f"| Overall Success Rate | {success/total*100:.1f}% |\n")
        f.write(f"| Subject Librarian Quality | {subject_lib_quality:.1f}% |\n")
        f.write(f"| Out-of-Scope Handling | {out_of_scope_quality:.1f}% |\n")
        f.write(f"| Stress Test Resilience | {stress_quality:.1f}% |\n\n")
        
        # Production readiness
        f.write("## 🚀 Production Readiness\n\n")
        
        if success/total >= 0.95 and subject_lib_quality >= 80 and out_of_scope_quality >= 80 and stress_quality >= 90:
            f.write("### ✅ READY FOR PRODUCTION\n\n")
            f.write("All quality thresholds met:\n")
            f.write("- ✅ Overall success rate ≥ 95%\n")
            f.write("- ✅ Subject librarian quality ≥ 80%\n")
            f.write("- ✅ Out-of-scope handling ≥ 80%\n")
            f.write("- ✅ Stress test resilience ≥ 90%\n\n")
        else:
            f.write("### ⚠️ NEEDS IMPROVEMENT\n\n")
            f.write("Quality thresholds not met:\n")
            if success/total < 0.95:
                f.write(f"- ❌ Overall success rate: {success/total*100:.1f}% (need ≥ 95%)\n")
            if subject_lib_quality < 80:
                f.write(f"- ❌ Subject librarian quality: {subject_lib_quality:.1f}% (need ≥ 80%)\n")
            if out_of_scope_quality < 80:
                f.write(f"- ❌ Out-of-scope handling: {out_of_scope_quality:.1f}% (need ≥ 80%)\n")
            if stress_quality < 90:
                f.write(f"- ❌ Stress test resilience: {stress_quality:.1f}% (need ≥ 90%)\n")
            f.write("\n")
        
        # Recommendations
        f.write("## 💡 Recommendations\n\n")
        
        # Analyze failures
        failed_categories = {}
        for result in results:
            if result['status'] != 'SUCCESS' or (result['status'] == 'SUCCESS' and result['analysis'].get('has_error')):
                cat = result['category']
                if cat not in failed_categories:
                    failed_categories[cat] = []
                failed_categories[cat].append(result)
        
        if failed_categories:
            f.write("### Issues Found\n\n")
            for cat, failures in failed_categories.items():
                f.write(f"**{cat}**: {len(failures)} issues\n")
                for failure in failures[:3]:  # Show first 3
                    f.write(f"- {failure['question'][:80]}\n")
                f.write("\n")
        
        # Out-of-scope issues
        oos_not_denied = [r for r in out_of_scope_results if not r['analysis'].get('is_out_of_scope')]
        if oos_not_denied:
            f.write("### Out-of-Scope Handling Issues\n\n")
            f.write(f"Found {len(oos_not_denied)} queries that should be denied but weren't:\n\n")
            for r in oos_not_denied[:5]:
                f.write(f"- {r['question']}\n")
            f.write("\n")
        
        f.write("### Next Steps\n\n")
        if success/total >= 0.95 and subject_lib_quality >= 80 and out_of_scope_quality >= 80:
            f.write("1. ✅ Bot is production-ready\n")
            f.write("2. 📊 Monitor real-world usage for edge cases\n")
            f.write("3. 📝 Collect user feedback for improvements\n")
            f.write("4. 🔄 Schedule monthly data syncs\n")
            f.write("5. 📧 Configure email alerts for server monitoring\n")
        else:
            f.write("1. ❌ Fix identified issues before launch\n")
            f.write("2. 🔄 Re-run this test suite after fixes\n")
            f.write("3. 📊 Focus on failing categories\n")
            f.write("4. 🧪 Add more test coverage for edge cases\n")
    
    print(f"\n{'='*100}")
    print(f"✅ Report generated: {report_file}")
    print(f"✅ Raw results saved: {json_file}")
    print("=" * 100)
    
    return report_file


async def main():
    """Main test execution."""
    print("\n🚀 Starting Ultimate Comprehensive Test Suite...")
    print("⏱️ This will take approximately 5-10 minutes...")
    
    results = await run_all_tests()
    report_file = await generate_report(results)
    
    print(f"\n{'='*100}")
    print("✅ ULTIMATE COMPREHENSIVE TEST COMPLETE")
    print("=" * 100)
    print(f"\n📄 Full report: {report_file}")
    print("\nNext: Review the report for production readiness assessment")


if __name__ == "__main__":
    asyncio.run(main())
