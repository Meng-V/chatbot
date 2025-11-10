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

**Backend**: Python 3.12, FastAPI, LangGraph, OpenAI o4-mini, Prisma, Socket.IO  
**Frontend**: React 18, Vite, Chakra UI, Socket.IO Client  
**Databases**: PostgreSQL (conversations), Weaviate (vector RAG)  
**APIs**: Primo, LibCal, LibGuides, LibAnswers, Google CSE

### Project Structure

```
chatbot/
├── .env                    # Environment configuration
├── local-auto-start.sh     # Dev startup script
├── ai-core/                # Python backend
│   ├── src/
│   │   ├── main.py         # FastAPI entry
│   │   ├── agents/         # AI agents
│   │   ├── graph/          # LangGraph orchestration
│   │   └── tools/          # Agent tools
│   └── tests/              # Test suite
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/
│   │   └── context/
│   └── vite.config.js
└── prisma/schema.prisma    # Database schema
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
prisma generate
```

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

1. User sends message via frontend
2. Socket.IO transmits to backend
3. **Hybrid Router** analyzes complexity:
   - Simple → Function Calling (fast)
   - Complex → LangGraph orchestration
4. **Meta Router** selects agents (1-6)
5. **Agents execute** in parallel
6. **LLM synthesizes** final answer
7. Response sent back via Socket.IO
8. Conversation saved to PostgreSQL

### Six Specialized Agents

| Agent | Purpose | API |
|-------|---------|-----|
| **Primo** | Catalog search | Ex Libris Primo |
| **LibCal** | Hours & rooms | SpringShare LibCal |
| **LibGuide** | Subject guides | SpringShare LibApps |
| **Google Site** | Website search | Google CSE |
| **LibChat** | Human handoff | LibAnswers |
| **Transcript RAG** | Memory/FAQs | Weaviate |

---

## 🎨 Customization

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
- **Agents**: `ai-core/src/agents/`
- **Tools**: `ai-core/src/tools/`
- **Orchestration**: `ai-core/src/graph/`
- **Frontend**: `client/src/`
- **Config**: `.env` (root), `client/.env`
- **Database schema**: `prisma/schema.prisma`

---

## 📚 Additional Resources

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

**Built by Miami University Libraries Web Services Team**  
**Version 1.0.0 | November 2025**
