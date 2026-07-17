# Router Refactor Guide

## Overview

This document describes the new routing system that replaces the old "many samples per category" approach with a multi-stage, high-accuracy routing pipeline.

## Architecture

### RouterSubgraph - 4-Node Pipeline

```
User Query
    ↓
[Node A: Heuristic Gate] ──→ Fast patterns, guardrails
    ↓
[Node B: Weaviate Prototypes] ──→ 8-12 high-quality prototypes per agent
    ↓
[Node C: Margin Decision] ──→ Confidence analysis (top1 vs top2)
    ↓
[Node D: LLM Triage] ──→ o4-mini clarification/arbitration
    ↓
Output: Route OR Clarify
```

## Key Improvements

### 1. Prototype-Based Classification

**Old approach:**
- 60+ samples per category
- Heavy overlap between categories
- "computer" appears in equipment_checkout samples
- High confidence but wrong classification

**New approach:**
- 8-12 prototypes per agent
- Action-verb focused for equipment_checkout
- High distinction between categories
- Equipment checkout prototypes: "Can I **borrow** a laptop", "How do I **check out** a Chromebook"

### 2. Heuristic Gate (Node A)

Fast pattern-based triage that catches:

**Entry-ambiguous phrases:**
- "who can I talk to for my computer problems" → Force triage (no action verb)
- "I need help with..." → Check for action verbs

**Equipment checkout guardrail:**
- Query mentions equipment (laptop, computer, etc.)
- Query has problem/issue keywords
- Query lacks action verbs (borrow, checkout, rent)
- → Block equipment_checkout, force triage

**Out-of-scope early rejection:**
- Homework help
- Tech support (broken computer, WiFi down)
- General university questions

### 3. Margin Decision (Node C)

Analyzes confidence gap between top-1 and top-2 candidates:

**Thresholds (configurable):**
```python
direct_score_threshold = 0.75    # Min top-1 score for direct route
direct_margin_threshold = 0.20   # Min margin for direct route
lowconf_score_threshold = 0.60   # Below this = low confidence
lowconf_margin_threshold = 0.10  # Below this = low confidence
clarify_margin_threshold = 0.05  # Very close = clarify
```

**Decision logic:**
- High score + good margin → Direct route (high confidence)
- Medium score + acceptable margin → Direct route (medium confidence)
- Very close scores (margin < 0.05) → Clarify
- Low score or small margin → LLM triage

### 4. LLM Triage (Node D)

Uses o4-mini for:

**Clarification generation:**
- Short question (1 sentence max)
- 3-5 button options
- Always includes "None of these (type more details)"
- Does NOT add words user didn't say

**Arbitration:**
- Chooses between close candidates
- Short JSON output only
- Brief reasoning (1 sentence)

## API Endpoints

### POST /route

Route a query to an agent or request clarification.

**Request:**
```json
{
  "query": "who can I talk to for my computer problems",
  "route_hint": null
}
```

**Response (Clarify):**
```json
{
  "mode": "clarify",
  "confidence": "low",
  "clarifying_question": "What kind of computer help do you need?",
  "options": [
    {
      "label": "My own computer/software",
      "value": "out_of_scope",
      "description": "Personal tech support"
    },
    {
      "label": "Library databases / VPN access",
      "value": "google_site",
      "description": "Remote access issues"
    },
    {
      "label": "Borrow a laptop/equipment",
      "value": "equipment_checkout",
      "description": "Check out library equipment"
    },
    {
      "label": "Coursework / programming help",
      "value": "subject_librarian",
      "description": "Academic research help"
    },
    {
      "label": "None of these (type more details)",
      "value": "other"
    }
  ]
}
```

**Response (Route):**
```json
{
  "mode": "vector",
  "agent_id": "equipment_checkout",
  "confidence": "high",
  "reason": "Clear checkout action detected",
  "candidates": [
    {
      "agent_id": "equipment_checkout",
      "score": 0.89,
      "text": "Can I borrow a laptop from the library?"
    },
    {
      "agent_id": "libcal_hours",
      "score": 0.45,
      "text": "What time does King Library close?"
    }
  ]
}
```

**Follow-up with route_hint:**
```json
{
  "query": "who can I talk to for my computer problems",
  "route_hint": "equipment_checkout"
}
```

## Frontend Integration

### ClarifyChips Component

```jsx
import { ClarifyChips } from '@/components/ClarifyChips';

function ChatInterface() {
  const [clarification, setClarification] = useState(null);
  
  const handleClarificationSelect = async (value) => {
    if (value === 'other') {
      // User wants to type more details
      setClarification(null);
      // Focus input, let user continue typing
    } else {
      // User selected an option
      // Send follow-up request with route_hint
      const response = await fetch('/route', {
        method: 'POST',
        body: JSON.stringify({
          query: originalQuery,
          route_hint: value
        })
      });
      // Process response...
    }
  };
  
  return (
    <div>
      {clarification && (
        <ClarifyChips
          question={clarification.clarifying_question}
          options={clarification.options}
          onSelect={handleClarificationSelect}
        />
      )}
    </div>
  );
}
```

## Weaviate Prototypes

### Initialize Collection

```bash
# Clear existing and initialize fresh
python scripts/initialize_prototypes.py --clear

# Add to existing
python scripts/initialize_prototypes.py
```

### Prototype Structure

```python
{
  "agent_id": "equipment_checkout",
  "prototype_text": "Can I borrow a laptop from the library?",
  "category": "Equipment Checkout",
  "is_action_based": True,  # Has action verb
  "priority": 3  # 1-3, higher = more important
}
```

### Adding Custom Prototypes

```python
from src.router.weaviate_router import WeaviateRouter

router = WeaviateRouter()

await router.add_prototype(
    agent_id="equipment_checkout",
    prototype_text="I need to rent a camera for my project",
    category="Equipment Checkout",
    is_action_based=True,
    priority=3
)
```

## Critical Test Cases

### ✅ MUST PASS: Computer Problems

```python
# Should NOT route to equipment_checkout
# Should trigger clarification OR route to libchat_handoff

"who can I talk to for my computer problems"
→ CLARIFY with options:
  1. My own computer/software (out_of_scope)
  2. Library databases / VPN (google_site)
  3. Borrow laptop/equipment (equipment_checkout)
  4. Coursework help (subject_librarian)
  5. None of these (other)
```

### ✅ Equipment Checkout (with action verbs)

```python
"can I borrow a laptop"
→ equipment_checkout (high confidence, vector)

"how do I check out a Chromebook"
→ equipment_checkout (high confidence, vector)

"I want to rent a camera"
→ equipment_checkout (high confidence, vector)
```

### ✅ Out-of-Scope Tech Support

```python
"my computer is not working"
→ out_of_scope (high confidence, heuristic)

"Canvas isn't working"
→ out_of_scope (high confidence, heuristic)

"WiFi is down"
→ out_of_scope (high confidence, heuristic)
```

## Evaluation

### Run Evaluation Script

```bash
python scripts/evaluate_routing.py

# With custom test file
python scripts/evaluate_routing.py --test-file tests/routing_tests.json

# Save results
python scripts/evaluate_routing.py --output results.json
```

### Metrics

- **Overall accuracy**: % of correct routes
- **Per-agent accuracy**: Accuracy for each agent
- **Mode distribution**: How often each mode is used (heuristic, vector, llm_judge, clarify)
- **Margin analysis**: Average margin for correct vs incorrect routes
- **Confusion matrix**: Which agents get confused with each other

### Threshold Tuning

Based on evaluation results, adjust thresholds:

```python
from src.router.margin import MarginConfig
from src.router.router_subgraph import RouterSubgraph

config = MarginConfig(
    direct_score_threshold=0.80,  # Increase for stricter routing
    direct_margin_threshold=0.25,  # Increase to require larger gaps
    lowconf_score_threshold=0.65,
    lowconf_margin_threshold=0.12,
    clarify_margin_threshold=0.05
)

router = RouterSubgraph(margin_config=config)
```

## Logging

All routing decisions are logged with:
- Query text
- Heuristic results (if matched)
- Top-K candidates from Weaviate
- Scores and margins
- Final decision (mode, agent_id, confidence)
- Reason for decision

Example log:
```
🔍 [Heuristic Gate] Entry-ambiguous phrase detected: who can I talk to
🛡️ [Heuristic Gate] Equipment checkout guardrail: computer mentioned with problem
📊 [Weaviate Router] Found 5 prototype matches
   1. libchat_handoff (0.72): I want to talk to a librarian
   2. google_site (0.68): How do I access library resources?
   3. equipment_checkout (0.45): Can I borrow a laptop?
📊 [Margin Decision] Top-1: libchat_handoff (0.72) | Top-2: google_site (0.68) | Margin: 0.04
✅ [Margin Decision] clarify (low) - Very close scores, margin too small
🤖 [LLM Triage] Generating clarification for: who can I talk to for my computer problems
✅ [LLM Triage] Generated clarification with 5 options
✅ [Router] Final route: CLARIFY
```

## Migration from Old System

### 1. Initialize Prototypes

```bash
python scripts/initialize_prototypes.py --clear
```

### 2. Update Frontend

Add ClarifyChips component and handle clarification responses.

### 3. Test Critical Cases

```bash
python scripts/evaluate_routing.py
```

### 4. Monitor & Tune

- Review logs for misclassifications
- Adjust thresholds based on margin analysis
- Add/refine prototypes for problematic categories

## Configuration

### Environment Variables

```bash
# Weaviate connection
WEAVIATE_HOST=localhost
WEAVIATE_SCHEME=http
WEAVIATE_API_KEY=

# OpenAI (for embeddings and o4-mini)
OPENAI_API_KEY=your_key
OPENAI_MODEL=o4-mini
```

### Margin Thresholds

Edit `src/router/margin.py` or pass custom config:

```python
from src.router.margin import MarginConfig

config = MarginConfig(
    direct_score_threshold=0.75,
    direct_margin_threshold=0.20,
    lowconf_score_threshold=0.60,
    lowconf_margin_threshold=0.10,
    clarify_margin_threshold=0.05
)
```

## Troubleshooting

### Issue: Too many clarifications

**Solution:** Lower `clarify_margin_threshold` or increase `direct_margin_threshold`

### Issue: Wrong routes with high confidence

**Solution:** 
1. Check prototypes for overlap
2. Add negative prototypes (heuristic blockers)
3. Review margin analysis in evaluation

### Issue: Equipment checkout still getting "computer problems"

**Solution:**
1. Verify heuristic gate is active
2. Check that equipment prototypes have action verbs
3. Review blocked_agents in logs

### Issue: Slow routing

**Solution:**
1. Reduce top_k in Weaviate search (default: 5)
2. Use heuristic fast-paths for common queries
3. Cache embeddings for frequent queries

## Best Practices

1. **Prototypes should be distinctive**: Each prototype should clearly represent its agent
2. **Action verbs for equipment**: Always include action verbs in equipment checkout prototypes
3. **Test edge cases**: Focus on ambiguous queries that could go multiple ways
4. **Monitor margins**: Low margins indicate overlapping categories
5. **Use clarification wisely**: Only when truly ambiguous, not as a crutch
6. **Log everything**: Comprehensive logs enable continuous improvement
7. **Iterate on prototypes**: Add/remove based on real-world misclassifications
