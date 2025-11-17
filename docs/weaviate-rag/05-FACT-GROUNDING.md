# Fact Grounding System - Usage Guide

## Overview

This guide explains how to ensure your chatbot uses **RAG-retrieved information** instead of the LLM's training data for factual questions.

## Problem This Solves

**Before**: Bot might give wrong answers like:
- "King Library was built in 1965" (wrong year)
- "The makerspace is on the 2nd floor" (wrong location)
- Using outdated contact information

**After**: Bot retrieves correct facts from Weaviate RAG database and verifies them.

---

## How It Works

### 3-Layer Defense System

```
User Query → [1. Fact Detection] → [2. Strict Grounding] → [3. Verification] → Response
```

#### Layer 1: Fact Type Detection
Automatically detects factual queries requiring RAG:
- **Dates**: "When was King Library built?"
- **Locations**: "Where is the makerspace?"
- **People**: "Who is the biology librarian?"
- **Quantities**: "How many study rooms?"
- **Policies**: "How do I renew a book?"

#### Layer 2: Strict Grounding Mode
When factual query detected:
1. Checks RAG confidence score
2. If confidence < 70%, escalates to human librarian
3. If confidence >= 70%, uses **enhanced grounding prompt** that:
   - Forces LLM to ONLY use RAG context
   - Prohibits using training data for facts
   - Requires citing sources

#### Layer 3: Fact Verification
After LLM generates response:
1. Extracts factual claims (dates, names, locations, etc.)
2. Verifies each claim exists in RAG context
3. If unverified claims found, adds disclaimer
4. Logs verification results

---

## Adding/Correcting Facts in RAG

### Method 1: Programmatic Update (Recommended)

Create a script to update or add Q&A pairs to Weaviate:

```python
# scripts/update_rag_facts.py
import weaviate
import weaviate.classes as wvc
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Connect to Weaviate
client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_HOST,
    auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
    headers={"X-OpenAI-Api-Key": OPENAI_API_KEY}
)

collection = client.collections.get("TranscriptQA")

# Define correct facts to add/update
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library was built in 1972 and renovated in 2015.",
        "topic": "building_information",
        "keywords": ["King Library", "built", "1972", "construction", "history"]
    },
    {
        "question": "Where is the makerspace located?",
        "answer": "The makerspace is located on the 1st floor of King Library, Room 101.",
        "topic": "location_information",
        "keywords": ["makerspace", "location", "King Library", "1st floor", "Room 101"]
    },
    {
        "question": "What are King Library's hours?",
        "answer": "King Library is open Monday-Thursday 7:30am-2am, Friday 7:30am-6pm, Saturday 10am-6pm, and Sunday 10am-2am during regular semesters.",
        "topic": "hours",
        "keywords": ["hours", "King Library", "open", "schedule"]
    }
]

# Add facts to Weaviate
for fact in CORRECT_FACTS:
    try:
        # Check if similar question already exists
        results = collection.query.near_text(
            query=fact["question"],
            limit=1,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        # If very similar exists (distance < 0.05), update it
        if results.objects and results.objects[0].metadata.distance < 0.05:
            uuid = results.objects[0].uuid
            collection.data.update(
                uuid=uuid,
                properties=fact
            )
            print(f"✅ Updated: {fact['question']}")
        else:
            # Add new fact
            collection.data.insert(properties=fact)
            print(f"✅ Added: {fact['question']}")
    
    except Exception as e:
        print(f"❌ Error with '{fact['question']}': {e}")

client.close()
print("\n✅ All facts updated in RAG database!")
```

### Method 2: Bulk Upload from CSV

```python
# scripts/bulk_upload_facts.py
import pandas as pd
import weaviate
import weaviate.classes as wvc
import os
from pathlib import Path
from dotenv import load_dotenv

# Load CSV with correct facts
df = pd.read_csv("data/library_facts.csv")
# Expected columns: question, answer, topic, keywords

# Connect to Weaviate (same as above)
# ...

# Upload all rows
for _, row in df.iterrows():
    fact = {
        "question": row["question"],
        "answer": row["answer"],
        "topic": row["topic"],
        "keywords": row["keywords"].split("|")  # Assuming pipe-separated
    }
    collection.data.insert(properties=fact)

print(f"✅ Uploaded {len(df)} facts!")
```

### CSV Format Example

```csv
question,answer,topic,keywords
"When was King Library built?","King Library was built in 1972.","building_information","King Library|built|1972|construction"
"Where is the makerspace?","The makerspace is on the 1st floor of King Library, Room 101.","location_information","makerspace|location|1st floor|Room 101"
```

---

## Testing the System

### Test Factual Queries

```python
# tests/test_fact_grounding.py
import asyncio
from src.agents.transcript_rag_agent import transcript_rag_query
from src.utils.fact_grounding import (
    detect_factual_query_type,
    is_high_confidence_rag_match
)

async def test_fact_retrieval():
    queries = [
        "When was King Library built?",
        "Where is the makerspace located?",
        "Who is the biology librarian?",
        "How many study rooms are in King Library?"
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        # Detect fact types
        fact_types = detect_factual_query_type(query)
        print(f"Detected fact types: {fact_types}")
        
        # Query RAG
        rag_result = await transcript_rag_query(query)
        print(f"RAG Success: {rag_result.get('success')}")
        print(f"Confidence: {rag_result.get('confidence')}")
        print(f"Similarity: {rag_result.get('similarity_score', 0):.2f}")
        
        # Check if high confidence
        is_confident, reason = await is_high_confidence_rag_match(rag_result)
        print(f"High confidence match: {is_confident} - {reason}")
        
        print(f"\nAnswer:\n{rag_result.get('text', 'N/A')[:200]}...")

if __name__ == "__main__":
    asyncio.run(test_fact_retrieval())
```

---

## Configuration

### Adjust Confidence Thresholds

In `src/utils/fact_grounding.py`:

```python
# Adjust these values based on your accuracy requirements
async def is_high_confidence_rag_match(
    rag_response: Dict[str, Any],
    confidence_threshold: float = 0.80  # Increase for stricter matching
) -> Tuple[bool, str]:
    ...
```

### Add New Fact Types

In `src/utils/fact_grounding.py`:

```python
FACTUAL_PATTERNS = {
    "date": [...],
    "location": [...],
    "person": [...],
    # Add new type:
    "service": [
        r"\b(what services|available services|offer)\b",
        r"\b(can I|do you have|provide)\b.*\b(service|resource)\b"
    ]
}
```

---

## Monitoring

### Check Logs

The system logs all fact grounding operations:

```
🔒 [Fact Grounding] Detected factual query types: date, location
📊 [Fact Grounding] RAG confidence: High confidence match (similarity: 0.89)
🔒 [Fact Grounding] Using strict grounding mode
🔍 [Fact Verifier] Checking factual claims against RAG context
✅ [Fact Verifier] All factual claims verified against RAG
```

### Low Confidence Escalation

When RAG confidence < 70% for factual queries:
```
⚠️ [Fact Grounding] Low confidence for factual query - suggesting human assistance
```
Bot will suggest contacting a librarian instead of guessing.

---

## Best Practices

### 1. Regular RAG Updates
- Review chatbot logs weekly for incorrect answers
- Update RAG database with corrections
- Re-test queries to verify fixes

### 2. Fact Verification
- Include sources in RAG answers when possible
- Use specific dates, not ranges ("1972" not "early 1970s")
- Include room numbers, floor numbers, building names

### 3. Quality Q&A Pairs
✅ **Good RAG Entry**:
```json
{
  "question": "When was King Library built?",
  "answer": "King Library was constructed in 1972 and underwent major renovations in 2015.",
  "keywords": ["King Library", "built", "1972", "construction", "renovations", "2015"]
}
```

❌ **Bad RAG Entry**:
```json
{
  "question": "Library info",
  "answer": "The library was built a while ago.",
  "keywords": ["library"]
}
```

### 4. Testing After Updates
Always test queries after updating RAG:
```bash
cd ai-core
python scripts/test_fact_queries.py
```

---

## Troubleshooting

### Issue: Bot still gives wrong facts

**Solution**:
1. Check if fact is in RAG: `python scripts/query_rag.py "your question"`
2. Verify RAG confidence score (should be > 0.80)
3. Check if fact pattern is detected: add to `FACTUAL_PATTERNS`
4. Review logs for grounding mode activation

### Issue: Bot refuses to answer (always escalates)

**Solution**:
- Lower confidence threshold from 0.80 to 0.70
- Add more detailed Q&A pairs to RAG
- Check if RAG database has sufficient coverage

### Issue: Fact verification fails

**Solution**:
- Ensure RAG answer contains the exact fact (dates, names, etc.)
- Don't use abbreviations inconsistently
- Add fact variants to RAG (e.g., "1972" and "nineteen seventy-two")

---

## Example: Full Workflow for Correction

Let's say bot incorrectly answers "King Library was built in 1965":

### Step 1: Identify Correct Fact
Research and confirm: King Library was built in **1972**

### Step 2: Add to RAG
```python
# scripts/correct_king_library_year.py
fact = {
    "question": "When was King Library built?",
    "answer": "King Library was built in 1972.",
    "topic": "building_information",
    "keywords": ["King Library", "built", "1972", "construction", "year"]
}
collection.data.insert(properties=fact)
```

### Step 3: Test
```python
result = await transcript_rag_query("When was King Library built?")
print(result["text"])  # Should show "1972"
```

### Step 4: Verify End-to-End
Ask bot: "When was King Library built?"
- Check logs show fact grounding activated
- Verify answer contains "1972"
- Confirm no verification warnings

✅ **Done!** Bot now uses correct information from RAG.

---

## Additional Resources

- **Weaviate Documentation**: https://weaviate.io/developers/weaviate
- **RAG Best Practices**: Internal wiki link
- **Support**: Contact AI team for RAG database access

---

## Quick Reference

| Task | Command |
|------|---------|
| Add single fact | `python scripts/update_rag_facts.py` |
| Bulk upload | `python scripts/bulk_upload_facts.py` |
| Test retrieval | `python scripts/test_fact_queries.py` |
| Check RAG content | `python scripts/query_rag.py "question"` |
| View logs | Check application logs for `[Fact Grounding]` |

---

**Last Updated**: November 2025  
**Version**: 1.0  
**Maintainer**: AI Development Team
