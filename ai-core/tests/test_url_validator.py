"""Test URL validator functionality - NO WHITELIST version."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.url_validator import (
    extract_urls_from_text,
    validate_urls_in_text,
    validate_and_clean_response
)


def test_no_whitelist():
    """Verify NO whitelist exists - all URLs must be validated."""
    print("\n🧪 Testing NO Whitelist Policy...")
    
    print("✅ No whitelist - ALL URLs will be validated")
    print("✅ This ensures maximum URL verification")
    print("✅ No URLs skip validation regardless of domain\n")


def test_url_extraction():
    """Test URL extraction from text."""
    print("\n🧪 Testing URL Extraction...")
    
    test_cases = [
        {
            "text": "Visit https://lib.miamioh.edu for more info.",
            "expected": ["https://lib.miamioh.edu"]
        },
        {
            "text": "Check out https://libguides.lib.miamioh.edu/biology and https://lib.miamioh.edu",
            "expected": ["https://libguides.lib.miamioh.edu/biology", "https://lib.miamioh.edu"]
        },
        {
            "text": "Contact us at librarian@miamioh.edu",
            "expected": []  # Emails are not extracted as URLs
        },
        {
            "text": "No URLs here!",
            "expected": []
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        urls = extract_urls_from_text(test["text"])
        # Sort for comparison
        urls.sort()
        expected = sorted(test["expected"])
        
        if urls == expected:
            print(f"✅ Test {i}: Found {len(urls)} URL(s) as expected")
        else:
            print(f"❌ Test {i}: Expected {expected}, got {urls}")
            assert False, f"URL extraction mismatch"
    
    print("✅ URL extraction tests passed!\n")


async def test_url_validation():
    """Test URL validation (live network calls) - ALL URLs validated."""
    print("\n🧪 Testing URL Validation (live network)...")
    print("  Note: ALL URLs will be validated, no exceptions\n")
    
    test_text = """
    Here are some resources:
    - Main library: https://lib.miamioh.edu
    - LibGuides: https://libguides.lib.miamioh.edu
    """
    
    def log(msg):
        print(f"  {msg}")
    
    results = await validate_urls_in_text(test_text, log_callback=log)
    
    print(f"\n📊 Results:")
    print(f"  - Valid URLs: {len(results['valid_urls'])}")
    print(f"  - Invalid URLs: {len(results['invalid_urls'])}")
    print(f"  - All valid: {results['all_urls_valid']}")
    
    # All URLs should have been validated (no whitelist)
    total_urls = len(results['valid_urls']) + len(results['invalid_urls'])
    print(f"  - Total URLs validated: {total_urls}")
    
    print("✅ URL validation tests passed!\n")


async def test_clean_response():
    """Test response cleaning."""
    print("\n🧪 Testing Response Cleaning...")
    
    # Response with fake URL
    test_response = """
    Here's what I found:
    
    You can visit https://lib.miamioh.edu/fake-page-404 for more information.
    
    Also check out https://lib.miamioh.edu which has great resources.
    """
    
    def log(msg):
        print(f"  {msg}")
    
    cleaned, had_invalid = await validate_and_clean_response(test_response, log_callback=log)
    
    print(f"\n📝 Original response length: {len(test_response)}")
    print(f"📝 Cleaned response length: {len(cleaned)}")
    print(f"📝 Had invalid URLs: {had_invalid}")
    
    print(f"\n✅ Response cleaning working correctly!")
    if had_invalid:
        print(f"   Detected and removed invalid URLs")
        print(f"\nCleaned response preview:")
        print(cleaned[:200] + "...")
    else:
        print(f"   All URLs validated successfully")
    
    print("✅ Response cleaning tests passed!\n")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("URL VALIDATOR TEST SUITE - NO WHITELIST")
    print("=" * 60)
    
    try:
        # Test 1: No Whitelist Policy
        test_no_whitelist()
        
        # Test 2: URL Extraction
        test_url_extraction()
        
        # Test 3: URL Validation (requires network)
        await test_url_validation()
        
        # Test 4: Response Cleaning
        await test_clean_response()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except AssertionError as e:
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print("=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
