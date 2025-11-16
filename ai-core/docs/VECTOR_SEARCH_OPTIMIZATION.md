# Vector Search Optimization Guide

## 📋 Overview

This document explains the optimized approach to storing and retrieving Q&A pairs in Weaviate for maximum vector search performance.

**Key Changes**:
- **Simplified Schema**: Only 4 essential fields (question, answer, keywords, topic)
- **Generalized Content**: AI-powered abstraction for broader applicability
- **Merged Duplicates**: Similar questions combined with best answers
- **Optimized for Semantics**: Better leverage of vector database capabilities

---

## 🎯 Problem Statement

### Previous Approach Issues

The original TranscriptQA collection had several limitations:

1. **Too Much Metadata**: Fields like `rating`, `timestamp`, `answerer`, `department`, `source`, `tags` added noise
2. **Overly Specific Questions**: "Is 'Book Title XYZ' available?" only matches exact queries
3. **Duplicate Questions**: Many similar questions with slightly different wording
4. **Metadata-Dependent Filtering**: Relied on rating/confidence filters rather than pure semantic search

### Result
- Poor semantic matching
- Low retrieval recall
- Vector search capabilities underutilized

---

## ✨ New Optimized Approach

### Schema Simplification

**Old Schema** (12 fields):
```python
{
  "question": str,
  "answer": str,
  "topic": str,
  "keywords": List[str],
  "rating": int,              # ❌ Removed
  "confidence_score": float,  # ❌ Removed
  "source": str,              # ❌ Removed
  "chat_id": str,             # ❌ Removed
  "timestamp": str,           # ❌ Removed
  "answerer": str,            # ❌ Removed
  "department": str,          # ❌ Removed
  "tags": List[str]           # ❌ Removed
}
```

**New Schema** (4 fields):
```python
{
  "question": str,            # ✅ Generalized, abstract
  "answer": str,              # ✅ Enhanced, comprehensive
  "keywords": List[str],      # ✅ Optimized key concepts
  "topic": str                # ✅ Broad category
}
```

### AI-Powered Generalization

Each Q&A pair is processed through o4-mini to:

**1. Generalize Questions**
- Remove specific details (names, dates, titles)
- Make broadly applicable
- Preserve core intent

Example:
```
Before: "Is the book 'Introduction to Psychology' by Smith available?"
After:  "How can I check if a specific book is available in the library?"
```

**2. Enhance Answers**
- Make comprehensive and step-by-step
- Add general principles
- Remove temporal references
- Keep objective and professional

Example:
```
Before: "Yes, we have 2 copies available in King Library."
After:  "To check book availability:
         1. Go to the library catalog
         2. Search by title, author, or ISBN
         3. Check the 'Availability' section
         4. Note the call number and location
         You can also contact a librarian for assistance."
```

**3. Optimize Keywords**
- Extract 5-7 key concepts
- Focus on searchable terms
- Remove stop words and noise

**4. Classify Topics**
- discovery_search: Book/resource finding
- policy_or_service: Library rules and services
- technical_help: System access and troubleshooting
- research_help: Research guidance
- general_question: Other inquiries

### Question Clustering & Merging

Similar questions (≥80% similarity) are merged:

**Process**:
1. Calculate TF-IDF similarity between all questions
2. Group questions with similarity ≥ 0.80
3. Select best answer from cluster (based on length and quality)
4. Merge all keywords

**Example**:
```
Cluster of 3 similar questions:
- "How do I renew my books?"
- "Can I renew a book online?"
- "What's the process to renew library items?"

Merged Result:
Question: "How can I renew library materials?"
Answer: [Most comprehensive answer from the 3]
Keywords: [Combined from all 3]
```

---

## 🚀 Usage

### Step 1: Optimize Existing Data

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

python3 scripts/optimize_for_vector_search.py \
    --input data/final_filtered.json \
    --output data/optimized_for_weaviate.json \
    --batch-size 30
```

**Parameters**:
- `--input`: Source Q&A JSON file
- `--output`: Output optimized JSON file
- `--similarity-threshold`: Merge threshold (default: 0.80)
- `--batch-size`: AI processing batch size (default: 10)

**Time**: ~10-15 minutes for 1,600 items (batch-size 30)

### Step 2: Ingest into Weaviate

```bash
python3 scripts/ingest_transcripts_optimized.py

# Or specify custom file
TRANSCRIPTS_PATH=data/optimized_for_weaviate.json \
    python3 scripts/ingest_transcripts_optimized.py
```

This will:
1. Delete old TranscriptQA collection
2. Create new collection with simplified schema
3. Ingest optimized Q&A pairs
4. Verify ingestion

### Step 3: Update Your Agent

Replace the import in your main agent file:

```python
# Old
from agents.transcript_rag_agent import transcript_rag_query

# New
from agents.transcript_rag_agent_optimized import transcript_rag_query
```

Or rename the file:
```bash
cd src/agents
mv transcript_rag_agent.py transcript_rag_agent_old.py
mv transcript_rag_agent_optimized.py transcript_rag_agent.py
```

---

## 📊 Expected Results

### Data Reduction

Based on 1,632 input items:

| Stage | Count | Reduction |
|-------|-------|-----------|
| Original Q&A pairs | 1,632 | - |
| After AI generalization | 1,632 | 0% (content improved) |
| After merging similar questions | ~1,100-1,200 | ~25-35% |

**Why reduction is good**:
- Eliminates redundancy
- Each item represents broader knowledge
- Better vector space distribution
- Faster queries

### Query Performance

**Before Optimization**:
- Query: "How do I renew books?"
- Match: Only if exact "renew" + "book" present
- Results: 1-2 narrow matches

**After Optimization**:
- Query: "How do I renew books?"
- Match: Semantic understanding of renewal process
- Results: 3-5 broadly applicable answers
- Better coverage of edge cases

### Semantic Search Quality

Improved matching for:
- **Synonym queries**: "extend loan" matches "renew"
- **Implied questions**: "My book is due soon" matches renewal info
- **Broader terms**: "circulation services" matches specific policies
- **Related concepts**: "overdue" matches fine policies

---

## 🔧 Technical Details

### Vector Embedding

Using OpenAI's `text-embedding-3-small`:
- 1536 dimensions
- Optimized for semantic similarity
- Cost-effective
- Fast inference

### Similarity Scoring

```python
# Distance to similarity conversion
similarity = 1 - distance

# Confidence levels
if similarity >= 0.85:  # Very close match
    confidence = "high"
elif similarity >= 0.75:  # Good match
    confidence = "medium"
else:  # Weak match
    confidence = "low"
```

### Query Strategy

1. **Semantic Search**: Use Weaviate's `near_text` for vector similarity
2. **Top-K Retrieval**: Get top 5 most similar results
3. **Re-ranking**: Sort by similarity score
4. **Response Formatting**:
   - High confidence (1 result): Return single best answer
   - Medium/Low confidence (3 results): Show multiple options

---

## 📈 Best Practices

### 1. Regular Re-Optimization

Every 6-12 months, re-run optimization on accumulated data:

```bash
# Combine old and new data
cat data/optimized_for_weaviate.json data/2026_final.json > data/combined.json

# Re-optimize
python3 scripts/optimize_for_vector_search.py \
    --input data/combined.json \
    --output data/optimized_for_weaviate.json
```

### 2. Monitor Query Performance

Track metrics:
- Hit rate (queries with confidence ≥ medium)
- Average similarity scores
- Questions with no good matches

### 3. Adjust Similarity Threshold

If too many duplicates remain:
```bash
--similarity-threshold 0.75  # More aggressive merging
```

If losing important variations:
```bash
--similarity-threshold 0.85  # Keep more variations
```

### 4. Topic Filtering

For domain-specific queries:

```python
# Only search within discovery_search topic
result = await transcript_rag_query(
    "How do I find books?",
    topic_filter="discovery_search"
)
```

---

## 🐛 Troubleshooting

### Issue: AI Generalization Failures

**Symptom**: `⚠️ AI generalization failed: Expecting value: line 1 column 1`

**Cause**: o4-mini occasionally returns non-JSON responses

**Solution**: The script has fallback logic - original Q&A is kept. A few failures (5-10%) are normal and acceptable.

### Issue: Too Much Data Reduction

**Symptom**: Only 500 items after processing 1,600

**Solution**: Lower similarity threshold
```bash
--similarity-threshold 0.85
```

### Issue: Poor Query Results

**Symptom**: Low confidence scores for most queries

**Solutions**:
1. Check embedding quality: Ensure OpenAI API key is valid
2. Review generalized questions: May be too abstract
3. Increase dataset size: More data = better coverage
4. Add topic filtering: Narrow search scope

### Issue: Weaviate Connection Errors

**Symptom**: `Meta endpoint! Unexpected status code: 404`

**Solution**:
1. Verify Weaviate is running
2. Check `.env` credentials:
   ```
   WEAVIATE_HOST=xxx.weaviate.cloud
   WEAVIATE_API_KEY=xxx
   OPENAI_API_KEY=xxx
   ```

---

## 📚 Related Documentation

- **Data Pipeline**: `RAG_DATA_PIPELINE_README.md`
- **New Year Processing**: `PROCESS_NEW_YEAR_DATA.md`
- **Project Summary**: `../2025_RAG_PROJECT_SUMMARY.md`

---

## 🎓 Advanced Topics

### Custom Generalization Prompts

Edit `scripts/optimize_for_vector_search.py`:

```python
GENERALIZATION_PROMPT = """
Your custom prompt here...
Focus on your specific domain...
"""
```

### Multi-Language Support

For non-English content, adjust the TF-IDF vectorizer:

```python
vectorizer = TfidfVectorizer(
    max_features=500,
    stop_words=None,  # Remove English stop words filter
    ngram_range=(1, 2)
)
```

### Custom Confidence Thresholds

In `transcript_rag_agent_optimized.py`:

```python
# Adjust confidence levels
if top_similarity >= 0.90:  # Stricter high confidence
    confidence = "high"
elif top_similarity >= 0.80:  # Stricter medium
    confidence = "medium"
```

---

**Last Updated**: November 16, 2024  
**Version**: 1.0  
**Maintainer**: Chatbot Team
