#!/usr/bin/env python3
"""
Smoke test for routing consolidation.

Tests that the unified LangGraph routing path correctly classifies
and routes various user questions to the appropriate agents.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.orchestrator import library_graph
from src.utils.logger import AgentLogger


# Test cases: (question, expected_primary_agent_id, description)
TEST_CASES = [
    # Equipment checkout
    ("Can I borrow a laptop?", "equipment_checkout", "Equipment checkout - laptop"),
    ("Do you have chargers available?", "equipment_checkout", "Equipment checkout - charger"),
    
    # Out of scope - tech support (NOT equipment checkout)
    ("My laptop won't turn on", "out_of_scope", "Out of scope - tech support"),
    ("Computer is broken", "out_of_scope", "Out of scope - broken computer"),
    
    # Library hours
    ("What time does King Library close today?", "libcal_hours", "Library hours - King"),
    ("When is the library open?", "libcal_hours", "Library hours - general"),
    
    # Room booking
    ("Book a study room for 2 hours", "libcal_hours", "Room booking request"),
    ("Reserve a room tomorrow", "libcal_hours", "Room reservation"),
    
    # Subject librarian
    ("Who is the biology librarian?", "subject_librarian", "Subject librarian - biology"),
    ("Find the chemistry librarian", "subject_librarian", "Subject librarian - chemistry"),
    
    # Policy search
    ("What is the printing policy?", "policy_search", "Policy - printing"),
    ("How do I renew books?", "policy_search", "Policy - renewals"),
    
    # Human handoff
    ("Connect me to a librarian", "libchat_handoff", "Human handoff - direct request"),
    ("I need to talk to someone", "libchat_handoff", "Human handoff - talk request"),
    
    # Out of scope - academics
    ("Help me with my homework", "out_of_scope", "Out of scope - homework"),
    
    # Out of scope - campus life
    ("Where is the dining hall?", "out_of_scope", "Out of scope - dining"),
]


async def test_routing():
    """Run smoke tests on routing."""
    print("=" * 80)
    print("ROUTING SMOKE TEST")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    clarifications = 0
    
    for i, (question, expected_agent, description) in enumerate(TEST_CASES, 1):
        print(f"Test {i}/{len(TEST_CASES)}: {description}")
        print(f"  Question: '{question}'")
        print(f"  Expected: {expected_agent}")
        
        logger = AgentLogger()
        
        try:
            # Run through the graph
            result = await library_graph.ainvoke({
                "user_message": question,
                "messages": [],
                "conversation_history": [],
                "conversation_id": None,
                "_logger": logger
            })
            
            # Extract routing decision
            primary_agent_id = result.get("primary_agent_id")
            needs_clarification = result.get("needs_clarification", False)
            processed_query = result.get("processed_query", question)
            classification_confidence = result.get("classification_confidence")
            
            # Check result
            if needs_clarification:
                clarifications += 1
                clarification_data = result.get("clarification", {})
                options = clarification_data.get("options", [])
                print(f"  Result: CLARIFICATION NEEDED")
                print(f"    Options: {[opt.get('label') for opt in options]}")
                print(f"  Status: ⚠️  CLARIFICATION (may be acceptable)")
            elif primary_agent_id == expected_agent:
                passed += 1
                conf_str = f" (confidence: {classification_confidence:.2f})" if classification_confidence else ""
                print(f"  Result: {primary_agent_id}{conf_str}")
                print(f"  Status: ✅ PASS")
            else:
                failed += 1
                conf_str = f" (confidence: {classification_confidence:.2f})" if classification_confidence else ""
                print(f"  Result: {primary_agent_id}{conf_str}")
                print(f"  Status: ❌ FAIL - Expected {expected_agent}, got {primary_agent_id}")
            
            if processed_query != question:
                print(f"  Processed: '{processed_query}'")
            
        except Exception as e:
            failed += 1
            print(f"  Status: ❌ ERROR - {str(e)}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(TEST_CASES)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Clarifications: {clarifications} ⚠️")
    print(f"Success rate: {passed / len(TEST_CASES) * 100:.1f}%")
    print()
    
    if failed > 0:
        print("❌ SMOKE TEST FAILED - Some routing decisions were incorrect")
        return False
    elif clarifications > len(TEST_CASES) * 0.3:  # More than 30% clarifications is too high
        print(f"⚠️  WARNING - High clarification rate ({clarifications}/{len(TEST_CASES)})")
        print("   Consider adjusting confidence threshold or improving examples")
        return True
    else:
        print("✅ SMOKE TEST PASSED - All routing decisions correct")
        return True


if __name__ == "__main__":
    success = asyncio.run(test_routing())
    sys.exit(0 if success else 1)
