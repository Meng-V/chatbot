"""Comprehensive tests for all new tools."""
import pytest
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent

# LibCal Comprehensive Agent Tests

@pytest.mark.asyncio
async def test_libcal_agent_hours_routing():
    """Test LibCal agent routes to week hours tool."""
    agent = LibCalComprehensiveAgent()
    
    query = "What are the library hours this week?"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_week_hours"
    print(f"\n✅ Hours query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_room_search_routing():
    """Test LibCal agent routes to enhanced availability tool."""
    agent = LibCalComprehensiveAgent()
    
    query = "Are there any study rooms available?"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_enhanced_availability"
    print(f"\n✅ Room search query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_booking_routing():
    """Test LibCal agent routes to comprehensive reservation tool."""
    agent = LibCalComprehensiveAgent()
    
    query = "I want to book a study room for 3pm"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_comprehensive_reservation"
    print(f"\n✅ Booking query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_cancel_routing():
    """Test LibCal agent routes to cancel reservation tool."""
    agent = LibCalComprehensiveAgent()
    
    query = "Cancel my reservation 12345"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_cancel_reservation"
    print(f"\n✅ Cancel query → {tool_name}")

# LibGuide Comprehensive Agent Tests

@pytest.mark.asyncio
async def test_libguide_agent_subject_routing():
    """Test LibGuide agent routes to subject lookup."""
    agent = LibGuideComprehensiveAgent()
    
    query = "Who is the librarian for biology?"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libguide_subject_lookup"
    print(f"\n✅ Subject query → {tool_name}")

@pytest.mark.asyncio
async def test_libguide_agent_course_routing():
    """Test LibGuide agent routes to course lookup."""
    agent = LibGuideComprehensiveAgent()
    
    query = "I need help with ENG 111"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libguide_course_lookup"
    print(f"\n✅ Course query → {tool_name}")

@pytest.mark.asyncio
async def test_libguide_agent_course_code_routing():
    """Test LibGuide agent detects course codes."""
    agent = LibGuideComprehensiveAgent()
    
    queries = [
        ("BIO 201 databases", "libguide_course_lookup"),
        ("FIN 301 resources", "libguide_course_lookup"),
        ("PSY 111 help", "libguide_course_lookup")
    ]
    
    for query, expected_tool in queries:
        tool_name = await agent.route_to_tool(query)
        assert tool_name == expected_tool
        print(f"\n✅ '{query}' → {tool_name}")

# Google Site Comprehensive Agent Tests

@pytest.mark.asyncio
async def test_google_site_agent_citation_routing():
    """Test Google Site agent routes to citation tool."""
    agent = GoogleSiteComprehensiveAgent()
    
    queries = [
        "How do I cite in APA?",
        "MLA citation format",
        "Chicago style guide"
    ]
    
    for query in queries:
        tool_name = await agent.route_to_tool(query)
        assert tool_name == "citation_assist"
        print(f"\n✅ '{query}' → {tool_name}")

@pytest.mark.asyncio
async def test_google_site_agent_borrowing_routing():
    """Test Google Site agent routes to borrowing policy tool."""
    agent = GoogleSiteComprehensiveAgent()
    
    queries = [
        "How do I renew a book?",
        "What are the loan periods?",
        "Interlibrary loan policy"
    ]
    
    for query in queries:
        tool_name = await agent.route_to_tool(query)
        assert tool_name == "borrowing_policy_search"
        print(f"\n✅ '{query}' → {tool_name}")

@pytest.mark.asyncio
async def test_google_site_agent_general_routing():
    """Test Google Site agent routes to general search."""
    agent = GoogleSiteComprehensiveAgent()
    
    query = "How do I print in the library?"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "google_site_enhanced_search"
    print(f"\n✅ General query → {tool_name}")

# Agent Tool Listing Tests

@pytest.mark.asyncio
async def test_agent_tool_counts():
    """Test agents have correct number of tools."""
    libcal_agent = LibCalComprehensiveAgent()
    libguide_agent = LibGuideComprehensiveAgent()
    google_agent = GoogleSiteComprehensiveAgent()
    
    libcal_tools = libcal_agent.list_tools()
    libguide_tools = libguide_agent.list_tools()
    google_tools = google_agent.list_tools()
    
    assert len(libcal_tools) == 4, f"LibCal should have 4 tools, has {len(libcal_tools)}"
    assert len(libguide_tools) == 2, f"LibGuide should have 2 tools, has {len(libguide_tools)}"
    assert len(google_tools) == 3, f"Google should have 3 tools, has {len(google_tools)}"
    
    print(f"\n✅ LibCal tools ({len(libcal_tools)}): {libcal_tools}")
    print(f"✅ LibGuide tools ({len(libguide_tools)}): {libguide_tools}")
    print(f"✅ Google tools ({len(google_tools)}): {google_tools}")

# Multi-Query Tests

@pytest.mark.asyncio
async def test_libcal_multi_query_routing():
    """Test LibCal agent handles various query types."""
    agent = LibCalComprehensiveAgent()
    
    test_cases = [
        ("Library hours today", "libcal_week_hours"),
        ("Find a room for 4 people", "libcal_enhanced_availability"),
        ("Reserve room 145 for tomorrow", "libcal_comprehensive_reservation"),
        ("Cancel booking 123", "libcal_cancel_reservation")
    ]
    
    for query, expected_tool in test_cases:
        tool_name = await agent.route_to_tool(query)
        assert tool_name == expected_tool
        print(f"\n✅ '{query}' → {tool_name}")

# Fuzzy Matching Tests (for LibGuide)

@pytest.mark.asyncio
async def test_libguide_fuzzy_matching():
    """Test fuzzy matching for subject synonyms."""
    from src.tools.libguide_comprehensive_tools import _levenshtein_distance, _fuzzy_best_match
    
    # Test Levenshtein distance
    assert _levenshtein_distance("biology", "biology") == 0
    assert _levenshtein_distance("bio", "biology") > 0
    
    # Test fuzzy matching with synonyms
    synonym_mapping = {
        "bio": "Biology",
        "psych": "Psychology",
        "cs": "Computer Science"
    }
    
    choices = ["Biology", "Psychology", "Computer Science", "Mathematics"]
    
    # Should find Biology for "bio"
    matches = _fuzzy_best_match("bio", choices, synonym_mapping)
    assert len(matches) > 0
    assert matches[0][1] == "Biology"
    
    print(f"\n✅ Fuzzy match 'bio' → {matches[0][1]} (score: {matches[0][0]:.2f})")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
