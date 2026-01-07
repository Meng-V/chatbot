import os
import re
import json
from decimal import Decimal
from datetime import datetime, date
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
from src.api.route import router as route_router

# Load .env from project root (parent of ai-core)
# Path calculation: main.py -> src -> ai-core -> root
root_dir = Path(__file__).resolve().parent.parent.parent
env_path = root_dir / ".env"
print(f"Loading .env from: {env_path}")
load_dotenv(dotenv_path=env_path)


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
app.include_router(route_router)

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
        
        logger.log("✅ [Socket.IO] Response sent successfully")
        
    except Exception as e:
        print(f"❌ [Socket.IO] Error: {str(e)}")
        import traceback
        print(f"❌ [Socket.IO] Traceback: {traceback.format_exc()}")
        
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

@sio.event
async def clarificationChoice(sid, data):
    """
    Handle user's clarification choice selection.
    Expected data: {
        "choiceId": str,
        "originalQuestion": str,
        "clarificationData": dict,
        "conversationId": str (optional)
    }
    """
    try:
        from src.classification.clarification_handler import handle_clarification_choice, reclassify_with_additional_context
        
        choice_id = data.get("choiceId")
        original_question = data.get("originalQuestion")
        clarification_data = data.get("clarificationData")
        conversation_id = data.get("conversationId") or client_conversations.get(sid)
        
        print(f"🎯 [Clarification] User {sid} selected choice: {choice_id}")
        
        # Create logger
        logger = AgentLogger()
        logger.log("🎯 [Clarification Choice] Processing user selection", {
            "sid": sid,
            "choiceId": choice_id,
            "originalQuestion": original_question
        })
        
        # Handle the choice selection
        result = await handle_clarification_choice(
            choice_id=choice_id,
            original_question=original_question,
            clarification_data=clarification_data,
            logger=logger
        )
        
        if result.get("needs_more_info"):
            # User selected "None of the above" - ask for more details
            await sio.emit("requestMoreDetails", {
                "message": result.get("response_message"),
                "originalQuestion": original_question
            }, to=sid)
            
            logger.log("💬 [Clarification Choice] Requesting more details from user")
        else:
            # User selected a specific category - continue processing
            confirmed_category = result.get("confirmed_category")
            
            logger.log(f"✅ [Clarification Choice] Category confirmed: {confirmed_category}")
            
            # Get conversation history
            history = await get_conversation_history(conversation_id, limit=10)
            
            # Re-route with confirmed category
            # Create a modified question context that includes the confirmed category
            enhanced_question = f"{original_question} [User confirmed: {confirmed_category}]"
            
            # Process the question with the confirmed category
            final_result = await route_query(enhanced_question, logger, history, conversation_id)
            
            if final_result is None:
                final_result = {
                    "final_answer": "I encountered an issue. Please try again or contact a librarian.",
                    "selected_agents": [],
                    "classified_intent": "error"
                }
            
            final_answer = final_result.get("final_answer", "")
            final_answer = clean_response_for_frontend(final_answer)
            
            # Save assistant message
            message_id = await add_message(conversation_id, "assistant", final_answer)
            
            # Update tools used
            agents_used = final_result.get("selected_agents", [])
            if "tool_used" in final_result:
                agents_used = [final_result["tool_used"]]
            await update_conversation_tools(conversation_id, agents_used)
            
            # Send response
            response_data = json_serializable({
                "messageId": message_id,
                "message": final_answer,
                "conversationId": conversation_id,
                "intent": final_result.get("classified_intent"),
                "agents_used": agents_used,
                "needs_human": final_result.get("needs_human", False),
                "clarification_resolved": True
            })
            
            await sio.emit("message", response_data, to=sid)
            
            logger.log("✅ [Clarification Choice] Response sent successfully")
        
    except Exception as e:
        print(f"❌ [Clarification Choice] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        await sio.emit("message", json_serializable({
            "messageId": None,
            "message": "I encountered an error processing your choice. Please try again or contact a librarian.",
            "error": str(e)
        }), to=sid)

@sio.event
async def provideMoreDetails(sid, data):
    """
    Handle when user provides additional details after selecting "None of the above".
    Expected data: {
        "originalQuestion": str,
        "additionalDetails": str,
        "conversationId": str (optional)
    }
    """
    try:
        from src.classification.clarification_handler import reclassify_with_additional_context
        
        original_question = data.get("originalQuestion")
        additional_details = data.get("additionalDetails")
        conversation_id = data.get("conversationId") or client_conversations.get(sid)
        
        print(f"💬 [More Details] User {sid} provided: {additional_details}")
        
        # Create logger
        logger = AgentLogger()
        logger.log("💬 [More Details] Reclassifying with additional context", {
            "sid": sid,
            "originalQuestion": original_question,
            "additionalDetails": additional_details
        })
        
        # Get conversation history
        history = await get_conversation_history(conversation_id, limit=10)
        
        # Save user's additional details as a message
        await add_message(conversation_id, "user", additional_details)
        
        # Reclassify with additional context
        classification_result = await reclassify_with_additional_context(
            original_question=original_question,
            additional_details=additional_details,
            conversation_history=history,
            logger=logger
        )
        
        # Process with reclassified intent
        enhanced_question = f"{original_question}. {additional_details}"
        final_result = await route_query(enhanced_question, logger, history, conversation_id)
        
        if final_result is None:
            final_result = {
                "final_answer": "I encountered an issue. Please try again or contact a librarian.",
                "selected_agents": [],
                "classified_intent": "error"
            }
        
        final_answer = final_result.get("final_answer", "")
        final_answer = clean_response_for_frontend(final_answer)
        
        # Save assistant message
        message_id = await add_message(conversation_id, "assistant", final_answer)
        
        # Update tools used
        agents_used = final_result.get("selected_agents", [])
        if "tool_used" in final_result:
            agents_used = [final_result["tool_used"]]
        await update_conversation_tools(conversation_id, agents_used)
        
        # Send response
        response_data = json_serializable({
            "messageId": message_id,
            "message": final_answer,
            "conversationId": conversation_id,
            "intent": final_result.get("classified_intent"),
            "agents_used": agents_used,
            "needs_human": final_result.get("needs_human", False),
            "reclassified": True
        })
        
        await sio.emit("message", response_data, to=sid)
        
        logger.log("✅ [More Details] Reclassified and responded successfully")
        
    except Exception as e:
        print(f"❌ [More Details] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        await sio.emit("message", json_serializable({
            "messageId": None,
            "message": "I encountered an error processing your details. Please try again or contact a librarian.",
            "error": str(e)
        }), to=sid)

# uvicorn entry: uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload
