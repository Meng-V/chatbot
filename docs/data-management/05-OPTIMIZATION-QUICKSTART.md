# Vector Search Optimization - Quick Start

## 🎯 What This Does

Transforms your existing RAG data to be **optimized for vector search**:
- **Generalizes questions** → broader applicability
- **Enhances answers** → more comprehensive
- **Merges duplicates** → eliminates redundancy
- **Simplifies schema** → removes unnecessary metadata

**Result**: Better semantic search, higher retrieval accuracy, cleaner data.

---

## ⚡ Quick Start (3 Commands)

### 1. Optimize Data (~10-15 minutes)

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

python3 scripts/optimize_for_vector_search.py \
    --input data/final_filtered.json \
    --output data/optimized_for_weaviate.json \
    --batch-size 30
```

**What it does**:
- Uses o4-mini AI to generalize 1,632 Q&A pairs
- Merges similar questions (80%+ similarity)
- Expected output: ~1,100-1,200 optimized items

### 2. Clear & Re-Ingest (~2 minutes)

```bash
python3 scripts/ingest_transcripts_optimized.py
```

**What it does**:
- Deletes old TranscriptQA collection
- Creates new collection (only 4 fields)
- Ingests optimized data
- Verifies ingestion

### 3. Update Your Code

#### Option A: Replace Agent File
```bash
cd src/agents
mv transcript_rag_agent.py transcript_rag_agent_old.py
mv transcript_rag_agent_optimized.py transcript_rag_agent.py
```

#### Option B: Update Import
```python
# In your main agent file
from agents.transcript_rag_agent_optimized import transcript_rag_query
```

---

## 📊 Before vs After

### Schema Comparison

**Before** (12 fields):
```json
{
  "question": "how do i renew my book online",
  "answer": "Hi; thanks for this question. You can click...",
  "topic": "discovery_search",
  "keywords": ["renew", "book", "online"],
  "rating": 4,
  "confidence_score": 0.9,
  "source": "transcripts",
  "chat_id": "12345",
  "timestamp": "2024-01-15",
  "answerer": "Librarian",
  "department": "Reference",
  "tags": []
}
```

**After** (4 fields):
```json
{
  "question": "How can I renew library materials online?",
  "answer": "To renew library materials online: 1. Go to the library website...",
  "keywords": ["renew", "library", "materials", "online", "account"],
  "topic": "discovery_search"
}
```

### Query Performance

**Before**:
- Query: "extend my loan"
- Match: ❌ No exact "extend" keyword
- Results: 0 relevant answers

**After**:
- Query: "extend my loan"
- Match: ✅ Semantic understanding → "renew"
- Results: 3-5 relevant answers

---

## ✅ Verification

### Test Queries

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

python3 -c "
import asyncio
import sys
sys.path.insert(0, 'src')
from agents.transcript_rag_agent_optimized import transcript_rag_query

async def test():
    queries = [
        'How do I renew books?',
        'What is interlibrary loan?',
        'How can I access databases?'
    ]
    
    for q in queries:
        result = await transcript_rag_query(q)
        print(f'Q: {q}')
        print(f'Confidence: {result.get(\"confidence\")}')
        print(f'Similarity: {result.get(\"similarity_score\", 0):.3f}')
        print(f'Answer: {result.get(\"text\")[:100]}...\n')

asyncio.run(test())
"
```

**Expected Output**:
- All queries return `success: True`
- Confidence: high/medium
- Similarity scores: 0.75-0.90

---

## 🔍 What Changed

### Old Approach
1. Store every specific conversation
2. Filter by rating/confidence
3. Hope for keyword matches
4. Limited semantic understanding

### New Approach
1. Generalize to abstract knowledge
2. Pure vector similarity
3. Semantic understanding
4. Better coverage & recall

### Example Transformation

**Original Specific Q&A**:
- Q: "Is 'Introduction to Psychology 5th edition' available in King Library?"
- A: "Yes, we have 2 copies. Call number BF121.S45 2020."

**Generalized Q&A**:
- Q: "How can I check if a specific book is available in the library?"
- A: "To check book availability: 1. Visit the library catalog, 2. Search by title, author, or ISBN, 3. View availability and location, 4. Note the call number. You can also contact a librarian for assistance."

**Why Better**:
- Matches "book availability", "find books", "locate materials"
- Works for ANY book, not just one title
- Teaches the process, not just one instance

---

## ⚙️ Advanced Options

### Adjust Merge Threshold

**More aggressive merging** (fewer items):
```bash
python3 scripts/optimize_for_vector_search.py \
    --similarity-threshold 0.75
```

**Keep more variations** (more items):
```bash
python3 scripts/optimize_for_vector_search.py \
    --similarity-threshold 0.85
```

### Process Faster

```bash
python3 scripts/optimize_for_vector_search.py \
    --batch-size 50  # Process 50 at a time (faster)
```

### Topic-Specific Queries

```python
# Only search policy questions
result = await transcript_rag_query(
    "What is the fine policy?",
    topic_filter="policy_or_service"
)
```

---

## 🐛 Common Issues

### Issue: AI Failures

**Symptom**: `⚠️ AI generalization failed: Expecting value`

**Is this bad?** No! 5-10% failure rate is normal. Script uses fallback (keeps original).

**Too many failures?** (>20%)
```bash
# Reduce batch size
--batch-size 15
```

### Issue: Too Much Reduction

**Symptom**: 1,632 → 600 items (63% reduction)

**Cause**: Aggressive merging

**Fix**:
```bash
--similarity-threshold 0.85  # Less merging
```

### Issue: Weaviate Error

**Symptom**: `Connection failed`

**Check**:
1. Is Weaviate running?
2. Is `.env` correct?
```bash
cat ../. env | grep WEAVIATE
```

---

## 📚 Full Documentation

For detailed information, see:
- **Full Guide**: `VECTOR_SEARCH_OPTIMIZATION.md`
- **Troubleshooting**: `RAG_DATA_PIPELINE_README.md`

---

**Estimated Total Time**: 15-20 minutes  
**Skill Level**: Intermediate  
**Prerequisites**: Python 3.12+, Weaviate access, OpenAI API key
