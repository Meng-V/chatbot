# How to Fix RAG Classification Issues

## The Problem
"Who can help me with a computer question?" returns error because it's misclassifying as `library_equipment_checkout` instead of `out_of_scope_tech_support`.

## Why It Happens
The word "computer" appears in both categories:
- Equipment: "Can I borrow a **computer**?"
- Tech Support: "My **computer** is broken"

RAG uses semantic similarity, so it matches based on shared keywords.

## The Solution: Restart Your Backend

**After editing `category_examples.py` and running `initialize_rag_classifier.py`, you MUST restart the backend server:**

```bash
cd /Users/qum/Documents/GitHub/chatbot
# Stop the current server (Ctrl+C if running)
bash local-auto-start.sh
```

The backend loads the RAG classifier on startup. Changes don't take effect until restart.

## Self-Service Fix Workflow

### 1. Test Classification
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
python3 scripts/test_classification.py "Your failing question"
```

### 2. If Wrong Category - Add Examples
Edit `src/classification/category_examples.py`:

**For tech support questions, emphasize broken/fix/repair:**
```python
OUT_OF_SCOPE_TECH_SUPPORT = {
    "in_scope_examples": [
        "My computer is BROKEN",
        "Who can FIX my laptop?",
        "Computer REPAIR help",
        "My laptop won't TURN ON",
        # Add 5-10 variations with these action words
    ],
```

**For equipment checkout, emphasize borrow/checkout/get:**
```python
LIBRARY_EQUIPMENT_CHECKOUT = {
    "in_scope_examples": [
        "Can I BORROW a computer?",
        "How do I CHECKOUT a laptop?",
        "Can I GET Adobe?",
        # Focus on transactional verbs
    ],
```

### 3. Reinitialize
```bash
python3 scripts/initialize_rag_classifier.py
```

### 4. Restart Backend (CRITICAL!)
```bash
cd /Users/qum/Documents/GitHub/chatbot
bash local-auto-start.sh
```

### 5. Test in Browser
Try the question in the actual chatbot UI.

## Common Mistakes

❌ **Mistake 1:** Adding tech support to `out_of_scope_examples` in equipment_checkout
- Creates exact matches that override semantic similarity
- Makes classification worse

❌ **Mistake 2:** Forgetting to restart backend
- Changes only apply after server restart
- Test script uses fresh classifier, but web app uses cached one

❌ **Mistake 3:** Too few examples
- Add 5-10 variations of each failing question
- Use different phrasings with same intent

## When to Edit Examples

Only edit when:
1. **Category is wrong** (e.g., goes to general_question)
2. **Confidence < 0.7** consistently
3. **Production failures** reported by users

Don't edit if confidence > 0.7 and category is correct.

## Current Status

✅ **Fixed issues:**
- Adobe questions: Added 13 Adobe variations → 0.74 confidence
- Google Site Search credentials: Fixed runtime loading

⚠️ **Remaining issue:**
- Tech support questions: Still routing to equipment_checkout
- **Action needed:** Restart backend server to apply latest fixes
