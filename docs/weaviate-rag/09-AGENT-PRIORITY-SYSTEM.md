# Agent Priority System

**Last Updated**: November 17, 2025  
**Version**: 2.2.1

---

## 🎯 Overview

The chatbot uses **8 specialized agents** to answer questions. When multiple agents can answer the same question, the system now uses a **priority hierarchy** to ensure the most reliable information is used.

---

## 📊 Priority Hierarchy

```
1️⃣ HIGHEST PRIORITY: API Functions
   - LibCal (hours, room reservations)
   - Primo (catalog search)
   - LibGuides API (research guides)
   - Subject Librarian routing
   ✅ Real-time, verified data from official systems

2️⃣ MEDIUM PRIORITY: RAG (Weaviate Knowledge Base)
   - TranscriptRAG (your curated Q&A pairs)
   ✅ Library-verified factual knowledge
   ✅ Carefully reviewed and maintained
   
3️⃣ LOWEST PRIORITY: Google Site Search
   - Website crawling
   ⚠️  Use ONLY as fallback when no better source available
   ⚠️  May contain outdated or incorrect information
```

---

## 🔄 How It Works

### When User Asks: "When was King Library built?"

**Old Behavior** (Before fix):
```
1. Google Site Search runs → finds "1982" ❌ WRONG
2. RAG runs → finds "1966" ✅ CORRECT
3. Both results sent to synthesizer with EQUAL weight
4. LLM randomly picks one → User gets wrong answer 50% of the time
```

**New Behavior** (After fix):
```
1. RAG runs → finds "1966 and renovated in 1973 and 2007" ✅
2. Google Site Search runs → finds "1982" ❌
3. Results sent with PRIORITY LABELS:
   [TranscriptRAG - CURATED KNOWLEDGE BASE - HIGH PRIORITY]: 1966...
   [Website Search - USE ONLY IF NO BETTER SOURCE]: 1982...
4. LLM instructed to TRUST RAG over website
5. User gets CORRECT answer: 1966 ✅
```

---

## 🛠️ What Changed

### File: `/ai-core/src/graph/orchestrator.py`

#### Change 1: Priority Order Dictionary (Line 281-289)
```python
priority_order = {
    "primo": 1,           # API: Catalog search
    "libcal": 1,          # API: Hours & reservations
    "libguide": 1,        # API: Research guides
    "subject_librarian": 1, # API: Subject librarian routing
    "libchat": 1,         # API: Chat handoff
    "transcript_rag": 2,  # RAG: Curated knowledge base (HIGHER PRIORITY)
    "google_site": 3      # Website search (LOWER PRIORITY - fallback only)
}
```

#### Change 2: Sort Responses by Priority (Line 291-295)
```python
# Sort responses by priority
sorted_responses = sorted(
    responses.items(),
    key=lambda x: priority_order.get(x[0], 99)
)
```

#### Change 3: Add Priority Labels (Line 297-309)
```python
for agent_name, resp in sorted_responses:
    if resp.get("success"):
        priority_label = ""
        if agent_name == "transcript_rag":
            priority_label = " [CURATED KNOWLEDGE BASE - HIGH PRIORITY]"
        elif priority_order.get(agent_name, 99) == 1:
            priority_label = " [VERIFIED API DATA]"
        elif agent_name == "google_site":
            priority_label = " [WEBSITE SEARCH - USE ONLY IF NO BETTER SOURCE]"
        
        context_parts.append(f"[{resp.get('source', agent_name)}{priority_label}]: {resp.get('text', '')}")
```

#### Change 4: Synthesis Prompt Instructions (Line 396-401)
```python
10. **SOURCE PRIORITY - EXTREMELY IMPORTANT**:
    - ALWAYS prefer information from [VERIFIED API DATA] sources (most reliable)
    - THEN use [CURATED KNOWLEDGE BASE - HIGH PRIORITY] (TranscriptRAG)
    - ONLY use [WEBSITE SEARCH] if no better source is available
    - If RAG and website search conflict, TRUST THE RAG KNOWLEDGE BASE
    - Cite your source when providing factual information
```

---

## ✅ Testing the Fix

### Test 1: King Library History

**Question**: "When was King Library built?"

**Expected RAG Response**:
```
King Library was built in 1966 and underwent major renovations in 1973 and 2007.
```

**Expected Final Answer** (should use RAG, not Google):
```
King Library opened in 1966 as Miami's undergraduate library, originally known as 
the Leland S. Dutton Wing. The library expanded in 1973 with completion of the 
north wing and main entrance. It underwent a major three-phase renovation from 
1997 to 2007 to modernize for the digital age.

(Source: Library verified knowledge base)
```

### Test 2: Verify Priority in Logs

When running the chatbot, check the logs for:
```
🤖 [Synthesizer] Generating final answer
Information from library systems:
[TranscriptRAG - CURATED KNOWLEDGE BASE - HIGH PRIORITY]: King Library was built in 1966...
[Website Search - USE ONLY IF NO BETTER SOURCE]: King Library opened in 1982...
```

The RAG answer should appear FIRST, and the LLM should choose it.

---

## 🔍 How to Verify Priority Is Working

### Step 1: Restart the Chatbot
```bash
cd /Users/qum/Documents/GitHub/chatbot
bash local-auto-start.sh
```

### Step 2: Ask the Question
In the chatbot interface:
```
When was King Library built?
```

### Step 3: Check Response
Expected: **1966** (from RAG)  
Not: **1982** (from Google Site Search)

### Step 4: Check Logs
Look for:
```
[TranscriptRAG - CURATED KNOWLEDGE BASE - HIGH PRIORITY]
```
appearing BEFORE:
```
[Website Search - USE ONLY IF NO BETTER SOURCE]
```

---

## 🎯 Priority Rules Summary

| Agent | Priority | When Used | Reliability |
|-------|----------|-----------|-------------|
| **LibCal** | 1 (Highest) | Hours, room reservations | ✅ Real-time API |
| **Primo** | 1 (Highest) | Catalog search | ✅ Real-time API |
| **LibGuides** | 1 (Highest) | Research guides | ✅ Real-time API |
| **Subject Librarian** | 1 (Highest) | Find librarian by subject | ✅ Real-time API |
| **RAG (Weaviate)** | 2 (Medium) | Factual Q&A, policies, history | ✅ Curated & verified |
| **Google Site Search** | 3 (Lowest) | General website info | ⚠️  May be outdated |

---

## 🚫 What This Does NOT Do

This priority system does **NOT**:
- ❌ Stop Google Site Search from running (all agents still run in parallel)
- ❌ Ignore Google results completely (they're used if RAG has nothing)
- ❌ Prevent conflicts between API sources (APIs have equal priority)

What it **DOES**:
- ✅ Order agent responses by reliability
- ✅ Instruct LLM to prefer higher-priority sources
- ✅ Label sources so LLM knows which to trust
- ✅ Use Google only as fallback when no better source available

---

## 🔧 Adjusting Priorities

If you need to change priorities, edit `/ai-core/src/graph/orchestrator.py`:

```python
priority_order = {
    "primo": 1,           # Lower number = higher priority
    "libcal": 1,
    "libguide": 1,
    "subject_librarian": 1,
    "libchat": 1,
    "transcript_rag": 2,  # Change to 1 to equal API priority
    "google_site": 3      # Change to 2 to equal RAG priority
}
```

---

## 📈 Benefits

### For Users
- ✅ More accurate answers
- ✅ Fewer conflicting responses
- ✅ Reduced wrong information from outdated website pages

### For Library Managers
- ✅ Control what information is prioritized
- ✅ RAG knowledge base is now trusted source
- ✅ Can correct wrong website info via RAG updates

### For Developers
- ✅ Clear hierarchy of information sources
- ✅ Easier debugging (priority labels in logs)
- ✅ Predictable behavior

---

## 🐛 Troubleshooting

### Issue: Still getting wrong answers from Google

**Check**:
1. Did you restart the chatbot? (Required after code changes)
2. Check logs - are both agents running?
3. Is RAG returning results? (Check with `find_duplicates_simple.py`)

**Fix**: Clear any old sessions, restart browser

---

### Issue: RAG not being used at all

**Check**:
1. Is Weaviate connected? (Check `.env` file)
2. Are Q&A pairs loaded? (Run `find_duplicates_simple.py`)
3. Check intent classification - is it routing to RAG?

**Fix**: Run `python scripts/ingest_transcripts_optimized.py`

---

### Issue: Google always wins even with priority

**Possible cause**: Your RAG answer has very low similarity score

**Check**: Run `find_duplicates_simple.py "your question"` and check similarity

**Fix**: 
- Improve question phrasing in Weaviate
- Add more relevant keywords
- Update answer to be more comprehensive

---

## 📞 Need Help?

- **Documentation**: [Updating Workflow](./08-UPDATING-WORKFLOW.md)
- **RAG Management**: [Record Management](./03-RECORD-MANAGEMENT.md)
- **System Overview**: [RAG README](./README.md)

---

**Remember: RAG (your curated knowledge base) now has priority over Google Site Search!** 🎯
