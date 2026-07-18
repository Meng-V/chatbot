#!/usr/bin/env python3
"""Direct test of GoogleSiteComprehensiveAgent to debug tool invocation."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent

async def test_agent():
    """Test agent directly."""
    print("=" * 80)
    print("DIRECT AGENT TEST")
    print("=" * 80)
    
    # Create agent instance
    print("\n1. Creating GoogleSiteComprehensiveAgent instance...")
    agent = GoogleSiteComprehensiveAgent()
    
    # List tools
    print(f"\n2. Agent name: {agent.name}")
    print(f"   Registered tools: {agent.list_tools()}")
    
    # Test query
    query = "What is the library borrowing policy?"
    print(f"\n3. Testing query: '{query}'")
    
    # Call route_to_tool
    print(f"\n4. Calling route_to_tool()...")
    tool_name = await agent.route_to_tool(query)
    print(f"   → Selected tool: {tool_name}")
    
    # Execute agent
    print(f"\n5. Executing agent.execute()...")
    
    def log_callback(msg):
        print(f"   [LOG] {msg}")
    
    result = await agent.execute(query, log_callback=log_callback)
    
    print(f"\n6. Result:")
    print(f"   Agent: {result.get('agent')}")
    print(f"   Tool: {result.get('tool')}")
    print(f"   Success: {result.get('success')}")
    if result.get('error'):
        print(f"   Error: {result.get('error')}")
    if result.get('text'):
        print(f"   Text (first 200 chars): {result.get('text')[:200]}...")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_agent())
