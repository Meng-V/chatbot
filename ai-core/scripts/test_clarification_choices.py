#!/usr/bin/env python3
"""
Test Clarification Choices System

Tests the new clarification choice system with button-based user selection.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.classification.rag_classifier import classify_with_rag
from src.classification.clarification_handler import handle_clarification_choice, reclassify_with_additional_context


async def test_ambiguous_question():
    """Test a question that should trigger clarification choices."""
    print("\n" + "="*80)
    print("TEST 1: Ambiguous Question - Should Trigger Clarification")
    print("="*80)
    
    # This question could be about equipment checkout OR tech support
    question = "I need help with a computer"
    print(f"\n📝 Question: {question}")
    
    result = await classify_with_rag(question)
    
    print(f"\n✅ Classification Result:")
    print(f"   Category: {result['category']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Needs Clarification: {result.get('needs_clarification', False)}")
    
    if result.get('needs_clarification'):
        clarification = result.get('clarification_choices', {})
        print(f"\n🎯 Clarification Prompt:")
        print(f"   {clarification.get('prompt', 'N/A')}")
        
        print(f"\n📋 Available Choices:")
        for i, choice in enumerate(clarification.get('choices', []), 1):
            print(f"   {i}. [{choice['id']}] {choice['label']}")
            if choice.get('description'):
                print(f"      → {choice['description']}")
        
        return result
    else:
        print("\n⚠️  No clarification needed (unexpected)")
        return result


async def test_user_choice_selection(clarification_result):
    """Test handling user's choice selection."""
    print("\n" + "="*80)
    print("TEST 2: User Selects a Choice")
    print("="*80)
    
    clarification_data = clarification_result.get('clarification_choices', {})
    choices = clarification_data.get('choices', [])
    
    if not choices:
        print("⚠️  No choices available to test")
        return
    
    # Simulate user selecting the first choice
    selected_choice = choices[0]
    print(f"\n👤 User selects: {selected_choice['label']}")
    
    result = await handle_clarification_choice(
        choice_id=selected_choice['id'],
        original_question=clarification_data.get('original_question', ''),
        clarification_data=clarification_data
    )
    
    print(f"\n✅ Handler Result:")
    print(f"   Selected Category: {result.get('selected_category')}")
    print(f"   Needs More Info: {result.get('needs_more_info')}")
    print(f"   Response Message: {result.get('response_message')}")
    print(f"   Should Reclassify: {result.get('should_reclassify')}")
    
    return result


async def test_none_of_above_selection(clarification_result):
    """Test handling 'None of the above' selection."""
    print("\n" + "="*80)
    print("TEST 3: User Selects 'None of the Above'")
    print("="*80)
    
    clarification_data = clarification_result.get('clarification_choices', {})
    choices = clarification_data.get('choices', [])
    
    # Find "None of the above" choice
    none_choice = None
    for choice in choices:
        if choice['category'] == 'none_of_above':
            none_choice = choice
            break
    
    if not none_choice:
        print("⚠️  'None of the above' choice not found")
        return
    
    print(f"\n👤 User selects: {none_choice['label']}")
    
    result = await handle_clarification_choice(
        choice_id=none_choice['id'],
        original_question=clarification_data.get('original_question', ''),
        clarification_data=clarification_data
    )
    
    print(f"\n✅ Handler Result:")
    print(f"   Selected Category: {result.get('selected_category')}")
    print(f"   Needs More Info: {result.get('needs_more_info')}")
    print(f"   Response Message: {result.get('response_message')}")
    print(f"   Should Reclassify: {result.get('should_reclassify')}")
    print(f"   Prompt for Details: {result.get('prompt_for_details')}")


async def test_reclassification_with_context():
    """Test reclassification after user provides more details."""
    print("\n" + "="*80)
    print("TEST 4: Reclassification with Additional Context")
    print("="*80)
    
    original_question = "I need help with a computer"
    additional_details = "I want to borrow a laptop for my class project"
    
    print(f"\n📝 Original Question: {original_question}")
    print(f"💬 Additional Details: {additional_details}")
    
    result = await reclassify_with_additional_context(
        original_question=original_question,
        additional_details=additional_details
    )
    
    print(f"\n✅ Reclassification Result:")
    print(f"   Category: {result['category']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Agent: {result.get('agent', 'N/A')}")
    print(f"   Needs Clarification: {result.get('needs_clarification', False)}")


async def test_multiple_ambiguous_questions():
    """Test multiple questions that should trigger clarification."""
    print("\n" + "="*80)
    print("TEST 5: Multiple Ambiguous Questions")
    print("="*80)
    
    test_questions = [
        "I need a computer",
        "Can you help me with printing?",
        "I have a question about books",
        "Where can I study?",
    ]
    
    for question in test_questions:
        print(f"\n{'─'*80}")
        print(f"📝 Question: {question}")
        
        result = await classify_with_rag(question)
        
        print(f"   Category: {result['category']}")
        print(f"   Confidence: {result['confidence']:.2f}")
        print(f"   Needs Clarification: {result.get('needs_clarification', False)}")
        
        if result.get('needs_clarification'):
            clarification = result.get('clarification_choices', {})
            choices = clarification.get('choices', [])
            print(f"   Choices: {len(choices)} options")
            for choice in choices[:3]:  # Show first 3
                print(f"      • {choice['label']}")


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("CLARIFICATION CHOICES SYSTEM - COMPREHENSIVE TEST")
    print("="*80)
    
    try:
        # Test 1: Get clarification for ambiguous question
        clarification_result = await test_ambiguous_question()
        
        if clarification_result.get('needs_clarification'):
            # Test 2: User selects a specific choice
            await test_user_choice_selection(clarification_result)
            
            # Test 3: User selects "None of the above"
            await test_none_of_above_selection(clarification_result)
        
        # Test 4: Reclassification with context
        await test_reclassification_with_context()
        
        # Test 5: Multiple ambiguous questions
        await test_multiple_ambiguous_questions()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
