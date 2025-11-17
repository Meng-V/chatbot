# Fact Grounding - Quick Start Guide

**Problem**: Bot gives wrong facts (wrong years, locations, etc.)  
**Solution**: Force bot to use RAG database instead of LLM training data

---

## 🚀 Quick Start (5 Minutes)

### 1. Add Your Correct Facts

Edit `scripts/update_rag_facts.py`:

```python
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library was built in 1972.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1972"]
    },
    # ← ADD YOUR FACTS HERE
]
```

### 2. Run Update Script

```bash
cd ai-core
python scripts/update_rag_facts.py
```

Output:
```
✅ Added: 'When was King Library built?'
✅ All facts updated in RAG database!
```

### 3. Test It

```bash
python scripts/query_rag.py "When was King Library built?"
```

Output:
```
Answer: King Library was built in 1972.
Confidence: high
Similarity Score: 0.920
✅ Excellent match - use this answer confidently
```

### 4. Verify in Chatbot

Ask your chatbot: **"When was King Library built?"**

Expected: Bot uses RAG answer (1972) ✅

---

## 🎯 How It Works

```
User Query → Detect Fact Type → RAG Query → Strict Grounding → Verify → Response
                   ↓                 ↓              ↓            ↓
              "It's a date"    Find in DB    Use ONLY RAG   Check facts
```

**3 Layers of Protection**:
1. **Detection**: Recognizes factual queries (dates, locations, people, etc.)
2. **Strict Mode**: Forces LLM to use ONLY RAG context, not training data
3. **Verification**: Checks facts in response against RAG database

---

## 📋 Available Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `update_rag_facts.py` | Add/update correct facts | Edit CORRECT_FACTS, then run |
| `query_rag.py "question"` | Test RAG retrieval | `python scripts/query_rag.py "library hours"` |
| `test_fact_queries.py` | Run full test suite | Verifies all facts work correctly |

---

## 📚 Documentation

- **Complete Guide**: `docs/FACT_GROUNDING_GUIDE.md` (500+ lines)
- **Summary**: `docs/FACT_CORRECTION_SUMMARY.md`
- **This File**: Quick start only

---

## ✅ Verification Checklist

After adding facts, verify:

- [ ] Run `python scripts/update_rag_facts.py` → No errors
- [ ] Run `python scripts/query_rag.py "your question"` → Correct answer
- [ ] Check similarity score → Should be > 0.80
- [ ] Ask chatbot the question → Uses RAG answer
- [ ] Check logs for: `🔒 [Fact Grounding] Using strict grounding mode`

---

## 🔧 Common Issues

### Bot still gives wrong answer

```bash
# Check if fact is in RAG
python scripts/query_rag.py "your question"

# If similarity < 0.70:
#   → Add more specific Q&A pair

# If no results:
#   → Question not in RAG, add it
```

### Confidence too low

Options:
1. Add more detailed answer to RAG
2. Include more keywords
3. Add question variations
4. Lower threshold in `src/utils/fact_grounding.py` (line 69)

### Bot always says "contact librarian"

RAG confidence is too low. Solutions:
- Add more comprehensive Q&A pairs
- Include exact keywords in RAG answers
- Add multiple phrasings of same question

---

## 📊 Monitoring

**Good logs** (fact grounding working):
```
🔒 [Fact Grounding] Detected factual query types: date
📊 [Fact Grounding] RAG confidence: High confidence match (similarity: 0.92)
✅ [Fact Verifier] All factual claims verified against RAG
```

**Warning logs** (needs attention):
```
⚠️ [Fact Grounding] Low confidence for factual query
⚠️ [Fact Verifier] Found 2 unverified claim(s)
```

---

## 💡 Pro Tips

### 1. Be Specific in RAG Answers
✅ "King Library was built in 1972"  
❌ "King Library was built in the 1970s"

### 2. Include All Relevant Details
✅ "Makerspace is on 1st floor, Room 101"  
❌ "Makerspace is downstairs"

### 3. Add Keywords
```python
keywords: ["King Library", "1972", "built", "construction", "year"]
```

### 4. Test Edge Cases
- Different phrasings
- Partial questions
- Related questions

---

## 🎓 Example: Complete Workflow

**Scenario**: Bot says "King Library built in 1965" (WRONG)

**Step 1**: Add correct fact
```python
{
    "question": "When was King Library built?",
    "answer": "King Library was built in 1972.",
    "keywords": ["King Library", "1972", "built"]
}
```

**Step 2**: Update RAG
```bash
python scripts/update_rag_facts.py
# ✅ Added: 'When was King Library built?'
```

**Step 3**: Test
```bash
python scripts/query_rag.py "When was King Library built?"
# Similarity: 0.920 ✅
```

**Step 4**: Verify in chatbot
Ask: "When was King Library built?"  
Response: "King Library was built in 1972." ✅

**Done!** 🎉

---

## 📞 Need Help?

1. Read full guide: `docs/FACT_GROUNDING_GUIDE.md`
2. Check summary: `docs/FACT_CORRECTION_SUMMARY.md`
3. Run debug tool: `python scripts/query_rag.py "question"`
4. Review logs for `[Fact Grounding]` messages

---

**Ready to start?** → Edit `scripts/update_rag_facts.py` and run it!
