"""Test script to verify library spaces feature:
- All 3 spaces under King Library (Makerspace, Special Collections, Archives)
- Phone and email fields populated correctly
- Query extraction distinguishes Special Collections from Archives
- Location service returns correct data for each space

Run: python -m scripts.test_library_spaces
"""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.prisma_client import get_prisma_client
from src.services.location_service import get_location_service
from src.tools.libcal_comprehensive_tools import _extract_building_from_query


def test_extract_building_from_query():
    """Test that query extraction correctly distinguishes spaces."""
    print("\n" + "="*60)
    print("TEST 1: _extract_building_from_query disambiguation")
    print("="*60)
    
    test_cases = [
        # (query, expected_result)
        ("Where is the Makerspace?", "makerspace"),
        ("What are the Makerspace hours?", "makerspace"),
        ("Where is Special Collections?", "special collections"),
        ("How do I contact Special Collections?", "special collections"),
        ("Where are the University Archives?", "archives"),
        ("What is the Archives phone number?", "archives"),
        ("How do I contact archives?", "archives"),
        ("Where are the Digital Collections?", "digital collections"),
        ("What is the Digital Collections website?", "digital collections"),
        ("Where is King Library?", "king"),
        ("What are the library hours?", "king"),  # default
    ]
    
    passed = 0
    failed = 0
    for query, expected in test_cases:
        result = _extract_building_from_query(query)
        status = "✅" if result == expected else "❌"
        if result != expected:
            failed += 1
            print(f"  {status} '{query}' → got '{result}', expected '{expected}'")
        else:
            passed += 1
            print(f"  {status} '{query}' → '{result}'")
    
    print(f"\n  Results: {passed} passed, {failed} failed")
    return failed == 0


async def test_database_spaces():
    """Test that all 4 spaces exist in DB with correct data."""
    print("\n" + "="*60)
    print("TEST 2: Database LibrarySpace records")
    print("="*60)
    
    client = get_prisma_client()
    await client.connect()
    
    try:
        # Get all spaces under King Library
        king = await client.library.find_first(
            where={"shortName": "king"},
            include={"spaces": True}
        )
        
        if not king:
            print("  ❌ King Library not found in database!")
            return False
        
        spaces = king.spaces
        print(f"  Found {len(spaces)} space(s) under {king.displayName}:")
        
        expected_spaces = {
            "makerspace": {
                "phone": "(513) 529-2871",
                "email": "create@miamioh.edu",
                "buildingLocation": "Third floor, room 303",
                "website": "https://libguides.lib.miamioh.edu/create/makerspace",
            },
            "special collections": {
                "phone": "(513) 529-3323",
                "email": "SpecColl@MiamiOH.edu",
                "buildingLocation": "Third floor",
                "website": "https://spec.lib.miamioh.edu/home/",
            },
            "archives": {
                "phone": "(513) 529-6720",
                "email": "Archives@MiamiOH.edu",
                "buildingLocation": "Third floor",
                "website": "https://spec.lib.miamioh.edu/home/",
            },
            "digital collections": {
                "phone": None,
                "email": None,
                "buildingLocation": None,
                "website": "https://www.lib.miamioh.edu/digital-collections/",
            },
        }
        
        passed = 0
        failed = 0
        found_names = set()
        
        for space in spaces:
            short = space.shortName or ""
            found_names.add(short.lower())
            expected = expected_spaces.get(short.lower())
            
            if not expected:
                print(f"  ⚠️  Unexpected space: {space.displayName} (shortName: {short})")
                continue
            
            errors = []
            if space.phone != expected["phone"]:
                errors.append(f"phone: got '{space.phone}', expected '{expected['phone']}'")
            if space.email != expected["email"]:
                errors.append(f"email: got '{space.email}', expected '{expected['email']}'")
            if space.buildingLocation != expected["buildingLocation"]:
                errors.append(f"location: got '{space.buildingLocation}', expected '{expected['buildingLocation']}'")
            if space.website != expected["website"]:
                errors.append(f"website: got '{space.website}', expected '{expected['website']}'")
            
            if errors:
                failed += 1
                print(f"  ❌ {space.displayName}: {', '.join(errors)}")
            else:
                passed += 1
                print(f"  ✅ {space.displayName} — 📞 {space.phone} | 📧 {space.email} | 📍 {space.buildingLocation}")
        
        # Check all expected spaces were found
        for name in expected_spaces:
            if name not in found_names:
                failed += 1
                print(f"  ❌ Missing space: {name}")
        
        print(f"\n  Results: {passed} passed, {failed} failed")
        return failed == 0
    finally:
        await client.disconnect()


async def test_location_service():
    """Test that location service returns correct data for each space."""
    print("\n" + "="*60)
    print("TEST 3: LocationService.get_space_location_info()")
    print("="*60)
    
    location_service = get_location_service()
    
    test_cases = [
        ("makerspace", {
            "displayName": "Makerspace",
            "phone": "(513) 529-2871",
            "email": "create@miamioh.edu",
            "website": "https://libguides.lib.miamioh.edu/create/makerspace",
        }),
        ("special collections", {
            "displayName": "Walter Havighurst Special Collections",
            "phone": "(513) 529-3323",
            "email": "SpecColl@MiamiOH.edu",
            "website": "https://spec.lib.miamioh.edu/home/",
        }),
        ("archives", {
            "displayName": "University Archives & Preservation",
            "phone": "(513) 529-6720",
            "email": "Archives@MiamiOH.edu",
            "website": "https://spec.lib.miamioh.edu/home/",
        }),
        ("digital collections", {
            "displayName": "Digital Collections",
            "phone": None,
            "email": None,
            "website": "https://www.lib.miamioh.edu/digital-collections/",
        }),
    ]
    
    passed = 0
    failed = 0
    
    for space_name, expected in test_cases:
        info = await location_service.get_space_location_info(space_name)
        
        if not info:
            failed += 1
            print(f"  ❌ '{space_name}' → returned None!")
            continue
        
        errors = []
        for key, exp_val in expected.items():
            got = info.get(key)
            if got != exp_val:
                errors.append(f"{key}: got '{got}', expected '{exp_val}'")
        
        if errors:
            failed += 1
            print(f"  ❌ '{space_name}': {', '.join(errors)}")
        else:
            passed += 1
            print(f"  ✅ '{space_name}' → {info['displayName']}")
            print(f"     📍 {info['location']} | 📞 {info['phone']} | 📧 {info['email']}")
    
    print(f"\n  Results: {passed} passed, {failed} failed")
    return failed == 0


async def main():
    print("🧪 Library Spaces Feature Tests")
    print("Testing: Makerspace, Special Collections, Archives")
    
    results = []
    
    # Test 1: Query extraction (synchronous)
    results.append(("Query Extraction", test_extract_building_from_query()))
    
    # Test 2: Database records (async)
    results.append(("Database Spaces", await test_database_spaces()))
    
    # Test 3: Location service (async)
    results.append(("Location Service", await test_location_service()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 FINAL RESULTS")
    print("="*60)
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} — {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed. Review output above.")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
