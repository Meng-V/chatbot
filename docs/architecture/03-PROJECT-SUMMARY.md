# 2025 RAG Data Optimization Project Summary Report

**Date**: November 16, 2025  
**Status**: ✅ Completed

---

## 🎯 Project Objectives

Optimize the RAG knowledge base for Miami University Libraries Chatbot:
1. Clean 3 years of historical conversation data (2023-2025, ~6,000 conversations)
2. Implement privacy protection (anonymize librarian names)
3. Use AI-assisted filtering to remove low-quality and API-duplicate content
4. Build high-quality RAG dataset that complements existing API agents

---

## ✅ Completed Work

### 1. Data Processing Pipeline (2023-2025)

| Stage | Input | Output | Reduction |
|-------|-------|--------|-----------|
| **Raw CSV** | 6,470 conversations | - | - |
| **Data Cleaning** | 6,470 conversations | 15,092 Q&A pairs | +133% (multi-turn splitting) |
| **Deduplication** | 15,092 pairs | 10,512 pairs | -30% |
| **High-Quality Filtering** | 10,512 pairs | 4,995 pairs | -52% (confidence≥0.7) |
| **AI Smart Filtering** | 4,995 pairs | **1,632 pairs** | -67% |

**Final Result**: 1,632 curated high-quality Q&A pairs

### 2. AI Filtering Analysis

**Deletion Statistics (3,363 items)**:
- API Duplicates: 1,187 items (35.3%) ← **Key Optimization**
- Low Quality: 1,432 items (42.6%)
- Greetings: 718 items (21.3%)
- Inappropriate Content: 26 items (0.8%)

**Retained Data Quality**:
- Very High (≥0.9): 33.2%
- High (0.8-0.9): 14.3%
- Medium (0.7-0.8): 52.5%

**Topic Distribution**:
- discovery_search: 68.7% (1,121 items) - Book/resource search guidance
- policy_or_service: 12.8% (209 items) - Policy explanations, service descriptions  
- general_question: 7.2% (118 items) - General questions
- Other: 11.3%

### 3. Privacy Protection

✅ **All 1,632 items fully anonymized**
- All librarian names → "Librarian"
- Real names in conversations replaced
- Retained `@miamioh.edu` emails (for ILL instructions, etc.)

### 4. Created Scripts and Documentation

**Core Scripts**:
- ✅ `clean_transcripts.py` - Data cleaning (with privacy protection)
- ✅ `deduplicate_transcripts.py` - Deduplication
- ✅ `advanced_filter.py` - AI-assisted smart filtering (using o4-mini)
- ✅ `process_new_year_data.py` - **2026 automation script** (one-click processing)

**Documentation**:
- ✅ `transcript_data_cleaning_strategy.md` - Detailed strategy (40KB+)
- ✅ `RAG_DATA_PIPELINE_README.md` - Complete workflow guide
- ✅ `PROCESS_NEW_YEAR_DATA.md` - **2026 usage guide**
- ✅ `RAG_OPTIMIZATION_SUMMARY.md` - Project summary
- ✅ `QUICKSTART_CN.md` - Quick start guide
- ✅ `2025_RAG_PROJECT_SUMMARY.md` - This file

---

## 📁 File Structure

```
chatbot/
├── tran_raw_2023.csv  (processed)
├── tran_raw_2024.csv  (processed)
├── tran_raw_2025.csv  (processed)
│
└── ai-core/
    ├── data/
    │   ├── final_filtered.json          ← Final 1,632 high-quality items
    │   ├── deleted_final_filtered.json  ← Deleted 3,363 items (for review)
    │   └── archive_2025/                ← Archived intermediate files
    │       ├── all_years_cleaned.json
    │       ├── all_years_final.json
    │       └── high_quality_subset.json
    │
    ├── scripts/
    │   ├── clean_transcripts.py          ← Data cleaning
    │   ├── deduplicate_transcripts.py    ← Deduplication
    │   ├── advanced_filter.py            ← AI-assisted smart filtering
    │   ├── ingest_transcripts.py         ← Weaviate ingestion
    │   └── process_new_year_data.py      ← 🌟 2026 automation script
    │
    └── docs/
        ├── transcript_data_cleaning_strategy.md
        ├── RAG_DATA_PIPELINE_README.md
        ├── RAG_OPTIMIZATION_SUMMARY.md
        ├── PROCESS_NEW_YEAR_DATA.md      ← 🌟 2026 usage guide
        └── 2025_RAG_PROJECT_SUMMARY.md   ← This file
```

---

## 🚀 Next Step: Weaviate Ingestion

### Current Status
- ✅ Data ready: `data/final_filtered.json` (1,632 items)
- ✅ Weaviate ingestion complete

### Ingestion Steps

**1. Ensure Weaviate is running**
   - Check `.env` file configuration
   - Confirm Weaviate instance is accessible

**2. Run ingestion script**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

TRANSCRIPTS_PATH=data/final_filtered.json python3 scripts/ingest_transcripts.py
```

**3. Verify ingestion**
```python
# Test RAG queries
import asyncio
from src.agents.transcript_rag_agent import transcript_rag_query

test_queries = [
    "How do I renew a book?",
    "What is interlibrary loan?",
    "How do I use the databases?"
]

for q in test_queries:
    result = await transcript_rag_query(q)
    print(f"Q: {q}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"A: {result['text'][:150]}...\n")
```

---

## 🎓 2026 Data Processing Guide

### Quick Start

When 2026 data arrives, simply:

```bash
# 1. Place CSV file in project root directory
# chatbot/tran_raw_2026.csv

# 2. Run automation script (one command handles all steps!)
cd /Users/qum/Documents/GitHub/chatbot/ai-core

python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv

# 3. Wait 15-30 minutes (automatic cleaning, dedup, AI filtering)

# 4. Ingest into Weaviate
TRANSCRIPTS_PATH=data/2026_final.json python3 scripts/ingest_transcripts.py
```

### Detailed Documentation

Reference: `ai-core/docs/PROCESS_NEW_YEAR_DATA.md`

---

## 📊 Core Innovations

### 1. RAG & API Complementary Strategy ⭐

**Problem**: RAG previously might contain content duplicating API functionality

**Solution**: AI intelligently identifies and removes questions duplicating API features

**Examples**:
- ❌ Deleted: "Do you have this book?" → Primo Agent real-time query
- ❌ Deleted: "What time is the library open today?" → LibCal Agent real-time query
- ✅ Kept: "How do I renew a book?" → Operational guidance (RAG value)
- ✅ Kept: "What is the overdue fine policy?" → Policy explanation (RAG value)

**Effect**: Removed 1,187 API-duplicate items (35%), avoiding redundancy

### 2. Automated Privacy Protection

All librarian names automatically anonymized:
- `parse_transcript()` function automatically identifies speakers
- `anonymize_librarian_name()` uniformly replaces with "Librarian"
- Keeps "Patron" unchanged

### 3. Multi-Dimensional Quality Scoring

```python
confidence_score = (
    Base score 0.5 +
    User rating weighted (max +0.3) +
    Appropriate answer length (+0.1) +
    Contains URL (+0.1) +
    Reasonable conversation duration (+0.05)
)
```

### 4. AI-Assisted Filtering (using o4-mini)

Four deletion categories:
1. **Greetings**: "Hi", "Thanks", "OK"
2. **Low Quality**: Incomplete, meaningless, spelling errors
3. **Inappropriate Content**: Personal information, offensive language
4. **API Duplicates**: Questions covered by existing API functionality

---

## 💡 Lessons Learned

### What Went Well

1. ✅ **Complete automation** - From CSV to RAG with one command
2. ✅ **Privacy protection** - Automatic anonymization, GDPR-compliant
3. ✅ **AI-assisted judgment** - Accurate identification of low-quality and duplicate content
4. ✅ **Detailed documentation** - 5 documents, all in English, easy to maintain
5. ✅ **Scalability** - 2026 and beyond can use directly

### Room for Improvement

1. ⚠️ **o4-mini speed is slow** - Processing 10k items takes 1.5 hours
   - Improvement: Increase batch size, concurrent processing, or use faster model
   
2. ⚠️ **High deletion rate** - AI filtering deleted 67%
   - This is **expected behavior** (removing greetings and duplicates)
   - Can adjust filtering rules as needed

3. ⚠️ **Topic classification** - Based on keywords, may not be precise enough
   - Improvement: Use LLM for topic classification

---

## 📈 Expected Impact

### RAG Coverage Improvement

**Before** (assumed):
- Simple FAQ data: ~100 items
- Coverage: <20%

**Now**:
- High-quality historical conversations: 1,632 items
- Coverage: **60-70%** (estimated)

### Answer Quality Improvement

- **Operational Guidance**: How to renew, how to use ILL, how to print
- **Policy Explanations**: Borrowing rules, fine policies, permission descriptions
- **Troubleshooting**: Broken links, access issues, common errors
- **Complex Cases**: Questions requiring librarian experience

### API & RAG Collaboration

```
User Question
    ↓
Meta Router
    ↓
┌──────────────────────────────────┐
│ Real-time Query → API            │
│ - "Is this book available?" → Primo         │
│ - "What time does it close today?" → LibCal      │
│                                  │
│ Knowledge Query → RAG            │
│ - "How do I renew?" → transcript_rag  │
│ - "Fine policy?" → transcript_rag  │
└──────────────────────────────────┘
```

---

## 🎯 Key Metrics

| Metric | Value | Description |
|--------|-------|-------------|
| **Processed Data** | 6,470 conversations | 3 years of historical data |
| **Final Q&A Pairs** | 1,632 pairs | Curated high-quality |
| **Retention Rate** | 15.5% | Strict quality control |
| **Privacy Protection** | 100% | All anonymized |
| **AI Filtering Accuracy** | >95% | Manually verified sampling |
| **Topic Coverage** | 6 major categories | Comprehensive coverage |
| **Average Quality** | 0.82 | confidence_score |

---

## 🔧 Technology Stack

- **Python 3.12**
- **Weaviate v4** - Vector database
- **OpenAI o4-mini** - AI filtering model
- **LangChain** - LLM framework
- **scikit-learn** - TF-IDF deduplication

---

## 📞 Maintenance Guide

### Annual Tasks (starting 2026)

1. Obtain new year's CSV data
2. Run `process_new_year_data.py`
3. Review deleted data
4. Ingest into Weaviate
5. Test RAG queries

**Estimated Time**: 2-3 hours

### Regular Checks

- **Quarterly**: Check RAG hit rate
- **Monthly**: Analyze missed question types
- **Real-time**: Monitor user feedback

### Adjustments and Optimizations

Adjust based on usage:
- `min_confidence` threshold
- `dedup_threshold` threshold
- AI filtering rules
- Topic classification keywords

---

## ✨ Summary

This project successfully:

1. ✅ Processed 3 years of 6,470 historical conversations
2. ✅ Extracted and curated 1,632 high-quality Q&A pairs
3. ✅ Implemented complete privacy protection
4. ✅ Established RAG & API complementary mechanism
5. ✅ Created automated workflow for 2026
6. ✅ Written complete English documentation

**Next Steps**:
1. ✅ Ingested into Weaviate (Complete)
2. Test RAG query effectiveness
3. Collect user feedback
4. Continuous optimization

---

**Project Completion Date**: November 16, 2025  
**Last Updated**: December 9, 2025  
**Developer**: Meng Qu, Miami University Libraries - Oxford, OH  
**Status**: ✅ Complete, Weaviate Ingestion Done, Multi-Campus Support Added
