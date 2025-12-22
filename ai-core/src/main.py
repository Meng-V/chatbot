import os
import re
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import socketio
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from src.utils.logging_config import setup_logging
from contextlib import asynccontextmanager

from src.graph.orchestrator import library_graph
# from src.graph.hybrid_router import route_query
from src.graph.hybrid_router_rag import route_query_rag as route_query
from src.state import AgentState
from src.utils.logger import AgentLogger
from src.memory.conversation_store import (
    create_conversation,
    add_message,
    get_conversation_history,
    update_conversation_tools,
    update_message_rating,
    save_conversation_feedback,
    log_token_usage,
    log_tool_execution
)
from src.database.prisma_client import connect_database, disconnect_database
from src.api.health import router as health_router
from src.api.summarize import router as summarize_router
from src.api.askus_hours import router as askus_router

# Load .env from project root (parent of ai-core)
# Path calculation: main.py -> src -> ai-core -> root
root_dir = Path(__file__).resolve().parent.parent.parent
env_path = root_dir / ".env"
print(f"Loading .env from: {env_path}")
load_dotenv(dotenv_path=env_path)


def clean_response_for_frontend(text: str) -> str:
    """
    Remove internal metadata and source annotations from response before sending to frontend.
    These are useful for internal processing but awkward for end users to see.
    """
    if not text:
        return text
    
    # Patterns to remove (internal metadata that shouldn't be shown to users)
    patterns_to_remove = [
        # Source attribution lines
        r'\n*Source:\s*[^\n]+\[VERIFIED API DATA\][^\n]*\n*',
        r'\n*Source:\s*[^\n]+\[CURATED KNOWLEDGE BASE[^\]]*\][^\n]*\n*',
        r'\n*Source:\s*[^\n]+\[WEBSITE SEARCH[^\]]*\][^\n]*\n*',
        r'\n*Source:\s*Subject Librarian Agent[^\n]*\n*',
        r'\n*Source:\s*LibGuide[^\n]*\n*',
        # Standalone brackets with internal labels
        r'\s*\[VERIFIED API DATA\]',
        r'\s*\[CURATED KNOWLEDGE BASE[^\]]*\]',
        r'\s*\[WEBSITE SEARCH[^\]]*\]',
        r'\s*\[HIGH PRIORITY\]',
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace/newlines that might result from removal
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


# Lifecycle management for database connection
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    print("🚀 Starting Miami Libraries AI-Core...")
    setup_logging()  # Initialize logging system
    logging.info("🚀 Application starting...")
    await connect_database()
    logging.info("✅ Database connected")
    yield
    # Shutdown
    print("� Shutting down Miami Libraries AI-Core...")
    logging.info("🛑 Application shutting down...")
    await disconnect_database()
    logging.info("✅ Database disconnected")

# Create FastAPI app with lifecycle
app = FastAPI(
    title="Miami Libraries AI-Core",
    description="LangGraph-powered chatbot with 6 specialized agents",
    version="1.0.0",
    lifespan=lifespan
)

# Environment-based CORS configuration
node_env = os.getenv("NODE_ENV", "development")
frontend_url = os.getenv("FRONTEND_URL", "https://new.lib.miamioh.edu")

cors_origins = [frontend_url]
if node_env == "development":
    cors_origins.extend([
        "http://localhost:5173",
        "http://localhost:3000"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include health/monitoring routers
app.include_router(health_router)
app.include_router(summarize_router)
app.include_router(askus_router)

# Socket.IO server for real-time communication
# Allow all origins in development for easier debugging
socketio_cors = "*" if node_env == "development" else cors_origins

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=socketio_cors,
    logger=True,
    engineio_logger=True
)

app_sio = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/smartchatbot/socket.io")

# Store conversation mappings for Socket.IO clients
client_conversations = {}

@app.post("/ask")
async def ask_http(payload: dict):
    """Main endpoint using LangGraph orchestrator."""
    message = payload.get("message", "")
    conversation_id = payload.get("conversationId")
    
    # Create logger
    logger = AgentLogger()
    logger.log("📥 [API] Received request", {"message": message, "conversationId": conversation_id})
    
    try:
        # Create or get conversation
        if not conversation_id:
            conversation_id = await create_conversation()
            logger.log(f"🆕 [API] Created new conversation: {conversation_id}")
        
        # Save user message
        await add_message(conversation_id, "user", message)
        
        # Get conversation history for context
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Use hybrid router (smart selection between function calling and LangGraph)
        try:
            result = await route_query(message, logger, history, conversation_id)
        except Exception as router_error:
            logger.log(f"❌ [API] Router error: {str(router_error)}")
            import traceback
            logger.log(f"❌ [API] Traceback: {traceback.format_exc()}")
            result = None
        
        # Safety check for None result
        if result is None:
            logger.log("⚠️ [API] Router returned None, using fallback response")
            result = {
                "final_answer": "I encountered an error. Please try again or contact a librarian.",
                "selected_agents": [],
                "classified_intent": "error"
            }
        
        final_answer = result.get("final_answer", "")
        agents_used = result.get("selected_agents", [])
        if "tool_used" in result:
            agents_used = [result["tool_used"]]
        
        # Save assistant message
        await add_message(conversation_id, "assistant", final_answer)
        
        # Update tools used
        await update_conversation_tools(conversation_id, agents_used)
        
        # Log token usage if available
        if "token_usage" in result and result["token_usage"] is not None:
            token_data = result["token_usage"]
            await log_token_usage(
                conversation_id,
                token_data.get("model", "unknown"),
                token_data.get("prompt_tokens", 0),
                token_data.get("completion_tokens", 0),
                token_data.get("total_tokens", 0)
            )
        
        # Log tool executions if available
        if "tool_executions" in result:
            for execution in result["tool_executions"]:
                await log_tool_execution(
                    conversation_id,
                    execution.get("agent_name", "unknown"),
                    execution.get("tool_name", "unknown"),
                    execution.get("parameters", {}),
                    execution.get("success", True),
                    execution.get("execution_time", 0)
                )
        
        logger.log("✅ [API] Request completed successfully")
        
        return {
            "success": True,
            "conversationId": conversation_id,
            "intent": result.get("classified_intent"),
            "agents_used": agents_used,
            "agent_responses": result.get("agent_responses", {}),
            "final_answer": final_answer,
            "needs_human": result.get("needs_human", False),
            "logs": logger.get_logs(),
            "history_count": len(history)
        }
    except Exception as e:
        logger.log(f"❌ [API] Error: {str(e)}")
        return {
            "success": False,
            "conversationId": conversation_id,
            "error": str(e),
            "final_answer": "I encountered an error. Please try again or contact a librarian.",
            "logs": logger.get_logs()
        }

# Enhanced Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    print(f"🔌 Client connected: {sid}")
    # Create new conversation for this client
    conversation_id = await create_conversation()
    client_conversations[sid] = conversation_id
    await sio.emit("status", {
        "status": "connected",
        "conversationId": conversation_id
    }, to=sid)

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    print(f"🔌 Client disconnected: {sid}")
    if sid in client_conversations:
        del client_conversations[sid]

@sio.event
async def message(sid, data):
    """
    Handle incoming message from client.
    Compatible with NestJS format.
    """
    # Parse message (support both string and dict formats)
    text_input = data if isinstance(data, str) else (data.get("message", "") if isinstance(data, dict) else "")
    
    # Get or create conversation
    conversation_id = client_conversations.get(sid)
    if not conversation_id:
        conversation_id = await create_conversation()
        client_conversations[sid] = conversation_id
    
    try:
        # Save user message
        await add_message(conversation_id, "user", text_input)
        
        # Get conversation history for context
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Create logger
        logger = AgentLogger()
        logger.log("📥 [Socket.IO] Received message", {
            "sid": sid,
            "conversationId": conversation_id,
            "message": text_input,
            "history_count": len(history)
        })
        
        # Use hybrid router (smart selection between function calling and LangGraph)
        result = await route_query(text_input, logger, history, conversation_id)
        
        # Safety check for None result
        if result is None:
            logger.log("⚠️ [Socket.IO] Router returned None, using fallback response")
            result = {
                "final_answer": "I encountered an issue processing your request. Please try again or contact a librarian.",
                "selected_agents": [],
                "classified_intent": "error"
            }
        
        final_answer = result.get("final_answer", "")
        agents_used = result.get("selected_agents", [])
        if "tool_used" in result:
            agents_used = [result["tool_used"]]
        
        # Clean internal metadata before sending to frontend
        final_answer = clean_response_for_frontend(final_answer)
        
        # Save assistant message
        message_id = await add_message(conversation_id, "assistant", final_answer)
        
        # Update tools used
        await update_conversation_tools(conversation_id, agents_used)
        
        # Log token usage if available
        if "token_usage" in result and result["token_usage"] is not None:
            token_data = result["token_usage"]
            await log_token_usage(
                conversation_id,
                token_data.get("model", "unknown"),
                token_data.get("prompt_tokens", 0),
                token_data.get("completion_tokens", 0),
                token_data.get("total_tokens", 0)
            )
        
        # Log tool executions if available
        if "tool_executions" in result:
            for execution in result["tool_executions"]:
                await log_tool_execution(
                    conversation_id,
                    execution.get("agent_name", "unknown"),
                    execution.get("tool_name", "unknown"),
                    execution.get("parameters", {}),
                    execution.get("success", True),
                    execution.get("execution_time", 0)
                )
        
        # Emit response
        await sio.emit("message", {
            "messageId": message_id,
            "message": final_answer,
            "conversationId": conversation_id,
            "intent": result.get("classified_intent"),
            "agents_used": agents_used,
            "needs_human": result.get("needs_human", False)
        }, to=sid)
        
        logger.log("✅ [Socket.IO] Response sent successfully")
        
    except Exception as e:
        print(f"❌ [Socket.IO] Error: {str(e)}")
        await sio.emit("message", {
            "messageId": None,
            "message": f"I encountered an error. Please try again or contact a librarian.",
            "error": str(e)
        }, to=sid)

@sio.event
async def messageRating(sid, data):
    """
    Handle message rating (thumbs up/down).
    Expected data: { "messageId": str, "isPositiveRated": bool }
    """
    try:
        message_id = data.get("messageId")
        is_positive = data.get("isPositiveRated", True)
        
        if message_id:
            await update_message_rating(message_id, is_positive)
            print(f"👍 Message {message_id} rated: {'positive' if is_positive else 'negative'}")
            
            await sio.emit("ratingAck", {
                "messageId": message_id,
                "success": True
            }, to=sid)
    except Exception as e:
        print(f"❌ Error updating message rating: {str(e)}")
        await sio.emit("ratingAck", {
            "success": False,
            "error": str(e)
        }, to=sid)

@sio.event
async def userFeedback(sid, data):
    """
    Handle user feedback for conversation.
    Expected data: { "conversationId": str, "userRating": int, "userComment": str }
    """
    try:
        conversation_id = data.get("conversationId") or client_conversations.get(sid)
        user_rating = data.get("userRating", 0)
        user_comment = data.get("userComment", "")
        
        if conversation_id:
            await save_conversation_feedback(conversation_id, user_rating, user_comment)
            print(f"💬 Feedback saved for conversation {conversation_id}: {user_rating}/5")
            
            await sio.emit("feedbackAck", {
                "conversationId": conversation_id,
                "success": True
            }, to=sid)
    except Exception as e:
        print(f"❌ Error saving feedback: {str(e)}")
        await sio.emit("feedbackAck", {
            "success": False,
            "error": str(e)
        }, to=sid)

# uvicorn entry: uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload
