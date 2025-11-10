"""Tests for multi-tool agent architecture."""
import pytest
from src.agents.libcal_multi_tool_agent import LibCalAgent
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.google_site_multi_tool_agent import GoogleSiteAgent

@pytest.mark.asyncio
async def test_libcal_agent_hours_routing():
    """Test LibCal agent routes to hours tool."""
    agent = LibCalAgent()
    
    # Test hours query
    query = "What time does King Library close today?"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_hours"
    print(f"\n✅ Hours query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_room_search_routing():
    """Test LibCal agent routes to room search tool."""
    agent = LibCalAgent()
    
    # Test room search query
    query = "Find me a study room"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_room_search"
    print(f"\n✅ Room search query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_reservation_routing():
    """Test LibCal agent routes to reservation tool."""
    agent = LibCalAgent()
    
    # Test reservation query
    query = "I want to book a study room for 3pm"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "libcal_reservation"
    print(f"\n✅ Reservation query → {tool_name}")

@pytest.mark.asyncio
async def test_libcal_agent_execution():
    """Test LibCal agent executes the correct tool."""
    agent = LibCalAgent()
    
    # Test full execution
    query = "What time is the library open?"
    result = await agent.execute(query)
    
    assert result["agent"] == "LibCal"
    assert "tool" in result
    print(f"\n✅ LibCal agent executed: {result['tool']}")

@pytest.mark.asyncio
async def test_primo_agent_search_routing():
    """Test Primo agent routes to search tool."""
    agent = PrimoAgent()
    
    query = "Find books about climate change"
    tool_name = await agent.route_to_tool(query)
    
    assert tool_name == "primo_search"
    print(f"\n✅ Search query → {tool_name}")

@pytest.mark.asyncio
async def test_agent_tool_listing():
    """Test agents can list their tools."""
    libcal_agent = LibCalAgent()
    primo_agent = PrimoAgent()
    
    libcal_tools = libcal_agent.list_tools()
    primo_tools = primo_agent.list_tools()
    
    assert "libcal_hours" in libcal_tools
    assert "libcal_room_search" in libcal_tools
    assert "libcal_reservation" in libcal_tools
    
    assert "primo_search" in primo_tools
    assert "primo_availability" in primo_tools
    
    print(f"\n✅ LibCal tools: {libcal_tools}")
    print(f"✅ Primo tools: {primo_tools}")

@pytest.mark.asyncio
async def test_multiple_queries_same_agent():
    """Test one agent handling different query types."""
    agent = LibCalAgent()
    
    queries = [
        ("What time does library close?", "libcal_hours"),
        ("Find a study room", "libcal_room_search"),
        ("Book a room for tomorrow", "libcal_reservation")
    ]
    
    for query, expected_tool in queries:
        tool_name = await agent.route_to_tool(query)
        assert tool_name == expected_tool
        print(f"\n✅ '{query}' → {tool_name}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
