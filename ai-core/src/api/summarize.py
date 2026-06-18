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
from src.config.models import resolve_model, is_reasoning_model  # noqa: E402
OPENAI_MODEL = resolve_model("basic")  # env: LLM_MODEL_BASIC (default gpt-5.4-mini)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


class ChatSummaryRequest(BaseModel):
    """Request model for chat summary generation."""
    chatHistory: str


class ChatSummaryResponse(BaseModel):
    """Response model for chat summary."""
    summary: str


# LibAnswers ticket QUESTION (subject) field caps at 150 chars; the ticket
# form prepends a short "[AI] " marker (5 chars), so the summary gets almost
# the whole budget. Cap a touch under 145 for a safety margin.
SUBJECT_CHAR_LIMIT = 140


def _fit_subject(text: str, limit: int = SUBJECT_CHAR_LIMIT) -> str:
    """Collapse whitespace and trim to <= limit chars at a WORD boundary
    (never mid-word), adding an ellipsis when truncated."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return (cut or text[:limit]).rstrip() + "…"


@router.post("/summarize-chat", response_model=ChatSummaryResponse)
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
        if not is_reasoning_model(OPENAI_MODEL):  # reasoning models reject temperature
            llm_kwargs["temperature"] = 0.3  # Lower temperature for focused summaries
        
        llm = ChatOpenAI(**llm_kwargs)

        # The summary goes into the LibAnswers ticket QUESTION (subject)
        # field, which is capped at 150 chars; the ticket form prepends a
        # ~42-char "Summarized by AI" marker, so anything past ~108 chars
        # was cut mid-word in the subject (prod 2026-06-17). Ask for a
        # short one-line subject, not a multi-sentence paragraph.
        system_prompt = """You are writing the SUBJECT LINE for a library help-desk ticket, summarizing what a user needs based on their chat with the library bot.

Write ONE concise line capturing the user's main question(s) and any key specifics (subject, building, course, what's unresolved) -- at most ~130 characters (about 20 words). No preamble, no "the user asked", no full sentences. Pack in the useful details, not filler.
Examples: "Library hours, and who the dean of libraries is"; "Booking a 2-3pm study room at King for tomorrow"; "Finding a peer-reviewed article on insomnia and academic performance"."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Chat History:\n{request.chatHistory}\n\nSubject:")
        ]

        # Generate summary using async invoke (matching system pattern)
        response = await llm.ainvoke(messages)
        summary = _fit_subject(response.content.strip())

        return ChatSummaryResponse(summary=summary)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary: {str(e)}"
        )
