# Weaviate RAG System Documentation

## Overview

This folder contains all documentation for managing the Weaviate-powered Retrieval-Augmented Generation (RAG) system, which is the knowledge base that powers accurate chatbot responses.

---

## 📚 What's Inside

### 1. Setup & Configuration
- **[01-SETUP.md](./01-SETUP.md)** - Initial Weaviate cloud setup and configuration

### 2. Usage Tracking & Analytics
- **[02-RAG-USAGE-TRACKING.md](./02-RAG-USAGE-TRACKING.md)** - Monitor how often RAG is used and analyze query patterns

### 3. Record Management & Cleanup
- **[03-RECORD-MANAGEMENT.md](./03-RECORD-MANAGEMENT.md)** - Complete guide for finding and deleting problematic records
- **[04-CLEANUP-QUICKSTART.md](./04-CLEANUP-QUICKSTART.md)** - Quick reference for record cleanup

### 4. Fact Grounding & Accuracy
- **[05-FACT-GROUNDING.md](./05-FACT-GROUNDING.md)** - Detailed guide on ensuring factual accuracy
- **[06-FACT-GROUNDING-QUICKSTART.md](./06-FACT-GROUNDING-QUICKSTART.md)** - Quick start for fact correction
- **[07-FACT-CORRECTION.md](./07-FACT-CORRECTION.md)** - Summary of fact correction features
- **[08-UPDATING-WORKFLOW.md](./08-UPDATING-WORKFLOW.md)** - ⭐ **Complete workflow for updating knowledge** (START HERE for updates!)
- **[09-AGENT-PRIORITY-SYSTEM.md](./09-AGENT-PRIORITY-SYSTEM.md)** - ⭐ **Agent priority: RAG > Google Site Search** (NEW!)

---

## 🎯 Common Tasks

### ⭐ Update Knowledge (Add/Fix Q&A)
**⚠️ IMPORTANT**: Editing local JSON does NOT update Weaviate Cloud!

**Quick Method** (1-20 changes):
```bash
# 1. Edit the update script
nano ai-core/scripts/update_rag_facts.py
# Add facts to CORRECT_FACTS array (line 57)

# 2. Run update
cd ai-core
python scripts/update_rag_facts.py
```

**Bulk Method** (50+ changes):
```bash
# 1. Edit JSON
nano ai-core/data/optimized_for_weaviate.json

# 2. Re-ingest all data
cd ai-core
python scripts/ingest_transcripts_optimized.py
```

📖 **Complete Workflow**: [08-UPDATING-WORKFLOW.md](./08-UPDATING-WORKFLOW.md) ← **Read this!**

---

### Fix a Wrong Answer
```bash
# 1. Find the problematic record
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/find_problematic_rag_records.py --query "student's question"

# 2. Delete the bad record
python scripts/delete_weaviate_records.py --ids <RECORD_ID>

# 3. Add correct answer
python scripts/update_rag_facts.py
```
📖 **Full Guide**: [03-RECORD-MANAGEMENT.md](./03-RECORD-MANAGEMENT.md)

---

### Check RAG Usage Analytics
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/analyze_rag_usage.py --detailed
```
📖 **Full Guide**: [02-RAG-USAGE-TRACKING.md](./02-RAG-USAGE-TRACKING.md)

---

### Find Low Quality Records
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/find_problematic_rag_records.py --low-confidence --export bad_ids.txt
python scripts/delete_weaviate_records.py --file bad_ids.txt
```
📖 **Full Guide**: [04-CLEANUP-QUICKSTART.md](./04-CLEANUP-QUICKSTART.md)

---

## 🔄 Workflow Summary

```
User asks question
      ↓
System searches Weaviate (1,568 Q&A pairs)
      ↓
Returns top matches with similarity scores
      ↓
Fact grounding verifies accuracy
      ↓
Chatbot provides grounded answer
      ↓
Usage logged to database ✓
```

---

## 📊 Key Statistics

- **Total Q&A Pairs**: 1,568
- **Vector Database**: Weaviate Cloud
- **Embedding Model**: OpenAI text-embedding-3-small
- **Vector Dimensions**: 1,536
- **Tracking**: Automatic usage logging to Prisma DB

---

## 🛠️ Related Scripts

All scripts are located in `/ai-core/scripts/`:

| Script | Purpose |
|--------|---------|
| `setup_weaviate.py` | Initial Weaviate setup |
| `ingest_transcripts_optimized.py` | Load Q&A data into Weaviate |
| `query_rag.py` | Test RAG queries |
| `find_problematic_rag_records.py` | Find records needing cleanup |
| `delete_weaviate_records.py` | Delete problematic records |
| `update_rag_facts.py` | Add/update facts |
| `analyze_rag_usage.py` | View usage analytics |

---

## 📖 Reading Order

For first-time setup:
1. [01-SETUP.md](./01-SETUP.md) - Set up Weaviate
2. [05-FACT-GROUNDING.md](./05-FACT-GROUNDING.md) - Understand accuracy system
3. [02-RAG-USAGE-TRACKING.md](./02-RAG-USAGE-TRACKING.md) - Learn tracking

For ongoing maintenance:
1. [04-CLEANUP-QUICKSTART.md](./04-CLEANUP-QUICKSTART.md) - Quick cleanup reference
2. [03-RECORD-MANAGEMENT.md](./03-RECORD-MANAGEMENT.md) - Detailed management

---

**Keep your knowledge base accurate and up-to-date!** 🎯

---

**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH
