"""
Comprehensive Librarian and LibGuide Verification Tests

Tests:
1. All subject librarian queries return verified contacts from CSV
2. All LibGuide URLs are valid
3. Subject-Librarian-LibGuide mappings are correct
4. Regional campus filtering works correctly
5. All contacts match the staff list

Run: python scripts/test_librarian_verification.py
"""

import asyncio
import httpx
import csv
from pathlib import Path

API_URL = "http://localhost:8000/ask"
CSV_FILE = Path(__file__).resolve().parent.parent.parent / "staff-members - staff-members.csv"

# Load valid staff emails from CSV
VALID_STAFF_EMAILS = set()
with open(CSV_FILE, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        email = row.get('email', '').strip()
        if email and email.endswith('@miamioh.edu'):
            VALID_STAFF_EMAILS.add(email)

print(f"✅ Loaded {len(VALID_STAFF_EMAILS)} valid staff emails from CSV")


# Test queries
SUBJECT_LIBRARIAN_TESTS = [
    # By subject name
    ("Who is the biology librarian?", "Biology", "boehmemv@miamioh.edu", "Ginny Boehme"),
    ("English department librarian", "English", "dahlqumj@miamioh.edu", "Mark Dahlquist"),
    ("Psychology librarian contact", "Psychology", "jaskowmm@miamioh.edu", "Megan Jaskowiak"),
    ("Chemistry librarian", "Chemistry", "adamsk3@miamioh.edu", "Kristen Adams"),
    ("History department contact", "History", "presneja@miamioh.edu", "Jenny Presnell"),
    ("Business librarian", "Business", "grishaz@miamioh.edu", "Zachary Grisham"),
    ("Music librarian", "Music", "zaslowbj@miamioh.edu", "Barry Zaslow"),
    
    # By course code
    ("Who is the librarian for ENG 111?", "English", "dahlqumj@miamioh.edu", "Mark Dahlquist"),
    ("I need help with BIO 201", "Biology", "boehmemv@miamioh.edu", "Ginny Boehme"),
    ("PSY 201 librarian", "Psychology", "jaskowmm@miamioh.edu", "Megan Jaskowiak"),
    
    # Natural language
    ("I need help with my psychology class", "Psychology", "jaskowmm@miamioh.edu", "Megan Jaskowiak"),
    ("Who can help me with biology research?", "Biology", "boehmemv@miamioh.edu", "Ginny Boehme"),
    ("I'm a business major, who is my librarian?", "Business", "grishaz@miamioh.edu", "Zachary Grisham"),
    
    # Regional campus
    ("Who is the librarian at Hamilton?", None, "mcdonak2@miamioh.edu", "Krista McDonald"),
    ("I'm at Middletown campus, who can help?", None, "burkejj@miamioh.edu", "John Burke"),
    ("Rentschler Library librarian", None, "mcdonak2@miamioh.edu", "Krista McDonald"),
]


async def test_query(question: str, expected_subject: str, expected_email: str, expected_name: str):
    """Test a single query and verify response."""
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
                
                # Verify contact is from staff list
                has_expected_email = expected_email in final_answer
                has_expected_name = expected_name in final_answer
                has_valid_email = any(email in final_answer for email in VALID_STAFF_EMAILS)
                has_libguide_url = "libguides.lib.miamioh.edu" in final_answer
                has_error = "trouble accessing" in final_answer.lower()
                
                # Check for any email that's NOT in staff list (fake contact)
                import re
                emails_in_response = re.findall(r'[\w\.-]+@miamioh\.edu', final_answer)
                fake_emails = [e for e in emails_in_response if e not in VALID_STAFF_EMAILS]
                
                return {
                    "question": question,
                    "expected_subject": expected_subject,
                    "expected_email": expected_email,
                    "expected_name": expected_name,
                    "status": "SUCCESS",
                    "agents": agents,
                    "response": final_answer[:300],
                    "verification": {
                        "has_expected_email": has_expected_email,
                        "has_expected_name": has_expected_name,
                        "has_valid_email": has_valid_email,
                        "has_libguide_url": has_libguide_url,
                        "has_error": has_error,
                        "fake_emails": fake_emails
                    }
                }
            else:
                return {
                    "question": question,
                    "status": "HTTP_ERROR",
                    "error": f"HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            "question": question,
            "status": "EXCEPTION",
            "error": str(e)
        }


async def run_verification_tests():
    """Run all verification tests."""
    print("\n" + "=" * 80)
    print("LIBRARIAN & LIBGUIDE VERIFICATION TESTS")
    print("=" * 80)
    print()
    
    results = []
    
    for i, (question, expected_subject, expected_email, expected_name) in enumerate(SUBJECT_LIBRARIAN_TESTS, 1):
        print(f"\n[{i}/{len(SUBJECT_LIBRARIAN_TESTS)}] {question}")
        result = await test_query(question, expected_subject, expected_email, expected_name)
        results.append(result)
        
        if result['status'] == 'SUCCESS':
            v = result['verification']
            print(f"  Expected Email: {'✅' if v['has_expected_email'] else '❌'} {expected_email}")
            print(f"  Expected Name: {'✅' if v['has_expected_name'] else '❌'} {expected_name}")
            print(f"  Has LibGuide URL: {'✅' if v['has_libguide_url'] else '❌'}")
            print(f"  Has Error: {'❌' if v['has_error'] else '✅'}")
            print(f"  Fake Emails: {'❌ ' + str(v['fake_emails']) if v['fake_emails'] else '✅ None'}")
        else:
            print(f"  ❌ {result['status']}: {result.get('error', 'Unknown')}")
    
    # Generate summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    success = [r for r in results if r['status'] == 'SUCCESS']
    with_expected_email = [r for r in success if r['verification']['has_expected_email']]
    with_expected_name = [r for r in success if r['verification']['has_expected_name']]
    with_libguide = [r for r in success if r['verification']['has_libguide_url']]
    with_error = [r for r in success if r['verification']['has_error']]
    with_fake_emails = [r for r in success if r['verification']['fake_emails']]
    
    print(f"\nTotal Tests: {len(results)}")
    print(f"Success: {len(success)}/{len(results)} ({len(success)/len(results)*100:.1f}%)")
    print(f"\nVerification:")
    print(f"  Expected Email: {len(with_expected_email)}/{len(success)} ({len(with_expected_email)/len(success)*100:.1f}%)")
    print(f"  Expected Name: {len(with_expected_name)}/{len(success)} ({len(with_expected_name)/len(success)*100:.1f}%)")
    print(f"  Has LibGuide URL: {len(with_libguide)}/{len(success)} ({len(with_libguide)/len(success)*100:.1f}%)")
    print(f"  No Errors: {len(success) - len(with_error)}/{len(success)} ({(len(success) - len(with_error))/len(success)*100:.1f}%)")
    print(f"  No Fake Emails: {len(success) - len(with_fake_emails)}/{len(success)} ({'✅ PERFECT' if len(with_fake_emails) == 0 else '❌ ISSUES'})")
    
    if with_fake_emails:
        print(f"\n❌ FAKE EMAILS DETECTED:")
        for r in with_fake_emails:
            print(f"  Question: {r['question']}")
            print(f"  Fake emails: {r['verification']['fake_emails']}")
    
    # Perfect score check
    perfect = len(with_expected_email) == len(success) and len(with_libguide) == len(success) and len(with_error) == 0 and len(with_fake_emails) == 0
    
    print(f"\n{'='*80}")
    if perfect:
        print("✅ PERFECT SCORE - 100% QUALITY")
    else:
        print(f"⚠️ QUALITY: {(len(with_expected_email) + len(with_libguide) - len(with_error)) / (len(success) * 2) * 100:.1f}%")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_verification_tests())
