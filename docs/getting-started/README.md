# Getting Started with the Miami University Library Chatbot

## Welcome! 👋

This guide helps you understand and use the Miami University Library AI Chatbot system, whether you're a library manager, developer, or administrator.

---

## 📖 Who Should Read What?

### **Library Managers & Non-Technical Staff**
Start here to understand what the chatbot does and how to manage it:

1. **[Main README](../../README.md)** - Complete overview of chatbot capabilities
2. **[Weaviate RAG Quick Start](../weaviate-rag/04-CLEANUP-QUICKSTART.md)** - Update wrong answers
3. **[RAG Usage Tracking](../weaviate-rag/02-RAG-USAGE-TRACKING.md)** - View analytics

**Common Tasks:**
- ✅ Fix a wrong answer → [Record Management](../weaviate-rag/03-RECORD-MANAGEMENT.md)
- ✅ View chatbot usage → Run `/ai-core/scripts/analyze_rag_usage.py`
- ✅ Add new Q&A → Edit `/ai-core/scripts/update_rag_facts.py`

---

### **Developers & Technical Staff**
Technical setup and development:

1. **[Developer Guide](../architecture/02-DEVELOPER-GUIDE.md)** - Complete setup instructions
2. **[System Architecture](../architecture/01-SYSTEM-ARCHITECTURE.md)** - Understand the system
3. **[Weaviate Setup](../weaviate-rag/01-SETUP.md)** - Configure vector database

**Common Tasks:**
- ✅ Set up development environment → [Developer Guide](../architecture/02-DEVELOPER-GUIDE.md)
- ✅ Add a new agent → See agent examples in `/ai-core/src/agents/`
- ✅ Modify routing → Edit `/ai-core/src/graph/hybrid_router.py`

---

### **Data Managers**
Processing and managing transcript data:

1. **[Data Cleaning Strategy](../data-management/01-CLEANING-STRATEGY.md)** - Understand data processing
2. **[Process New Year Data](../data-management/02-PROCESS-NEW-YEAR-DATA.md)** - Add 2026+ data
3. **[Data Pipeline](../data-management/03-DATA-PIPELINE.md)** - Complete pipeline overview

**Common Tasks:**
- ✅ Add 2026 transcripts → [New Year Data Guide](../data-management/02-PROCESS-NEW-YEAR-DATA.md)
- ✅ Clean transcripts → Run `/ai-core/scripts/clean_transcripts.py`
- ✅ Optimize for search → Run `/ai-core/scripts/optimize_for_vector_search.py`

---

## 🚀 Quick Setup (5 Minutes)

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL 14+
- Git

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd chatbot
```

### Step 2: Set Up Environment
```bash
# Copy environment template
cp .env.example .env

# Edit with your API keys
nano .env
```

Required API keys:
- `OPENAI_API_KEY` - OpenAI o4-mini access
- `WEAVIATE_API_KEY` - Weaviate Cloud
- `WEAVIATE_HOST` - Weaviate cluster URL
- `DATABASE_URL` - PostgreSQL connection

### Step 3: Install Dependencies
```bash
# Backend (Python)
cd ai-core
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Database
cd ..
npx prisma generate
npx prisma db push

# Frontend (Node.js)
cd client
npm install
```

### Step 4: Start Services
```bash
# Terminal 1: Backend
cd ai-core
source .venv/bin/activate
python src/main.py

# Terminal 2: Frontend
cd client
npm run dev
```

### Step 5: Test
Visit http://localhost:5173 and ask: "What time does King Library close?"

✅ **Full Setup Guide**: [Developer Guide](../architecture/02-DEVELOPER-GUIDE.md)

---

## 📊 System Overview

### What Does It Do?
The chatbot helps students find library resources, check hours, book rooms, and get research help - 24/7.

### How Does It Work?
```
Student Question
      ↓
AI Classification (OpenAI o4-mini)
      ↓
8 Specialized Agents (parallel execution)
      ↓
Knowledge Base Search (Weaviate, 1,568 Q&A pairs)
      ↓
Response Synthesis
      ↓
Answer to Student ✓
```

### Key Features
- **8 Specialized Agents**: Discovery, Hours, Guides, Website Search, RAG, etc.
- **Hybrid Routing**: Fast function calling or complex orchestration
- **Fact Grounding**: Ensures factual accuracy
- **Scope Enforcement**: Only library-related questions
- **24/7 Availability**: Always online

---

## 🎯 Common Administrative Tasks

### Update a Wrong Answer

**Scenario**: Student reports chatbot gave wrong information

**Solution**:
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# 1. Find the problematic record
python scripts/find_problematic_rag_records.py --query "student's question"

# 2. Delete the bad record
python scripts/delete_weaviate_records.py --ids <RECORD_ID>

# 3. Add correct answer
python scripts/update_rag_facts.py
```

📖 **Full Guide**: [Record Management](../weaviate-rag/03-RECORD-MANAGEMENT.md)

---

### View Usage Analytics

**What**: See how often RAG is used, confidence levels, common queries

**How**:
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/analyze_rag_usage.py --detailed
```

📖 **Full Guide**: [RAG Usage Tracking](../weaviate-rag/02-RAG-USAGE-TRACKING.md)

---

### Add New Year Transcript Data

**When**: At the start of 2026, you want to add new year chat transcripts

**Steps**:
```bash
# 1. Place tran_raw_2026.csv in root directory

# 2. Process the data
cd ai-core
python scripts/process_new_year_data.py --year 2026

# 3. Optimize for vector search
python scripts/optimize_for_vector_search.py

# 4. Ingest into Weaviate
python scripts/ingest_transcripts_optimized.py
```

📖 **Full Guide**: [Process New Year Data](../data-management/02-PROCESS-NEW-YEAR-DATA.md)

---

### Find Low Quality Responses

**What**: Identify records that consistently have low confidence

**How**:
```bash
cd ai-core
python scripts/find_problematic_rag_records.py --low-confidence --days 30
```

📖 **Full Guide**: [Cleanup Quickstart](../weaviate-rag/04-CLEANUP-QUICKSTART.md)

---

## 📁 Important Directories

| Directory | Purpose | Who Uses It |
|-----------|---------|-------------|
| `/docs/` | All documentation | Everyone |
| `/ai-core/` | Backend Python code | Developers |
| `/ai-core/scripts/` | Management scripts | Library managers |
| `/ai-core/data/` | Q&A data (1,568 pairs) | Data managers |
| `/client/` | Frontend React app | Developers |
| `/prisma/` | Database schema | Developers |

---

## 🔑 Important Scripts

All scripts are in `/ai-core/scripts/`:

### For Library Managers
- `analyze_rag_usage.py` - View usage analytics
- `find_problematic_rag_records.py` - Find bad records
- `delete_weaviate_records.py` - Delete records
- `update_rag_facts.py` - Add/update Q&A
- `query_rag.py` - Test RAG queries

### For Data Managers
- `process_new_year_data.py` - Add new year data
- `clean_transcripts.py` - Clean transcript data
- `optimize_for_vector_search.py` - Optimize for search
- `ingest_transcripts_optimized.py` - Load into Weaviate

### For Developers
- `setup_weaviate.py` - Set up Weaviate
- `health_check.py` - System health check

---

## 🆘 Getting Help

### Documentation
- **[Documentation Index](../README.md)** - Complete navigation
- **[Developer Guide](../architecture/02-DEVELOPER-GUIDE.md)** - Technical setup
- **[Troubleshooting](../architecture/02-DEVELOPER-GUIDE.md#troubleshooting)** - Common issues

### Support Channels
- **GitHub Issues** - Report bugs
- **Library IT** - Internal support
- **Email** - webservices@miamioh.edu

---

## 🎓 Learning Path

### Week 1: Understanding
1. Read [Main README](../../README.md)
2. Review [System Architecture](../architecture/01-SYSTEM-ARCHITECTURE.md)
3. Browse [Weaviate RAG docs](../weaviate-rag/)

### Week 2: Setup
1. Follow [Developer Guide](../architecture/02-DEVELOPER-GUIDE.md)
2. Set up local environment
3. Run test queries

### Week 3: Management
1. Learn [Record Management](../weaviate-rag/03-RECORD-MANAGEMENT.md)
2. Practice updating wrong answers
3. View analytics

### Week 4: Advanced
1. Study [Data Pipeline](../data-management/03-DATA-PIPELINE.md)
2. Process sample transcript data
3. Experiment with agents

---

## ✅ Quick Checklist

Before going to production:
- [ ] Environment variables configured (`.env`)
- [ ] Database set up and migrated
- [ ] Weaviate cloud connected
- [ ] Q&A pairs loaded
- [ ] Frontend and backend running
- [ ] Test queries successful
- [ ] Health check passing
- [ ] Documentation reviewed

---

**Ready to dive deeper? Check out the [Documentation Index](../README.md)!**

---

**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH
