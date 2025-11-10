# Miami University Libraries AI-Core
**LangGraph-based chatbot backend with 6 specialized agents**

## Architecture
- **Meta Router**: GPT-4o-mini classifies user intent
- **6 Agents**:
  1. Primo Agent (discovery search)
  2. LibCal Agent (hours, room booking)
  3. LibGuide/MyGuide Agent (course guides, librarians)
  4. Google Site Search Agent (policies, services)
  5. LibChat Agent (human handoff)
  6. Transcript RAG Agent (Weaviate vector search)
- **Orchestrator**: LangGraph manages agent execution and synthesis

## Quickstart
```bash
# Setup
cd ai-core
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -e .

# Configure (uses project root .env file)
# The ai-core service loads environment variables from the root .env file
# No separate .env needed in ai-core directory

# Run
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000

# Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does King Library close?"}'
```

## Testing
```bash
pytest tests/ -v
```

## Endpoints
- `GET /health` - Health check
- `POST /ask` - Main chat endpoint (JSON)
- Socket.IO: `/smartchatbot/socket.io` (legacy)

## Development
- Add agents: `src/agents/your_agent.py`
- Update routing: `src/graph/orchestrator.py`
- Change classification: Edit `ROUTER_SYSTEM_PROMPT`
