# Weaviate Record Cleanup - Quick Start

## 🎯 Quick Reference

### Find Bad Records
```bash
# Find low confidence matches
python scripts/find_problematic_rag_records.py --low-confidence

# Find by query
python scripts/find_problematic_rag_records.py --query "wrong answer"

# See recent usage
python scripts/find_problematic_rag_records.py --recent
```

### Delete Records
```bash
# Interactive (safest)
python scripts/delete_weaviate_records.py

# Direct deletion
python scripts/delete_weaviate_records.py --ids abc-123-def-456

# From file
python scripts/delete_weaviate_records.py --file bad_ids.txt
```

---

## 📋 Complete Workflow

### When user reports wrong answer:

```bash
# 1. Find the problematic records
python scripts/find_problematic_rag_records.py --query "user's question"

# 2. Delete bad records
python scripts/delete_weaviate_records.py --ids <ID1> <ID2>

# 3. Add correct fact
nano scripts/update_rag_facts.py  # Edit to add correct Q&A
python scripts/update_rag_facts.py

# 4. Test it works
python scripts/query_rag.py "user's question"
```

---

## 🔍 What Gets Tracked

Every RAG query now stores:
- ✅ User's question
- ✅ Confidence level  
- ✅ Similarity score
- ✅ **Weaviate record IDs** ← NEW!

View in analytics:
```bash
python scripts/analyze_rag_usage.py --detailed
```

Output includes:
```
1. 2025-11-17 12:45:30 ✅
   Query: When was King Library built?
   Confidence: low | Similarity: 0.623
   Weaviate IDs: abc-123, def-456, ghi-789  ← These are the records!
```

---

## 💾 Export & Delete Pattern

```bash
# Find bad records and export to file
python scripts/find_problematic_rag_records.py --low-confidence --export bad.txt

# Review the file
cat bad.txt

# Delete them all at once
python scripts/delete_weaviate_records.py --file bad.txt
```

---

## 🛡️ Safety Features

1. **Preview** - Shows record content before deletion
2. **Confirmation** - Must type 'DELETE' to confirm  
3. **Non-destructive find** - Finding doesn't change anything

Skip safety (not recommended):
```bash
python scripts/delete_weaviate_records.py --ids abc-123 --no-preview --no-confirm
```

---

## 📊 Common Scenarios

### Scenario 1: Low quality answers
```bash
# Find records with consistent low confidence
python scripts/find_problematic_rag_records.py --low-confidence --days 30

# Export IDs
python scripts/find_problematic_rag_records.py --low-confidence --export bad.txt

# Delete
python scripts/delete_weaviate_records.py --file bad.txt
```

### Scenario 2: Specific wrong answer
```bash
# Find records that matched the wrong query
python scripts/find_problematic_rag_records.py --query "King Library 1985"

# Delete the IDs shown
python scripts/delete_weaviate_records.py --ids <IDs from output>

# Add correct answer
python scripts/update_rag_facts.py
```

### Scenario 3: Clean up old/outdated info
```bash
# Find recent low-quality matches
python scripts/find_problematic_rag_records.py --recent --days 7

# Review and delete as needed
python scripts/delete_weaviate_records.py --ids <IDs>
```

---

## 📁 Files Created

| Script | Purpose |
|--------|---------|
| `find_problematic_rag_records.py` | Find bad records by confidence/query |
| `delete_weaviate_records.py` | Delete records by ID |
| `analyze_rag_usage.py` | View RAG usage with IDs *(updated)* |

---

## 🎓 Example Session

```bash
$ python scripts/find_problematic_rag_records.py --low-confidence

📊 Found 3 problematic record(s):

ID                                       Low Conf.    Avg Sim    Sample Query
========================================================================================
abc-123-def-456                          5            0.623      When was King Library...
ghi-789-jkl-012                          3            0.688      Where is makerspace...

$ python scripts/delete_weaviate_records.py --ids abc-123-def-456

📄 Record Preview (ID: abc-123-def-456):
   Question: When was King Library built? (Incorrect: says 1985)
   Topic: building_information

⚠️  You are about to DELETE 1 record(s)
   Type 'DELETE' to confirm: DELETE

✅ Successfully deleted: 1

$ nano scripts/update_rag_facts.py  # Add correct answer

$ python scripts/update_rag_facts.py

✅ Added 1 new fact(s)

$ python scripts/query_rag.py "When was King Library built?"

📊 QUERY RESULTS:
   Confidence: high
   Similarity Score: 0.92
   Answer: King Library was built in 1972.  ← CORRECT!
```

---

## 🚀 Quick Commands

| Task | Command |
|------|---------|
| Find bad records | `python scripts/find_problematic_rag_records.py --low-confidence` |
| Delete interactively | `python scripts/delete_weaviate_records.py` |
| Delete specific IDs | `python scripts/delete_weaviate_records.py --ids <ID> <ID>` |
| View recent with IDs | `python scripts/analyze_rag_usage.py --detailed` |
| Test query | `python scripts/query_rag.py "question"` |

---

**Complete Documentation**: `docs/WEAVIATE_RECORD_MANAGEMENT.md`

**Keep your RAG clean!** 🧹✨
