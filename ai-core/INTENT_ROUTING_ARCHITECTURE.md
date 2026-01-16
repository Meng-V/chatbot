# Intent-Based Routing Architecture

## Overview

The routing system has been refactored to implement a **two-step, deterministic, testable routing process** with explicit intent normalization.

**Last Updated:** January 16, 2026  
**Version:** 2.0 (Intent Translation Layer)

---

## Core Principles

1. **Intent Normalization is Explicit** - User input is translated into a standardized intent representation BEFORE routing
2. **Category Classification is Pure** - Category classifier only maps intent → category, nothing else
3. **Agent Selection is Deterministic** - Category → Agent mapping is a simple lookup from single source of truth
4. **Routing is Testable** - Every step produces structured output that can be batch-tested
5. **No Hidden Logic** - All routing decisions happen in one place (orchestrator.py)

---

## Two-Step Routing Process

### Step 1: Intent Normalization

**Function:** `normalize_intent(user_message, conversation_history) -> NormalizedIntent`

**Location:** `src/graph/intent_normalizer.py`

**Purpose:** Translate raw user input into standardized intent representation

**Does:**
- Rewrites user question into clear intent statement
- Extracts key entities (locations, equipment, subjects)
- Assesses confidence in understanding
- Flags ambiguous intents

**Does NOT:**
- Choose agents
- Do category classification
- Answer questions
- Make routing decisions

**Output:**
```python
NormalizedIntent(
    intent_summary="User is asking about borrowing library equipment (laptop)",
    confidence=0.95,
    ambiguity=False,
    ambiguity_reason=None,
    key_entities=["laptop", "borrow", "equipment"],
    original_query="Can I borrow a laptop?"
)
```

### Step 2: Category Classification

**Function:** `classify_category(normalized_intent, logger) -> CategoryClassification`

**Location:** `src/graph/rag_router.py`

**Purpose:** Map normalized intent to category using RAG embeddings

**Does:**
- Takes NormalizedIntent
- Uses semantic similarity against category_examples.py
- Returns category with confidence
- Applies differentiated thresholds (in-scope: 0.65, out-of-scope: 0.45)

**Does NOT:**
- Choose agents (that's category_to_agent_map)
- Answer questions (that's agents)
- Handle clarifications (that's orchestrator)

**Output:**
```python
CategoryClassification(
    category="library_equipment_checkout",
    confidence=0.92,
    is_out_of_scope=False,
    needs_clarification=False,
    clarification_reason=None
)
```

### Step 3: Agent Selection

**Function:** `category_to_agent_map()` from `category_examples.py`

**Purpose:** Deterministic mapping from category to agent ID

**Single Source of Truth:**
```python
{
    "library_equipment_checkout": "equipment_checkout",
    "library_hours_rooms": "libcal_hours",
    "subject_librarian_guides": "subject_librarian",
    "research_help_handoff": "libchat_handoff",
    "library_policies_services": "policy_search",
    "out_of_scope_tech_support": "out_of_scope",
    # ... etc
}
```

---

## Complete Routing Flow

```
User Message
    ↓
┌─────────────────────────────────────┐
│ Intent Normalization Layer          │
│ (src/graph/intent_normalizer.py)   │
│                                     │
│ Input: Raw user message             │
│ Output: NormalizedIntent            │
│   - intent_summary                  │
│   - confidence                      │
│   - ambiguity flag                  │
│   - key_entities                    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Category Classifier                 │
│ (src/graph/rag_router.py)          │
│                                     │
│ Input: NormalizedIntent             │
│ Process: RAG embeddings             │
│ Output: CategoryClassification      │
│   - category                        │
│   - confidence                      │
│   - needs_clarification             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Ambiguity Check                     │
│ (orchestrator.py)                   │
│                                     │
│ If ambiguous → Clarification        │
│ Else → Agent Selection              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Agent Selection                     │
│ (category_to_agent_map)             │
│                                     │
│ Input: Category                     │
│ Output: primary_agent_id            │
│ Lookup: category_examples.py        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Agent Execution                     │
│ (execute_agents_node)               │
└─────────────────────────────────────┘
    ↓
Final Answer
```

---

## Data Models

### NormalizedIntent

**File:** `src/models/intent.py`

```python
class NormalizedIntent(BaseModel):
    intent_summary: str          # "User is asking about..."
    confidence: float            # 0.0-1.0
    ambiguity: bool             # True if unclear
    ambiguity_reason: Optional[str]
    key_entities: List[str]     # ["laptop", "borrow"]
    original_query: str         # Original user message
```

### CategoryClassification

```python
class CategoryClassification(BaseModel):
    category: str               # From category_examples.py
    confidence: float           # 0.0-1.0
    is_out_of_scope: bool      # True if out-of-scope
    needs_clarification: bool   # True if confidence too low
    clarification_reason: Optional[str]
```

### RoutingDecision

```python
class RoutingDecision(BaseModel):
    normalized_intent: NormalizedIntent
    category: str
    category_confidence: float
    primary_agent_id: Optional[str]
    secondary_agent_ids: List[str]
    needs_clarification: bool
    clarification_reason: Optional[str]
    routing_trace: dict
```

---

## Single Source of Truth

### Category Definitions

**File:** `src/classification/category_examples.py`

**Contains:**
- All category definitions
- In-scope and out-of-scope examples
- Category descriptions
- Keywords

**Helper Functions:**
- `list_all_categories()` - List all category names
- `category_to_agent_map()` - Authoritative category → agent mapping
- `get_category_metadata(category)` - Get full category data

**This is the ONLY place** where categories and their agent mappings are defined.

---

## Logging & Observability

Every routing decision logs:

```python
{
    "normalized_intent": {
        "intent_summary": "User is asking about borrowing library equipment (laptop)",
        "confidence": 0.95,
        "ambiguity": False
    },
    "category": "library_equipment_checkout",
    "category_confidence": 0.92,
    "primary_agent_id": "equipment_checkout",
    "needs_clarification": False,
    "routing_trace": {
        "intent_confidence": 0.95,
        "category_confidence": 0.92,
        "threshold_used": 0.65,
        "is_out_of_scope": False
    }
}
```

This data is:
- Logged via `AgentLogger`
- Stored in graph state
- Accessible to evaluation scripts
- Returned in API responses

---

## Batch Evaluation

### Routing-Only Testing

**Script:** `scripts/eval_routing_batch.py`

**Mode 1: Full Execution (current)**
- Runs complete graph
- Tests end-to-end behavior

**Mode 2: Routing-Only (recommended for iteration)**
```python
# Test just the routing layer
normalized_intent = await normalize_intent(question, [])
category_result = await classify_category(normalized_intent)
agent_id = category_to_agent_map()[category_result.category]

# Compare with expected
assert agent_id == expected_agent_id
```

**Benefits:**
- Fast iteration (no agent execution)
- Deterministic results
- Easy to test 1000+ questions
- Clear failure attribution

---

## Migration Path

### Current State (Backward Compatible)

The system supports BOTH:

**Legacy Path (deprecated):**
```
user_message → rag_router_node → agent selection
```

**New Path (recommended):**
```
user_message → normalize_intent → classify_category → category_to_agent_map → agent selection
```

### Migration Steps

1. **Phase 1: Dual Mode** (current)
   - Legacy rag_router_node still works
   - New functions available for testing
   - No breaking changes

2. **Phase 2: Gradual Adoption**
   - Update orchestrator to use new two-step process
   - Keep legacy path for fallback
   - Monitor metrics

3. **Phase 3: Full Migration**
   - Remove legacy rag_router_node
   - All routing uses two-step process
   - Update documentation

---

## File Structure

### New Files
- `src/models/intent.py` - Pydantic models for intent and routing
- `src/graph/intent_normalizer.py` - Intent normalization layer
- `INTENT_ROUTING_ARCHITECTURE.md` - This document

### Modified Files
- `src/graph/rag_router.py` - Now pure category classifier
- `src/classification/category_examples.py` - Added helper functions
- `src/graph/orchestrator.py` - Updated to use two-step process (pending)
- `scripts/eval_routing_batch.py` - Supports routing-only mode (pending)

### Unchanged Files
- `src/main.py` - API contracts preserved
- `src/state.py` - State schema extended, not changed
- Agent files - No changes to agent logic

---

## Testing Strategy

### Unit Tests

**Intent Normalization:**
```python
intent = await normalize_intent("Can I borrow a laptop?", [])
assert intent.intent_summary.contains("borrowing")
assert intent.confidence > 0.8
assert not intent.ambiguity
```

**Category Classification:**
```python
intent = NormalizedIntent(
    intent_summary="User is asking about borrowing library equipment",
    confidence=0.95,
    ambiguity=False,
    key_entities=["laptop"],
    original_query="Can I borrow a laptop?"
)
category = await classify_category(intent)
assert category.category == "library_equipment_checkout"
assert category.confidence > 0.8
```

**Agent Mapping:**
```python
mapping = category_to_agent_map()
assert mapping["library_equipment_checkout"] == "equipment_checkout"
assert mapping["out_of_scope_campus_life"] == "out_of_scope"
```

### Integration Tests

**End-to-End Routing:**
```python
# Full pipeline
intent = await normalize_intent(question, [])
category = await classify_category(intent)
agent_id = category_to_agent_map()[category.category]

# Verify
assert agent_id == expected_agent_id
```

### Batch Evaluation

**Test 200 Questions:**
```bash
python scripts/eval_routing_batch.py test_data/routing_test_cases.csv --routing-only
```

**Output:**
- Accuracy per category
- Confusion matrix
- Confidence distribution
- Ambiguity rate

---

## Benefits of New Architecture

### 1. Explainability
Every routing decision has clear trace:
- What did we understand? (NormalizedIntent)
- What category did we assign? (CategoryClassification)
- What agent did we choose? (category_to_agent_map)

### 2. Testability
Each step is independently testable:
- Test intent normalization in isolation
- Test category classification in isolation
- Test agent mapping with simple dict lookup

### 3. Debuggability
When routing fails, you know exactly where:
- Intent normalization failed? → Improve LLM prompt
- Category classification failed? → Add training examples
- Agent mapping wrong? → Update category_to_agent_map

### 4. Maintainability
Single source of truth:
- Categories defined once in category_examples.py
- Agent mapping defined once in category_to_agent_map()
- No hidden routing logic in agents

### 5. Iteration Speed
Fast feedback loop:
- Change category examples
- Re-run batch eval (routing-only)
- See impact immediately
- No need to execute agents

---

## Next Steps

### Immediate
1. Update orchestrator.py to use two-step process
2. Add routing-only mode to eval_routing_batch.py
3. Run smoke tests to verify behavior preserved

### Short-term
1. Create unit tests for intent normalization
2. Create unit tests for category classification
3. Build routing-only test suite (1000+ questions)

### Long-term
1. Remove legacy rag_router_node
2. Add intent normalization metrics to dashboard
3. Implement active learning from clarifications

---

## Troubleshooting

### Issue: Intent normalization returns low confidence
**Solution:** Review LLM prompt, add more examples

### Issue: Category classification wrong
**Solution:** Add training examples to category_examples.py, re-initialize classifier

### Issue: Agent mapping incorrect
**Solution:** Update category_to_agent_map() in category_examples.py

### Issue: Too many clarifications
**Solution:** Adjust thresholds in rag_router.py (CONFIDENCE_THRESHOLD_IN_SCOPE, CONFIDENCE_THRESHOLD_OUT_OF_SCOPE)

---

## Contact

For questions about the intent-based routing architecture:
- Review this document
- Check src/models/intent.py for data models
- Check src/graph/intent_normalizer.py for implementation
- Run batch evaluation to test changes

**Maintainer:** Meng Qu  
**Repository:** Miami Libraries Smart Chatbot
