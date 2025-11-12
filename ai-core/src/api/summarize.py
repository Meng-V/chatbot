"""
API endpoint for generating AI-powered chat summaries.
Used for LibChat handoff to provide librarians with quick context.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import os

router = APIRouter(tags=["summarize"])

# Use o4-mini as specified in .env
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


class ChatSummaryRequest(BaseModel):
    """Request model for chat summary generation."""
    chatHistory: str


class ChatSummaryResponse(BaseModel):
    """Response model for chat summary."""
    summary: str


@router.post("/api/summarize-chat", response_model=ChatSummaryResponse)
async def summarize_chat(request: ChatSummaryRequest):
    """
    Generate an AI-powered summary of a chat conversation.
    
    This endpoint is used when users hand off to human librarians,
    providing a concise summary of:
    - Main question/topic
    - Key information discussed
    - Current status/outcome
    
    Args:
        request: ChatSummaryRequest containing the chat history
        
    Returns:
        ChatSummaryResponse with the generated summary
    """
    try:
        # Initialize OpenAI chat model using o4-mini pattern from system
        # o4-mini doesn't support temperature parameter
        llm_kwargs = {"model": OPENAI_MODEL, "api_key": OPENAI_API_KEY}
        if not OPENAI_MODEL.startswith("o"):
            llm_kwargs["temperature"] = 0.3  # Lower temperature for focused summaries
        
        llm = ChatOpenAI(**llm_kwargs)
        
        # Create summary prompt using system pattern (SystemMessage + HumanMessage)
        system_prompt = """You are summarizing a conversation between a user and a library chatbot for a human librarian.

Create a concise summary (3-5 sentences) that includes:
1. The user's main question or need
2. Key topics or resources discussed
3. Current status (resolved, needs follow-up, etc.)
4. Any specific details the librarian should know"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Chat History:\n{request.chatHistory}\n\nSummary:")
        ]
        
        # Generate summary using async invoke (matching system pattern)
        response = await llm.ainvoke(messages)
        summary = response.content.strip()
        
        return ChatSummaryResponse(summary=summary)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary: {str(e)}"
        )
