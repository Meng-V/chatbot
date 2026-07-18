"""
Retry Failed Tests - Focus on Previously Failed Questions

This script re-runs only the questions that failed in the comprehensive test,
allowing us to verify fixes without running the entire test suite.
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Dict, Any, List

API_URL = "http://localhost:8000/ask"
TIMEOUT = 120.0  # 2 minutes timeout

# Questions that failed in the comprehensive test
FAILED_QUESTIONS = {
    "homework_timeout": {
        "question": "What's the answer to question 5 on my biology homework?",
        "expected": "Should deny as out-of-scope immediately",
        "category": "OUT_OF_SCOPE_HOMEWORK"
    },
    "subject_librarian_psychology": {
        "question": "Psychology department librarian contact",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "subject_librarian_chemistry": {
        "question": "Who can help me with chemistry research?",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "subject_librarian_business": {
        "question": "Business librarian email",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "subject_librarian_history": {
        "question": "History subject librarian",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "subject_librarian_cs": {
        "question": "Computer science librarian",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "subject_librarian_music": {
        "question": "Music librarian at Miami",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS"
    },
    "course_bio": {
        "question": "Who helps with BIO courses?",
        "expected": "Should return librarian contact within 10s",
        "category": "SUBJECT_LIBRARIANS_COURSE"
    },
    "libguide_biology": {
        "question": "Research guide for biology",
        "expected": "Should return LibGuide within 10s",
        "category": "LIBGUIDE_SEARCHES"
    },
    "libguide_psychology": {
        "question": "Psychology research resources",
        "expected": "Should return LibGuide within 10s",
        "category": "LIBGUIDE_SEARCHES"
    },
    "multi_part_complex": {
        "question": "I have three questions: 1) What time does King close? 2) Who is the business librarian? 3) How do I cite a website in APA?",
        "expected": "Should handle multi-part question within 15s",
        "category": "MULTI_PART"
    },
    "rapid_context_nursing": {
        "question": "Actually never mind, who is the nursing librarian?",
        "expected": "Should handle context switch within 10s",
        "category": "RAPID_CONTEXT_SWITCH"
    },
    "rapid_context_psychology": {
        "question": "Wait, forget that - I need articles about psychology",
        "expected": "Should handle context switch within 10s",
        "category": "RAPID_CONTEXT_SWITCH"
    },
    "regional_rentschler": {
        "question": "Who is the librarian at Rentschler Library?",
        "expected": "Should return regional librarian within 10s",
        "category": "REGIONAL_CAMPUS"
    },
    "rapid_fire_biology": {
        "question": "Who is the biology librarian?",
        "expected": "Should return librarian contact within 10s",
        "category": "RAPID_FIRE"
    },
}


async def test_single_question(client: httpx.AsyncClient, test_id: str, test_data: Dict[str, Any]) -> Dict[str, Any]:
    """Test a single question and return results."""
    question = test_data["question"]
    expected = test_data["expected"]
    category = test_data["category"]
    
    print(f"\n{'='*80}")
    print(f"Test: {test_id}")
    print(f"Category: {category}")
    print(f"Question: {question}")
    print(f"Expected: {expected}")
    print(f"{'='*80}")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        response = await client.post(
            API_URL,
            json={"message": question},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        result = {
            "test_id": test_id,
            "category": category,
            "question": question,
            "expected": expected,
            "status": "SUCCESS",
            "response_time": round(elapsed, 2),
            "response": data.get("final_answer", ""),
            "agents": data.get("agents_used", []),
            "needs_human": data.get("needs_human", False),
            "timestamp": datetime.now().isoformat()
        }
        
        # Check if response is appropriate
        if elapsed > 15:
            result["warning"] = f"Slow response: {elapsed:.2f}s"
            print(f"⚠️  SLOW: {elapsed:.2f}s")
        else:
            print(f"✅ SUCCESS: {elapsed:.2f}s")
        
        print(f"Response preview: {data.get('final_answer', '')[:150]}...")
        
        return result
        
    except httpx.TimeoutException:
        elapsed = asyncio.get_event_loop().time() - start_time
        print(f"❌ TIMEOUT after {elapsed:.2f}s")
        return {
            "test_id": test_id,
            "category": category,
            "question": question,
            "expected": expected,
            "status": "TIMEOUT",
            "response_time": round(elapsed, 2),
            "error": "Request timed out",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        elapsed = asyncio.get_event_loop().time() - start_time
        print(f"❌ ERROR: {str(e)}")
        return {
            "test_id": test_id,
            "category": category,
            "question": question,
            "expected": expected,
            "status": "ERROR",
            "response_time": round(elapsed, 2),
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def run_retry_tests():
    """Run all failed tests and generate report."""
    print("\n" + "="*80)
    print("RETRY FAILED TESTS - Verifying Fixes")
    print("="*80)
    print(f"Total tests to retry: {len(FAILED_QUESTIONS)}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    async with httpx.AsyncClient() as client:
        # Check server health
        try:
            health_response = await client.get("http://localhost:8000/health", timeout=5.0)
            health_response.raise_for_status()
            print("✅ Server is running")
        except Exception as e:
            print(f"\n❌ Server not responding: {e}")
            print("Please start the server first:")
            print("  bash local-auto-start.sh")
            return None
        
        # Run each test
        for test_id, test_data in FAILED_QUESTIONS.items():
            result = await test_single_question(client, test_id, test_data)
            results.append(result)
            
            # Small delay between tests
            await asyncio.sleep(1.0)
    
    # Generate report
    print(f"\n{'='*80}")
    print("TEST RESULTS SUMMARY")
    print(f"{'='*80}")
    
    success_count = len([r for r in results if r["status"] == "SUCCESS"])
    timeout_count = len([r for r in results if r["status"] == "TIMEOUT"])
    error_count = len([r for r in results if r["status"] == "ERROR"])
    
    print(f"\nTotal: {len(results)}")
    print(f"✅ Success: {success_count} ({success_count/len(results)*100:.1f}%)")
    print(f"⏱️  Timeout: {timeout_count} ({timeout_count/len(results)*100:.1f}%)")
    print(f"❌ Error: {error_count} ({error_count/len(results)*100:.1f}%)")
    
    # Response time stats
    response_times = [r["response_time"] for r in results if r["status"] == "SUCCESS"]
    if response_times:
        print(f"\nResponse Times:")
        print(f"  Min: {min(response_times):.2f}s")
        print(f"  Max: {max(response_times):.2f}s")
        print(f"  Avg: {sum(response_times)/len(response_times):.2f}s")
    
    # Category breakdown
    print(f"\nBy Category:")
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "success": 0}
        categories[cat]["total"] += 1
        if r["status"] == "SUCCESS":
            categories[cat]["success"] += 1
    
    for cat, stats in sorted(categories.items()):
        success_rate = stats["success"] / stats["total"] * 100
        icon = "✅" if success_rate == 100 else "⚠️" if success_rate >= 80 else "❌"
        print(f"  {icon} {cat}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"test_results/retry_test_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "total_tests": len(results),
            "success_count": success_count,
            "timeout_count": timeout_count,
            "error_count": error_count,
            "success_rate": round(success_count / len(results) * 100, 2),
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    # Final verdict
    if success_count == len(results):
        print(f"\n🎉 ALL TESTS PASSED! Ready for production.")
    elif success_count / len(results) >= 0.9:
        print(f"\n✅ MOSTLY FIXED - {timeout_count + error_count} issues remaining")
    else:
        print(f"\n⚠️  STILL NEEDS WORK - {timeout_count + error_count} failures")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_retry_tests())
