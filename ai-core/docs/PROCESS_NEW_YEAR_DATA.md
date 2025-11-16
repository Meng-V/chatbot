# New Year Data Processing Guide

## 📋 Overview

This document explains how to process 2026 and future years' chat transcript data.

The entire workflow has been automated - you only need one command to complete all steps.

## 🚀 Quick Start (2026 Example)

### 1. Prepare CSV File

Place the 2026 raw data CSV file in the project root directory:
```
chatbot/
├── tran_raw_2026.csv  ← New year's data
├── ai-core/
│   └── scripts/
│       └── process_new_year_data.py  ← Automation script
```

### 2. Run Automation Script

```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core

# Basic usage (recommended)
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv
```

### 3. Wait for Processing to Complete

The script will automatically complete the following steps:
1. ✅ Data Cleaning (Privacy protection: all librarian names → "Librarian")
2. ✅ Deduplication (similarity ≥0.85 considered duplicates)
3. ✅ High-Quality Filtering (confidence ≥0.7)
4. ✅ AI-Assisted Smart Filtering (using o4-mini model)
5. ⏭️ Weaviate Ingestion (manual or with `--auto-ingest`)

**Estimated Time**: 15-30 minutes (depends on data volume)

### 4. View Results

After processing, the following files will be generated:
```
ai-core/data/
├── 2026_final.json          ← Final high-quality data (for RAG)
├── 2026_deleted.json        ← Deleted data (for review)
├── 2026_step1_cleaned.json  ← Checkpoint 1: After cleaning
├── 2026_step2_deduped.json  ← Checkpoint 2: After deduplication
└── 2026_step3_high_quality.json  ← Checkpoint 3: After quality filtering
```

### 5. Ingest into Weaviate

```bash
# Manual ingestion
TRANSCRIPTS_PATH=data/2026_final.json python3 scripts/ingest_transcripts.py

# Or auto-ingest during processing
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --auto-ingest
```

---

## 📚 Advanced Usage

### Process Multiple CSV Files

```bash
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026_q1.csv ../tran_raw_2026_q2.csv ../tran_raw_2026_q3.csv ../tran_raw_2026_q4.csv
```

### Adjust Quality Thresholds

```bash
# Stricter quality requirements (confidence ≥0.8)
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --min-confidence 0.8

# More lenient deduplication threshold (similarity ≥0.9 to be considered duplicate)
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --dedup-threshold 0.9
```

### Speed Up Processing

```bash
# Increase batch size (faster but more concentrated API calls)
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --ai-batch-size 30

# Skip AI filtering (much faster but quality may be lower)
python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --skip-ai-filter
```

---

## 🔧 Parameter Reference

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `--year` | Data year (required) | - | `2026` |
| `--csv-files` | CSV file path(s) (required, multiple allowed) | - | `../tran_raw_2026.csv` |
| `--output-dir` | Output directory | `data` | `data/2026` |
| `--min-confidence` | Minimum confidence threshold | `0.7` | `0.8` |
| `--dedup-threshold` | Deduplication similarity threshold | `0.85` | `0.9` |
| `--ai-batch-size` | AI processing batch size | `20` | `30` |
| `--skip-ai-filter` | Skip AI filtering | `False` | - |
| `--auto-ingest` | Auto-ingest into Weaviate | `False` | - |

---

## 📊 Detailed Processing Workflow

### Step 1: Data Cleaning
- Parse `Transcript` field in CSV files
- Extract all Q&A pairs (not just first question and answer)
- **Privacy Protection**: All librarian names → "Librarian"
- Filter low-quality conversations (low ratings, too few/many messages, etc.)
- Auto-classify topics (discovery_search, policy_or_service, etc.)
- Calculate quality confidence scores (0.0-1.0)

### Step 2: Deduplication
- Use TF-IDF to calculate question similarity
- Similarity ≥ threshold considered duplicates
- Keep the highest quality version

### Step 3: High-Quality Filtering
- Only keep data with `confidence_score ≥ min_confidence`
- Default 0.7, adjustable

### Step 4: AI-Assisted Smart Filtering
Use o4-mini model to determine whether to delete:
- **Remove Greetings**: "Hi", "Thanks", "OK", etc.
- **Remove Low Quality**: Incomplete, meaningless, spelling errors
- **Remove Inappropriate Content**: Personal information, offensive language
- **Remove API Duplicates**: Questions covered by existing API agents
  - Real-time catalog queries → Should be handled by Primo Agent
  - Library hours → Should be handled by LibCal Agent
  - Etc.

**Core Strategy**: RAG should answer "how to" and "what is the policy", not "is it available now" or "what time does it close today"

### Step 5: Weaviate Ingestion
Import final data into Weaviate RAG system

---

## 📈 Expected Results

Based on 2023-2025 data experience:

| Stage | Expected Data Volume | Notes |
|-------|---------------------|-------|
| Raw CSV conversations | ~2,000 items | One year of conversation records |
| Extracted Q&A pairs | ~5,000 items | Multi-turn conversations split |
| After deduplication | ~3,500 items | 30% reduction |
| After quality filtering | ~1,800 items | 50% reduction |
| After AI filtering | ~600 items | 67% reduction |

**Final Retention Rate**: ~30% (600/2000)

**Quality Distribution**:
- Very High (≥0.9): ~30%
- High (0.8-0.9): ~15%
- Medium (0.7-0.8): ~55%

**Topic Distribution**:
- discovery_search: ~65%
- policy_or_service: ~15%
- general_question: ~10%
- Other: ~10%

---

## ⚠️ Frequently Asked Questions

### Q1: Processing takes too long, what should I do?

**Solution 1**: Increase batch size
```bash
--ai-batch-size 30  # default is 20
```

**Solution 2**: Skip AI filtering
```bash
--skip-ai-filter  # Much faster but may retain low-quality data
```

**Solution 3**: Raise quality threshold
```bash
--min-confidence 0.8  # Reduce amount of data needing AI processing
```

### Q2: Is the AI filtering deletion rate too high?

This is **normal**! The AI's task is to:
1. Remove greetings and low-quality content
2. Remove questions that duplicate API functionality

If you think too much is being deleted, check `data/YEAR_deleted.json` to see if the deletion reasons are reasonable.

### Q3: How do I adjust deletion rules?

Edit `scripts/advanced_filter.py`:
- Modify `SIMPLE_GREETINGS` list (simple greetings)
- Modify `API_AGENT_CAPABILITIES` (API functionality definitions)
- Modify `FILTER_SYSTEM_PROMPT` (AI judgment prompt)

### Q4: Weaviate ingestion failed?

Ensure:
1. Weaviate instance is running
2. `.env` file has correct connection information:
   ```
   WEAVIATE_HOST=xxx
   WEAVIATE_API_KEY=xxx
   OPENAI_API_KEY=xxx
   ```

Manual ingestion:
```bash
TRANSCRIPTS_PATH=data/2026_final.json python3 scripts/ingest_transcripts.py
```

### Q5: Want to keep intermediate results?

All checkpoint files are automatically saved in `data/` directory:
- `2026_step1_cleaned.json` - After cleaning
- `2026_step2_deduped.json` - After deduplication
- `2026_step3_high_quality.json` - After quality filtering
- `2026_deleted.json` - Deleted data

If a step fails, you can continue from the checkpoint.

---

## 🎯 Best Practices

### 1. Test on Small Sample First

```bash
# Process only first 100 rows (modify CSV file)
head -101 tran_raw_2026.csv > tran_raw_2026_sample.csv

python3 scripts/process_new_year_data.py \
    --year 2026 \
    --csv-files ../tran_raw_2026_sample.csv
```

### 2. Review Deleted Data

```bash
# View deleted data
cat data/2026_deleted.json | jq '.[] | {q: .question, a: .answer, reason: ._delete_reason}' | less
```

### 3. Regular Updates

Recommended to process new data **quarterly** or **annually** to keep RAG knowledge base up-to-date.

### 4. Backup Important Files

```bash
# Backup final data
cp data/2026_final.json data/backups/2026_final_$(date +%Y%m%d).json
```

---

## 📞 Need Help?

Reference Documents:
- Complete Workflow: `ai-core/docs/RAG_DATA_PIPELINE_README.md`
- Cleaning Strategy: `ai-core/docs/transcript_data_cleaning_strategy.md`
- Quick Start: `QUICKSTART_CN.md`

---

**Created**: 2024-11-16  
**Applies to**: 2026 and future years  
**Maintained by**: Chatbot Team
