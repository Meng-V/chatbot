# Architecture Documentation

## Overview

This folder contains technical architecture documentation, system design diagrams, and developer resources for the Miami University Library Chatbot.

---

## 📚 Documentation Files

### System Design
- **[01-SYSTEM-ARCHITECTURE.md](./01-SYSTEM-ARCHITECTURE.md)** - Complete system architecture with diagrams and component descriptions

### Developer Resources
- **[02-DEVELOPER-GUIDE.md](./02-DEVELOPER-GUIDE.md)** - Complete setup guide for developers, contribution guidelines

### Project Overview
- **[03-PROJECT-SUMMARY.md](./03-PROJECT-SUMMARY.md)** - 2025 RAG implementation project summary and achievements

---

## 🏗️ System Components

### Frontend
- **Technology**: React + Vite
- **Location**: `/client/`
- **Purpose**: User interface for students and library staff

### Backend (AI Core)
- **Technology**: Python + LangGraph + FastAPI
- **Location**: `/ai-core/`
- **Purpose**: AI orchestration, agent coordination, RAG queries

### Database
- **Technology**: PostgreSQL + Prisma ORM
- **Location**: `/prisma/`
- **Purpose**: Conversation history, tool execution logging, analytics

### Vector Database
- **Technology**: Weaviate Cloud
- **Purpose**: Semantic search over 1,568 Q&A pairs

---

## 🔄 Request Flow

```
Student Question
      ↓
React Client (Socket.IO)
      ↓
FastAPI Backend (main.py)
      ↓
Hybrid Router (routing logic)
      ↓
Meta Router (intent classification)
      ↓
Orchestrator (parallel agent execution)
      ↓
├── Google Site Agent (library website search)
├── Transcript RAG Agent (Weaviate knowledge base)
├── MyGuide Agent (research guides)
└── Discovery Agent (catalog & database search)
      ↓
Synthesizer (combine results + fact grounding)
      ↓
Response to Student ✓
```

---

## 🎯 Key Features

### Intent Classification
Uses OpenAI to classify student questions into categories:
- Discovery Search (books, databases)
- Policy & Service (hours, borrowing)
- Research Help (citations, guides)
- Technical Support (printing, access)

### Parallel Agent Execution
Multiple specialized agents run simultaneously for comprehensive answers

### Fact Grounding
Ensures factual accuracy by requiring high confidence for policy/service questions

### Conversation Memory
Stores full conversation history in PostgreSQL for continuity

---

## 🛠️ Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **Backend** | Python | 3.12+ |
| **AI Framework** | LangGraph | Latest |
| **LLM** | OpenAI o4-mini | Latest |
| **Embeddings** | text-embedding-3-small | 1536-dim |
| **Vector DB** | Weaviate Cloud | Latest |
| **Database** | PostgreSQL | 14+ |
| **ORM** | Prisma | Latest |
| **Frontend** | React + Vite | Latest |
| **Communication** | Socket.IO | Real-time |

---

## 📁 Directory Structure

```
/chatbot/
├── ai-core/              # Backend AI system
│   ├── src/              # Source code
│   │   ├── agents/       # Specialized agents
│   │   ├── graph/        # LangGraph orchestration
│   │   ├── database/     # Prisma client
│   │   └── main.py       # FastAPI entry point
│   ├── scripts/          # Utility scripts
│   └── data/             # Q&A data
├── client/               # React frontend
│   └── src/              # Frontend source
├── prisma/               # Database schema
├── docs/                 # All documentation
└── README.md             # Main README
```

---

## 🚀 Quick Start for Developers

```bash
# 1. Clone repository
git clone <repository-url>
cd chatbot

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Install Python dependencies
cd ai-core
pip install -r requirements.txt

# 4. Set up database
cd ..
npx prisma generate
npx prisma db push

# 5. Install frontend dependencies
cd client
npm install

# 6. Start backend
cd ../ai-core
python src/main.py

# 7. Start frontend (in new terminal)
cd ../client
npm run dev
```

📖 **Full Setup**: [02-DEVELOPER-GUIDE.md](./02-DEVELOPER-GUIDE.md)

---

## 📊 Performance Metrics

- **Response Time**: ~2-3 seconds average
- **Agent Execution**: Parallel (simultaneous)
- **Weaviate Query**: ~500ms average
- **Conversation History**: Unlimited
- **Concurrent Users**: Scalable via Socket.IO

---

## 🔐 Security Features

- **PII Removal**: Automatically filters personal information from transcripts
- **API Key Management**: Environment variables only
- **Input Validation**: All user inputs sanitized
- **Scope Enforcement**: Only answers library-related questions

---

## 📖 Reading Order

For developers:
1. [02-DEVELOPER-GUIDE.md](./02-DEVELOPER-GUIDE.md) - Start here
2. [01-SYSTEM-ARCHITECTURE.md](./01-SYSTEM-ARCHITECTURE.md) - Understand the system
3. [03-PROJECT-SUMMARY.md](./03-PROJECT-SUMMARY.md) - Recent improvements

For system administrators:
1. [01-SYSTEM-ARCHITECTURE.md](./01-SYSTEM-ARCHITECTURE.md) - Full architecture
2. [03-PROJECT-SUMMARY.md](./03-PROJECT-SUMMARY.md) - What's new

---

**Build on a solid foundation!** 🏗️

---

**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH
