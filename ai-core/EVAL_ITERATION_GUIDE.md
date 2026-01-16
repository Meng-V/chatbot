# Evaluation and Iteration Guide

## Overview

This guide documents the evaluation and iteration loop for systematically improving RAG classification accuracy in the Miami Libraries Smart Chatbot routing system.

**Last Updated:** January 16, 2026  
**Version:** 1.0 (Eval + Iteration Loop)

---

## System Architecture

**Single Production Routing Path:**
```
main.py → library_graph.ainvoke() → understand_query → rag_router → execute_agents → synthesize
```

All handlers (HTTP, Socket.IO, clarification follow-ups) use this unified path.

---

## A) Clarification Follow-up Consistency

### Changes Made

**File:** `src/main.py`

Both `clarificationChoice` and `provideMoreDetails` handlers now use `library_graph.ainvoke()` instead of the deprecated `route_query()`.

**Clarification Choice Handler:**
- If user selects "libchat"/"librarian"/"human_help" → routes to libchat_handoff
- If user selects "none" → requests more details
- Otherwise → re-runs library_graph with augmented context: `"{original_question} [User clarified: {choice_id}]"`

**Provide More Details Handler:**
- Combines original question with additional details
- Re-runs library_graph with: `"{original_question}. {additional_details}"`
- Maintains conversation history consistency

---

## B) Batch Evaluation Script

### Script: `scripts/eval_routing_batch.py`

**Features:**
- Accepts CSV or JSONL input files
- Runs each question through `library_graph.ainvoke()`
- Captures routing decisions, confidence, categories
- Outputs detailed results (CSV + JSON)
- Calculates accuracy, precision, recall, F1 per agent
- Identifies top 20 confusion pairs

**Usage:**
```bash
cd ai-core
source venv/bin/activate
python scripts/eval_routing_batch.py test_data/routing_test_cases.csv --output-dir eval_results
```

**Input Format (CSV):**
```csv
question,expected_primary_agent_id,notes,category
Can I borrow a laptop?,equipment_checkout,Equipment checkout,library_equipment_checkout
Where is the dining hall?,out_of_scope,Campus life - dining,out_of_scope_campus_life
```

**Input Format (JSONL):**
```json
{"question": "Can I borrow a laptop?", "expected_primary_agent_id": "equipment_checkout", "notes": "Equipment checkout", "category": "library_equipment_checkout"}
{"question": "Where is the dining hall?", "expected_primary_agent_id": "out_of_scope", "notes": "Campus life - dining", "category": "out_of_scope_campus_life"}
```

**Output Files:**
- `eval_results/eval_results.csv` - Detailed results per question
- `eval_results/eval_results.json` - Full results with metrics
- `eval_results/hard_negatives.jsonl` - Failures and clarifications for training

**Metrics Calculated:**
- Overall accuracy (excluding clarifications)
- Clarification rate
- Per-agent precision, recall, F1
- Confusion matrix (top 20 pairs)

---

## C) Hard Negative Mining

The eval script automatically generates `hard_negatives.jsonl` containing:
- All failed classifications
- All clarifications triggered
- Suggested labels for training data expansion

**Format:**
```json
{
  "question": "Where is the dining hall?",
  "expected_primary_agent_id": "out_of_scope",
  "predicted_primary_agent_id": "libcal_hours",
  "router_category": "library_hours_rooms",
  "confidence": 0.82,
  "suggested_label": "library_hours_rooms",
  "status": "fail"
}
```

**Usage:**
1. Review hard negatives
2. Add failed examples to appropriate categories in `src/classification/category_examples.py`
3. Re-initialize RAG classifier: `python scripts/initialize_rag_classifier.py`
4. Re-run evaluation to measure improvement

---

## D) Expanded Out-of-Scope Coverage

### Changes Made

**File:** `src/classification/category_examples.py`

**OUT_OF_SCOPE_CAMPUS_LIFE** expanded with:

**Dining/Food (18 examples):**
- "Where is the dining hall?"
- "Dining hall hours"
- "When does the dining hall open?"
- "What time does the cafeteria close?"
- "Where can I eat on campus?"
- "Where is Starbucks?"
- etc.

**Housing/Dorms (6 examples):**
- "Where is my dorm?"
- "How do I get to my residence hall?"
- etc.

**Parking (7 examples):**
- "How do I get parking?"
- "Where can I park?"
- etc.

**Sports/Recreation (10 examples):**
- "Rec center hours"
- "When does the gym open?"
- "What time does the rec center close?"
- "Fitness center hours"
- etc.

**Campus Buildings (11 examples):**
- "Bookstore hours"
- "When does the bookstore open?"
- "What time does the bookstore close?"
- "Student center hours"
- etc.

**Borderline Cases (hours-like but NOT library):**
- "Gym hours"
- "Rec center hours"
- "Dining hall hours"
- "Bookstore hours"
- "Student center hours"

These examples help the classifier distinguish between library hours and non-library facility hours.

---

## E) Differentiated Threshold Policy

### Changes Made

**File:** `src/graph/rag_router.py`

**Policy:**
- **Out-of-scope categories:** Route directly if `confidence >= 0.45` (no clarification)
- **In-scope categories:** Require `confidence >= 0.65` (clarify if lower)

**Rationale:**
- Out-of-scope should terminate quickly even with moderate confidence
- Prevents misrouting like "dining hall" → "libcal_hours"
- In-scope categories need higher confidence to ensure correct agent selection

**Implementation:**
```python
is_out_of_scope_category = category.startswith("out_of_scope_")

if is_out_of_scope_category and confidence >= 0.45:
    # Route directly, don't clarify
    pass
elif needs_clarification or confidence < CONFIDENCE_THRESHOLD:
    # Trigger clarification
    pass
```

---

## F) Category Trace Logging

### Changes Made

**File:** `src/graph/rag_router.py`

Added comprehensive logging for evaluation:
```python
logger.log(f"📊 [RAG Router] Category trace", {
    "processed_query": user_msg,
    "category": category,
    "confidence": confidence,
    "primary_agent_id": primary_agent_id,
    "is_out_of_scope": category.startswith("out_of_scope_")
})
```

This enables the eval script to capture all routing decisions consistently.

---

## Validation Results

### Test: `scripts/test_routing_smoke.py`

**Status:** ✅ Still runs successfully

**Results:**
- 12/16 passing (75%)
- 3 clarifications (acceptable)
- 1 failure: "Where is the dining hall?" (will be fixed after re-initializing classifier with new examples)

### Sample Evaluation Run

**Command:**
```bash
python scripts/eval_routing_batch.py test_data/routing_test_cases.csv
```

**Expected Output:**
```
Evaluating 30 test cases...
================================================================================

[1/30] Can I borrow a laptop?...
  ✅ PASS - equipment_checkout
     Confidence: 0.92

[2/30] Where is the dining hall?...
  ✅ PASS - out_of_scope
     Confidence: 0.78

...

================================================================================
EVALUATION SUMMARY
================================================================================

Total test cases: 30
Evaluated (excluding clarifications): 28
Correct: 26
Accuracy: 92.9%
Clarifications: 2 (6.7%)
Errors: 0

--------------------------------------------------------------------------------
PER-AGENT METRICS
--------------------------------------------------------------------------------
Agent                     Precision    Recall       F1           Support   
--------------------------------------------------------------------------------
equipment_checkout        100.0%       100.0%       100.0%       5         
libcal_hours              100.0%       87.5%        93.3%        8         
subject_librarian         100.0%       100.0%       100.0%       3         
policy_search             100.0%       100.0%       100.0%       2         
libchat_handoff           100.0%       100.0%       100.0%       3         
out_of_scope              85.7%        100.0%       92.3%        7         

--------------------------------------------------------------------------------
TOP 20 CONFUSION PAIRS
--------------------------------------------------------------------------------
Expected                  Predicted                 Count     
--------------------------------------------------------------------------------
out_of_scope              libcal_hours              2         

✅ Saved detailed results to: eval_results/eval_results.csv
✅ Saved JSON results to: eval_results/eval_results.json
✅ Saved 4 hard negatives to: eval_results/hard_negatives.jsonl

================================================================================
Evaluation complete!
================================================================================
```

---

## Iteration Workflow

### Step 1: Run Evaluation
```bash
python scripts/eval_routing_batch.py test_data/routing_test_cases.csv
```

### Step 2: Review Results
- Check `eval_results/eval_results.csv` for detailed failures
- Review `eval_results/hard_negatives.jsonl` for training candidates
- Analyze confusion pairs to identify systematic errors

### Step 3: Expand Training Data
- Add hard negative examples to `src/classification/category_examples.py`
- Focus on categories with low precision/recall
- Add borderline cases that cause confusion

### Step 4: Re-initialize Classifier
```bash
python scripts/initialize_rag_classifier.py
```

### Step 5: Re-evaluate
```bash
python scripts/eval_routing_batch.py test_data/routing_test_cases.csv --output-dir eval_results_v2
```

### Step 6: Compare Metrics
- Compare accuracy between iterations
- Check if confusion pairs decreased
- Verify clarification rate is acceptable (<20%)

### Step 7: Iterate
Repeat steps 1-6 until target accuracy is achieved (>95%).

---

## Best Practices

### Adding Training Examples

**DO:**
- Add real user questions from hard negatives
- Include variations (synonyms, different phrasings)
- Add borderline cases that look similar to other categories
- Balance positive and negative examples

**DON'T:**
- Add synthetic/made-up examples that users wouldn't ask
- Duplicate existing examples
- Add ambiguous examples without clarification strategy

### Threshold Tuning

**Current Thresholds:**
- In-scope confidence: 0.65
- Out-of-scope confidence: 0.45

**Adjust if:**
- Too many clarifications → Lower in-scope threshold
- Too many misclassifications → Raise in-scope threshold
- Out-of-scope still misrouted → Raise out-of-scope threshold

### Monitoring Production

**Track:**
- Clarification rate (target: <15%)
- Per-agent accuracy
- Most common confusion pairs
- User feedback on misrouted questions

---

## Files Modified

### Core Routing
- `src/graph/rag_router.py` - Differentiated threshold policy, category trace logging
- `src/main.py` - Clarification handlers use library_graph.ainvoke()

### Training Data
- `src/classification/category_examples.py` - Expanded out-of-scope campus life examples

### Evaluation
- `scripts/eval_routing_batch.py` - NEW: Batch evaluation script
- `test_data/routing_test_cases.csv` - NEW: Sample test data

### Documentation
- `ROUTING_CONTRACT.md` - Updated with clarification sources
- `EVAL_ITERATION_GUIDE.md` - NEW: This guide

---

## Troubleshooting

### Issue: Evaluation script fails with import errors
**Solution:** Ensure virtual environment is activated: `source venv/bin/activate`

### Issue: Hard negatives file is empty
**Solution:** Perfect accuracy! No failures or clarifications to mine.

### Issue: Clarification rate too high (>30%)
**Solution:** 
1. Lower CONFIDENCE_THRESHOLD in `rag_router.py`
2. Add more distinctive examples to confused categories
3. Review boundary cases and add clear examples

### Issue: Out-of-scope still misrouted
**Solution:**
1. Add more out-of-scope examples to category_examples.py
2. Lower out-of-scope threshold (currently 0.45)
3. Re-initialize classifier

---

## Contact

For questions or issues with the evaluation system:
- Review logs in eval_results/
- Check hard_negatives.jsonl for patterns
- Run smoke tests to verify basic functionality

**Maintainer:** Meng Qu  
**Repository:** Miami Libraries Smart Chatbot
