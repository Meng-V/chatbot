import os
import re
import json
import time
import logging
from decimal import Decimal
from datetime import datetime, date
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from src.utils.logging_config import setup_logging, UVICORN_LOG_CONFIG
from contextlib import asynccontextmanager

from src.graph.orchestrator import library_graph
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
from src.utils.weaviate_client import get_weaviate_client, close_weaviate_client, get_weaviate_url
from src.api.health import router as health_router
from src.api.summarize import router as summarize_router
from src.api.askus_hours import router as askus_router
from src.api.route import router as route_router

# ---------------------------------------------------------------------------
# .env loading — MUST NOT follow symlinks on production
# ---------------------------------------------------------------------------
# On production the deploy layout is:
#   /opt/chatbot/current  →  /opt/chatbot/releases/<timestamp>  (symlink)
#   /opt/chatbot/shared/.env                                      (canonical)
#   /opt/chatbot/releases/<timestamp>/.env → shared/.env          (symlink)
#
# Path(__file__).resolve() follows ALL symlinks, locking us to a stale
# release directory.  os.path.abspath() makes the path absolute WITHOUT
# resolving symlinks, so we always read through the 'current' symlink.
# ---------------------------------------------------------------------------
_this_file = os.path.abspath(__file__)          # …/current/ai-core/src/main.py
root_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(_this_file))))

# Prefer the canonical shared .env on production; fall back to project root
_shared_env = Path("/opt/chatbot/shared/.env")
if _shared_env.exists():
    env_path = _shared_env
else:
    env_path = root_dir / ".env"

load_dotenv(dotenv_path=env_path, override=True)
print(f"Loading .env from: {env_path}")

# Initialize logging EARLY (module level) so it takes effect before uvicorn
# configures its own loggers. This prevents INFO spam in systemd journal.
setup_logging()
logging.info(f"📂 .env loaded from: {env_path}  (root_dir={root_dir})")
logging.info(f"📂 __file__ resolved WITHOUT symlinks: {_this_file}")


def json_serializable(obj):
    """
    Convert non-JSON-serializable objects to serializable types.
    Handles Decimal, datetime, date, and other common types.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [json_serializable(item) for item in obj]
    else:
        return obj


def clean_response_for_frontend(text: str) -> str:
    """
    Remove internal metadata and source annotations from response before sending to frontend.
    These are useful for internal processing but awkward for end users to see.
    """
    if not text:
        return text
    
    # Patterns to remove (internal metadata that shouldn't be shown to users)
    patterns_to_remove = [
        # Source attribution lines - remove ALL source lines
        r'\n*Source:\s*[^\n]+\n*',
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
    setup_logging()  # Re-apply logging config (overrides uvicorn's defaults)
    logging.info("🚀 Application starting...")

    # --- Database connection ---
    try:
        await connect_database()
        logging.info("✅ Database (Prisma) connected successfully")
    except Exception as e:
        logging.error(f"❌ Database connection FAILED: {e}", exc_info=True)

    # --- Weaviate connection check ---
    weaviate_url = get_weaviate_url()
    logging.info(f"🔗 [Weaviate] Attempting connection to {weaviate_url}")
    try:
        wv_client = get_weaviate_client()
        if wv_client is not None:
            is_ready = wv_client.is_ready()
            if is_ready:
                meta = wv_client.get_meta()
                version = meta.get("version", "unknown") if isinstance(meta, dict) else "unknown"
                collections = wv_client.collections.list_all()
                col_names = list(collections.keys()) if isinstance(collections, dict) else [str(c) for c in collections]
                logging.info(
                    f"✅ [Weaviate] Connected successfully | "
                    f"url={weaviate_url} | version={version} | "
                    f"collections={len(col_names)} ({', '.join(col_names[:10])})"
                )
            else:
                logging.warning(f"⚠️ [Weaviate] Client created but NOT READY at {weaviate_url}")
        else:
            logging.warning(
                f"⚠️ [Weaviate] Client is None — connection failed or disabled | url={weaviate_url} | "
                f"WEAVIATE_ENABLED={os.getenv('WEAVIATE_ENABLED', 'true')} | "
                f"WEAVIATE_HOST={os.getenv('WEAVIATE_HOST', '(not set)')}"
            )
    except Exception as e:
        logging.error(f"❌ [Weaviate] Connection FAILED at {weaviate_url}: {e}", exc_info=True)

    # --- Initialize RAG classifier vector store ---
    try:
        from src.classification.rag_classifier import RAGQuestionClassifier
        classifier = RAGQuestionClassifier()
        await classifier.initialize_vector_store(force_refresh=False)
        logging.info("✅ [RAG Classifier] Vector store initialized")
    except Exception as e:
        logging.error(f"⚠️ [RAG Classifier] Vector store init failed: {e}", exc_info=True)

    logging.info("🚀 Application startup complete")
    yield

    # Shutdown
    logging.info("🛑 Application shutting down...")
    close_weaviate_client()
    logging.info("🔌 [Weaviate] Client closed")
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
app.include_router(route_router)

# Socket.IO server for real-time communication
# Allow all origins in development for easier debugging
socketio_cors = "*" if node_env == "development" else cors_origins

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=socketio_cors,
    logger=False,
    engineio_logger=False
)

app_sio = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/smartchatbot/socket.io")

# Store conversation mappings for Socket.IO clients
client_conversations = {}

@app.post("/ask")
async def ask_http(payload: dict):
    """Main endpoint using LangGraph orchestrator."""
    message = payload.get("message", "")
    conversation_id = payload.get("conversationId")
    
    # Create logger with unique request ID
    logger = AgentLogger(request_id=f"http_{int(time.time()*1000)}")
    logger.log("📥 [API] Received request", {"message": message[:100], "conversationId": conversation_id})
    logger.start_timer("total_request")
    
    try:
        # Create or get conversation
        if not conversation_id:
            conversation_id = await create_conversation()
            logger.log(f"🆕 [API] Created new conversation: {conversation_id}")
        
        # Save user message
        await add_message(conversation_id, "user", message)
        
        # Get conversation history for context
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Call LangGraph workflow directly (production routing path)
        try:
            result = await library_graph.ainvoke({
                "user_message": message,
                "messages": [],
                "conversation_history": history,
                "conversation_id": conversation_id,
                "_logger": logger
            })
        except Exception as graph_error:
            logger.log(f"❌ [API] LangGraph error: {str(graph_error)}")
            import traceback
            logger.log(f"❌ [API] Traceback: {traceback.format_exc()}")
            result = None
        
        # Safety check for None result
        if result is None:
            logger.log("⚠️ [API] LangGraph returned None, using fallback response")
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
        
        total_ms = logger.stop_timer("total_request")
        logger.log("✅ [API] Request completed successfully", {
            "agents_used": agents_used,
            "intent": result.get("classified_intent"),
            "total_ms": total_ms
        })
        
        # Determine primary agent used
        primary_agent = agents_used[0] if agents_used else result.get("classified_intent")
        
        return {
            "success": True,
            "conversationId": conversation_id,
            "response": final_answer,  # Primary field for response text
            "final_answer": final_answer,  # Keep for backwards compatibility
            "agent": primary_agent,  # Primary agent used
            "agents_used": agents_used,  # Keep for backwards compatibility
            "toolsUsed": agents_used,  # Frontend expects this field name
            "intent": result.get("classified_intent"),
            "agent_responses": result.get("agent_responses", {}),
            "needs_human": result.get("needs_human", False),
            "logs": logger.get_logs(),
            "history_count": len(history)
        }
    except Exception as e:
        logger.log_error("API", e, context=f"message='{message[:60]}'")
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
    logging.info(f"🔌 Client connected: {sid}")
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
    logging.info(f"🔌 Client disconnected: {sid}")
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
        
        # Create logger with unique request ID
        logger = AgentLogger(request_id=f"ws_{sid[:8]}_{int(time.time()*1000)}")
        logger.log("📥 [Socket.IO] Received message", {
            "sid": sid,
            "conversationId": conversation_id,
            "message": text_input[:100],
            "history_count": len(history)
        })
        logger.start_timer("total_request")
        
        # Call LangGraph workflow directly (production routing path)
        result = await library_graph.ainvoke({
            "user_message": text_input,
            "messages": [],
            "conversation_history": history,
            "conversation_id": conversation_id,
            "_logger": logger
        })
        
        # Safety check for None result
        if result is None:
            logger.log("⚠️ [Socket.IO] LangGraph returned None, using fallback response")
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
        
        # Emit response (ensure all data is JSON-serializable)
        response_data = {
            "messageId": message_id,
            "message": final_answer,
            "conversationId": conversation_id,
            "intent": result.get("classified_intent"),
            "agents_used": agents_used,
            "needs_human": result.get("needs_human", False)
        }
        
        # Convert any non-serializable types to JSON-safe formats
        response_data = json_serializable(response_data)
        
        await sio.emit("message", response_data, to=sid)
        
        total_ms = logger.stop_timer("total_request")
        logger.log("✅ [Socket.IO] Response sent successfully", {
            "total_ms": total_ms,
            "agents_used": agents_used,
            "intent": result.get("classified_intent")
        })
        
    except Exception as e:
        logging.error(f"❌ [Socket.IO] Error: {str(e)}", exc_info=True)
        
        error_data = {
            "messageId": None,
            "message": "I encountered an error. Please try again or contact a librarian.",
            "error": str(e)
        }
        
        await sio.emit("message", json_serializable(error_data), to=sid)

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
            logging.info(f"👍 Message {message_id} rated: {'positive' if is_positive else 'negative'}")
            
            await sio.emit("ratingAck", {
                "messageId": message_id,
                "success": True
            }, to=sid)
    except Exception as e:
        logging.error(f"❌ Error updating message rating: {str(e)}")
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
            logging.info(f"💬 Feedback saved for conversation {conversation_id}: {user_rating}/5")
            
            await sio.emit("feedbackAck", {
                "conversationId": conversation_id,
                "success": True
            }, to=sid)
    except Exception as e:
        logging.error(f"❌ Error saving feedback: {str(e)}")
        await sio.emit("feedbackAck", {
            "success": False,
            "error": str(e)
        }, to=sid)

@sio.event
async def clarificationChoice(sid, data):
    """
    Handle user's clarification choice selection.
    Uses unified library_graph.ainvoke() path for consistency.
    Expected data: {
        "choiceId": str,
        "originalQuestion": str,
        "clarificationData": dict,
        "conversationId": str (optional)
    }
    """
    try:
        choice_id = data.get("choiceId")
        original_question = data.get("originalQuestion")
        conversation_id = data.get("conversationId") or client_conversations.get(sid)
        
        logging.info(f"🎯 [Clarification] User {sid} selected choice: {choice_id}")
        
        # Create logger
        logger = AgentLogger()
        logger.log("🎯 [Clarification Choice] Processing user selection", {
            "sid": sid,
            "choiceId": choice_id,
            "originalQuestion": original_question
        })
        
        # Get conversation history
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Check if user wants to talk to librarian
        if choice_id in ["libchat", "librarian", "human_help"]:
            logger.log("👤 [Clarification Choice] User chose to talk to librarian")
            
            # Save user's choice as a message
            await add_message(conversation_id, "user", "I'd like to talk to a librarian")
            
            # Route directly to libchat_handoff by setting a clear message
            result = await library_graph.ainvoke({
                "user_message": "Connect me to a librarian",
                "messages": [],
                "conversation_history": history,
                "conversation_id": conversation_id,
                "_logger": logger
            })
        elif choice_id == "none":
            # User selected "None of the above" - ask for more details
            await sio.emit("requestMoreDetails", {
                "message": "Could you provide more details about what you're looking for? This will help me understand your question better.",
                "originalQuestion": original_question
            }, to=sid)
            
            logger.log("💬 [Clarification Choice] Requesting more details from user")
            return
        else:
            # User selected a specific category - re-run with context
            logger.log(f"✅ [Clarification Choice] User selected option: {choice_id}")
            
            # Save user's clarification choice as a message
            await add_message(conversation_id, "user", f"Regarding: {original_question} (selected: {choice_id})")
            
            # Re-run library_graph with augmented context
            enhanced_question = f"{original_question} [User clarified: {choice_id}]"
            
            result = await library_graph.ainvoke({
                "user_message": enhanced_question,
                "messages": [],
                "conversation_history": history,
                "conversation_id": conversation_id,
                "_logger": logger
            })
        
        # Process result
        if result is None:
            result = {
                "final_answer": "I encountered an issue. Please try again or contact a librarian.",
                "selected_agents": [],
                "classified_intent": "error"
            }
        
        final_answer = result.get("final_answer", "")
        final_answer = clean_response_for_frontend(final_answer)
        
        # Save assistant message
        message_id = await add_message(conversation_id, "assistant", final_answer)
        
        # Update tools used
        agents_used = result.get("selected_agents", [])
        if "tool_used" in result:
            agents_used = [result["tool_used"]]
        await update_conversation_tools(conversation_id, agents_used)
        
        # Send response
        response_data = json_serializable({
            "messageId": message_id,
            "message": final_answer,
            "conversationId": conversation_id,
            "intent": result.get("classified_intent"),
            "agents_used": agents_used,
            "needs_human": result.get("needs_human", False),
            "clarification_resolved": True
        })
        
        await sio.emit("message", response_data, to=sid)
        
        logger.log("✅ [Clarification Choice] Response sent successfully")
        
    except Exception as e:
        logging.error(f"❌ [Clarification Choice] Error: {str(e)}", exc_info=True)
        
        await sio.emit("message", json_serializable({
            "messageId": None,
            "message": "I encountered an error processing your choice. Please try again or contact a librarian.",
            "error": str(e)
        }), to=sid)

@sio.event
async def provideMoreDetails(sid, data):
    """
    Handle when user provides additional details after selecting "None of the above".
    Uses unified library_graph.ainvoke() path for consistency.
    Expected data: {
        "originalQuestion": str,
        "additionalDetails": str,
        "conversationId": str (optional)
    }
    """
    try:
        original_question = data.get("originalQuestion")
        additional_details = data.get("additionalDetails")
        conversation_id = data.get("conversationId") or client_conversations.get(sid)
        
        logging.info(f"💬 [More Details] User {sid} provided: {additional_details}")
        
        # Create logger
        logger = AgentLogger()
        logger.log("💬 [More Details] Processing with additional context", {
            "sid": sid,
            "originalQuestion": original_question,
            "additionalDetails": additional_details
        })
        
        # Get conversation history
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Save user's additional details as a message
        await add_message(conversation_id, "user", additional_details)
        
        # Combine original question with additional details
        combined_question = f"{original_question}. {additional_details}"
        
        # Re-run library_graph with combined question and updated history
        result = await library_graph.ainvoke({
            "user_message": combined_question,
            "messages": [],
            "conversation_history": history,
            "conversation_id": conversation_id,
            "_logger": logger
        })
        
        if result is None:
            result = {
                "final_answer": "I encountered an issue. Please try again or contact a librarian.",
                "selected_agents": [],
                "classified_intent": "error"
            }
        
        final_answer = result.get("final_answer", "")
        final_answer = clean_response_for_frontend(final_answer)
        
        # Save assistant message
        message_id = await add_message(conversation_id, "assistant", final_answer)
        
        # Update tools used
        agents_used = result.get("selected_agents", [])
        if "tool_used" in result:
            agents_used = [result["tool_used"]]
        await update_conversation_tools(conversation_id, agents_used)
        
        # Send response
        response_data = json_serializable({
            "messageId": message_id,
            "message": final_answer,
            "conversationId": conversation_id,
            "intent": result.get("classified_intent"),
            "agents_used": agents_used,
            "needs_human": result.get("needs_human", False),
            "reclassified": True
        })
        
        await sio.emit("message", response_data, to=sid)
        
        logger.log("✅ [More Details] Responded successfully")
        
    except Exception as e:
        logging.error(f"❌ [More Details] Error: {str(e)}", exc_info=True)
        
        await sio.emit("message", json_serializable({
            "messageId": None,
            "message": "I encountered an error processing your details. Please try again or contact a librarian.",
            "error": str(e)
        }), to=sid)

# ---------------------------------------------------------------------------
# Programmatic uvicorn entry point  (preferred on production)
# Usage:  python -m src.main
# This passes UVICORN_LOG_CONFIG so every log line has a timestamp.
# Falls back to: uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
#   but the CLI approach will NOT have timestamps unless you also pass
#   --log-config ai-core/uvicorn_log_config.json
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app_sio",
        host="0.0.0.0",
        port=int(os.getenv("AI_CORE_PORT", "8000")),
        log_config=UVICORN_LOG_CONFIG,
    )
