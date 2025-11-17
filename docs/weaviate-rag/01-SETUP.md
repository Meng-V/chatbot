# Weaviate Database Setup Guide

## Quick Setup (5 Minutes)

### Step 1: Get Your Weaviate Credentials

1. Go to **Weaviate Cloud Console**: https://console.weaviate.cloud/
2. Select your new cluster
3. Click the **"Details"** tab
4. Copy your credentials:
   - **API Key** (looks like: `abcd1234efgh5678...`)
   - **Cluster URL** (looks like: `xyz123.c0.us-east1.gcp.weaviate.cloud`)

### Step 2: Update `.env` File

Open `/Users/qum/Documents/GitHub/chatbot/.env` and update lines 18-21:

```bash
# Weaviate Vector Database (NEW DATABASE - UPDATE THESE VALUES)
WEAVIATE_API_KEY=paste_your_api_key_here
WEAVIATE_HOST=paste_your_cluster_url_here
WEAVIATE_SCHEME=https
```

**Important**: 
- For `WEAVIATE_HOST`, use the URL **without** `https://`
- Example: `xyz123.c0.us-east1.gcp.weaviate.cloud` (correct)
- NOT: `https://xyz123.c0.us-east1.gcp.weaviate.cloud` (wrong)

### Step 3: Run Setup Script

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/setup_weaviate.py
```

The script will:
- ✅ Test connection to your database
- ✅ Create the `TranscriptQA` collection with proper schema
- ✅ Optionally load sample data
- ✅ Verify everything works

### Step 4: Add Your Data

After setup, add your facts:

```bash
# Edit the facts you want to add
nano scripts/update_rag_facts.py

# Run the update script
python scripts/update_rag_facts.py
```

---

## What the Setup Script Does

### 1. Environment Check
Verifies all required credentials are set:
- ✅ `WEAVIATE_HOST`
- ✅ `WEAVIATE_API_KEY`
- ✅ `OPENAI_API_KEY`

### 2. Connection Test
Tests connection to your Weaviate cluster and displays:
- Weaviate version
- Connection status
- Host information

### 3. Collection Setup
Creates `TranscriptQA` collection with schema:
- **question** (TEXT) - The question
- **answer** (TEXT) - The answer  
- **topic** (TEXT) - Category
- **keywords** (TEXT_ARRAY) - Search keywords
- **Vectorizer**: OpenAI text-embedding-3-small

### 4. Data Loading Options

**Option A: Sample Data**
- 5 example Q&A pairs
- Good for testing
- Can be deleted later

**Option B: Existing Data File**
- Loads from `data/optimized_for_weaviate.json` if exists
- Your historical Q&A pairs
- Preserves previous work

### 5. Verification
Tests the setup by:
- Counting objects in collection
- Running a test query
- Showing similarity scores

---

## Troubleshooting

### Error: "Connection failed"

**Check:**
1. WEAVIATE_HOST has no `https://` prefix
2. WEAVIATE_API_KEY is correct (copy-paste from console)
3. Cluster is running (check Weaviate Cloud Console)
4. Your IP is allowed (if using IP allowlist)

**Fix:**
```bash
# Test connection manually
curl https://YOUR_CLUSTER_URL_HERE/v1/meta
```

### Error: "WEAVIATE_HOST: NOT SET"

You need to update your `.env` file:

```bash
# Edit .env
nano /Users/qum/Documents/GitHub/chatbot/.env

# Update these lines (around line 18-21):
WEAVIATE_API_KEY=your_actual_api_key
WEAVIATE_HOST=your_actual_cluster_url
```

### Error: "TranscriptQA collection already exists"

The script will ask if you want to delete and recreate:
- **yes**: Deletes old collection and creates fresh one
- **no**: Keeps existing collection as-is

### Error: "OpenAI API key required"

Ensure `OPENAI_API_KEY` is set in `.env`:
```bash
OPENAI_API_KEY=sk-your-key-here
```

This is needed for the text-embedding-3-small vectorizer.

---

## Schema Details

### TranscriptQA Collection

```json
{
  "name": "TranscriptQA",
  "vectorizer": "text2vec-openai",
  "model": "text-embedding-3-small",
  "properties": [
    {
      "name": "question",
      "dataType": ["text"],
      "description": "The question being asked"
    },
    {
      "name": "answer",
      "dataType": ["text"],
      "description": "The answer to the question"
    },
    {
      "name": "topic",
      "dataType": ["text"],
      "description": "Topic category"
    },
    {
      "name": "keywords",
      "dataType": ["text[]"],
      "description": "Keywords for search"
    }
  ]
}
```

**Vector Dimensions**: 1536 (OpenAI text-embedding-3-small)

---

## After Setup

### 1. Test RAG Query

```bash
python scripts/query_rag.py "How do I renew a book?"
```

Expected output:
```
Confidence: high
Similarity Score: 0.920
✅ Excellent match - use this answer confidently
```

### 2. Add Your Facts

Edit `scripts/update_rag_facts.py`:

```python
CORRECT_FACTS = [
    {
        "question": "When was King Library built?",
        "answer": "King Library was built in 1972.",
        "topic": "building_information",
        "keywords": ["King Library", "1972", "built"]
    },
    # Add more facts here
]
```

Run:
```bash
python scripts/update_rag_facts.py
```

### 3. Run Tests

```bash
python scripts/test_fact_queries.py
```

### 4. Start Chatbot

Your chatbot will now automatically use the new Weaviate database for RAG queries.

---

## Common Commands

| Task | Command |
|------|---------|
| Setup new database | `python scripts/setup_weaviate.py` |
| Add/update facts | `python scripts/update_rag_facts.py` |
| Test single query | `python scripts/query_rag.py "question"` |
| Run test suite | `python scripts/test_fact_queries.py` |

---

## Database Credentials Locations

Your Weaviate credentials are stored in:
- **Primary**: `/Users/qum/Documents/GitHub/chatbot/.env` (lines 18-21)
- **Used by**: All scripts in `ai-core/scripts/` and `ai-core/src/agents/`

**Security Notes**:
- ✅ `.env` is in `.gitignore` (not committed to git)
- ✅ Never hardcode credentials in scripts
- ✅ Use environment variables only

---

## Getting Help

If you encounter issues:

1. **Check logs** during setup - they show specific errors
2. **Verify credentials** in Weaviate Cloud Console
3. **Test connection** with curl:
   ```bash
   curl https://your-cluster.weaviate.cloud/v1/meta
   ```
4. **Review documentation**: `docs/FACT_GROUNDING_GUIDE.md`

---

## Next Steps After Setup

✅ Database connected and collection created  
→ Add your library facts with `update_rag_facts.py`  
→ Test queries with `query_rag.py`  
→ Verify in chatbot  
→ Monitor logs for fact grounding

---

**Setup Script**: `scripts/setup_weaviate.py`  
**Last Updated**: November 2025  
**Version**: 1.0
