"""OpenAI function calling mode (alternative to LangGraph orchestration)."""
import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

# Import all tools
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
from src.agents.libchat_agent import libchat_handoff
from src.agents.transcript_rag_agent import transcript_rag_query

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# o4-mini doesn't support temperature parameter
llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
if not OPENAI_MODEL.startswith("o"):
    llm_kwargs["temperature"] = 0

# Initialize agents
primo_agent = PrimoAgent()
libcal_agent = LibCalComprehensiveAgent()
libguide_agent = LibGuideComprehensiveAgent()
google_site_agent = GoogleSiteComprehensiveAgent()

# Define tool schemas for OpenAI function calling
class SearchCatalogInput(BaseModel):
    query: str = Field(description="Search query for books, articles, journals")

class GetLibraryHoursInput(BaseModel):
    building: str = Field(default="king", description="Building name: king, art, armstrong, rentschler, gardner-harvey")

class SearchRoomsInput(BaseModel):
    date: str = Field(description="Date in YYYY-MM-DD format")
    start_time: str = Field(description="Start time in HH:MM format (24-hour)")
    end_time: str = Field(description="End time in HH:MM format (24-hour)")
    capacity: int = Field(default=1, description="Minimum room capacity (number of people)")
    building: str = Field(default="king", description="Building name")

class SearchWebsiteInput(BaseModel):
    query: str = Field(description="Search query for library website")

class FindSubjectGuideInput(BaseModel):
    subject: str = Field(description="Academic subject or major (e.g., biology, english, business)")

class FindCourseGuideInput(BaseModel):
    course_code: str = Field(description="Course code (e.g., ENG 111, BIO 201)")

class ConnectLibrarianInput(BaseModel):
    message: str = Field(default="User needs help", description="Reason for connecting to librarian")

async def search_catalog_wrapper(query: str) -> str:
    """Search library catalog for books and articles."""
    try:
        result = await primo_agent.execute(query)
        return result.get("text", "No results found")
    except Exception as e:
        return f"Error searching catalog: {str(e)}"

async def get_library_hours_wrapper(building: str = "king") -> str:
    """Get library hours for a building."""
    try:
        result = await libcal_agent.execute(f"hours for {building}")
        return result.get("text", "Hours not available")
    except Exception as e:
        return f"Error getting hours: {str(e)}"

async def search_rooms_wrapper(date: str, start_time: str, end_time: str, capacity: int = 1, building: str = "king") -> str:
    """Search for available study rooms."""
    try:
        query = f"room on {date} from {start_time} to {end_time} for {capacity} people at {building}"
        result = await libcal_agent.execute(query)
        return result.get("text", "No rooms available")
    except Exception as e:
        return f"Error searching rooms: {str(e)}"

async def search_website_wrapper(query: str) -> str:
    """Search library website for policies and information."""
    try:
        result = await google_site_agent.execute(query)
        return result.get("text", "No information found")
    except Exception as e:
        return f"Error searching website: {str(e)}"

async def find_subject_guide_wrapper(subject: str) -> str:
    """Find research guide for an academic subject."""
    try:
        # Pass subject_name parameter to the tool
        result = await libguide_agent.execute(subject, subject_name=subject)
        return result.get("text", "No guide found")
    except Exception as e:
        return f"Error finding subject guide: {str(e)}"

async def find_course_guide_wrapper(course_code: str) -> str:
    """Find research guide for a course."""
    try:
        # Pass course_code parameter to the tool
        result = await libguide_agent.execute(course_code, course_code=course_code)
        return result.get("text", "No guide found")
    except Exception as e:
        return f"Error finding course guide: {str(e)}"

async def connect_librarian_wrapper(message: str = "User needs help") -> str:
    """Connect user with a human librarian."""
    try:
        result = await libchat_handoff(message)
        return result.get("text", "Visit libanswers.lib.miamioh.edu/chat/widget")
    except Exception as e:
        return f"Error connecting to librarian: {str(e)}"

# Create LangChain tools
tools = [
    StructuredTool.from_function(
        func=search_catalog_wrapper,
        name="search_catalog",
        description="Search library catalog for books, articles, journals, e-resources. Use this when users ask about finding materials or checking availability.",
        args_schema=SearchCatalogInput,
        coroutine=search_catalog_wrapper
    ),
    StructuredTool.from_function(
        func=get_library_hours_wrapper,
        name="get_library_hours",
        description="Get library building hours. Use for questions about opening/closing times or schedules.",
        args_schema=GetLibraryHoursInput,
        coroutine=get_library_hours_wrapper
    ),
    StructuredTool.from_function(
        func=search_rooms_wrapper,
        name="search_rooms",
        description="Search for available study rooms. Requires date, time range, and optionally capacity and building.",
        args_schema=SearchRoomsInput,
        coroutine=search_rooms_wrapper
    ),
    StructuredTool.from_function(
        func=search_website_wrapper,
        name="search_website",
        description="Search library website for policies, services, how-to guides. Use for questions about borrowing, renewals, printing, access, etc.",
        args_schema=SearchWebsiteInput,
        coroutine=search_website_wrapper
    ),
    StructuredTool.from_function(
        func=find_subject_guide_wrapper,
        name="find_subject_guide",
        description="Find research guide for an academic subject or major.",
        args_schema=FindSubjectGuideInput,
        coroutine=find_subject_guide_wrapper
    ),
    StructuredTool.from_function(
        func=find_course_guide_wrapper,
        name="find_course_guide",
        description="Find research guide for a specific course code.",
        args_schema=FindCourseGuideInput,
        coroutine=find_course_guide_wrapper
    ),
    StructuredTool.from_function(
        func=connect_librarian_wrapper,
        name="connect_librarian",
        description="Connect user with a human librarian for complex questions or personalized help.",
        args_schema=ConnectLibrarianInput,
        coroutine=connect_librarian_wrapper
    )
]

# Create LLM with tools bound
llm = ChatOpenAI(**llm_kwargs)
llm_with_tools = llm.bind_tools(tools)

async def handle_with_function_calling(user_message: str, logger=None) -> Dict[str, Any]:
    """
    Handle user message using OpenAI function calling (alternative to LangGraph).
    This matches the NestJS approach more closely.
    """
    if logger:
        logger.log("🔧 [Function Calling] Using direct OpenAI function calling mode")
    
    system_message = """You are a helpful Miami University Libraries assistant.
You have access to several tools to help users. Use the appropriate tool based on the user's question.

FORMATTING GUIDELINES:
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks between sections
- Use inline bullet points (•) for short lists (2-3 items)
- Highlight actionable links and important details
- Keep paragraphs concise (2-3 sentences max)
- Use natural, conversational language
- Make responses easy to scan quickly

Always provide clear, helpful responses and cite sources when relevant."""
    
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=user_message)
    ]
    
    try:
        # First LLM call - decide which tool to use
        response = await llm_with_tools.ainvoke(messages)
        
        # Check if tool was called
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            if logger:
                logger.log(f"🔨 [Function Calling] Tool selected: {tool_name}", tool_args)
            
            # Execute tool
            tool_map = {t.name: t for t in tools}
            if tool_name in tool_map:
                tool = tool_map[tool_name]
                tool_result = await tool.ainvoke(tool_args)
                
                if logger:
                    logger.log(f"✅ [Function Calling] Tool executed successfully")
                
                # Second LLM call - synthesize final answer
                # Properly format the tool response for OpenAI API
                messages.append(response)
                messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call["id"]
                ))
                
                final_response = await llm.ainvoke(messages)
                
                return {
                    "success": True,
                    "final_answer": final_response.content,
                    "tool_used": tool_name,
                    "tool_args": tool_args,
                    "mode": "function_calling"
                }
        else:
            # No tool needed, direct answer
            if logger:
                logger.log("💬 [Function Calling] No tool needed, direct answer")
            
            return {
                "success": True,
                "final_answer": response.content,
                "mode": "function_calling"
            }
    
    except Exception as e:
        if logger:
            logger.log(f"❌ [Function Calling] Error: {str(e)}")
        
        return {
            "success": False,
            "final_answer": "I encountered an error. Please try again or contact a librarian.",
            "error": str(e),
            "mode": "function_calling"
        }
