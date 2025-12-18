#!/usr/bin/env python3
"""
Chatbot Self-Test Script
Tests 20 key questions to verify chatbot functionality.
"""
import asyncio
import httpx
import json
from datetime import datetime

TEST_QUESTIONS = [
    ("1", "What are the library hours?"),
    ("2", "What is the address of the library?"),
    ("3", "What is the library phone number?"),
    ("4", "Who is the subject librarian for Biology?"),
    ("5", "Can I check out a camera?"),
    ("6", "Who can help me with a research question?"),
    ("7", "Can I put a ticket in for help?"),
    ("8", "What are the hours for live chat help from the librarians?"),
    ("9", "How long can I check a book out for?"),
    ("10", "Is there a class guide for my class?"),
    ("11", "How do I print in the library?"),
    ("12", "How do I get/renew my NYT subscription?"),
    ("13", "How do I reserve a study room in Rentschler?"),
    ("14", "Can you book a study room for me in King Library?"),
    ("15", "Can I eat/drink in the library?"),
    ("16", "How do I get Adobe?"),
    ("17", "Do you have a copy of The Great Gatsby?"),
    ("18", "How do I get a book not available at Miami?"),
    ("19", "Can I renew a book that's due soon?"),
    ("20", "I need 3 articles 19 pages or more that talk about the effects of economy, tourism/travel, and employments from 9/11"),
]

async def test_question(client: httpx.AsyncClient, question: str, timeout: int = 60) -> dict:
    """Send a question to the chatbot and get the response."""
    try:
        response = await client.post(
            "http://localhost:8000/ask",
            json={"message": question, "conversation_id": None},
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            return {"success": True, "response": data.get("final_answer", data.get("response", "No response"))}
        else:
            return {"success": False, "response": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "response": f"Error: {type(e).__name__}: {str(e)[:100]}"}

async def run_tests():
    """Run all test questions and generate report."""
    results = []
    
    async with httpx.AsyncClient() as client:
        # Check if server is up
        try:
            health = await client.get("http://localhost:8000/health", timeout=5)
            if health.status_code != 200:
                print("❌ Server not healthy!")
                return
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return
        
        print(f"\n{'='*60}")
        print(f"CHATBOT SELF-TEST - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        for num, question in TEST_QUESTIONS:
            print(f"Testing Q{num}: {question[:50]}...")
            result = await test_question(client, question)
            
            # Truncate response for display
            resp_preview = result["response"][:200] if len(result["response"]) > 200 else result["response"]
            status = "✅" if result["success"] else "❌"
            
            results.append({
                "num": num,
                "question": question,
                "success": result["success"],
                "response": result["response"],
                "preview": resp_preview
            })
            
            print(f"  {status} Response: {resp_preview[:100]}...\n")
            
            # Small delay between requests
            await asyncio.sleep(1)
    
    # Generate markdown report
    generate_report(results)
    
    # Summary
    passed = sum(1 for r in results if r["success"])
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(results)} tests passed")
    print(f"{'='*60}")

def generate_report(results: list):
    """Generate markdown report file."""
    report = f"""# Chatbot Self-Test Report

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | {len(results)} |
| Passed | {sum(1 for r in results if r["success"])} |
| Failed | {sum(1 for r in results if not r["success"])} |

## Test Results

"""
    
    for r in results:
        status = "✅ PASS" if r["success"] else "❌ FAIL"
        report += f"""### Q{r['num']}: {r['question']}

**Status:** {status}

**Response:**
```
{r['response'][:500]}{'...' if len(r['response']) > 500 else ''}
```

---

"""
    
    # Write report
    report_path = "/Users/qum/Documents/GitHub/chatbot/ai-core/test_results.md"
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"\n📄 Report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(run_tests())
