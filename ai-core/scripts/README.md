# Scripts Directory

This directory contains utility scripts for database setup, data processing, RAG management, and system maintenance.

## 📋 Table of Contents

1. [Database Setup](#database-setup)
2. [Data Ingestion Pipeline](#data-ingestion-pipeline)
3. [RAG Management](#rag-management)
4. [Analysis & Debugging](#analysis--debugging)

---

## 🗄️ Database Setup

### `setup_db.sh`
**Purpose**: Initialize PostgreSQL database with Prisma schema  
**Usage**: `./scripts/setup_db.sh`  
**When to use**: First-time setup or database reset

### `setup_weaviate.py`
**Purpose**: Initialize Weaviate vector database with proper schema and collections  
**Usage**: `python -m scripts.setup_weaviate`  
**When to use**: First-time setup or Weaviate schema changes

### `seed_library_locations.py`
**Purpose**: Populate library location hierarchy (Campus → Library → LibrarySpace) with LibCal IDs  
**Usage**: `python -m scripts.seed_library_locations`  
**When to use**: After database reset or when adding new libraries  
**Data populated**:
- Oxford Campus: King Library, Art & Architecture Library
- Hamilton Campus: Rentschler Library  
- Middletown Campus: Gardner-Harvey Library
- Spaces: Makerspace, Special Collections

---

## 📊 Data Ingestion Pipeline

### Complete Pipeline: `process_new_year_data.py`
**Purpose**: Automated end-to-end pipeline for processing new chat transcript data  
**Usage**:
```bash
python -m scripts.process_new_year_data \
    --year 2026 \
    --csv-files ../tran_raw_2026.csv \
    --output data/2026_final.json \
    --ingest
```
**Workflow**:
1. Data cleaning (privacy protection)
2. Deduplication
3. Quality filtering
4. AI-assisted smart filtering
5. Weaviate ingestion (optional)

**When to use**: Processing new year's chat transcript data

---

### Individual Pipeline Components

#### `clean_transcripts.py`
**Purpose**: Clean raw CSV transcript data with privacy protection  
**Usage**:
```bash
python -m scripts.clean_transcripts \
    --csv-files ../tran_raw_2024.csv ../tran_raw_2025.csv \
    --output data/cleaned.json
```
**Features**:
- Removes PII (names, emails, IDs)
- Extracts Q&A pairs from conversations
- Handles encoding issues
- Categorizes by topic

#### `deduplicate_transcripts.py`
**Purpose**: Remove duplicate Q&A pairs using fuzzy matching  
**Usage**:
```bash
python -m scripts.deduplicate_transcripts \
    --input data/cleaned.json \
    --output data/deduplicated.json
```
**Features**:
- Uses TF-IDF + cosine similarity
- Configurable threshold (default: 0.95)
- Preserves best quality answers

#### `advanced_filter.py`
**Purpose**: AI-assisted filtering to remove low-quality and API-redundant Q&A pairs  
**Usage**:
```bash
python -m scripts.advanced_filter \
    --input data/deduplicated.json \
    --output data/filtered.json
```
**Features**:
- Removes simple greetings
- Filters API-redundant content (Primo, LibCal already handle these)
- AI quality assessment using o4-mini
- Batch processing for efficiency

#### `ingest_transcripts_optimized.py`
**Purpose**: Ingest processed transcript data into Weaviate with optimized batch processing  
**Usage**:
```bash
python -m scripts.ingest_transcripts_optimized \
    --json-file data/filtered.json \
    --batch-size 100
```
**Features**:
- Batch insertion for performance
- Error handling and retry logic
- Progress tracking
- Duplicate detection

#### `ingest_myguide.py`
**Purpose**: Ingest MyGuide data (library guides, tutorials) into Weaviate  
**Usage**: `python -m scripts.ingest_myguide --json-file data/myguide.json`  
**When to use**: Adding new library guide content

#### `optimize_for_vector_search.py`
**Purpose**: Optimize Q&A pairs for better vector search by generating keyword expansions  
**Usage**:
```bash
python -m scripts.optimize_for_vector_search \
    --input data/filtered.json \
    --output data/optimized.json
```
**Features**:
- Generates alternative phrasings
- Adds domain-specific keywords
- Improves semantic search recall

---

## 🔧 RAG Management

### `add_correction_to_rag.py`
**Purpose**: Add manual corrections to RAG for fact updates  
**Usage**:
```bash
python -m scripts.add_correction_to_rag \
    --question "What are the library hours?" \
    --answer "Updated hours information..." \
    --topic "library_hours" \
    --source "manual_correction"
```
**When to use**: Adding corrections for outdated/incorrect RAG responses

### `update_rag_facts.py`
**Purpose**: Batch update RAG facts from JSON file  
**Usage**: `python -m scripts.update_rag_facts --input corrections.json`  
**When to use**: Updating multiple facts at once

### `list_rag_corrections.py`
**Purpose**: List all manual corrections in Weaviate  
**Usage**: `python -m scripts.list_rag_corrections`  
**Output**: Displays correction history with timestamps

### `verify_correction.py`
**Purpose**: Verify that a correction was successfully added to RAG  
**Usage**: `python -m scripts.verify_correction --query "library hours"`  
**When to use**: QA testing after adding corrections

### `find_problematic_rag_records.py`
**Purpose**: Find RAG records with quality issues  
**Usage**: `python -m scripts.find_problematic_rag_records`  
**Detects**:
- Short/incomplete answers
- Potentially outdated content
- Low-quality Q&A pairs

### `delete_weaviate_records.py`
**Purpose**: Delete specific records from Weaviate by UUID or query  
**Usage**:
```bash
# Delete by UUID
python -m scripts.delete_weaviate_records --uuid abc-123-def

# Delete by query
python -m scripts.delete_weaviate_records --query "outdated policy"
```
**When to use**: Removing incorrect or obsolete RAG entries

### `weaviate_cleanup.py`
**Purpose**: Clean up Weaviate database (remove duplicates, low-quality entries)  
**Usage**: `python -m scripts.weaviate_cleanup`  
**When to use**: Regular maintenance, after large data imports

---

## 🔍 Analysis & Debugging

### `analyze_rag_usage.py`
**Purpose**: Analyze RAG usage patterns and quality metrics  
**Usage**: `python -m scripts.analyze_rag_usage`  
**Provides**:
- Topic distribution
- Average answer quality
- Most/least retrieved topics
- Coverage gaps

### `query_rag.py`
**Purpose**: Test RAG retrieval with custom queries  
**Usage**: `python -m scripts.query_rag --query "How do I reserve a study room?"`  
**When to use**: Debugging RAG responses, testing improvements

---

## 🧹 Cleanup Summary

**Deleted scripts** (6 total):
- `add_space_websites.py` - One-time migration (completed)
- `add_website_column.py` - One-time migration (completed)
- `update_library_websites.py` - One-time migration (completed)
- `ingest_transcripts.py` - Replaced by optimized version
- `review_filtered.py` - Development utility (no longer needed)
- `health_check.py` - Basic health check (replaced by proper monitoring)

**Remaining scripts**: 19 useful scripts organized by function

---

## 📝 Best Practices

1. **New Data Processing**: Use `process_new_year_data.py` for complete automated pipeline
2. **Database Reset**: Run in order: `setup_db.sh` → `setup_weaviate.py` → `seed_library_locations.py`
3. **RAG Updates**: Use `add_correction_to_rag.py` for single updates, `update_rag_facts.py` for batch
4. **Regular Maintenance**: Run `weaviate_cleanup.py` monthly, `find_problematic_rag_records.py` quarterly
5. **Quality Checks**: Use `analyze_rag_usage.py` to monitor RAG performance

---

## 🚨 Important Notes

- All scripts use `o4-mini` model for AI operations (no temperature parameter)
- Always backup before running cleanup scripts (`delete_weaviate_records.py`, `weaviate_cleanup.py`)
- Run scripts from project root: `python -m scripts.<script_name>`
- Check `.env` file has required API keys (OPENAI_API_KEY, WEAVIATE_URL, etc.)
