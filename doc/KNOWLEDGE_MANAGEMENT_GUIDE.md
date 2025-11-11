# Knowledge Management & RAG Optimization Guide

**Date**: November 11, 2025  
**Version**: 1.0  

---

## Table of Contents
1. [Current System Analysis](#current-system-analysis)
2. [Identified Limitations](#identified-limitations)
3. [Knowledge Management Strategy](#knowledge-management-strategy)
4. [RAG System Optimization](#rag-system-optimization)
5. [Manual Knowledge Curation](#manual-knowledge-curation)
6. [Implementation Roadmap](#implementation-roadmap)

---

## Current System Analysis

### ✅ You ARE Using RAG

**Location**: `ai-core/src/agents/transcript_rag_agent.py`

**Current Setup**:
- **Vector Database**: Weaviate (cloud-hosted)
- **Collection**: `TranscriptQA` 
- **Embeddings**: OpenAI embeddings (via X-OpenAI-Api-Key header)
- **Query Method**: `near_text` semantic search
- **Limit**: 3 most relevant results
- **Purpose**: Retrieve answers from historical chat transcripts

**How It Works**:
```python
# User asks: "How do I renew a book?"
# System:
# 1. Converts query to embedding
# 2. Searches Weaviate for similar Q&A pairs
# 3. Returns top 3 most relevant historical answers
# 4. LLM synthesizes response using retrieved context
```

### Current Knowledge Sources

Your chatbot has **7 specialized agents** with different knowledge sources:

| Agent | Knowledge Source | Type |
|-------|------------------|------|
| **Primo Agent** | Miami catalog API | Live API |
| **LibCal Agent** | LibCal hours/rooms API | Live API |
| **LibGuide Agent** | LibGuides API | Live API |
| **Google Site Agent** | Miami library website | Live search |
| **Subject Librarian** | MuGuide database (710 subjects) | Database |
| **Transcript RAG** | Weaviate vector store | RAG/Vector DB |
| **LibChat** | Human handoff | LibChat Widget |

---

## Identified Limitations

### 🔴 Critical Issues

1. **Limited RAG Coverage**
   - Only uses historical transcripts
   - No library policies, procedures, or FAQs in RAG
   - No subject-specific research guidance
   - No departmental information

2. **Knowledge Gaps**
   - Complex multi-step procedures not documented
   - Nuanced policy interpretations missing
   - Edge cases and exceptions not covered
   - Context-dependent answers need better grounding

3. **Stale Knowledge**
   - Historical transcripts may contain outdated info
   - No version control on knowledge
   - No mechanism to retire old information
   - API responses may change without warning

4. **Poor Knowledge Discovery**
   - Hard to identify what bot doesn't know
   - No analytics on failed queries
   - Limited feedback loop for improvement
   - Difficult to trace incorrect answers to source

---

## Knowledge Management Strategy

### Phase 1: Audit & Categorize (Week 1-2)

#### 1.1 Identify Knowledge Gaps

**Create tracking spreadsheet** with columns:
- User query (exact question)
- Current answer (what bot said)
- Correct answer (what it should say)
- Knowledge source needed
- Priority (high/medium/low)
- Status (pending/curated/ingested)

**Sample Categories**:
```
1. Library Policies
   - Borrowing limits
   - Fines and fees
   - Lost items
   - Interlibrary loan rules
   - Access policies
   - Copyright and fair use

2. Procedures
   - How to place a hold
   - How to request ILL
   - How to access databases off-campus
   - How to cite sources
   - How to contact subject librarian

3. Services & Resources
   - Writing center hours
   - Research consultations
   - Equipment checkout
   - Study room policies
   - Special collections access

4. Technical Issues
   - Login problems
   - Database access errors
   - VPN setup
   - Account issues
   - Browser compatibility

5. Subject-Specific
   - Engineering research guides
   - Business databases
   - Science citations
   - Humanities primary sources
```

#### 1.2 Quality Assessment

**Review current RAG data**:
```bash
cd ai-core
source .venv/bin/activate

# Check what's in Weaviate
python scripts/check_weaviate_content.py
```

**Evaluation criteria**:
- ✅ Accuracy: Is information correct?
- ✅ Currency: Is it up to date?
- ✅ Completeness: Does it fully answer?
- ✅ Clarity: Is it understandable?
- ✅ Source: Can we verify it?

### Phase 2: Manual Knowledge Curation (Week 3-6)

#### 2.1 Create Knowledge Base Documents

**Recommended Format**: Markdown with metadata

```markdown
---
title: "How to Renew Books"
category: borrowing_policies
keywords: [renew, renewal, extend, due date, books]
last_updated: 2025-11-11
verified_by: jane.doe@miamioh.edu
source_url: https://lib.miamioh.edu/use/borrowing/renewals
---

# How to Renew Books

## Quick Answer
You can renew books up to 3 times online through your library account.

## Detailed Steps
1. Log in to lib.miamioh.edu
2. Click "My Account" 
3. Select "Loans"
4. Click "Renew" next to each item
5. Confirm renewal

## Important Notes
- Books must be renewed before due date
- Cannot renew if someone else has requested the item
- Maximum 3 renewals per item
- Recall requests override renewals

## Exceptions
- Reserve materials cannot be renewed
- Recalled items must be returned immediately
- Overdue items must be returned before renewal

## Contact
Questions? Email library@miamioh.edu or call (513) 529-4141
```

#### 2.2 Curated Knowledge Structure

**Organize by hierarchy**:
```
knowledge_base/
├── policies/
│   ├── borrowing.md
│   ├── fines_fees.md
│   ├── access_privileges.md
│   └── copyright.md
├── procedures/
│   ├── renewals.md
│   ├── holds.md
│   ├── ill_requests.md
│   └── database_access.md
├── services/
│   ├── research_help.md
│   ├── study_spaces.md
│   ├── equipment.md
│   └── special_collections.md
├── technical/
│   ├── vpn_setup.md
│   ├── account_issues.md
│   └── troubleshooting.md
└── subjects/
    ├── engineering/
    ├── business/
    ├── sciences/
    └── humanities/
```

### Phase 3: RAG Enhancement (Week 7-10)

#### 3.1 Create Ingestion Pipeline

**New script**: `scripts/ingest_knowledge_base.py`

```python
"""Ingest curated knowledge base into Weaviate."""
import os
import frontmatter  # For parsing markdown with metadata
import weaviate
from pathlib import Path

def ingest_knowledge_base(knowledge_dir: Path):
    """
    Ingest markdown files with metadata into Weaviate.
    
    Features:
    - Extracts metadata from frontmatter
    - Chunks long documents intelligently
    - Preserves source attribution
    - Tracks ingestion date
    - Supports versioning
    """
    client = connect_weaviate()
    
    for md_file in knowledge_dir.rglob("*.md"):
        post = frontmatter.load(md_file)
        
        # Create document with rich metadata
        doc = {
            "title": post.get("title", md_file.stem),
            "content": post.content,
            "category": post.get("category", "general"),
            "keywords": post.get("keywords", []),
            "last_updated": post.get("last_updated"),
            "source_url": post.get("source_url"),
            "verified_by": post.get("verified_by"),
            "file_path": str(md_file),
            "ingestion_date": datetime.now().isoformat()
        }
        
        # Chunk if needed (split on headers)
        chunks = chunk_document(post.content)
        
        # Insert each chunk
        for i, chunk in enumerate(chunks):
            client.collections.get("LibraryKnowledge").data.insert({
                **doc,
                "content": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
```

#### 3.2 Multi-Source RAG Strategy

**Enhance Weaviate schema** for multiple collections:

```python
# Collection 1: Curated Knowledge (HIGH PRIORITY)
LibraryKnowledge {
    title: str
    content: str
    category: str
    keywords: [str]
    last_updated: date
    source_url: str
    verified_by: str
    confidence_score: float  # 0-1, based on verification
}

# Collection 2: Historical Transcripts (MEDIUM PRIORITY)
TranscriptQA {
    question: str
    answer: str
    timestamp: date
    success_rating: float  # Based on user feedback
    deprecated: bool  # Mark old answers
}

# Collection 3: Policy Documents (HIGH PRIORITY)
PolicyDocuments {
    policy_name: str
    content: str
    effective_date: date
    last_reviewed: date
    authority: str  # Who approved it
}

# Collection 4: FAQs (HIGH PRIORITY)
FrequentlyAskedQuestions {
    question: str
    answer: str
    category: str
    view_count: int
    helpful_votes: int
    last_updated: date
}
```

**Query Strategy** (in order of priority):

```python
async def enhanced_rag_query(user_question: str):
    """
    Multi-source RAG with prioritization.
    """
    results = []
    
    # 1. Check curated knowledge first (highest confidence)
    curated = await query_collection("LibraryKnowledge", user_question, limit=3)
    results.extend(curated)
    
    # 2. Check FAQs (verified answers)
    faqs = await query_collection("FrequentlyAskedQuestions", user_question, limit=2)
    results.extend(faqs)
    
    # 3. Check policy documents (authoritative)
    if is_policy_question(user_question):
        policies = await query_collection("PolicyDocuments", user_question, limit=2)
        results.extend(policies)
    
    # 4. Fall back to historical transcripts (lowest confidence)
    if len(results) < 3:
        transcripts = await query_collection(
            "TranscriptQA", 
            user_question, 
            limit=5,
            filters={"deprecated": False, "success_rating": {"$gte": 0.7}}
        )
        results.extend(transcripts)
    
    # Deduplicate and rank by confidence
    return rank_and_deduplicate(results)
```

### Phase 4: Feedback & Improvement (Ongoing)

#### 4.1 Knowledge Quality Metrics

**Track these KPIs**:

```sql
-- Message ratings by knowledge source
SELECT 
    tool_name,
    COUNT(*) as total_uses,
    AVG(CASE WHEN m.isPositiveRated THEN 1 ELSE 0 END) as positive_rate,
    COUNT(DISTINCT conversation_id) as unique_conversations
FROM ToolExecution te
JOIN Message m ON te.conversationId = m.conversationId
WHERE m.type = 'assistant'
GROUP BY tool_name
ORDER BY positive_rate DESC;

-- Identify knowledge gaps
SELECT 
    m.content as user_question,
    COUNT(*) as frequency,
    AVG(CASE WHEN m2.isPositiveRated THEN 1 ELSE 0 END) as satisfaction
FROM Message m
JOIN Message m2 ON m.conversationId = m2.conversationId 
WHERE m.type = 'user' 
  AND m2.type = 'assistant'
  AND m2.isPositiveRated IS NOT NULL
GROUP BY m.content
HAVING AVG(CASE WHEN m2.isPositiveRated THEN 1 ELSE 0 END) < 0.5
ORDER BY frequency DESC
LIMIT 50;
```

#### 4.2 Knowledge Update Workflow

**Weekly Review Process**:

1. **Monday**: Export low-rated interactions
2. **Tuesday**: Review and categorize issues
3. **Wednesday**: Research correct answers
4. **Thursday**: Update knowledge base
5. **Friday**: Re-ingest and test

**Deprecation Strategy**:
```python
# Mark outdated information
def deprecate_knowledge(doc_id, reason, replaced_by=None):
    client.collections.get("LibraryKnowledge").data.update(
        doc_id,
        properties={
            "deprecated": True,
            "deprecation_reason": reason,
            "deprecation_date": datetime.now().isoformat(),
            "replaced_by": replaced_by
        }
    )
```

---

## RAG System Optimization

### Current RAG Configuration Review

**File**: `ai-core/src/agents/transcript_rag_agent.py`

**Current Issues**:
```python
# ❌ Problem 1: No filtering
response = collection.query.near_text(
    query=query,
    limit=3
)
# Should filter out deprecated/low-quality results

# ❌ Problem 2: No metadata returned
# Can't see source, date, confidence

# ❌ Problem 3: Fixed limit of 3
# Sometimes need more, sometimes less

# ❌ Problem 4: No reranking
# First 3 results may not be best
```

### Recommended Improvements

#### 1. Enhanced Query with Filtering

```python
async def enhanced_rag_query(query: str, log_callback=None) -> Dict[str, Any]:
    """Enhanced RAG with filtering and reranking."""
    
    if not client:
        return error_response()
    
    try:
        collection = client.collections.get("TranscriptQA")
        
        # Add filters for quality
        response = collection.query.near_text(
            query=query,
            limit=10,  # Get more candidates
            filters={
                "deprecated": False,  # Exclude old info
                "success_rating": {"$gte": 0.6}  # Minimum quality threshold
            },
            return_metadata=["distance", "certainty"],
            include_vector=False
        )
        
        # Rerank by multiple factors
        results = rerank_results(
            response.objects,
            factors={
                "semantic_similarity": 0.4,
                "recency": 0.2,
                "success_rating": 0.3,
                "view_count": 0.1
            }
        )
        
        # Return top 3 after reranking
        top_results = results[:3]
        
        # Format with source attribution
        formatted_answers = []
        for r in top_results:
            formatted_answers.append({
                "answer": r.properties["answer"],
                "confidence": r.metadata.certainty,
                "source": "Historical Q&A",
                "last_verified": r.properties.get("timestamp"),
                "helpful_votes": r.properties.get("success_rating", 0)
            })
        
        return {
            "source": "Enhanced TranscriptRAG",
            "success": True,
            "results": formatted_answers,
            "text": synthesize_answer(formatted_answers)
        }
        
    except Exception as e:
        return error_response(str(e))
```

#### 2. Hybrid Search (Keyword + Semantic)

```python
def hybrid_search(query: str, alpha=0.5):
    """
    Combine keyword (BM25) and semantic (vector) search.
    
    alpha: Weight between keyword (0) and semantic (1)
           0.5 = equal weight
    """
    collection = client.collections.get("LibraryKnowledge")
    
    # Weaviate v4 hybrid search
    response = collection.query.hybrid(
        query=query,
        alpha=alpha,  # Tune this based on query type
        limit=10,
        return_metadata=["score", "explainScore"]
    )
    
    return response.objects
```

#### 3. Query Expansion

```python
async def expand_query(original_query: str) -> List[str]:
    """
    Generate query variations for better retrieval.
    """
    llm_prompt = f"""Given this library question: "{original_query}"

Generate 3 alternative phrasings that mean the same thing:
1. More formal version
2. Simplified version
3. Common variations

Return as JSON array."""

    response = await llm.ainvoke([HumanMessage(content=llm_prompt)])
    variations = json.loads(response.content)
    
    return [original_query] + variations

# Usage
async def rag_with_expansion(query: str):
    queries = await expand_query(query)
    
    all_results = []
    for q in queries:
        results = await rag_query(q)
        all_results.extend(results)
    
    # Deduplicate and rank
    return deduplicate_results(all_results)
```

#### 4. Confidence Scoring

```python
def calculate_confidence(result, query):
    """
    Multi-factor confidence score.
    """
    factors = {
        # Semantic similarity (from Weaviate)
        "similarity": result.metadata.certainty,
        
        # Recency (prefer newer information)
        "recency": time_decay_score(result.properties["last_updated"]),
        
        # Verification status
        "verified": 1.0 if result.properties.get("verified_by") else 0.5,
        
        # User feedback
        "user_rating": result.properties.get("success_rating", 0.5),
        
        # Source authority
        "source_trust": SOURCE_TRUST_SCORES.get(result.properties["source"], 0.5)
    }
    
    # Weighted combination
    confidence = (
        factors["similarity"] * 0.35 +
        factors["recency"] * 0.15 +
        factors["verified"] * 0.25 +
        factors["user_rating"] * 0.15 +
        factors["source_trust"] * 0.10
    )
    
    return min(1.0, confidence)
```

---

## Manual Knowledge Curation Workflow

### Step-by-Step Process

#### Week 1: Planning & Setup

1. **Create Knowledge Repository**
```bash
mkdir -p knowledge_base/{policies,procedures,services,technical,subjects}
```

2. **Setup Curation Spreadsheet**
   - Google Sheets or Excel
   - Columns: Topic, Current Gap, Priority, Assigned To, Status, Date Added, Date Completed
   - Share with library staff

3. **Identify Subject Matter Experts**
   - Assign categories to specific librarians
   - Schedule weekly check-ins

#### Week 2-3: Content Creation

**Daily Workflow** (2 hours/day per curator):

1. **Morning (30 min)**: Review user questions from previous day
   - Check database for thumbs-down ratings
   - Identify patterns in failed queries

2. **Mid-day (60 min)**: Write/update 2-3 knowledge articles
   - Use template format (shown earlier)
   - Include metadata
   - Verify information with authoritative sources

3. **Afternoon (30 min)**: Review and approve team submissions
   - Check for accuracy
   - Ensure consistent formatting
   - Add to git repository

**Sample Daily Output**:
- 2-3 new articles per curator
- 5-10 articles reviewed
- 1-2 deprecated articles marked

#### Week 4: Quality Review

1. **Content Audit**
   - All articles reviewed by second person
   - Cross-reference with official policies
   - Test in chatbot staging environment

2. **Ingestion Testing**
   - Run ingestion script
   - Test retrieval quality
   - Measure response accuracy

3. **Stakeholder Review**
   - Demo to library leadership
   - Gather feedback
   - Adjust priorities

#### Ongoing: Monthly Maintenance

**First Monday of Each Month**:
- Review analytics from previous month
- Identify top 10 poorly-answered questions
- Update knowledge base accordingly
- Deprecate outdated information

**Quarterly**:
- Full audit of all knowledge articles
- Update last_reviewed dates
- Archive unused content
- Measure ROI (time saved, satisfaction improved)

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- ✅ Set up database schema for token tracking
- ✅ Set up detailed tool execution logging
- ✅ Create knowledge management repository
- ✅ Assign subject matter experts
- ✅ Create curation templates

### Phase 2: Content Creation (Weeks 3-6)
- [ ] Curate 100+ high-priority knowledge articles
- [ ] Document 20+ common procedures
- [ ] Create FAQ database (50+ items)
- [ ] Digitize policy documents

### Phase 3: RAG Enhancement (Weeks 7-10)
- [ ] Create new Weaviate collections
- [ ] Build enhanced ingestion pipeline
- [ ] Implement hybrid search
- [ ] Add confidence scoring
- [ ] Deploy reranking logic

### Phase 4: Integration (Weeks 11-12)
- [ ] Update transcript_rag_agent.py
- [ ] Add multi-source querying
- [ ] Implement fallback logic
- [ ] Add source attribution
- [ ] Update synthesis prompts

### Phase 5: Testing & Refinement (Weeks 13-14)
- [ ] A/B test new vs old RAG
- [ ] Measure accuracy improvements
- [ ] Gather user feedback
- [ ] Fine-tune ranking weights
- [ ] Document best practices

### Phase 6: Launch & Monitor (Week 15+)
- [ ] Deploy to production
- [ ] Monitor KPIs daily
- [ ] Weekly knowledge reviews
- [ ] Monthly reports
- [ ] Continuous improvement

---

## Success Metrics

### Key Performance Indicators

**Immediate (Week 1-4)**:
- Knowledge articles created: Target 100+
- Coverage of common queries: Target 80%
- Curation team trained: Target 5+ staff

**Short-term (Month 1-3)**:
- User satisfaction (thumbs up): Target >75%
- First-response accuracy: Target >85%
- Knowledge base queries/day: Target >50

**Long-term (Month 6+)**:
- Human escalation rate: Target <15%
- Time to answer: Target <30 seconds
- Knowledge freshness: Target <30 days average age

---

## Tools & Resources

### Recommended Tools

1. **Notion** or **GitBook**: Knowledge base authoring
2. **Airtable**: Curation tracking
3. **Figma**: Visual process documentation
4. **Slack**: Team coordination
5. **GitHub**: Version control for content

### Useful Libraries

```python
# Content processing
pip install python-frontmatter  # Parse markdown metadata
pip install markdown2           # Markdown to HTML
pip install beautifulsoup4      # HTML parsing

# Text chunking
pip install langchain_text_splitters

# Search & retrieval
pip install rank-bm25           # Keyword search
pip install sentence-transformers  # Alternative embeddings

# Monitoring
pip install prometheus-client   # Metrics
pip install sentry-sdk         # Error tracking
```

---

## Conclusion

You have a strong foundation with RAG already implemented via Weaviate. The key improvements needed are:

1. **Expand knowledge sources** beyond just transcripts
2. **Curate high-quality content** manually for critical topics
3. **Implement better filtering and ranking** in RAG queries
4. **Track detailed metrics** to identify gaps
5. **Establish ongoing maintenance** workflow

Start with Phase 1-2 (curating 100 articles) - this will have the biggest immediate impact on chatbot quality.

**Next Steps**:
1. Review this guide with your team
2. Assign roles and responsibilities  
3. Start knowledge gap analysis this week
4. Begin content creation next week
5. Plan RAG enhancement for Month 2

---

**Questions?** Create issues in your GitHub repo or schedule a knowledge management workshop.
