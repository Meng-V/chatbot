"""Test all agents and tools to ensure they work correctly."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Now import after env is loaded
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
from src.agents.libchat_agent import libchat_handoff
from src.graph.function_calling import handle_with_function_calling
from src.utils.logger import AgentLogger

async def test_primo():
    """Test Primo catalog search."""
    print("\n" + "="*60)
    print("TESTING PRIMO AGENT")
    print("="*60)
    
    agent = PrimoAgent()
    logger = AgentLogger()
    
    try:
        result = await agent.execute("Python programming books", log_callback=logger.log)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('text', 'No text')[:200]}...")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def test_libcal_hours():
    """Test LibCal hours lookup."""
    print("\n" + "="*60)
    print("TESTING LIBCAL AGENT - HOURS")
    print("="*60)
    
    agent = LibCalComprehensiveAgent()
    logger = AgentLogger()
    
    try:
        result = await agent.execute("What are King Library hours?", log_callback=logger.log)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('text', 'No text')[:200]}...")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def test_libguide():
    """Test LibGuide subject lookup."""
    print("\n" + "="*60)
    print("TESTING LIBGUIDE AGENT")
    print("="*60)
    
    agent = LibGuideComprehensiveAgent()
    logger = AgentLogger()
    
    try:
        result = await agent.execute("biology research", subject_name="biology", log_callback=logger.log)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('text', 'No text')[:200]}...")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def test_google_site():
    """Test Google Site search."""
    print("\n" + "="*60)
    print("TESTING GOOGLE SITE AGENT")
    print("="*60)
    
    agent = GoogleSiteComprehensiveAgent()
    logger = AgentLogger()
    
    try:
        result = await agent.execute("How to renew books", log_callback=logger.log)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('text', 'No text')[:200]}...")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def test_libchat():
    """Test LibChat handoff."""
    print("\n" + "="*60)
    print("TESTING LIBCHAT AGENT")
    print("="*60)
    
    logger = AgentLogger()
    
    try:
        result = await libchat_handoff("User needs help", log_callback=logger.log)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('text', 'No text')[:200]}...")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def test_function_calling():
    """Test function calling mode."""
    print("\n" + "="*60)
    print("TESTING FUNCTION CALLING MODE")
    print("="*60)
    
    logger = AgentLogger()
    
    try:
        result = await handle_with_function_calling("Who is the librarian for biology?", logger)
        print(f"\n✅ Status: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"📝 Response: {result.get('final_answer', 'No answer')[:200]}...")
        print(f"🔧 Tool used: {result.get('tool_used', 'None')}")
        return result.get('success', False)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False

async def run_all_tests():
    """Run all tests."""
    print("\n" + "🧪 "*20)
    print("STARTING COMPREHENSIVE AGENT TESTS")
    print("🧪 "*20)
    
    results = {
        "Primo Agent": await test_primo(),
        "LibCal Agent (Hours)": await test_libcal_hours(),
        "LibGuide Agent": await test_libguide(),
        "Google Site Agent": await test_google_site(),
        "LibChat Agent": await test_libchat(),
        "Function Calling": await test_function_calling(),
    }
    
    print("\n" + "="*60)
    print("FINAL TEST RESULTS")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\n{'='*60}")
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print(f"{'='*60}\n")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
