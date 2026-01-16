"""OpenAI function calling mode (alternative to LangGraph orchestration)."""
import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# Import all tools
from src.agents.primo_multi_tool_agent import PrimoAgent
from src.agents.libcal_comprehensive_agent import LibCalComprehensiveAgent
from src.agents.libguide_comprehensive_agent import LibGuideComprehensiveAgent
from src.agents.google_site_comprehensive_agent import GoogleSiteComprehensiveAgent
from src.agents.libchat_agent import libchat_handoff
from src.agents.transcript_rag_agent import transcript_rag_query
from src.agents.subject_librarian_agent import find_subject_librarian_query
from src.agents.enhanced_subject_librarian_agent import EnhancedSubjectLibrarianAgent
from src.tools.url_validator import validate_and_clean_response

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
    building: str = Field(default="king", description="Building name: king, art, rentschler, gardner-harvey")

class SearchRoomsInput(BaseModel):
    date: str = Field(description="Date in flexible format: 11/12/2025, tomorrow, next Monday, YYYY-MM-DD all work")
    start_time: str = Field(description="Start time in flexible format: 8pm, 8:00 PM, 20:00, 8:00pm all work")
    end_time: str = Field(description="End time in flexible format: 10pm, 10:00 PM, 22:00, 10:00pm all work")
    capacity: int = Field(default=1, description="Minimum room capacity (number of people)")
    building: str = Field(default="king", description="Building name")

class BookRoomInput(BaseModel):
    first_name: str = Field(description="User's first name")
    last_name: str = Field(description="User's last name")
    email: str = Field(description="User's @miamioh.edu email address")
    date: str = Field(description="Date in flexible format: 11/12/2025, tomorrow, next Monday, YYYY-MM-DD all work")
    start_time: str = Field(description="Start time in flexible format: 8pm, 8:00 PM, 20:00, 8:00pm all work")
    end_time: str = Field(description="End time in flexible format: 10pm, 10:00 PM, 22:00, 10:00pm all work")
    capacity: int = Field(default=1, description="Number of people")
    building: str = Field(default="king", description="Building name: king, art, rentschler, gardner-harvey")

class SearchWebsiteInput(BaseModel):
    query: str = Field(description="Search query for library website")

class FindSubjectGuideInput(BaseModel):
    subject: str = Field(description="Academic subject or major (e.g., biology, english, business)")

class FindCourseGuideInput(BaseModel):
    course_code: str = Field(description="Course code (e.g., ENG 111, BIO 201)")

class FindSubjectLibrarianInput(BaseModel):
    subject: str = Field(description="Academic subject, major, or department (e.g., business, chemistry, computer science, biology)")

class ConnectLibrarianInput(BaseModel):
    message: str = Field(default="User needs help", description="Reason for connecting to librarian")

class CancelReservationInput(BaseModel):
    booking_id: str = Field(description="Confirmation number / booking ID from the reservation email")
    email: str = Field(description="User's @miamioh.edu email address used for the booking")

async def search_catalog_wrapper(query: str) -> str:
    """Catalog search is NOT available - redirect to human librarian."""
    # CRITICAL: Do NOT provide book/article titles, authors, or any catalog information
    # User MUST search themselves or contact a librarian
    return """I'd love to help you find those materials! However, our catalog search feature is currently unavailable.

**To search for books, articles, and e-resources, please:**

• **Search the library catalog yourself**: https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU&lang=en&mode=basic

• **Chat with a librarian for personalized help**: https://www.lib.miamioh.edu/research/research-support/ask/

A librarian can help you find the best resources for your research needs."""

async def get_library_hours_wrapper(building: str = "king") -> str:
    """Get library hours for a building."""
    try:
        result = await libcal_agent.execute(f"hours for {building}")
        return result.get("text", "Hours not available")
    except Exception as e:
        return f"Error getting hours: {str(e)}"

# Valid libraries with study rooms (from database)
VALID_ROOM_LIBRARIES = {
    "king": "King Library",
    "art": "Art & Architecture Library",
    "rentschler": "Rentschler Library (Hamilton)",
    "hamilton": "Rentschler Library (Hamilton)",
    "gardner-harvey": "Gardner-Harvey Library (Middletown)",
    "middletown": "Gardner-Harvey Library (Middletown)",
}

def _validate_library_name(building: str) -> tuple[bool, str]:
    """Validate library name for room booking.
    
    Returns:
        Tuple of (is_valid, error_message_or_normalized_name)
    """
    building_lower = building.lower().strip()
    
    if building_lower in VALID_ROOM_LIBRARIES:
        return True, building_lower
    
    # Check for partial matches
    for key in VALID_ROOM_LIBRARIES:
        if key in building_lower or building_lower in key:
            return True, key
    
    # Invalid library - return error with valid options
    valid_options = "\n".join([f"• {name}" for name in set(VALID_ROOM_LIBRARIES.values())])
    return False, f"'{building}' is not a valid library for room reservations. Study rooms are available at:\n{valid_options}\n\nPlease specify one of these libraries."

async def search_rooms_wrapper(date: str, start_time: str, end_time: str, capacity: int = 1, building: str = "king") -> str:
    """Search for available study rooms."""
    try:
        # Validate library name
        is_valid, result = _validate_library_name(building)
        if not is_valid:
            return result
        building = result
        
        query = f"room on {date} from {start_time} to {end_time} for {capacity} people at {building}"
        result = await libcal_agent.execute(query)
        return result.get("text", "No rooms available")
    except Exception as e:
        return f"Error searching rooms: {str(e)}"

async def book_room_wrapper(first_name: str, last_name: str, email: str, date: str, start_time: str, end_time: str, capacity: int = 1, building: str = "king") -> str:
    """Book a study room with full user information and email validation."""
    try:
        # Validate library name first
        is_valid, result = _validate_library_name(building)
        if not is_valid:
            return result
        building = result
        
        # Validate email
        if not email.lower().endswith("@miamioh.edu"):
            return "Error: Email must be a valid @miamioh.edu address. Please provide your Miami University email to complete the booking."
        
        # Use LibCal comprehensive reservation tool
        from src.tools.libcal_comprehensive_tools import LibCalComprehensiveReservationTool
        booking_tool = LibCalComprehensiveReservationTool()
        
        result = await booking_tool.execute(
            query=f"book room for {first_name} {last_name}",
            first_name=first_name,
            last_name=last_name,
            email=email,
            date=date,
            start_time=start_time,
            end_time=end_time,
            room_capacity=capacity,
            building=building
        )
        
        return result.get("text", "Booking failed. Please try again or visit https://lib.miamioh.edu/use/spaces/room-reservations/")
    except Exception as e:
        return f"Error booking room: {str(e)}"

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

async def find_subject_librarian_wrapper(subject: str) -> str:
    """Find subject librarian and LibGuide for an academic subject or major."""
    try:
        enhanced_agent = EnhancedSubjectLibrarianAgent()
        result = await enhanced_agent.execute(subject)
        return result.get("text", "No subject librarian found") if result else "No subject librarian found"
    except Exception as e:
        return f"Error finding subject librarian: {str(e)}"

async def connect_librarian_wrapper(message: str = "User needs help") -> str:
    """Connect user with a human librarian."""
    try:
        result = await libchat_handoff(message)
        return result.get("text", "Visit https://www.lib.miamioh.edu/research/research-support/ask/ for help")
    except Exception as e:
        return f"Error connecting to librarian: {str(e)}"

async def cancel_reservation_wrapper(booking_id: str, email: str) -> str:
    """Cancel a room reservation with email verification."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"🔍 [Cancel Wrapper] Starting cancellation for booking_id={booking_id}, email={email}")
        
        # Validate email
        if not email.lower().endswith("@miamioh.edu"):
            logger.warning(f"❌ [Cancel Wrapper] Invalid email format: {email}")
            return "Error: Email must be a valid @miamioh.edu address."
        
        # Use LibCal cancel reservation tool
        from src.tools.libcal_comprehensive_tools import LibCalCancelReservationTool
        cancel_tool = LibCalCancelReservationTool()
        
        result = await cancel_tool.execute(
            query=f"cancel booking {booking_id}",
            booking_id=booking_id,
            email=email,
            log_callback=logger.info
        )
        
        logger.info(f"📊 [Cancel Wrapper] Tool result: success={result.get('success')}, text={result.get('text')[:100]}")
        
        return result.get("text", "Cancellation failed. Please visit https://www.lib.miamioh.edu/use/spaces/room-reservations/ or contact the library.")
    except Exception as e:
        logger.error(f"❌ [Cancel Wrapper] Exception: {str(e)}")
        return f"Error canceling reservation: {str(e)}"

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
        description="Search for available study rooms at a specific time and date. Use this to CHECK availability first before booking.",
        args_schema=SearchRoomsInput,
        coroutine=search_rooms_wrapper
    ),
    StructuredTool.from_function(
        func=book_room_wrapper,
        name="book_room",
        description="Book a study room. MANDATORY REQUIREMENTS - You MUST have ALL of these before calling: firstName, lastName, @miamioh.edu email, date (YYYY-MM-DD), start_time (HH:MM), end_time (HH:MM), capacity (number of people), building. DO NOT call this tool until you have collected ALL required information from the user. The API will send a confirmation email automatically upon successful booking.",
        args_schema=BookRoomInput,
        coroutine=book_room_wrapper
    ),
    StructuredTool.from_function(
        func=search_website_wrapper,
        name="search_website",
        description="Search library website for policies, services, and general information.",
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
        func=find_subject_librarian_wrapper,
        name="find_subject_librarian",
        description="Find subject librarian contact information and research guides for an academic subject, major, or department. Use this when users ask 'who is my [subject] librarian' or need help with a specific academic area.",
        args_schema=FindSubjectLibrarianInput,
        coroutine=find_subject_librarian_wrapper
    ),
    StructuredTool.from_function(
        func=connect_librarian_wrapper,
        name="connect_librarian",
        description="Connect user with a human librarian for complex questions or personalized help.",
        args_schema=ConnectLibrarianInput,
        coroutine=connect_librarian_wrapper
    ),
    StructuredTool.from_function(
        func=cancel_reservation_wrapper,
        name="cancel_reservation",
        description="Cancel a study room reservation. MUST have confirmation number (booking ID) and email address. Verifies the email matches before canceling.",
        args_schema=CancelReservationInput,
        coroutine=cancel_reservation_wrapper
    )
]

# Create LLM with tools bound
llm = ChatOpenAI(**llm_kwargs)
llm_with_tools = llm.bind_tools(tools)

async def handle_with_function_calling(user_message: str, logger=None, conversation_history=None) -> Dict[str, Any]:
    """
    Handle user message using OpenAI function calling (alternative to LangGraph).
    This matches the NestJS approach more closely.
    
    Args:
        user_message: Current user query
        logger: Logger instance
        conversation_history: List of previous messages for context
    """
    if logger:
        history_len = len(conversation_history) if conversation_history else 0
        logger.log("🔧 [Function Calling] Using direct OpenAI function calling mode", {"history_messages": history_len})
    
    # Format conversation history
    history_text = ""
    if conversation_history:
        history_formatted = []
        for msg in conversation_history[-6:]:  # Last 6 messages (3 exchanges)
            role = "User" if msg["type"] == "user" else "Assistant"
            history_formatted.append(f"{role}: {msg['content']}")
        history_text = "\n\nPrevious conversation:\n" + "\n".join(history_formatted)
    
    system_message = f"""You are a helpful Miami University Libraries assistant speaking to a human user.
You have access to several tools to help users. Use the appropriate tool based on the user's question.
{history_text}

🚨 CRITICAL RULES - VIOLATION OF THESE RULES IS COMPLETELY UNACCEPTABLE:

CONTACT INFORMATION RULES - ABSOLUTELY NO EXCEPTIONS:
- NEVER create, invent, or fabricate contact information
- ONLY use contact information from tool results (LibGuides, MyGuide, Google Site Search)
- If tools don't provide contact info, don't mention it - just provide general library contact

WHAT YOU CAN PROVIDE (from tool results only):
✅ Librarian names - if from tools
✅ Email addresses - ONLY if they appear in tool results (LibGuides/MyGuide)
✅ Subject areas and specialties
✅ LibGuide profile URLs
✅ Subject guide URLs
✅ General library phone: (513) 529-4141

WHAT YOU MUST NEVER DO:
❌ Fabricate or guess email addresses (e.g., "lastname@miamioh.edu")
❌ Make up librarian names or titles
❌ Invent phone extensions or office numbers
❌ Create office locations or building/room numbers
❌ Provide contact info not found in tool results

HOW TO HANDLE SUBJECT/RESEARCH QUESTIONS:
1. Search LibGuides and MyGuide for the subject area
2. If found with contact info, provide: Librarian name + Email (if in result) + Subject guide URL
3. Format: "For [subject] questions, contact [Name] ([email if provided]). View their subject guide: [URL]"
4. If no specific info found, direct to: https://www.lib.miamioh.edu/research/research-support/ask/ or (513) 529-4141

URL RULES:
- ONLY use URLs from tool results - NEVER create or modify web addresses
- Allowed domains: lib.miamioh.edu, libcal.miamioh.edu, libguides.lib.miamioh.edu, miamioh.libguides.com, libanswers.lib.miamioh.edu, digital.lib.miamioh.edu
- If unsure about a URL, provide the general library website: https://www.lib.miamioh.edu

OTHER RULES:
- Use conversation history to provide contextual follow-up responses
- Always cite the source of your information

STUDY ROOM BOOKING RULES - EXTREMELY IMPORTANT:
- VALID LIBRARIES FOR STUDY ROOMS (ONLY these 4):
  * King Library (Oxford campus) - use "king"
  * Art & Architecture Library (Oxford campus) - use "art"
  * Rentschler Library (Hamilton campus) - use "rentschler" or "hamilton"
  * Gardner-Harvey Library (Middletown campus) - use "gardner-harvey" or "middletown"
- If user mentions ANY OTHER library name (e.g., "Farmer", "Science", "Law", etc.), you MUST:
  * Inform them that library does NOT have study rooms
  * List the 4 valid libraries above
  * Ask which one they'd like to book
- NEVER say "checking availability", "let me check", "I'll look for", or similar status updates
- The backend handles all availability checking automatically
- BEFORE calling book_room tool, you MUST collect ALL required information:
  * First name
  * Last name
  * @miamioh.edu email address
  * Date (accept ANY format: 11/12/2025, tomorrow, next Monday, Dec 15, etc.)
  * Start time and end time (accept ANY format: 8pm, 8:00 PM, 20:00, 2pm, etc.)
  * Number of people
  * Building preference (MUST be one of the 4 valid libraries above)
- The system automatically converts all date/time formats, so accept user's natural language
- DO NOT call book_room until you have ALL of the above information
- ONLY present the FINAL result from the tool:
  1. If missing information: Ask for the specific missing details (especially first name, last name, email)
  2. If no rooms available: State directly that no rooms are available
  3. If booking confirmed: Present the confirmation number and mention the confirmation email
- DO NOT provide intermediate status messages about what you're doing

WARNING - ABSOLUTELY FORBIDDEN:
- NEVER output JSON, code, or programming syntax
- NEVER show API responses or data structures
- NEVER use curly braces, square brackets, or code formatting
- NEVER output raw technical data
- ALWAYS write in natural, conversational, human language

FORMATTING GUIDELINES:
- Write in complete, natural sentences like you're talking to a person
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks between sections
- Use bullet points (•) for lists - NOT JSON or arrays
- Highlight actionable links and important details
- Keep paragraphs concise (2-3 sentences max)
- Use natural, conversational, HUMAN language
- Make responses easy to scan quickly
- ALWAYS present information in readable paragraph/list format, NEVER as code

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
                
                # Validate URLs in response
                if logger:
                    logger.log("🔍 [URL Validator] Checking URLs in response")
                
                validated_answer, had_invalid_urls = await validate_and_clean_response(
                    final_response.content,
                    log_callback=logger.log if logger else None,
                    user_message=user_message
                )
                
                if had_invalid_urls and logger:
                    logger.log("⚠️ [URL Validator] Removed invalid URLs from response")
                
                # Extract token usage
                token_usage = None
                if hasattr(final_response, 'response_metadata') and 'token_usage' in final_response.response_metadata:
                    usage = final_response.response_metadata['token_usage']
                    token_usage = {
                        "model": final_response.response_metadata.get('model_name', OPENAI_MODEL),
                        "prompt_tokens": usage.get('prompt_tokens', 0),
                        "completion_tokens": usage.get('completion_tokens', 0),
                        "total_tokens": usage.get('total_tokens', 0)
                    }
                
                # Log tool execution details
                tool_executions = [{
                    "agent_name": "function_calling",
                    "tool_name": tool_name,
                    "parameters": tool_args,
                    "success": True,
                    "execution_time": 0
                }]
                
                return {
                    "success": True,
                    "final_answer": validated_answer,
                    "tool_used": tool_name,
                    "tool_args": tool_args,
                    "token_usage": token_usage,
                    "tool_executions": tool_executions,
                    "mode": "function_calling"
                }
        else:
            # No tool needed, direct answer
            if logger:
                logger.log("💬 [Function Calling] No tool needed, direct answer")
            
            # Validate URLs in direct response
            if logger:
                logger.log("🔍 [URL Validator] Checking URLs in direct response")
            
            validated_answer, had_invalid_urls = await validate_and_clean_response(
                response.content,
                log_callback=logger.log if logger else None,
                user_message=user_message
            )
            
            if had_invalid_urls and logger:
                logger.log("⚠️ [URL Validator] Removed invalid URLs from direct response")
            
            return {
                "success": True,
                "final_answer": validated_answer,
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
