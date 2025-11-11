# AI-Core Backend

**Python FastAPI + LangGraph backend for Miami University Libraries Smart Chatbot**

This is the intelligent backend powering the chatbot with 6 specialized AI agents orchestrated by LangGraph.

---

## 🎯 Key Features

- **Strict Scope Enforcement**: ONLY answers Miami University LIBRARIES questions (not general university)
- **Hybrid Router**: Automatically selects between fast function calling and complex multi-agent orchestration
- **7 Specialized Agents**: Primo, LibCal, LibGuide, Google Site, Subject Librarian, LibChat, Transcript RAG
- **Meta Router**: OpenAI o4-mini classifies user intent and detects out-of-scope questions
- **MuGuide Integration**: 710 subjects mapped to LibGuides and subject librarians
- **Contact Info Validation**: NEVER makes up emails, phone numbers, or names - only uses verified API data
- **Real-time Communication**: Socket.IO for WebSocket support
- **OAuth Integration**: Centralized token management for SpringShare APIs
- **Vector Search**: Weaviate integration for FAQ/documentation RAG
- **Production Ready**: Health monitoring, auto-restart, comprehensive logging

## 🚀 Quick Start

### Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or .venv\Scripts\activate on Windows

# Install dependencies
pip install --upgrade pip
pip install -e .

# Generate Prisma client
prisma generate
```

### Configuration

The backend loads configuration from the **root `.env` file** (located at project root, not in ai-core directory).

```bash
# Navigate to project root
cd ..

# Copy template
cp .env.example .env

# Edit with your API keys
nano .env

# Optional: Create .env.local for local overrides (already in .gitignore)
cp .env.local.example .env.local
nano .env.local
```

**Environment File Structure:**
- `.env` - Main configuration file (contains all production values)
- `.env.local` - Local development overrides (not committed to git)
- `.env.example` - Template with placeholder values

See `DEVELOPER_GUIDE.md` for complete configuration instructions.

### Running

```bash
# Development (with auto-reload)
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
```

### Verification

```bash
# Health check
curl http://localhost:8000/health

# Test query
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does King Library close?"}'

# API documentation
open http://localhost:8000/docs
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_all_agents.py -v
```

## 📡 API Endpoints

- **GET /health** - System health and status
- **GET /readiness** - Readiness probe for orchestration
- **GET /metrics** - Performance metrics
- **POST /ask** - Main chat endpoint (HTTP JSON)
- **WebSocket** - `/smartchatbot/socket.io` - Real-time communication
- **GET /docs** - Interactive API documentation (Swagger UI)
- **GET /redoc** - Alternative API documentation

## 🏛️ Architecture

```
Request Flow:
User Message
    ↓
Hybrid Router (complexity analysis)
    ↓
    ├─→ Simple: Function Calling (fast)
    └─→ Complex: LangGraph Orchestration
            ↓
        Meta Router (intent classification)
            ↓
        Agent Selection (1-6 agents)
            ↓
        Parallel Execution
            ↓
        LLM Synthesis
            ↓
        Response to User
```

### Directory Structure

```
src/
├── main.py              # FastAPI app, Socket.IO, CORS
├── state.py             # LangGraph state definition
├── agents/              # Specialized agents
│   ├── base_agent.py
│   ├── primo_multi_tool_agent.py
│   ├── libcal_comprehensive_agent.py
│   ├── libguide_comprehensive_agent.py
│   ├── google_site_comprehensive_agent.py
│   ├── libchat_agent.py
│   └── transcript_rag_agent.py
├── graph/               # LangGraph orchestration
│   ├── orchestrator.py      # Main workflow
│   ├── function_calling.py  # Fast mode
│   └── hybrid_router.py     # Smart routing
├── tools/               # Agent tools
├── services/            # OAuth services
├── database/            # Prisma client
├── memory/              # Conversation storage
├── api/                 # Health/monitoring
└── utils/               # Logging, helpers
```

## 🎨 Customization

See `DEVELOPER_GUIDE.md` for detailed instructions on:
- Adding new agents
- Changing the LLM model
- Customizing response formatting
- Integrating new APIs

## 📚 Documentation

- **User Guide**: See root `README.md`
- **Developer Guide**: See root `DEVELOPER_GUIDE.md`
- **API Docs**: http://localhost:8000/docs (when running)

## 🔧 Troubleshooting

**Port in use:**
```bash
lsof -ti:8000 | xargs kill -9
```

**Import errors:**
```bash
pip install -e .
```

**Prisma not generated:**
```bash
prisma generate
```

**Database connection:**
```bash
# Verify DATABASE_URL in root .env
psql "postgresql://..."
```

---

**For complete documentation, see [DEVELOPER_GUIDE.md](../DEVELOPER_GUIDE.md)**
