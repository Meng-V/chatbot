"""Comprehensive tests for all library agents."""
import pytest
import asyncio
from src.agents.primo_agent import primo_search
from src.agents.libcal_agent import libcal_query
from src.agents.libguide_agent import libguide_query
from src.agents.google_site_agent import google_site_search
from src.agents.libchat_agent import libchat_handoff
from src.agents.transcript_rag_agent import transcript_rag_query

@pytest.mark.asyncio
async def test_primo_agent():
    """Test Primo discovery search agent."""
    result = await primo_search("The Great Gatsby")
    assert result is not None
    assert "source" in result
    assert result["source"] == "Primo"
    assert "text" in result
    print(f"\n[Primo Test] {result}")

@pytest.mark.asyncio
async def test_libcal_hours():
    """Test LibCal hours lookup."""
    result = await libcal_query("What time does King Library close today?")
    assert result is not None
    assert result["source"] == "LibCal"
    assert "text" in result
    print(f"\n[LibCal Hours Test] {result}")

@pytest.mark.asyncio
async def test_libcal_rooms():
    """Test LibCal room search."""
    result = await libcal_query("Book a study room")
    assert result is not None
    assert result["source"] == "LibCal"
    assert "text" in result
    print(f"\n[LibCal Rooms Test] {result}")

@pytest.mark.asyncio
async def test_libguide_agent():
    """Test LibGuide/MyGuide agent."""
    result = await libguide_query("English 111 guide")
    assert result is not None
    assert result["source"] == "LibGuides"
    assert "text" in result
    print(f"\n[LibGuides Test] {result}")

@pytest.mark.asyncio
async def test_google_site_agent():
    """Test Google Site Search."""
    result = await google_site_search("How do I renew a book?")
    assert result is not None
    assert result["source"] == "GoogleSite"
    assert "text" in result
    print(f"\n[GoogleSite Test] {result}")

@pytest.mark.asyncio
async def test_libchat_agent():
    """Test LibChat handoff."""
    result = await libchat_handoff("I want to talk to a person")
    assert result is not None
    assert result["source"] == "LibChat"
    assert result["needs_human"] is True
    assert "text" in result
    print(f"\n[LibChat Test] {result}")

@pytest.mark.asyncio
async def test_transcript_rag_agent():
    """Test Transcript RAG agent."""
    result = await transcript_rag_query("How can I print in the library?")
    assert result is not None
    assert result["source"] == "TranscriptRAG"
    assert "text" in result
    print(f"\n[TranscriptRAG Test] {result}")

@pytest.mark.asyncio
async def test_all_agents_parallel():
    """Test running multiple agents in parallel."""
    queries = [
        ("Do you have The Great Gatsby?", primo_search),
        ("What time does the library close?", libcal_query),
        ("Who's the librarian for biology?", libguide_query),
        ("How do I renew a book?", google_site_search),
        ("I need help", libchat_handoff),
        ("Where can I print?", transcript_rag_query)
    ]
    
    tasks = [func(query) for query, func in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    assert len(results) == 6
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"\n[Agent {i}] ERROR: {result}")
        else:
            assert "source" in result
            print(f"\n[Agent {i}] {result['source']}: {result.get('success', False)}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
