# Data Management Documentation

## Overview

This folder contains documentation for processing, cleaning, and optimizing library transcript data for the chatbot's knowledge base.

---

## 📚 Documentation Files

### 1. Cleaning & Processing
- **[01-CLEANING-STRATEGY.md](./01-CLEANING-STRATEGY.md)** - Comprehensive strategy for cleaning transcript data
- **[02-PROCESS-NEW-YEAR-DATA.md](./02-PROCESS-NEW-YEAR-DATA.md)** - How to add new year transcript data (e.g., 2026)

### 2. Data Pipeline
- **[03-DATA-PIPELINE.md](./03-DATA-PIPELINE.md)** - Complete RAG data pipeline from raw transcripts to Weaviate

### 3. Optimization
- **[04-VECTOR-OPTIMIZATION.md](./04-VECTOR-OPTIMIZATION.md)** - Optimizing data for vector search performance
- **[05-OPTIMIZATION-QUICKSTART.md](./05-OPTIMIZATION-QUICKSTART.md)** - Quick optimization guide

---

## 🎯 Common Tasks

### Add New Year Transcript Data
```bash
# 1. Place raw CSV in root directory
# Example: tran_raw_2026.csv

# 2. Process the new data
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/process_new_year_data.py --year 2026

# 3. Optimize for vector search
python scripts/optimize_for_vector_search.py

# 4. Ingest into Weaviate
python scripts/ingest_transcripts_optimized.py
```
📖 **Full Guide**: [02-PROCESS-NEW-YEAR-DATA.md](./02-PROCESS-NEW-YEAR-DATA.md)

---

### Clean Existing Transcripts
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/clean_transcripts.py
```
📖 **Full Guide**: [01-CLEANING-STRATEGY.md](./01-CLEANING-STRATEGY.md)

---

### Optimize for Better Search
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python scripts/optimize_for_vector_search.py
```
📖 **Full Guide**: [04-VECTOR-OPTIMIZATION.md](./04-VECTOR-OPTIMIZATION.md)

---

## 🔄 Data Pipeline Flow

```
Raw Transcript CSV
      ↓
Clean & Filter (PII removal, deduplication)
      ↓
Optimize for Vector Search (question extraction, keyword generation)
      ↓
Store in JSON (optimized_for_weaviate.json)
      ↓
Ingest to Weaviate Cloud
      ↓
Ready for RAG Queries ✓
```

---

## 📊 Data Statistics

**Current Data** (as of December 2025):
- Raw transcripts: 2023-2025 (3 years)
- Cleaned Q&A pairs: 1,568
- Data location: `/ai-core/data/optimized_for_weaviate.json`

---

## 🛠️ Related Scripts

All scripts are in `/ai-core/scripts/`:

| Script | Purpose |
|--------|---------|
| `clean_transcripts.py` | Clean and filter transcript data |
| `deduplicate_transcripts.py` | Remove duplicate Q&A pairs |
| `process_new_year_data.py` | Add new year data |
| `optimize_for_vector_search.py` | Optimize for semantic search |
| `advanced_filter.py` | Advanced filtering with AI |
| `ingest_transcripts_optimized.py` | Load data into Weaviate |

---

## 📖 Reading Order

For first-time data processing:
1. [01-CLEANING-STRATEGY.md](./01-CLEANING-STRATEGY.md) - Understand the approach
2. [03-DATA-PIPELINE.md](./03-DATA-PIPELINE.md) - Learn the complete pipeline
3. [04-VECTOR-OPTIMIZATION.md](./04-VECTOR-OPTIMIZATION.md) - Optimize for performance

For adding new data:
1. [02-PROCESS-NEW-YEAR-DATA.md](./02-PROCESS-NEW-YEAR-DATA.md) - Step-by-step guide

---

**Clean data = Accurate answers!** 📊✨

---

**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH
