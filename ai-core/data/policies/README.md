# Oxford LibGuides Policy Data

This directory contains ingested policy data from Miami University Oxford LibGuides pages for use in the circulation and borrowing policy routing system.

## Files

- `circulation_policies_oxford_chunks.jsonl` - Semantic chunks from Oxford LibGuides policy pages (300-700 tokens each)
- `circulation_policies_oxford_facts.jsonl` - Atomic Q&A fact cards for direct answer mode

## Data Sources

Authoritative Oxford policy pages:

1. Main circulation policies: https://libguides.lib.miamioh.edu/mul-circulation-policies
2. Loan periods & fines: https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-fines
3. OhioLINK & ILL: https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-ohiolink-ill
4. Recall & request: https://libguides.lib.miamioh.edu/mul-circulation-policies/recall-request
5. Course reserves: https://libguides.lib.miamioh.edu/reserves-textbooks
6. Streaming video: https://libguides.lib.miamioh.edu/reserves-textbooks/StreamingVideoAndRemoteInstruction
7. Electronic reserves: https://libguides.lib.miamioh.edu/reserves-textbooks/electronicreserves
8. Document Delivery and Remote Instruction: https://libguides.lib.miamioh.edu/reserves-textbooks/documentdelivery

## Usage

### 1. Ingest Policy Pages

Fetch and parse Oxford LibGuides policy pages, generate chunks and fact cards:

```bash
cd ai-core
python -m scripts.ingest_libguides_policies_oxford
```

This creates:
- `circulation_policies_oxford_chunks.jsonl` (semantic chunks)
- `circulation_policies_oxford_facts.jsonl` (Q&A fact cards)

### 2. Upsert to Weaviate

Load data into Weaviate collections:

```bash
python -m scripts.upsert_policies_to_weaviate
```

This creates/updates:
- `CirculationPolicies` collection (chunks)
- `CirculationPolicyFacts` collection (fact cards)

### 3. Test Routing

Verify policy routing works correctly:

```bash
python -m scripts.test_policy_routing
```

## Data Structure

### Chunks (CirculationPolicies)

```json
{
  "id": "unique_hash",
  "canonical_url": "https://libguides.lib.miamioh.edu/...",
  "source_url": "https://libguides.lib.miamioh.edu/...",
  "title": "Circulation Policies",
  "section_path": "Loan Periods",
  "campus_scope": "oxford",
  "topic": "loan_periods",
  "audience": "students",
  "keywords": ["loan", "borrow", "checkout"],
  "chunk_text": "Full text content..."
}
```

### Fact Cards (CirculationPolicyFacts)

```json
{
  "id": "unique_hash",
  "campus_scope": "oxford",
  "fact_type": "loan_period",
  "question_patterns": [
    "how long can I borrow books",
    "what is the loan period for books",
    "book checkout period"
  ],
  "answer": "Books: Loan period: 28 days, Renewable: Yes",
  "canonical_url": "https://libguides.lib.miamioh.edu/...",
  "source_url": "https://libguides.lib.miamioh.edu/...",
  "anchor_hint": "loan-periods",
  "tags": ["loan", "book", "checkout"]
}
```

## Routing Behavior

### Default Campus Scope

**Oxford-default rule**: All policy queries assume Oxford/King Library unless user explicitly mentions:
- Hamilton campus / Rentschler Library
- Middletown campus / Gardner-Harvey Library
- Regional campuses

### Query Priority

1. **CirculationPolicyFacts** (score ≥ 0.78) → Direct answer with URL
2. **CirculationPolicies chunks** (score ≥ 0.70) → URL with excerpt
3. **Google CSE** with Oxford constraints → Oxford mul-circulation-policies pages only

### Oxford Constraints for Google

When falling back to Google CSE, queries are constrained to:
- Site: `libguides.lib.miamioh.edu`
- Prefer: `mul-circulation-policies` pages
- Exclude: `BorrowingPolicy` (regional), `-Hamilton`, `-Middletown`

## Maintenance

### Re-ingest Data

To update policy data after LibGuides changes:

```bash
# 1. Re-fetch and parse
python -m scripts.ingest_libguides_policies_oxford

# 2. Re-upsert to Weaviate
python -m scripts.upsert_policies_to_weaviate

# 3. Verify
python -m scripts.test_policy_routing
```

### Add New Policy Pages

Edit `scripts/ingest_libguides_policies_oxford.py`:

```python
OXFORD_POLICY_URLS = [
    # ... existing URLs
    "https://libguides.lib.miamioh.edu/new-policy-page",  # Add here
]
```

Then re-run ingestion and upsert.

## Integration

### Tools Using This Data

1. **CirculationPolicyTool** (`src/tools/circulation_policy_tool.py`)
   - Queries CirculationPolicyFacts for direct answers
   - Falls back to CirculationPolicies chunks
   - Returns Oxford mul-circulation-policies URL if no match

2. **BorrowingPolicySearchTool** (`src/tools/google_site_enhanced_tools.py`)
   - Tries CirculationPolicyFacts first
   - Then CirculationPolicies chunks
   - Finally Google CSE with Oxford constraints

### Campus Scope Detection

`src/utils/campus_scope.py` provides:
- `detect_campus_scope(message)` → "oxford" | "hamilton" | "middletown"
- `is_oxford_default(message)` → True unless regional mentioned
- `get_campus_display_name(scope)` → Human-readable name

## Expected Behavior

### Example: "how long can I borrow a book"

**Before (problematic)**:
- Google CSE returns regional BorrowingPolicy page
- Wrong campus, not authoritative

**After (correct)**:
1. Check CirculationPolicyFacts → High-confidence match (score 0.85)
2. Return direct answer: "Books: Loan period: 28 days, Renewable: Yes"
3. Include URL: https://libguides.lib.miamioh.edu/mul-circulation-policies/loan-periods-fines

### Example: "Hamilton campus borrowing policy"

**Behavior**:
1. Detect campus_scope = "hamilton"
2. Query Weaviate with campus filter (may have no Hamilton data yet)
3. Fall back to Google with regional allowed
4. Return appropriate Hamilton/Rentschler result

## Troubleshooting

### No fact matches found

- Check Weaviate collections exist: `CirculationPolicyFacts`, `CirculationPolicies`
- Verify data was upserted: Check collection object counts
- Try re-running ingestion with fresh data

### Wrong campus returned

- Check `detect_campus_scope()` logic in `src/utils/campus_scope.py`
- Verify campus_scope parameter passed to tools
- Review query for campus keywords

### Still getting BorrowingPolicy URLs

- Check Google CSE query constraints in `BorrowingPolicySearchTool`
- Verify Oxford filter: `site:libguides.lib.miamioh.edu mul-circulation-policies`
- Check negative terms: `-BorrowingPolicy -regional`

## Performance

- **Chunks**: ~50-150 items (depends on page content)
- **Facts**: ~100-300 items (depends on tables and sections)
- **Query time**: <200ms for Weaviate, 500-1500ms for Google CSE
- **Cache**: Google CSE results cached 7 days

## Quality Criteria

✅ **Passing criteria**:
- Oxford queries never return regional BorrowingPolicy URLs
- High-confidence facts (≥0.78) return direct answers
- Fallback URLs always point to Oxford mul-circulation-policies
- Regional queries (when requested) still work

❌ **Failing criteria**:
- BorrowingPolicy URLs appear for Oxford queries
- Low-confidence queries trigger unnecessary clarification
- Wrong campus data returned
