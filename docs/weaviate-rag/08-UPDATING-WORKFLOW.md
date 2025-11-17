# Updating Weaviate Knowledge - Complete Workflow

**Last Updated**: November 17, 2025

---

## ⚠️ CRITICAL: Understand the Data Flow

```
┌─────────────────────────────────────┐
│ Local JSON File                     │
│ /ai-core/data/                      │
│   optimized_for_weaviate.json       │
│                                     │
│ ❌ Chatbot DOES NOT read this!     │
└─────────────────────────────────────┘
          ↓
    (Must upload via script)
          ↓
┌─────────────────────────────────────┐
│ Weaviate Cloud Database             │
│ (Live vector database)              │
│                                     │
│ ✅ Chatbot queries this in real-time│
└─────────────────────────────────────┘
```

**Key Point**: Editing the local JSON file does NOTHING unless you run the ingestion script!

---

## 🔄 Two Update Methods

### Method 1: Individual Fact Updates (Recommended)

**Use when**: Fixing 1-20 wrong answers or adding new Q&A pairs

**Advantages**:
- ✅ No need to reload all 1,568 records
- ✅ Fast and safe
- ✅ Automatically checks for duplicates
- ✅ Can update existing records

**Steps**:

#### 1. Edit the Update Script
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
nano scripts/update_rag_facts.py
```

#### 2. Add Your Facts to the `CORRECT_FACTS` Array (Line 57)
```python
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library opened in 1982 and has served Miami University for over 40 years.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1982", "history", "opened"]
    },
    {
        "question": "What are the library hours?",
        "answer": "King Library is open Monday-Friday 8am-10pm. Check lib.miamioh.edu/hours for current hours.",
        "topic": "hours",
        "keywords": ["hours", "King Library", "schedule", "open"]
    },
    # Add more facts here
]
```

#### 3. Run the Update Script
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
source .venv/bin/activate  # Activate virtual environment
python scripts/update_rag_facts.py
```

#### 4. Verify Updates
The script will show:
```
✅ Connected to Weaviate
📝 Processing 2 facts...

1/2: Added new: 'When was King Library built?' (UUID: abc-123...)
  📋 Verification:
     Question: When was King Library built?
     Answer: King Library opened in 1982...
     ✅ Excellent match!

2/2: Updated (distance: 0.045): 'library hours' → 'What are the library hours?'
  ✅ Excellent match!

✅ Complete! Added: 1, Updated: 1, Errors: 0
```

#### 5. Test in Chatbot
Ask the question immediately - it should return the new answer!

---

### Method 2: Bulk Re-ingestion (All Data)

**Use when**: 
- Adding 50+ new Q&A pairs
- Major data restructuring
- Initial setup

**Warning**: This will reload ALL 1,568 records (takes ~5 minutes)

**Steps**:

#### 1. Edit the JSON File
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
nano data/optimized_for_weaviate.json
```

Add or modify entries:
```json
{
  "qa_pairs": [
    {
      "question": "When was King Library built?",
      "answer": "King Library opened in 1982.",
      "topic": "building_information",
      "keywords": ["King Library", "built", "1982", "history"]
    }
  ]
}
```

#### 2. **Delete Existing Collection** (Important!)
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/setup_weaviate.py
# Choose option to delete and recreate collection
```

#### 3. Re-ingest All Data
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
source .venv/bin/activate
python scripts/ingest_transcripts_optimized.py
```

This will:
- ✅ Upload all records to Weaviate Cloud
- ✅ Vectorize with OpenAI embeddings
- ✅ Show progress (batch 1/32, 2/32, etc.)

#### 4. Verify Ingestion
```
✅ Successfully inserted batch 32/32 (1568 total)
✅ Verification: Collection has 1568 objects
```

#### 5. Test in Chatbot
Ask questions to verify new answers appear.

---

## 🎯 Quick Reference

### What You Did (Wrong ❌)
```bash
# 1. Edited local JSON file
nano ai-core/data/optimized_for_weaviate.json

# 2. Restarted chatbot
bash local-auto-start.sh

# ❌ Changes NOT reflected (Weaviate Cloud unchanged!)
```

### What You Should Do (Correct ✅)

**For Few Changes**:
```bash
# 1. Edit update script
nano ai-core/scripts/update_rag_facts.py

# 2. Add facts to CORRECT_FACTS array

# 3. Run update
cd ai-core
python scripts/update_rag_facts.py

# ✅ Changes immediately live!
```

**For Many Changes**:
```bash
# 1. Edit JSON
nano ai-core/data/optimized_for_weaviate.json

# 2. Re-ingest
cd ai-core
python scripts/ingest_transcripts_optimized.py

# ✅ All data reloaded!
```

---

## 🔍 Common Issues

### Issue 1: "Bot still gives old answer"

**Cause**: You didn't run the upload script

**Fix**: Run `update_rag_facts.py` or `ingest_transcripts_optimized.py`

---

### Issue 2: "Duplicate answers appearing"

**Cause**: Added same question twice without updating

**Fix**: Use `update_rag_facts.py` - it automatically detects duplicates

---

### Issue 3: "Script says 'not connected'"

**Cause**: Missing Weaviate credentials

**Fix**: Check `.env` file at root:
```bash
WEAVIATE_HOST=your-cluster.weaviate.network
WEAVIATE_API_KEY=your-key
OPENAI_API_KEY=your-key
```

---

### Issue 4: "How do I find wrong records?"

**Use the find script**:
```bash
cd ai-core
python scripts/find_problematic_rag_records.py --query "King Library"
```

Then delete bad records:
```bash
python scripts/delete_weaviate_records.py --ids uuid-1 uuid-2
```

---

## 📊 Complete Update Workflow

```
┌─────────────────────────────────────┐
│ 1. Identify Wrong Answer            │
│    - User reports error              │
│    - Or find via analytics           │
└─────────────────────────────────────┘
          ↓
┌─────────────────────────────────────┐
│ 2. Find Weaviate Record ID          │
│    python find_problematic_          │
│           rag_records.py             │
└─────────────────────────────────────┘
          ↓
┌─────────────────────────────────────┐
│ 3A. Delete Bad Record (Optional)    │
│     python delete_weaviate_          │
│            records.py --ids <UUID>   │
└─────────────────────────────────────┘
          ↓
┌─────────────────────────────────────┐
│ 3B. Add Correct Answer              │
│     Edit update_rag_facts.py         │
│     Add to CORRECT_FACTS array       │
└─────────────────────────────────────┘
          ↓
┌─────────────────────────────────────┐
│ 4. Run Update Script                │
│    python update_rag_facts.py        │
└─────────────────────────────────────┘
          ↓
┌─────────────────────────────────────┐
│ 5. Verify in Chatbot                │
│    Ask the question                  │
│    Check new answer appears          │
└─────────────────────────────────────┘
```

---

## 🎓 Best Practices

1. **Use Method 1 for < 20 updates** - Faster and safer
2. **Always verify after updating** - Test in chatbot immediately
3. **Keep a changelog** - Note what you changed and when
4. **Back up before bulk re-ingestion** - Export current data first
5. **Check for duplicates** - Use similarity threshold in update script

---

## 🚀 Example: Complete Fix Workflow

### Scenario: Bot says "King Library built in 1966" (wrong!)

**Step 1: Find the bad record**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/find_problematic_rag_records.py --query "King Library built"
```

Output:
```
Found 1 record:
UUID: abc-123-def-456
Question: When was King Library built?
Answer: King Library was built in 1966...
```

**Step 2: Delete the bad record**
```bash
python scripts/delete_weaviate_records.py --ids abc-123-def-456
```

**Step 3: Add correct answer**
Edit `scripts/update_rag_facts.py`:
```python
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library opened in 1982 and has served Miami University for over 40 years.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1982", "opened", "history"]
    },
]
```

**Step 4: Run update**
```bash
python scripts/update_rag_facts.py
```

Output:
```
✅ Added new: 'When was King Library built?'
✅ Complete! Added: 1, Updated: 0, Errors: 0
```

**Step 5: Test**
Ask chatbot: "When was King Library built?"

Expected: "King Library opened in 1982..."

✅ **Fixed!**

---

## 📞 Need Help?

- **Documentation**: [Record Management Guide](./03-RECORD-MANAGEMENT.md)
- **Find bad records**: [Cleanup Quickstart](./04-CLEANUP-QUICKSTART.md)
- **Analytics**: [RAG Usage Tracking](./02-RAG-USAGE-TRACKING.md)

---

**Remember: Local file edits DO NOT update Weaviate Cloud. Always run the upload script!** 🔄
