# Weaviate Record Management Guide

## Overview

Every RAG query now tracks the **Weaviate record IDs** that were matched, allowing developers to identify and delete problematic records when errors are found.

---

## 🎯 What Gets Tracked

When a user question triggers RAG:

✅ **Query details** (question, confidence, similarity)  
✅ **Weaviate record IDs** (UUIDs of matched records)  
✅ **Performance metrics** (execution time)  
✅ **Match quality** (confidence level, similarity score)

**Example stored data:**
```json
{
  "query": "When was King Library built?",
  "confidence": "low",
  "similarity_score": 0.65,
  "matched_topic": "building_information",
  "weaviate_ids": [
    "abc-123-def-456",
    "ghi-789-jkl-012",
    "mno-345-pqr-678"
  ]
}
```

---

## 📊 Finding Problematic Records

### Option 1: Find Low Confidence Matches

Find Weaviate records that consistently return low confidence:

```bash
# Find records with 2+ low confidence matches in last 7 days
python scripts/find_problematic_rag_records.py --low-confidence

# Adjust parameters
python scripts/find_problematic_rag_records.py --low-confidence --days 30 --min-occurrences 5
```

**Example output:**
```
📊 Found 15 problematic record(s):

ID                                       Low Conf.    Avg Sim    Sample Query
========================================================================================
abc-123-def-456                          8            0.623      When was King Library built?...
ghi-789-jkl-012                          5            0.701      Where is the makerspace...
mno-345-pqr-678                          4            0.688      How do I renew a book...
```

### Option 2: Search by Query Text

Find records that matched a specific query:

```bash
# Find all records that matched queries containing "King Library"
python scripts/find_problematic_rag_records.py --query "King Library"

# Find records for a specific error
python scripts/find_problematic_rag_records.py --query "wrong answer"
```

### Option 3: View Recent RAG Usage

See recent queries with their Weaviate IDs:

```bash
python scripts/find_problematic_rag_records.py --recent --days 3
```

### Option 4: Check Analytics

View detailed RAG usage with Weaviate IDs:

```bash
python scripts/analyze_rag_usage.py --detailed
```

**Example output:**
```
1. 2025-11-17 12:45:30 ✅
   Query: When was King Library built?
   Confidence: low | Similarity: 0.623
   Execution Time: 245ms
   Weaviate IDs: abc-123-def-456, ghi-789-jkl-012, mno-345-pqr-678
```

---

## 🗑️ Deleting Records

### Interactive Mode (Recommended)

```bash
python scripts/delete_weaviate_records.py
```

Then enter IDs when prompted:
- Single: `abc-123-def-456`
- Multiple (comma): `abc-123, def-456, ghi-789`
- Multiple (space): `abc-123 def-456 ghi-789`

### Delete Specific IDs

```bash
# Single record
python scripts/delete_weaviate_records.py --ids abc-123-def-456

# Multiple records
python scripts/delete_weaviate_records.py --ids abc-123 def-456 ghi-789
```

### Delete from File

```bash
# Create file with IDs (one per line)
echo "abc-123-def-456" > ids_to_delete.txt
echo "ghi-789-jkl-012" >> ids_to_delete.txt

# Delete from file
python scripts/delete_weaviate_records.py --file ids_to_delete.txt
```

### Export and Delete Workflow

```bash
# Step 1: Find problematic records and export IDs
python scripts/find_problematic_rag_records.py --low-confidence --export bad_ids.txt

# Step 2: Review the file
cat bad_ids.txt

# Step 3: Delete those records
python scripts/delete_weaviate_records.py --file bad_ids.txt
```

---

## 🔍 Complete Workflow Example

### Scenario: User reports incorrect answer

**User reports**: "The chatbot said King Library was built in 1985, but it was actually built in 1972."

#### Step 1: Find the query in database

```bash
python scripts/find_problematic_rag_records.py --query "King Library built"
```

Output shows:
```
📝 Query: When was King Library built?
   Confidence: low | Similarity: 0.623
   Weaviate IDs: abc-123-def-456, ghi-789-jkl-012
```

#### Step 2: Preview the records

```bash
python scripts/delete_weaviate_records.py --ids abc-123-def-456 ghi-789-jkl-012
```

Output shows:
```
📄 Record Preview (ID: abc-123-def-456):
   Question: When was King Library built?
   Topic: building_information
   
📄 Record Preview (ID: ghi-789-jkl-012):
   Question: What year was King Library constructed?
   Topic: building_information

⚠️  You are about to DELETE 2 record(s)
   This action CANNOT be undone!
   
   Type 'DELETE' to confirm:
```

#### Step 3: Delete incorrect records

Type `DELETE` to confirm.

Output:
```
✅ Successfully deleted: 2
```

#### Step 4: Add correct fact

```bash
nano scripts/update_rag_facts.py
```

Add:
```python
{
    "question": "When was King Library built?",
    "answer": "King Library was built in 1972.",
    "topic": "building_information",
    "keywords": ["King Library", "1972", "built", "construction"]
}
```

Run:
```bash
python scripts/update_rag_facts.py
```

---

## 🛡️ Safety Features

### Preview Before Deletion

By default, the script shows a preview of each record:

```
📄 Record Preview (ID: abc-123-def-456):
   Question: When was King Library built?...
   Topic: building_information
```

**Skip preview** (not recommended):
```bash
python scripts/delete_weaviate_records.py --ids abc-123 --no-preview
```

### Confirmation Prompt

Before deletion, you must type `DELETE`:

```
⚠️  You are about to DELETE 5 record(s)
   This action CANNOT be undone!
   
   Type 'DELETE' to confirm:
```

**Skip confirmation** (dangerous!):
```bash
python scripts/delete_weaviate_records.py --ids abc-123 --no-confirm
```

---

## 📋 Command Reference

### Find Problematic Records

```bash
# Low confidence matches (2+ occurrences in 7 days)
python scripts/find_problematic_rag_records.py --low-confidence

# Adjust thresholds
python scripts/find_problematic_rag_records.py --low-confidence --days 30 --min-occurrences 5

# Find by query text
python scripts/find_problematic_rag_records.py --query "King Library"

# View recent usage
python scripts/find_problematic_rag_records.py --recent --days 7

# Export IDs to file
python scripts/find_problematic_rag_records.py --low-confidence --export bad_ids.txt
```

### Delete Records

```bash
# Interactive mode
python scripts/delete_weaviate_records.py

# Single ID
python scripts/delete_weaviate_records.py --ids abc-123-def-456

# Multiple IDs
python scripts/delete_weaviate_records.py --ids abc-123 def-456 ghi-789

# From file
python scripts/delete_weaviate_records.py --file ids_to_delete.txt

# Skip preview/confirmation (USE WITH CAUTION)
python scripts/delete_weaviate_records.py --ids abc-123 --no-preview --no-confirm
```

### View Analytics

```bash
# Show detailed logs with Weaviate IDs
python scripts/analyze_rag_usage.py --detailed

# Last 30 days
python scripts/analyze_rag_usage.py --days 30 --detailed
```

---

## 💡 Best Practices

### 1. Regular Audits

Schedule weekly reviews to identify problematic records:

```bash
# Weekly cron job
0 9 * * 1 cd /path/to/ai-core && python scripts/find_problematic_rag_records.py --low-confidence --days 7 --export /tmp/bad_ids.txt
```

### 2. Keep Records

Before mass deletion, keep a backup:

```bash
# Export current problematic IDs
python scripts/find_problematic_rag_records.py --low-confidence --export backup_$(date +%Y%m%d).txt
```

### 3. Verify After Deletion

After deleting records, add correct ones:

```bash
# Delete bad record
python scripts/delete_weaviate_records.py --ids abc-123

# Add correct fact
python scripts/update_rag_facts.py
```

### 4. Document Changes

Keep a log of deletions:

```bash
# Create deletion log
echo "$(date): Deleted records abc-123, def-456 - Reason: Incorrect building year" >> deletion_log.txt
```

### 5. Test After Changes

After deleting/adding records, test the RAG:

```bash
python scripts/query_rag.py "When was King Library built?"
```

---

## 🔄 Database Schema

Weaviate IDs are stored in the `ToolExecution` table's `parameters` field:

```sql
SELECT 
    timestamp,
    parameters::json->>'query' as query,
    parameters::json->>'confidence' as confidence,
    parameters::json->'weaviate_ids' as weaviate_ids
FROM "ToolExecution"
WHERE "agentName" = 'transcript_rag'
ORDER BY timestamp DESC
LIMIT 10;
```

Example result:
```
timestamp           | query                       | confidence | weaviate_ids
--------------------+-----------------------------+------------+---------------------------
2025-11-17 12:45:30 | When was King Library built?| low        | ["abc-123", "def-456"]
2025-11-17 12:40:15 | Library hours?              | high       | ["ghi-789"]
```

---

## 🎓 Advanced Usage

### Bulk Operations

Delete multiple sets of records:

```bash
# Find multiple problem types
python scripts/find_problematic_rag_records.py --low-confidence --export low_conf.txt
python scripts/find_problematic_rag_records.py --query "wrong" --export wrong_info.txt

# Combine files
cat low_conf.txt wrong_info.txt | sort -u > all_bad_ids.txt

# Delete all
python scripts/delete_weaviate_records.py --file all_bad_ids.txt
```

### Programmatic Deletion

Use in your own scripts:

```python
from scripts.delete_weaviate_records import connect_to_weaviate, delete_records

client = connect_to_weaviate()
ids_to_delete = ["abc-123", "def-456"]
delete_records(client, ids_to_delete, preview=True, confirm=False)
client.close()
```

### Query Database Directly

```python
import asyncio
from src.database.prisma_client import get_prisma_client
import json

async def get_weaviate_ids_for_query(query_text):
    prisma = get_prisma_client()
    await prisma.connect()
    
    executions = await prisma.toolexecution.find_many(
        where={"agentName": "transcript_rag"}
    )
    
    all_ids = []
    for exec in executions:
        params = json.loads(exec.parameters)
        if query_text.lower() in params.get("query", "").lower():
            all_ids.extend(params.get("weaviate_ids", []))
    
    await prisma.disconnect()
    return list(set(all_ids))

# Usage
ids = asyncio.run(get_weaviate_ids_for_query("King Library"))
print(f"Found IDs: {ids}")
```

---

## ⚠️ Troubleshooting

### "Record not found"

The record may have already been deleted or the ID is incorrect.

**Check:**
```bash
# Verify ID exists in Weaviate
python scripts/query_rag.py "test query"
```

### "Connection failed"

Check your `.env` credentials:

```bash
# Test connection
python scripts/setup_weaviate.py
```

### "No problematic records found"

This is good! It means your RAG is performing well.

**Adjust thresholds:**
```bash
# Lower minimum occurrences
python scripts/find_problematic_rag_records.py --low-confidence --min-occurrences 1
```

---

## 📚 Related Documentation

- **RAG Usage Tracking**: `docs/RAG_USAGE_TRACKING.md`
- **Fact Grounding**: `docs/FACT_GROUNDING_GUIDE.md`
- **Weaviate Setup**: `WEAVIATE_SETUP.md`
- **Quick Start**: `FACT_GROUNDING_QUICKSTART.md`

---

## 🎉 Summary

✅ **Weaviate IDs tracked** in database  
✅ **Find problematic records** by confidence/query  
✅ **Safe deletion** with preview + confirmation  
✅ **Complete workflow** from find → delete → add correct  

**Keep your RAG database clean and accurate!** 🚀

---

**Last Updated**: November 2025  
**Version**: 1.0
