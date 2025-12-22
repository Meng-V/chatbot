# AI-Core Backend

**Python FastAPI + LangGraph backend for Miami University Libraries Smart Chatbot**

## What This Does (For Non-Technical Readers)

This is the **"brain" of the library chatbot** - the backend system that:
- 🧠 Understands what users are asking (even when questions are unclear)
- 🎯 Decides which library services to check (hours, guides, librarians, etc.)
- 📞 Calls external APIs to get current, accurate information
- 💬 Generates natural, helpful responses in under 5 seconds
- ✅ Verifies all information before responding (never makes up phone numbers or websites)

**Key Benefit for Libraries:** Handles routine questions 24/7, reducing workload for librarians while maintaining accuracy and professionalism.

---

## Technical Overview (For Developers)

This is the intelligent backend powering the chatbot with **RAG-based classification** and **5 specialized AI agents** orchestrated by a hybrid routing system that combines fast function calling with complex multi-agent orchestration.

---

Last update: 12/22/2025 Afternoon

## 🎯 Key Features

- **RAG-Based Classification**: Weaviate vector database classifies user intent with confidence scoring and margin-based ambiguity detection
- **Smart Clarification System**: Interactive button choices when questions are ambiguous - user-in-the-loop decision making
- **Hybrid Routing System**: Intelligently selects between fast function calling (simple queries) and LangGraph orchestration (complex queries)
- **5 Specialized Agents**: 
  - **LibCal** (Hours/Booking) - Multi-tool agent for hours and room reservations
  - **LibGuides** (Course Guides) - Multi-tool agent for research guides
  - **Google Site** (Website Search) - Multi-tool agent for library website content
  - **Subject Librarian** - MuGuide integration for 710 subjects with fuzzy matching
  - **LibChat** - Human handoff agent with real-time availability
- **Meta Router**: Intent classification with strict scope enforcement (libraries only)
- **Clarification Handler**: Processes user choice selections and reclassifies with additional context
- **Strict Scope Enforcement**: Automatically detects and redirects out-of-scope questions
- **MuGuide Integration**: 710 subjects, 587 LibGuides, 586 majors mapped with fuzzy matching
- **URL Validation**: Validates and filters URLs to prevent hallucination
- **Contact Info Validation**: NEVER generates fake contact information - only uses verified API data
- **Real-time Communication**: Socket.IO WebSocket at `/smartchatbot/socket.io`
- **OAuth Integration**: Centralized token management for SpringShare APIs (LibCal, LibGuides, LibAnswers)
- **Production Ready**: Health monitoring, auto-restart, comprehensive logging, token usage tracking

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
# Activate virtual environment first
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_all_agents.py -v

# Run specific test function
pytest tests/test_all_agents.py::test_primo_agent -v
```

## 📡 API Endpoints

### HTTP Endpoints
- **GET /health** - System health check (database, external APIs)
- **GET /readiness** - Kubernetes readiness probe
- **GET /metrics** - Performance metrics (future)
- **POST /ask** - HTTP chat endpoint (JSON request/response)
- **POST /summarize** - Generate conversation summaries
- **GET /docs** - Interactive API documentation (Swagger UI)
- **GET /redoc** - Alternative API documentation (ReDoc)

### WebSocket
- **Socket.IO** - `/smartchatbot/socket.io`
  - Event `connect` - Client connection
  - Event `message` - Send/receive chat messages
  - Event `messageRating` - Rate assistant responses (thumbs up/down)
  - Event `userFeedback` - Submit conversation feedback
  - Event `disconnect` - Client disconnection

## 🌌 Architecture

```
Request Flow:
User Message
    ↓
Hybrid Router (complexity analysis via o4-mini)
    ↓
    ├─→ SIMPLE: Function Calling Mode (< 2s)
    │       ↓
    │   LLM with function calling
    │       ↓
    │   Single tool execution
    │       ↓
    │   Direct response
    │
    └─→ COMPLEX: LangGraph Orchestration (3-5s)
            ↓
        Meta Router (intent classification + scope check)
            ↓
        Agent Selection (1-7 domain agents)
            ↓
        Parallel Execution (asyncio.gather)
            ↓
        URL Validation
            ↓
        LLM Synthesis (o4-mini)
            ↓
        Response to User

Key Components:
- Hybrid Router: src/graph/hybrid_router.py
- Function Calling: src/graph/function_calling.py  
- LangGraph Orchestrator: src/graph/orchestrator.py
- Scope Enforcement: src/config/scope_definition.py
- URL Validation: src/tools/url_validator.py
```

### Directory Structure

```
src/
├── main.py              # FastAPI app, Socket.IO, CORS, lifecycle
├── state.py             # LangGraph state definition
├── agents/              # 8 specialized agents
│   ├── base_agent.py                       # Base class for multi-tool agents
│   ├── primo_multi_tool_agent.py           # Discovery search
│   ├── libcal_comprehensive_agent.py       # Hours & booking
│   ├── libguide_comprehensive_agent.py     # Course guides
│   ├── google_site_comprehensive_agent.py  # Website search
│   ├── subject_librarian_agent.py          # Subject-to-librarian routing
│   ├── libchat_agent.py                    # Human handoff
│   └── transcript_rag_agent.py             # RAG memory
├── graph/               # Routing & orchestration
│   ├── hybrid_router.py     # Complexity analyzer & mode selector
│   ├── function_calling.py  # Fast mode for simple queries
│   └── orchestrator.py      # LangGraph workflow for complex queries
├── config/              # Configuration
│   └── scope_definition.py  # Scope boundaries & prompts
├── tools/               # Agent tools
│   ├── *_tools.py           # Tool implementations
│   ├── subject_matcher.py   # Fuzzy subject matching
│   └── url_validator.py     # URL validation
├── services/            # External services
│   └── oauth_service.py     # OAuth token management
├── database/            # Database clients
│   └── prisma_client.py     # Prisma connection
├── memory/              # Conversation management
│   └── conversation_store.py # DB operations
├── api/                 # API endpoints
│   ├── health.py            # Health checks
│   └── summarize.py         # Conversation summaries
└── utils/               # Utilities
    └── logger.py            # Logging utilities
```

## 🎨 Customization

See [Developer Guide](../docs/architecture/02-DEVELOPER-GUIDE.md) for detailed instructions on:
- **Adding new agents** - Extend the multi-tool agent base class
- **Changing the LLM model** - Update OPENAI_MODEL in .env
- **Modifying scope boundaries** - Edit `src/config/scope_definition.py`
- **Customizing response formatting** - Adjust synthesis prompts in orchestrator
- **Integrating new APIs** - Add to tools/ and create corresponding agents
- **Adjusting routing logic** - Modify hybrid_router.py complexity analysis

## 📚 Documentation

All comprehensive documentation is organized in the `/docs/` folder at project root:

### Quick Links
- **[Documentation Index](../docs/README.md)** - Complete navigation guide
- **[System Architecture](../docs/architecture/01-SYSTEM-ARCHITECTURE.md)** - Full system design
- **[Developer Guide](../docs/architecture/02-DEVELOPER-GUIDE.md)** - Setup and deployment
- **API Docs**: http://localhost:8000/docs (when running)

### By Feature Area
- **[Weaviate RAG](../docs/weaviate-rag/)** - Knowledge base management, record cleanup, fact correction
- **[Data Management](../docs/data-management/)** - Transcript processing, new year data, optimization
- **[Architecture](../docs/architecture/)** - System design, developer resources, project summary
- **[Knowledge Management](../docs/knowledge-management/)** - Guide routing, scope enforcement, integrations

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

## ⚙️ Version

- **AI-Core Version**: 3.1.0
- **Last Updated**: December 22, 2025
- **Python**: 3.13 (3.12 compatible)
- **LangGraph**: Latest
- **OpenAI Model**: o4-mini
- **FastAPI**: Latest
- **Prisma**: 0.15.0
- **Weaviate**: Cloud (RAG classification + correction pool)
- **Multi-Campus Support**: Oxford, Hamilton, Middletown libraries
- **New Features**: RAG classification, clarification choices, database-driven addresses

---

**Developed by Meng Qu, Miami University Libraries - Oxford, OH**

**For complete documentation, see [Documentation Index](../docs/README.md)**
