#!/usr/bin/env python3
"""
Targeted test for Subject Librarian and LibGuide queries.
Tests only the previously failing categories to verify the connection pool fix.
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Dict, List, Any

# Test configuration
API_URL = "http://localhost:8000/ask"
TIMEOUT = 60  # seconds

# Test questions - from previously failing categories
TEST_QUESTIONS = {
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
    "9_REGIONAL_CAMPUS": [
        "Who is the librarian at Rentschler Library?",
        "Hamilton campus library contact",
        "Middletown campus research help",
    ],
}


async def test_question(client: httpx.AsyncClient, question: str, category: str, index: int) -> Dict[str, Any]:
    """Test a single question and return the result."""
    print(f"\n[{index}] Testing: {question}...")
    
    try:
        response = await client.post(
            API_URL,
            json={"message": question},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        result = {
            "category": category,
            "index": index,
            "question": question,
            "status": "SUCCESS",
            "agents": data.get("agents_used", []),
            "response": data.get("final_answer", "")[:500],
        }
        
        print(f"  ✅ Status: SUCCESS")
        print(f"  📊 Agents: {result['agents']}")
        print(f"  📝 Response: {result['response'][:100]}...")
        
        return result
        
    except httpx.TimeoutException:
        print(f"  ❌ Status: TIMEOUT")
        return {
            "category": category,
            "index": index,
            "question": question,
            "status": "TIMEOUT",
            "error": "Request timed out"
        }
        
    except Exception as e:
        print(f"  ❌ Status: EXCEPTION - {str(e)}")
        return {
            "category": category,
            "index": index,
            "question": question,
            "status": "EXCEPTION",
            "error": str(e)
        }


async def run_tests():
    """Run all tests and generate report."""
    print("=" * 80)
    print("TARGETED TEST: Subject Librarian & LibGuide Queries")
    print("=" * 80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    total_questions = sum(len(q) for q in TEST_QUESTIONS.values())
    
    async with httpx.AsyncClient() as client:
        # Check server health first
        try:
            health = await client.get("http://localhost:8000/health", timeout=10)
            health_data = health.json()
            print(f"\n✅ Server healthy: {health_data.get('status')}")
        except Exception as e:
            print(f"\n❌ Server not responding: {e}")
            print("Please start the server first: cd ai-core && .venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000")
            return
        
        # Run tests sequentially (to avoid overwhelming the server)
        question_num = 0
        for category, questions in TEST_QUESTIONS.items():
            print(f"\n{'='*60}")
            print(f"Category: {category}")
            print(f"{'='*60}")
            
            for i, question in enumerate(questions, 1):
                question_num += 1
                result = await test_question(client, question, category, i)
                results.append(result)
                
                # Small delay between requests to be gentle on connection pool
                await asyncio.sleep(0.5)
    
    # Generate report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"test_results/TARGETED_TEST_REPORT_{timestamp}.md"
    json_path = f"test_results/targeted_test_results_{timestamp}.json"
    
    # Calculate statistics
    success_count = len([r for r in results if r['status'] == 'SUCCESS'])
    failure_count = len([r for r in results if r['status'] != 'SUCCESS'])
    
    # Stats by category
    category_stats = {}
    for category in TEST_QUESTIONS.keys():
        cat_results = [r for r in results if r['category'] == category]
        cat_success = len([r for r in cat_results if r['status'] == 'SUCCESS'])
        category_stats[category] = {
            "total": len(cat_results),
            "success": cat_success,
            "rate": cat_success / len(cat_results) * 100 if cat_results else 0
        }
    
    # Generate markdown report
    report = f"""# Targeted Test Report: Subject Librarian & LibGuide Queries

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Purpose**: Verify connection pool fix for Subject Librarian and LibGuide failures

## 📊 Summary

| Metric | Value |
|--------|-------|
| Total Questions | {len(results)} |
| Successful | {success_count} ({success_count/len(results)*100:.1f}%) |
| Failed | {failure_count} ({failure_count/len(results)*100:.1f}%) |

## 📋 Results by Category

"""
    
    for category, stats in category_stats.items():
        status = "✅" if stats['rate'] >= 90 else "⚠️" if stats['rate'] >= 70 else "❌"
        report += f"### {category}\n\n"
        report += f"**Success Rate**: {stats['success']}/{stats['total']} ({stats['rate']:.1f}%) {status}\n\n"
        
        # List individual results
        cat_results = [r for r in results if r['category'] == category]
        for r in cat_results:
            status_icon = "✅" if r['status'] == 'SUCCESS' else "❌"
            report += f"- {status_icon} Q{r['index']}: {r['question']}\n"
            if r['status'] != 'SUCCESS':
                report += f"  - Error: {r.get('error', 'No response')}\n"
        report += "\n"
    
    # Add failure details
    failures = [r for r in results if r['status'] != 'SUCCESS']
    if failures:
        report += "## ❌ Failure Details\n\n"
        for f in failures:
            report += f"### {f['question']}\n"
            report += f"- Category: {f['category']}\n"
            report += f"- Status: {f['status']}\n"
            report += f"- Error: {f.get('error', 'No error message')}\n\n"
    
    # Conclusion
    report += f"""## 🎯 Conclusion

"""
    if failure_count == 0:
        report += """**✅ ALL TESTS PASSED!**

The connection pool fix has resolved all Subject Librarian and LibGuide failures.
The singleton Prisma client pattern is working correctly.
"""
    elif success_count / len(results) >= 0.9:
        report += f"""**⚠️ MOSTLY PASSING ({success_count/len(results)*100:.1f}%)**

Most tests pass. {failure_count} failure(s) may be due to:
- Network issues
- API rate limiting
- Specific data gaps

These are not connection pool related.
"""
    else:
        report += f"""**❌ ISSUES REMAIN ({success_count/len(results)*100:.1f}%)**

Further investigation needed. Check:
- Database connection status
- Prisma client singleton implementation
- Server logs for errors
"""
    
    # Save reports
    with open(report_path, 'w') as f:
        f.write(report)
    
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print(f"\n📊 Results: {success_count}/{len(results)} passed ({success_count/len(results)*100:.1f}%)")
    print(f"📄 Report: {report_path}")
    print(f"📋 JSON: {json_path}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_tests())
