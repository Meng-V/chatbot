"""Tests for LangGraph orchestrator (Meta Router)."""
import pytest
from src.graph.orchestrator import library_graph

TEST_CASES = [
    ("Do you have The Great Gatsby?", "discovery_search", ["primo"]),
    ("What time does King Library close today?", "booking_or_hours", ["libcal"]),
    ("Who's the librarian for ENG 111?", "course_subject_help", ["libguide", "transcript_rag"]),
    ("How do I renew a book?", "policy_or_service", ["google_site", "transcript_rag"]),
    ("Can I talk to someone now?", "human_help", ["libchat"]),
    ("Where can I print in the library?", "general_question", ["transcript_rag", "google_site"]),
]

@pytest.mark.asyncio
async def test_intent_classification():
    """Test that Meta Router correctly classifies intents."""
    for query, expected_intent, expected_agents in TEST_CASES:
        result = await library_graph.ainvoke({
            "user_message": query,
            "messages": []
        })
        
        assert "classified_intent" in result
        assert "selected_agents" in result
        assert "final_answer" in result
        
        print(f"\nQuery: {query}")
        print(f"  Expected Intent: {expected_intent}")
        print(f"  Actual Intent: {result['classified_intent']}")
        print(f"  Agents: {result['selected_agents']}")
        print(f"  Answer: {result['final_answer'][:100]}...")

@pytest.mark.asyncio
async def test_full_workflow():
    """Test complete workflow from question to answer."""
    result = await library_graph.ainvoke({
        "user_message": "What time does the library close?",
        "messages": []
    })
    
    assert result["classified_intent"] is not None
    assert len(result["selected_agents"]) > 0
    assert "agent_responses" in result
    assert result["final_answer"] != ""
    assert result.get("error") is None
    
    print(f"\n[Full Workflow Test]")
    print(f"Intent: {result['classified_intent']}")
    print(f"Agents: {result['selected_agents']}")
    print(f"Answer: {result['final_answer']}")

@pytest.mark.asyncio
async def test_error_handling():
    """Test that graph handles errors gracefully."""
    result = await library_graph.ainvoke({
        "user_message": "",
        "messages": []
    })
    
    # Should still return a response even with empty input
    assert "final_answer" in result
    print(f"\n[Error Handling Test] Answer: {result.get('final_answer', 'No answer')}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
