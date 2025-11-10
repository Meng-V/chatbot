"""Conversation memory using Prisma + PostgreSQL."""
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.database.prisma_client import get_prisma_client

async def ensure_connection():
    """Ensure Prisma is connected."""
    prisma = get_prisma_client()
    if not prisma.is_connected():
        await prisma.connect()

async def create_conversation(tool_used: List[str] = None) -> str:
    """Create a new conversation and return its ID."""
    await ensure_connection()
    prisma = get_prisma_client()
    conversation = await prisma.conversation.create(
        data={
            "toolUsed": tool_used or []
        }
    )
    return conversation.id

async def add_message(
    conversation_id: str,
    message_type: str,  # "user" or "assistant"
    content: str
) -> str:
    """Add a message to a conversation."""
    await ensure_connection()
    prisma = get_prisma_client()
    message = await prisma.message.create(
        data={
            "conversationId": conversation_id,
            "type": message_type,
            "content": content,
            "timestamp": datetime.now()
        }
    )
    return message.id

async def get_conversation_history(
    conversation_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Retrieve recent messages from a conversation."""
    await ensure_connection()
    prisma = get_prisma_client()
    messages = await prisma.message.find_many(
        where={"conversationId": conversation_id},
        order={"timestamp": "desc"},
        take=limit
    )
    
    # Reverse to get chronological order
    messages.reverse()
    
    return [
        {
            "type": msg.type,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat()
        }
        for msg in messages
    ]

async def update_conversation_tools(conversation_id: str, tools: List[str]):
    """Update the tools used in a conversation."""
    await ensure_connection()
    prisma = get_prisma_client()
    await prisma.conversation.update(
        where={"id": conversation_id},
        data={"toolUsed": tools}
    )

async def log_token_usage(
    conversation_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int
):
    """Log LLM token usage."""
    await ensure_connection()
    prisma = get_prisma_client()
    await prisma.modeltokenusage.create(
        data={
            "conversationId": conversation_id,
            "llmModelName": model_name,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": total_tokens
        }
    )

async def update_message_rating(message_id: str, is_positive: bool):
    """Update message rating (thumbs up/down)."""
    await ensure_connection()
    prisma = get_prisma_client()
    await prisma.message.update(
        where={"id": message_id},
        data={"isPositiveRated": is_positive}
    )

async def save_conversation_feedback(
    conversation_id: str,
    rating: int,
    user_comment: str = ""
):
    """Save user feedback for a conversation."""
    await ensure_connection()
    prisma = get_prisma_client()
    
    # Check if feedback already exists
    existing = await prisma.conversationfeedback.find_unique(
        where={"conversationId": conversation_id}
    )
    
    if existing:
        # Update existing feedback
        await prisma.conversationfeedback.update(
            where={"conversationId": conversation_id},
            data={
                "rating": rating,
                "userComment": user_comment
            }
        )
    else:
        # Create new feedback
        await prisma.conversationfeedback.create(
            data={
                "conversationId": conversation_id,
                "rating": rating,
                "userComment": user_comment
            }
        )
