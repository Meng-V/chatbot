# 🚨 QUICK FIX: Update Weaviate Knowledge

## The Problem You're Having

**You edited the local JSON file, but the chatbot still gives old answers.**

### Why?
```
❌ Local JSON File                     ✅ Weaviate Cloud
/ai-core/data/                         (Your live database)
  optimized_for_weaviate.json          
                                       ← Chatbot reads from HERE
Chatbot DOES NOT read this!            
```

**The chatbot queries Weaviate Cloud in real-time, NOT your local file!**

---

## ✅ Solution: Run the Upload Script

### For 1-20 Changes (Recommended)

**Step 1**: Edit the update script
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
nano scripts/update_rag_facts.py
```

**Step 2**: Add your correct Q&A to line 57
```python
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library opened in 1982 and has served Miami University for over 40 years.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1982", "opened", "history"]
    },
    # Add more facts here
]
```

**Step 3**: Run the update
```bash
source .venv/bin/activate
python scripts/update_rag_facts.py
```

**Step 4**: Test immediately - ask the question in chatbot!

---

### For 50+ Changes (Bulk Upload)

**Step 1**: Edit your JSON file (you may have already done this)
```bash
nano ai-core/data/optimized_for_weaviate.json
```

**Step 2**: Delete old collection (optional but recommended)
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/setup_weaviate.py
# Choose option to delete collection
```

**Step 3**: Re-upload ALL data to Weaviate Cloud
```bash
source .venv/bin/activate
python scripts/ingest_transcripts_optimized.py
```

This takes ~5 minutes and uploads all 1,568+ records.

**Step 4**: Test - new answers should appear immediately!

---

## 📋 What You Probably Did (Wrong ❌)

1. ❌ Edited `/ai-core/data/optimized_for_weaviate.json`
2. ❌ Restarted chatbot with `bash local-auto-start.sh`
3. ❌ Expected new answers to appear

**Missing**: You never uploaded to Weaviate Cloud!

---

## ✅ What You Should Do (Correct)

### Option A: Quick Individual Updates
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
nano scripts/update_rag_facts.py  # Add facts to CORRECT_FACTS
python scripts/update_rag_facts.py  # Upload to cloud
```

### Option B: Bulk Re-upload
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/ingest_transcripts_optimized.py  # Upload all data
```

---

## 🎯 Right Now - Do This

**If you changed 1-20 answers:**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
source .venv/bin/activate

# Edit and add your facts
nano scripts/update_rag_facts.py

# Upload to Weaviate Cloud
python scripts/update_rag_facts.py
```

**If you changed 50+ answers:**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
source .venv/bin/activate

# Upload ALL data to Weaviate Cloud
python scripts/ingest_transcripts_optimized.py
```

**Then test immediately in the chatbot!**

---

## 📖 Full Documentation

See: `/docs/weaviate-rag/08-UPDATING-WORKFLOW.md` for complete details.

---

**Remember: Restarting the chatbot does NOTHING. You must upload to Weaviate Cloud!** 🔄
