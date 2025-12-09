# Developer Guide: Miami University Libraries Smart Chatbot

Complete technical documentation for deploying, customizing, and extending this AI chatbot system.

---

## 📋 Quick Navigation

- [System Overview](#system-overview)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development-setup)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration-guide)
- [Architecture](#architecture)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## 🏗️ System Overview

### Technology Stack

**Backend**: Python 3.12, FastAPI, LangGraph, OpenAI o4-mini, Prisma, Python-SocketIO, Uvicorn  
**Frontend**: React 19, Vite 7, Chakra UI, Socket.IO Client  
**Databases**: PostgreSQL (conversations + MuGuide subjects), Weaviate (vector RAG)  
**APIs**: Primo, LibCal, LibGuides, LibAnswers, Google CSE, MuGuide  
**Key Features**: Hybrid routing, strict scope enforcement, 710 subjects mapped, contact validation, URL validation

### Project Structure

```
chatbot/
├── .env                           # Consolidated environment config
├── .env.example                   # Template with all variables
├── .env.local                     # Local overrides (gitignored)
├── local-auto-start.sh            # Dev startup script
├── README.md                      # User guide
├── doc/                           # Documentation
│   ├── DEVELOPER_GUIDE.md         # This file
│   ├── SCOPE_ENFORCEMENT_REPORT.md    # Scope boundaries & rules
│   ├── MUGUIDE_INTEGRATION_REPORT.md  # Subject mapping integration
│   ├── KNOWLEDGE_MANAGEMENT.md        # Knowledge base management
│   ├── KNOWLEDGE_MANAGEMENT_GUIDE.md  # Detailed KB guide
│   └── LIBGUIDE_VS_MYGUIDE_ROUTING.md # Routing strategy
├── ai-core/                       # Python backend
│   ├── src/
│   │   ├── main.py                # FastAPI app, Socket.IO, lifecycle
│   │   ├── state.py               # LangGraph state definition
│   │   ├── agents/                # 8 AI agents
│   │   │   ├── base_agent.py      # Base class for multi-tool agents
│   │   │   ├── primo_multi_tool_agent.py
│   │   │   ├── libcal_comprehensive_agent.py
│   │   │   ├── libguide_comprehensive_agent.py
│   │   │   ├── google_site_comprehensive_agent.py
│   │   │   ├── subject_librarian_agent.py  # MuGuide routing
│   │   │   ├── libchat_agent.py
│   │   │   └── transcript_rag_agent.py
│   │   ├── graph/                 # Routing & orchestration
│   │   │   ├── hybrid_router.py   # Complexity analyzer
│   │   │   ├── function_calling.py # Fast mode
│   │   │   └── orchestrator.py    # Meta router + LangGraph
│   │   ├── tools/                 # Agent tools
│   │   │   ├── *_tools.py         # Tool implementations
│   │   │   ├── subject_matcher.py # Fuzzy subject matching
│   │   │   └── url_validator.py   # URL validation
│   │   ├── config/                # Configuration
│   │   │   └── scope_definition.py # Scope boundaries
│   │   ├── services/              # External services
│   │   │   └── oauth_service.py   # OAuth token management
│   │   ├── database/              # Database
│   │   │   └── prisma_client.py
│   │   ├── memory/                # Conversation management
│   │   │   └── conversation_store.py
│   │   ├── api/                   # API endpoints
│   │   │   ├── health.py
│   │   │   └── summarize.py
│   │   └── utils/                 # Utilities
│   │       └── logger.py
│   ├── scripts/                   # Utility scripts
│   │   └── ingest_muguide.py      # MuGuide data ingestion
│   ├── tests/                     # Test suite
│   └── pyproject.toml             # Python dependencies
├── client/                        # React 19 frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatBotComponent.jsx
│   │   │   ├── HumanLibrarianWidget.jsx
│   │   │   ├── FeedbackFormComponent.jsx
│   │   │   └── ...
│   │   ├── context/
│   │   │   ├── SocketContextProvider.jsx
│   │   │   └── MessageContextProvider.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── vite.config.js
│   └── package.json
└── prisma/
    └── schema.prisma              # Database schema
```

---

## ✅ Prerequisites

### Required Software
- **Python 3.12+**
- **Node.js 18+**
- **PostgreSQL 14+**
- **Git**

### Required API Keys
1. **OpenAI** - API key for o4-mini model
2. **Weaviate Cloud** - Vector database
3. **Primo** - Ex Libris discovery search
4. **SpringShare** - OAuth for LibCal, LibGuides, LibAnswers
5. **Google Custom Search** - CSE ID and API key

---

## 🚀 Local Development Setup

### Step 1: Clone & Configure

```bash
git clone https://github.com/your-org/chatbot.git
cd chatbot

# Copy and edit environment file
cp .env.example .env
nano .env
```

**Key .env Settings for Development:**
```bash
NODE_ENV=development
FRONTEND_URL=http://localhost:5173
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=o4-mini
OPENAI_ORGANIZATION_ID=your-org-id
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

### Step 2: Backend Setup

```bash
cd ai-core
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install --upgrade pip
pip install -e .

# Generate Prisma client and push schema to database
prisma generate
prisma db push

# IMPORTANT: Configure MuGuide credentials in .env before running ingestion
# Edit root .env and add:
#   MUGUIDE_ID=your_muguide_id_here
#   MUGUIDE_API_KEY=your_muguide_api_key_here
# (Contact library web services for credentials)

# Ingest MuGuide subject mapping data (710 subjects)
python scripts/ingest_muguide.py
```

**Expected Output:**
```
✅ Fetched 710 subjects
✅ Ingestion complete!
   Ingested: 710
   Total LibGuides: 587
   Total Major Codes: 586
```

**Note**: If you see "MuGuide API credentials not found" error, ensure `MUGUIDE_ID` and `MUGUIDE_API_KEY` are set in your root `.env` file. See `.env.example` for template.

### Step 3: Frontend Setup

```bash
cd client
npm install

# Edit client/.env
nano .env
```

**Client .env for Development:**
```bash
VITE_BACKEND_PORT=8000
VITE_SOCKET_DOMAIN=http://localhost:8000
VITE_BASE_PATH=/smartchatbot
```

### Step 4: Start Development

**Automated (Recommended):**
```bash
./local-auto-start.sh
```

**Manual:**
```bash
# Terminal 1 - Backend
cd ai-core && source .venv/bin/activate
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Frontend
cd client && npm run start
```

### Step 5: Verify

```bash
# Health check
curl http://localhost:8000/health

# Test query
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does the library close?"}'

# Visit frontend
open http://localhost:5173/smartchatbot
```

---

## 🌐 Production Deployment

### Server Preparation

```bash
# Ubuntu 20.04+ server
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv nodejs npm \
  postgresql-client git nginx certbot

# SSL certificate
sudo certbot certonly --nginx -d new.lib.miamioh.edu
```

### Deployment Steps

**1. Clone and Configure**
```bash
cd /var/www/
sudo git clone https://github.com/your-org/chatbot.git
cd chatbot

# Edit .env for production
nano .env
```

**Production .env:**
```bash
NODE_ENV=production
FRONTEND_URL=https://new.lib.miamioh.edu
BACKEND_PORT=8000
```

**2. Backend Setup**
```bash
cd /var/www/chatbot/ai-core
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
prisma generate
```

**3. Frontend Build**
```bash
cd /var/www/chatbot/client

# Edit client/.env
VITE_BACKEND_URL=https://new.lib.miamioh.edu
VITE_SOCKET_DOMAIN=

npm install
npm run build
```

**4. Systemd Services**

Backend service: `/etc/systemd/system/chatbot-backend.service`
```ini
[Unit]
Description=Chatbot Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/chatbot/ai-core
Environment="PATH=/var/www/chatbot/ai-core/.venv/bin"
ExecStart=/var/www/chatbot/ai-core/.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot-backend
sudo systemctl start chatbot-backend
```

**5. Nginx Configuration**

```nginx
upstream chatbot_backend {
    server localhost:8000;
}

server {
    listen 443 ssl http2;
    server_name new.lib.miamioh.edu;

    ssl_certificate /etc/letsencrypt/live/new.lib.miamioh.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/new.lib.miamioh.edu/privkey.pem;

    # Frontend static files
    location /smartchatbot {
        alias /var/www/chatbot/client/dist;
        try_files $uri $uri/ /smartchatbot/index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://chatbot_backend/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Socket.IO
    location /smartchatbot/socket.io/ {
        proxy_pass http://chatbot_backend/smartchatbot/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Health check
    location /health {
        proxy_pass http://chatbot_backend/health;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## ⚙️ Configuration Guide

### Environment Variables

**Development vs Production:**

| Variable | Development | Production |
|----------|-------------|------------|
| `NODE_ENV` | `development` | `production` |
| `FRONTEND_URL` | `http://localhost:5173` | `https://new.lib.miamioh.edu` |
| `VITE_SOCKET_DOMAIN` | `http://localhost:8000` | `` (empty) |

### Switching Environments

**To Development:**
```bash
# Root .env
NODE_ENV=development
FRONTEND_URL=http://localhost:5173

# client/.env
VITE_SOCKET_DOMAIN=http://localhost:8000
```

**To Production:**
```bash
# Root .env
NODE_ENV=production
FRONTEND_URL=https://new.lib.miamioh.edu

# client/.env
VITE_SOCKET_DOMAIN=
```

---

## 🏛️ Architecture

### Request Flow

1. **User sends message** via frontend (React 19)
2. **Socket.IO transmits** to backend via WebSocket (`/smartchatbot/socket.io`)
3. **Hybrid Router** (o4-mini) analyzes query complexity:
   - **Simple query** → Function Calling Mode (< 2 seconds)
     - LLM selects single tool
     - Direct execution
     - Immediate response
   - **Complex query** → LangGraph Orchestration (3-5 seconds)
     - Meta Router classifies intent
     - Scope enforcement check
     - Multi-agent coordination
4. **Meta Router** (LangGraph mode only) classifies intent:
   - **Out-of-scope** (general university, homework) → Polite redirect with appropriate links
   - **In-scope** (library) → Selects 1-7 domain agents based on intent
5. **Agents execute** in parallel (asyncio.gather)
6. **URL Validation** checks all URLs in responses
7. **LLM synthesizes** final answer with strict formatting rules
8. **Response sent** back via Socket.IO
9. **Conversation saved** to PostgreSQL with metadata (tokens, agents used, ratings)

### Eight Specialized Agents

| Agent | Type | Purpose | API/Service | Data Source |
|-------|------|---------|-------------|-------------|
| **Hybrid Router** | Router | Complexity analysis & mode selection | OpenAI o4-mini | N/A |
| **Primo** | Multi-tool | Catalog search & availability | Ex Libris Primo | Library catalog |
| **LibCal** | Multi-tool | Hours & room reservations | SpringShare LibCal | Events/spaces |
| **LibGuide** | Multi-tool | Course & subject guides | SpringShare LibApps | Research guides |
| **Google Site** | Multi-tool | Website content search | Google CSE | lib.miamioh.edu |
| **Subject Librarian** | Function | Subject-to-librarian routing | MuGuide + LibGuides API | 710 mapped subjects |
| **LibChat** | Function | Human handoff | LibAnswers | Chat widget |
| **Transcript RAG** | Function | Memory/FAQ search | Weaviate | Vector database |

**Multi-tool agents** extend `BaseAgent` and can route to multiple tools internally.  
**Function agents** are simpler, single-purpose async functions.

### Scope Enforcement

The chatbot has **strict boundaries** enforced at multiple levels:

**1. Meta Router Classification**
- Analyzes every query for scope before processing
- Classifies as `out_of_scope` if not library-related
- Provides polite redirect with appropriate contact information

**2. Synthesis Prompt Enforcement**
- System prompts emphasize LIBRARIES-only responses
- NEVER answers general university questions
- Automatically suggests appropriate services

**3. URL Validation** (NEW in v2.1)
- Post-synthesis URL checking
- Only allows: `lib.miamioh.edu`, `libguides.lib.miamioh.edu`, `digital.lib.miamioh.edu`
- Removes hallucinated or incorrect URLs

**✅ IN SCOPE - Answers Provided:**
- Library resources, services, spaces, staff, policies
- ONLY Miami University **LIBRARIES** (not general university)

**❌ OUT OF SCOPE - Redirected:**
- General university (admissions, housing, courses, campus life)
- Course content, homework, assignments, test prep
- IT support (Canvas, email) unless library-specific
- Student services (advising, health, counseling)
- Non-library facilities

**🔒 Contact Validation:**
- NEVER makes up emails, phone numbers, or names
- All contact info from verified APIs (LibGuides, MuGuide DB)
- Fallback to general library contact: (513) 529-4141

See [SCOPE_ENFORCEMENT_REPORT.md](../SCOPE_ENFORCEMENT_REPORT.md) for complete details.

---

## 🎨 Customization

### 📖 Correcting AI Responses & Updating Knowledge

**IMPORTANT**: For detailed instructions on correcting AI mistakes, updating chatbot knowledge, and refining responses, see the **[Knowledge Management Guide](KNOWLEDGE_MANAGEMENT.md)**.

That guide covers:
- How to update AI responses when it makes mistakes
- Adding new facts to the vector database (Weaviate)
- Modifying system prompts for behavior changes
- Adding few-shot examples for specific patterns
- Maintenance schedules and best practices

The following sections cover code-level customization for developers.

---

### 1. Add New Agent

```python
# ai-core/src/agents/my_agent.py
from src.agents.base_agent import Agent
from src.tools.my_tools import MyTool

class MyAgent(Agent):
    def __init__(self):
        super().__init__(name="my_agent", description="My agent description")
        self.register_tool(MyTool())
    
    async def route_to_tool(self, state):
        return "my_tool"
```

Register in `ai-core/src/graph/orchestrator.py`:
```python
from src.agents.my_agent import MyAgent

agent_map = {
    # ... existing agents
    "my_agent": MyAgent(),
}
```

### 2. Change LLM Model

```bash
# In .env
OPENAI_MODEL=gpt-4o  # or gpt-4-turbo, gpt-3.5-turbo

# Note: Models starting with "o" (like o4-mini) don't support temperature=0
```

### 3. Customize Response Format

Edit `ai-core/src/graph/orchestrator.py`:
```python
FORMATTING_GUIDELINES = """
- Use **bold** for your key info
- Customize bullet style
- Set your tone and voice
"""
```

### 4. Change Theme Colors

Edit `client/src/components/ChatBotComponent.css`:
```css
/* Change from Miami red to your color */
.chat-message-container strong {
  color: #your-institution-color;
}
```

### 5. Update MuGuide Subject Mappings

The MuGuide subject-to-librarian mappings should be refreshed when:
- New academic programs are added
- Department reorganizations occur
- New LibGuides are created
- Subject assignments change

**Refresh MuGuide Data:**
```bash
cd ai-core
source .venv/bin/activate
python scripts/ingest_muguide.py
```

**Recommended frequency:** Monthly or when notified of changes

**Monitor Coverage:**
```sql
-- Check subjects without LibGuides
SELECT s.name FROM "Subject" s
LEFT JOIN "SubjectLibGuide" slg ON s.id = slg."subjectId"
WHERE slg.id IS NULL;

-- Total subject count
SELECT COUNT(*) FROM "Subject";
```

### 6. Modify Scope Boundaries

Edit `ai-core/src/config/scope_definition.py` to adjust what the chatbot can answer:

```python
IN_SCOPE_TOPICS = {
    "library_resources": [
        # Add new in-scope topics
    ],
    ...
}

OUT_OF_SCOPE_TOPICS = {
    "university_general": [
        # Add new out-of-scope topics
    ],
    ...
}
```

After changes, update the router prompt in `ai-core/src/graph/orchestrator.py` if needed.

---

## 🧪 Testing

```bash
cd ai-core

# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=src --cov-report=html

# Manual test queries
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"TEST_QUERY"}'
```

---

## 🔧 Troubleshooting

### Backend Won't Start

**Port in use:**
```bash
lsof -ti:8000 | xargs kill -9
```

**Missing Prisma client:**
```bash
cd ai-core
prisma generate
```

**Import errors:**
```bash
pip install -e .
```

### Frontend Connection Issues

**Socket.IO not connecting:**
- Check `VITE_SOCKET_DOMAIN` in `client/.env`
- Development: `http://localhost:8000`
- Production: empty string

**CORS errors:**
- Verify `NODE_ENV` in root `.env`
- Development allows all origins
- Production restricts to `FRONTEND_URL`

### Database Issues

**Prisma connection:**
```bash
# Test connection
psql "postgresql://user:pass@host:5432/db?sslmode=require"
```

**Weaviate connection:**
```bash
# Verify credentials
curl -H "Authorization: Bearer KEY" \
  https://your-instance.weaviate.cloud/v1/schema
```

### Logging

```bash
# Backend logs
sudo journalctl -u chatbot-backend -f

# Or manual debug mode
cd ai-core
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --log-level debug

# Frontend console
# Press F12 in browser, check Console tab
```

---

## 📝 Quick Reference

### Common Commands

```bash
# Start dev environment
./local-auto-start.sh

# Backend only
cd ai-core && source .venv/bin/activate
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload

# Frontend only
cd client && npm run start

# Run tests
cd ai-core && pytest tests/ -v

# Check health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs
```

### File Locations

- **Backend code**: `ai-core/src/`
- **Agents**: `ai-core/src/agents/` (7 agents including Subject Librarian)
- **Tools**: `ai-core/src/tools/` (includes `subject_matcher.py`)
- **Orchestration**: `ai-core/src/graph/orchestrator.py` (meta router + scope enforcement)
- **Configuration**: `ai-core/src/config/scope_definition.py` (scope boundaries)
- **Scripts**: `ai-core/scripts/ingest_muguide.py` (MuGuide data ingestion)
- **Frontend**: `client/src/`
- **Environment**: `.env` (root consolidated), `.env.local` (local overrides)
- **Database schemas**: 
  - `prisma/schema.prisma` (JavaScript/TypeScript client)
  - `ai-core/schema.prisma` (Python client with Subject tables)
- **Documentation**:
  - `SCOPE_ENFORCEMENT_REPORT.md` (scope rules)
  - `MUGUIDE_INTEGRATION_REPORT.md` (subject mapping)

---

## 📚 Additional Resources

### Project Documentation
- **User Guide**: `README.md` - Overview for librarians and administrators with scope boundaries
- **Developer Guide**: `doc/DEVELOPER_GUIDE.md` - This document
- **Knowledge Management Guide**: `KNOWLEDGE_MANAGEMENT.md` - How to correct AI responses and update chatbot knowledge
- **Scope Enforcement Report**: `SCOPE_ENFORCEMENT_REPORT.md` - Complete scope boundaries, validation rules, and enforcement mechanisms
- **MuGuide Integration Report**: `MUGUIDE_INTEGRATION_REPORT.md` - Subject mapping system technical documentation (710 subjects)
- **Environment Guide**: `ENV_QUICK_REFERENCE.md` - Environment configuration reference
- **Environment Consolidation**: `ENV_CONSOLIDATION_SUMMARY.md` - How environment files were consolidated

### External Documentation
- **FastAPI**: https://fastapi.tiangolo.com/
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **Prisma Python**: https://prisma-client-py.readthedocs.io/
- **Socket.IO**: https://socket.io/docs/v4/
- **React**: https://react.dev/

---

## 📞 Support

- **Technical Issues**: libwebservices@miamioh.edu
- **GitHub**: [Repository Issues]
- **Documentation**: See `/docs` endpoint when backend is running

---

**Developed by Meng Qu, Miami University Libraries - Oxford, OH**  
**Version 2.3.0 | December 9, 2025**

**What's New in 2.3:**
- ✅ **Multi-Campus Support**: Full support for Oxford, Hamilton, and Middletown campuses
- ✅ **Enhanced LibAnswers Integration**: Ask Us Chat Service hours API
- ✅ **Campus-Specific Building IDs**: Organized environment variables by campus
- ✅ **Real-time Librarian Availability**: Check human chat service hours

**Previous Features (2.0-2.2):**
- ✅ **Strict Scope Enforcement**: ONLY answers library questions (not general university)
- ✅ **MuGuide Integration**: 710 subjects mapped to LibGuides and librarians
- ✅ **Contact Validation**: NEVER makes up emails, phone numbers, or names
- ✅ **8 Specialized Agents**: Including Subject Librarian for subject-to-librarian routing
- ✅ **Weaviate RAG**: 1,568 Q&A pairs with fact grounding
- ✅ **Hybrid Routing**: Function calling + LangGraph orchestration
