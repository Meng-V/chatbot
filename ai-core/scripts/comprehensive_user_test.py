"""
Comprehensive Test Suite Based on User's Test Questions
Tests all 24 questions from the user's test list plus additional tricky questions

Run: python scripts/comprehensive_user_test.py
"""

import asyncio
import httpx
import json
from datetime import datetime
from pathlib import Path

API_URL = "http://localhost:8000/ask"
OUTPUT_DIR = Path(__file__).parent.parent / "test_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# User's 24 test questions from the image
USER_TEST_QUESTIONS = {
    "1_LIBRARY_HOURS": [
        "What are the library hours?",
        "Answer for MLK hours for The King Library",
        "Art and Architecture (test with and without Wertz)",
        "Makerspace",
        "Special Collections (test with and without full name)",
        "Regional: Hamilton, Middletown",
    ],
    
    "2_ADDRESS_PHONE": [
        "What is the address and phone number of the following library?",
        "King Library",
        "Art and Architecture (test with and without Wertz)",
        "Makerspace",
        "Special Collections",
        "Middletown",
        "Hamilton",
    ],
    
    "3_SUBJECT_LIBRARIAN": [
        "Who is the subject librarian for *X* (Geography, Marketing, Business, Special Collections, and Makerspace for Oxford and for Middletown)",
    ],
    
    "4_PC_CHECKOUT": [
        "Can I check out a PC?",
    ],
    
    "5_COMPUTER_HELP": [
        "Who can help me with a computer question",
    ],
    
    "6_RESEARCH_HELP": [
        "Who can help me with a research question",
    ],
    
    "7_TICKET": [
        "Can I put a ticket in for help",
    ],
    
    "8_LIVE_CHAT_HOURS": [
        "What are the hours for live chat help from the librarians",
    ],
    
    "9_BOOK_CHECKOUT_DURATION": [
        "How long can I check a book out for",
    ],
    
    "10_CLASS_GUIDES": [
        "Is there a class guide for my class - BUS 217, ENG 111, BIO 201",
    ],
    
    "11_PRINTING": [
        "How do I print in the library",
    ],
    
    "12_NYT_SUBSCRIPTION": [
        "How do I get/renew my NYT subscription",
    ],
    
    "13_STUDY_ROOM": [
        "How do I reserve a study room in Farmer",
    ],
    
    "14_STUDY_ROOM_BOOKING": [
        "book a study room FOR me in King, First name Meng, Last name Qu, people for 2, date this Friday, time afternoon 5-6",
    ],
    
    "15_EAT_DRINK_SLEEP": [
        "Can I eat/drink in the library? Can I sleep in the library?",
    ],
    
    "16_ADOBE": [
        "How do I get Adobe",
    ],
    
    "17_HARRY_POTTER": [
        "Do you have a copy of Harry Potter?",
    ],
    
    "18_ILL": [
        "How do I get a book/article not available at Miami",
    ],
    
    "19_BOOK_RENEWAL": [
        "Can I renew a book that's due soon",
    ],
    
    "20_OVERDUE_FINE": [
        "I have an overdue book what is the fine",
    ],
    
    "21_RESEARCH_ARTICLES": [
        "I need 3 articles 19 pages or more that talk about the affects of economy, tourism/travel, and employments from 9/11",
    ],
    
    "22_SPECIFIC_SEARCH": [
        "Looked up Foote Rupasingha Goetz 9/11 employment as suggested",
    ],
    
    "23_GIBBERISH": [
        "balabalabalabalabalaballabalb",
    ],
    
    "24_CODE_TEST": [
        "drop(* table) == true",
    ],
}

# Additional tricky questions to test edge cases
TRICKY_QUESTIONS = {
    "TRICKY_REGIONAL": [
        "Who is the librarian at Hamilton?",
        "Rentschler Library hours",
        "Gardner-Harvey Library phone number",
        "Can I book a room at Middletown?",
        "What are the hours for Rentschler?",
    ],
    
    "TRICKY_AMBIGUOUS": [
        "I need help with my computer",
        "Who can help me with computers?",
        "I have a question about computers",
    ],
    
    "TRICKY_SPECIFIC_NAMES": [
        "Who is Foote Rupasingha Goetz?",
        "Find librarian Foote",
        "Contact for Rupasingha Goetz",
    ],
    
    "TRICKY_MAKERSPACE": [
        "Makerspace librarian",
        "Who is the Makerspace librarian?",
        "Makerspace at Middletown",
        "3D printing",
    ],
    
    "TRICKY_SPECIAL_COLLECTIONS": [
        "Special Collections librarian",
        "Who is the Special Collections librarian?",
        "Special Collections hours",
    ],
    
    "TRICKY_BOOK_SEARCH": [
        "Do you have Frankenstein?",
        "Find me the book 1984",
        "Is The Great Gatsby available?",
    ],
    
    "TRICKY_RESEARCH": [
        "I need 5 articles about climate change",
        "Find me peer-reviewed sources on psychology",
        "I need articles 10 pages or longer about nursing",
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
                classified_intent = data.get("classified_intent", "")
                
                # Analyze response
                has_email = "@miamioh.edu" in final_answer
                has_url = "lib.miamioh.edu" in final_answer or "libguides" in final_answer
                has_phone = "(513)" in final_answer or "513-" in final_answer
                has_address = ("Oxford, OH" in final_answer or "Hamilton, OH" in final_answer or 
                              "Middletown, OH" in final_answer)
                has_hours = any(word in final_answer.lower() for word in ["open", "close", "hours", "am", "pm"])
                is_out_of_scope = "outside the scope" in final_answer.lower() or "can only help with library" in final_answer.lower()
                has_handoff = "chat with a librarian" in final_answer.lower() or "ask a librarian" in final_answer.lower()
                has_error = "trouble accessing" in final_answer.lower() or "error" in final_answer.lower()
                
                return {
                    "category": category,
                    "index": index,
                    "question": question,
                    "status": "SUCCESS",
                    "agents": agents,
                    "classified_intent": classified_intent,
                    "response": final_answer,
                    "analysis": {
                        "has_email": has_email,
                        "has_url": has_url,
                        "has_phone": has_phone,
                        "has_address": has_address,
                        "has_hours": has_hours,
                        "is_out_of_scope": is_out_of_scope,
                        "has_handoff": has_handoff,
                        "has_error": has_error,
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
    print("COMPREHENSIVE USER TEST SUITE - ALL 24 QUESTIONS + TRICKY CASES")
    print("=" * 100)
    print(f"\nTest Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    all_results = []
    
    # Combine all test questions
    all_test_questions = {**USER_TEST_QUESTIONS, **TRICKY_QUESTIONS}
    
    total_questions = sum(len(questions) for questions in all_test_questions.values())
    current = 0
    
    for category, questions in all_test_questions.items():
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
                print(f"  🎯 Intent: {result['classified_intent']}")
                print(f"  📊 Agents: {result['agents']}")
                print(f"  📝 Response: {result['response'][:150]}...")
                
                # Category-specific validation
                if "HOURS" in category:
                    print(f"  🕐 Has Hours: {'✅' if analysis['has_hours'] else '❌'}")
                
                elif "ADDRESS" in category or "PHONE" in category:
                    print(f"  📍 Has Address: {'✅' if analysis['has_address'] else '❌'}")
                    print(f"  📞 Has Phone: {'✅' if analysis['has_phone'] else '❌'}")
                
                elif "LIBRARIAN" in category:
                    print(f"  📧 Has Email: {'✅' if analysis['has_email'] else '❌'}")
                    print(f"  🔗 Has URL: {'✅' if analysis['has_url'] else '➖'}")
                
                elif "GIBBERISH" in category or "CODE_TEST" in category:
                    print(f"  🚫 Out-of-Scope: {'✅' if analysis['is_out_of_scope'] else '❌ SHOULD DENY'}")
                
                elif "RESEARCH" in category or "ARTICLES" in category:
                    print(f"  👋 Handoff: {'✅' if analysis['has_handoff'] else '❌ SHOULD HANDOFF'}")
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
    json_file = OUTPUT_DIR / f"comprehensive_user_test_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate markdown report
    report_file = OUTPUT_DIR / f"COMPREHENSIVE_USER_TEST_REPORT_{timestamp}.md"
    
    with open(report_file, 'w') as f:
        f.write("# COMPREHENSIVE USER TEST REPORT\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Questions**: {len(results)}\n\n")
        
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
        
        # Detailed results by category
        f.write("## 📝 Detailed Results\n\n")
        
        all_test_questions = {**USER_TEST_QUESTIONS, **TRICKY_QUESTIONS}
        
        for category in all_test_questions.keys():
            f.write(f"### {category}\n\n")
            cat_results = [r for r in results if r['category'] == category]
            
            for result in cat_results:
                status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
                f.write(f"#### {status_icon} Q{result['index']}: {result['question']}\n\n")
                
                if result['status'] == 'SUCCESS':
                    f.write(f"**Intent**: {result['classified_intent']}\n\n")
                    f.write(f"**Agents**: {', '.join(result['agents']) if result['agents'] else 'None'}\n\n")
                    f.write(f"**Response**:\n```\n{result['response'][:500]}\n```\n\n")
                    
                    # Analysis flags
                    analysis = result['analysis']
                    flags = []
                    if analysis.get('has_email'): flags.append("📧 Email")
                    if analysis.get('has_url'): flags.append("🔗 URL")
                    if analysis.get('has_phone'): flags.append("📞 Phone")
                    if analysis.get('has_address'): flags.append("📍 Address")
                    if analysis.get('has_hours'): flags.append("🕐 Hours")
                    if analysis.get('has_error'): flags.append("⚠️ Error")
                    if analysis.get('is_out_of_scope'): flags.append("🚫 Out-of-Scope")
                    if analysis.get('has_handoff'): flags.append("👋 Handoff")
                    
                    if flags:
                        f.write(f"**Flags**: {' | '.join(flags)}\n\n")
                else:
                    f.write(f"**Error**: {result.get('error', 'Unknown')}\n\n")
        
        # Issues found
        f.write("## ⚠️ Issues Found\n\n")
        
        failed = [r for r in results if r['status'] != 'SUCCESS']
        if failed:
            f.write(f"### Failed Queries ({len(failed)})\n\n")
            for r in failed:
                f.write(f"- **{r['category']}**: {r['question']}\n")
                f.write(f"  - Error: {r.get('error', 'Unknown')}\n\n")
        else:
            f.write("✅ No failed queries!\n\n")
        
        # Success rate by category
        f.write("## 📈 Success Rate by Category\n\n")
        f.write("| Category | Success | Total | Rate |\n")
        f.write("|----------|---------|-------|------|\n")
        
        for category in all_test_questions.keys():
            cat_results = [r for r in results if r['category'] == category]
            cat_success = [r for r in cat_results if r['status'] == 'SUCCESS']
            rate = len(cat_success) / len(cat_results) * 100 if cat_results else 0
            f.write(f"| {category} | {len(cat_success)} | {len(cat_results)} | {rate:.1f}% |\n")
        
        f.write("\n")
    
    print(f"\n{'='*100}")
    print(f"✅ Report generated: {report_file}")
    print(f"✅ Raw results saved: {json_file}")
    print("=" * 100)
    
    return report_file


async def main():
    """Main test execution."""
    print("\n🚀 Starting Comprehensive User Test Suite...")
    print("⏱️ This will take approximately 3-5 minutes...")
    
    results = await run_all_tests()
    report_file = await generate_report(results)
    
    print(f"\n{'='*100}")
    print("✅ COMPREHENSIVE USER TEST COMPLETE")
    print("=" * 100)
    print(f"\n📄 Full report: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())
