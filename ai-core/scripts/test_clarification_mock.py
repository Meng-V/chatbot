#!/usr/bin/env python3
"""
Mock Test for Clarification Choices System

Tests the clarification choice handling without requiring Weaviate connection.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.classification.clarification_handler import handle_clarification_choice, reclassify_with_additional_context


def create_mock_clarification_data():
    """Create mock clarification data for testing."""
    return {
        "prompt": "I want to make sure I understand your question correctly. Which of these best describes what you're looking for?",
        "choices": [
            {
                "id": "choice_0",
                "label": "Borrow equipment (laptops, chargers, etc.)",
                "description": "Questions about borrowing library equipment like laptops, chargers, calculators, etc.",
                "category": "library_equipment_checkout",
                "examples": ["Can I borrow a laptop?", "Checkout a charger"]
            },
            {
                "id": "choice_1",
                "label": "Get help with a broken computer",
                "description": "Technical problems with computers, devices, WiFi, Canvas, email, passwords.",
                "category": "out_of_scope_tech_support",
                "examples": ["My computer is broken", "WiFi not working"]
            },
            {
                "id": "choice_2",
                "label": "Find a computer to use in the library",
                "description": "Questions about using library computers and workstations.",
                "category": "library_policies_services",
                "examples": ["Where are the computers?", "Can I use a library computer?"]
            },
            {
                "id": "choice_none",
                "label": "None of the above",
                "description": "My question is about something else",
                "category": "none_of_above",
                "examples": []
            }
        ],
        "original_question": "I need help with a computer"
    }


async def test_user_selects_specific_choice():
    """Test handling when user selects a specific category."""
    print("\n" + "="*80)
    print("TEST 1: User Selects Specific Choice")
    print("="*80)
    
    clarification_data = create_mock_clarification_data()
    
    print(f"\n📝 Original Question: {clarification_data['original_question']}")
    print(f"\n🎯 Clarification Prompt:")
    print(f"   {clarification_data['prompt']}")
    
    print(f"\n📋 Available Choices:")
    for i, choice in enumerate(clarification_data['choices'], 1):
        print(f"   {i}. [{choice['id']}] {choice['label']}")
    
    # Simulate user selecting first choice
    selected_choice = clarification_data['choices'][0]
    print(f"\n👤 User selects: {selected_choice['label']}")
    
    result = await handle_clarification_choice(
        choice_id=selected_choice['id'],
        original_question=clarification_data['original_question'],
        clarification_data=clarification_data
    )
    
    print(f"\n✅ Handler Result:")
    print(f"   Selected Category: {result.get('selected_category')}")
    print(f"   Needs More Info: {result.get('needs_more_info')}")
    print(f"   Response Message: {result.get('response_message')}")
    print(f"   Should Reclassify: {result.get('should_reclassify')}")
    print(f"   Confirmed Category: {result.get('confirmed_category')}")
    
    assert result['selected_category'] == 'library_equipment_checkout'
    assert result['needs_more_info'] == False
    assert result['should_reclassify'] == False
    print("\n✅ Test 1 PASSED")


async def test_user_selects_none_of_above():
    """Test handling when user selects 'None of the above'."""
    print("\n" + "="*80)
    print("TEST 2: User Selects 'None of the Above'")
    print("="*80)
    
    clarification_data = create_mock_clarification_data()
    
    # Find "None of the above" choice
    none_choice = None
    for choice in clarification_data['choices']:
        if choice['category'] == 'none_of_above':
            none_choice = choice
            break
    
    print(f"\n📝 Original Question: {clarification_data['original_question']}")
    print(f"\n👤 User selects: {none_choice['label']}")
    
    result = await handle_clarification_choice(
        choice_id=none_choice['id'],
        original_question=clarification_data['original_question'],
        clarification_data=clarification_data
    )
    
    print(f"\n✅ Handler Result:")
    print(f"   Selected Category: {result.get('selected_category')}")
    print(f"   Needs More Info: {result.get('needs_more_info')}")
    print(f"   Response Message: {result.get('response_message')}")
    print(f"   Should Reclassify: {result.get('should_reclassify')}")
    print(f"   Prompt for Details: {result.get('prompt_for_details')}")
    
    assert result['selected_category'] == 'none_of_above'
    assert result['needs_more_info'] == True
    assert result['should_reclassify'] == True
    assert result['prompt_for_details'] == True
    print("\n✅ Test 2 PASSED")


async def test_invalid_choice_id():
    """Test handling when user provides invalid choice ID."""
    print("\n" + "="*80)
    print("TEST 3: Invalid Choice ID")
    print("="*80)
    
    clarification_data = create_mock_clarification_data()
    
    print(f"\n📝 Original Question: {clarification_data['original_question']}")
    print(f"\n❌ User provides invalid choice ID: 'invalid_choice_999'")
    
    result = await handle_clarification_choice(
        choice_id='invalid_choice_999',
        original_question=clarification_data['original_question'],
        clarification_data=clarification_data
    )
    
    print(f"\n✅ Handler Result:")
    print(f"   Selected Category: {result.get('selected_category')}")
    print(f"   Needs More Info: {result.get('needs_more_info')}")
    print(f"   Response Message: {result.get('response_message')}")
    
    assert result['selected_category'] is None
    assert result['needs_more_info'] == True
    print("\n✅ Test 3 PASSED")


async def test_choice_data_structure():
    """Test the structure of clarification data."""
    print("\n" + "="*80)
    print("TEST 4: Clarification Data Structure")
    print("="*80)
    
    clarification_data = create_mock_clarification_data()
    
    print(f"\n📋 Validating data structure...")
    
    # Validate required fields
    assert 'prompt' in clarification_data
    assert 'choices' in clarification_data
    assert 'original_question' in clarification_data
    print("   ✅ Required top-level fields present")
    
    # Validate choices
    assert len(clarification_data['choices']) >= 2  # At least 1 choice + "None of the above"
    print(f"   ✅ Has {len(clarification_data['choices'])} choices")
    
    # Validate each choice structure
    for choice in clarification_data['choices']:
        assert 'id' in choice
        assert 'label' in choice
        assert 'description' in choice
        assert 'category' in choice
        assert 'examples' in choice
    print("   ✅ All choices have required fields")
    
    # Validate "None of the above" exists
    has_none_option = any(c['category'] == 'none_of_above' for c in clarification_data['choices'])
    assert has_none_option
    print("   ✅ 'None of the above' option present")
    
    print("\n✅ Test 4 PASSED")


async def test_multiple_choice_selections():
    """Test selecting different choices."""
    print("\n" + "="*80)
    print("TEST 5: Multiple Choice Selections")
    print("="*80)
    
    clarification_data = create_mock_clarification_data()
    
    # Test each non-"None" choice
    for i, choice in enumerate(clarification_data['choices'][:-1], 1):  # Exclude "None of the above"
        print(f"\n{'─'*80}")
        print(f"Test {i}: Selecting '{choice['label']}'")
        
        result = await handle_clarification_choice(
            choice_id=choice['id'],
            original_question=clarification_data['original_question'],
            clarification_data=clarification_data
        )
        
        print(f"   Selected Category: {result['selected_category']}")
        print(f"   Needs More Info: {result['needs_more_info']}")
        
        assert result['selected_category'] == choice['category']
        assert result['needs_more_info'] == False
        print(f"   ✅ Choice {i} handled correctly")
    
    print("\n✅ Test 5 PASSED")


async def main():
    """Run all mock tests."""
    print("\n" + "="*80)
    print("CLARIFICATION CHOICES SYSTEM - MOCK TESTS")
    print("="*80)
    print("\nThese tests validate the clarification choice handling logic")
    print("without requiring a Weaviate connection.\n")
    
    try:
        await test_user_selects_specific_choice()
        await test_user_selects_none_of_above()
        await test_invalid_choice_id()
        await test_choice_data_structure()
        await test_multiple_choice_selections()
        
        print("\n" + "="*80)
        print("✅ ALL MOCK TESTS PASSED")
        print("="*80)
        print("\n📝 Next Steps:")
        print("   1. Start Weaviate: docker-compose up -d")
        print("   2. Run full tests: python3 scripts/test_clarification_choices.py")
        print("   3. Integrate with frontend ChatBotComponent")
        print("   4. Test end-to-end flow with real user interactions")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
