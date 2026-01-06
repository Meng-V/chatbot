# Router Module

Advanced question classification and routing system with multi-stage pipeline.

## Quick Start

```python
from src.router.router_subgraph import route_query
from src.utils.logger import AgentLogger

logger = AgentLogger()

# Route a query
result = await route_query(
    query="who can I talk to for my computer problems",
    logger=logger
)

if result["mode"] == "clarify":
    # Show clarification buttons to user
    print(result["clarifying_question"])
    for option in result["options"]:
        print(f"  - {option['label']}")
else:
    # Route to agent
    print(f"Route to: {result['agent_id']} ({result['confidence']})")
```

## Architecture

### 4-Node Pipeline

1. **Heuristic Gate** (`heuristics.py`)
   - Fast pattern matching
   - Entry-ambiguous phrase detection
   - Equipment checkout guardrails
   - Out-of-scope early rejection

2. **Weaviate Prototypes** (`weaviate_router.py`)
   - Semantic similarity search
   - 8-12 high-quality prototypes per agent
   - Action-verb focused for equipment

3. **Margin Decision** (`margin.py`)
   - Confidence analysis (top-1 vs top-2)
   - Configurable thresholds
   - Early stopping for high confidence

4. **LLM Triage** (`llm_triage.py`)
   - o4-mini clarification generation
   - Arbitration between close candidates
   - Short JSON output only

## Files

- `__init__.py` - Module exports
- `schemas.py` - Pydantic models for requests/responses
- `heuristics.py` - Fast pattern-based triage (Node A)
- `weaviate_router.py` - Prototype-based semantic search (Node B)
- `margin.py` - Confidence-based decision making (Node C)
- `llm_triage.py` - LLM-based clarification/arbitration (Node D)
- `router_subgraph.py` - LangGraph pipeline orchestration

## Key Features

### Equipment Checkout Guardrail

Prevents "computer problems" from routing to "borrow laptop":

```python
# ❌ Blocked: No action verb
"who can I talk to for my computer problems"
→ Force triage (clarification)

# ✅ Allowed: Has action verb
"can I borrow a laptop"
→ equipment_checkout
```

### Margin-Based Confidence

```python
# High confidence: Good score + good margin
top1: 0.85, top2: 0.60, margin: 0.25
→ Direct route (high confidence)

# Low confidence: Close scores
top1: 0.72, top2: 0.68, margin: 0.04
→ Clarify (ask user)

# Medium confidence: Decent score + margin
top1: 0.70, top2: 0.55, margin: 0.15
→ Direct route (medium confidence)
```

### Clarification Flow

```
User: "who can I talk to for my computer problems"
  ↓
Heuristic: Entry-ambiguous + no action verb
  ↓
Force Triage
  ↓
LLM generates clarification:
  "What kind of computer help do you need?"
  [My own computer] [Library databases] [Borrow laptop] [Other]
  ↓
User clicks [Borrow laptop]
  ↓
Follow-up request with route_hint="equipment_checkout"
  ↓
Direct route (high confidence)
```

## Configuration

### Margin Thresholds

```python
from src.router.margin import MarginConfig
from src.router.router_subgraph import RouterSubgraph

config = MarginConfig(
    direct_score_threshold=0.75,    # Min score for direct route
    direct_margin_threshold=0.20,   # Min margin for direct route
    lowconf_score_threshold=0.60,   # Below = low confidence
    lowconf_margin_threshold=0.10,  # Below = low confidence
    clarify_margin_threshold=0.05   # Below = clarify
)

router = RouterSubgraph(margin_config=config)
```

### Heuristic Patterns

Edit `heuristics.py` to add custom patterns:

```python
# Add to ENTRY_AMBIGUOUS_PATTERNS
r'\bneed\s+help\s+with\b',

# Add to OUT_OF_SCOPE_PATTERNS
'homework': [
    r'\bwhat\'s\s+the\s+answer\b',
]
```

## Prototypes

### Initialize

```bash
python scripts/initialize_prototypes.py --clear
```

### Add Custom Prototype

```python
from src.router.weaviate_router import WeaviateRouter

router = WeaviateRouter()

await router.add_prototype(
    agent_id="equipment_checkout",
    prototype_text="I need to rent a camera",
    category="Equipment Checkout",
    is_action_based=True,
    priority=3
)
```

### Prototype Guidelines

1. **High distinction**: Each prototype should clearly represent its agent
2. **Action verbs for equipment**: "borrow", "checkout", "rent", "reserve"
3. **8-12 per agent**: Quality over quantity
4. **No overlap**: Avoid similar phrases across agents
5. **Priority levels**: 1=low, 2=medium, 3=high

## Testing

### Unit Tests

```bash
pytest tests/test_router.py
```

### Evaluation

```bash
python scripts/evaluate_routing.py
```

### Critical Test Cases

```python
# Must NOT route to equipment_checkout
"who can I talk to for my computer problems"
"my computer is not working"
"I need help with my computer"

# Must route to equipment_checkout
"can I borrow a laptop"
"how do I check out a Chromebook"
"I want to rent a camera"

# Must route to out_of_scope
"my wifi isn't working"
"what's the answer to homework question 5"
"Canvas login not working"
```

## Logging

All routing decisions are logged:

```python
logger = AgentLogger()
result = await route_query(query, logger=logger)

# View logs
for log in logger.get_logs():
    print(log)
```

Example log output:
```
🔍 [Heuristic Gate] Entry-ambiguous phrase detected
🛡️ [Heuristic Gate] Equipment checkout guardrail active
📊 [Weaviate Router] Found 5 prototype matches
📊 [Margin Decision] Top-1: libchat (0.72) | Top-2: google (0.68) | Margin: 0.04
🤖 [LLM Triage] Generating clarification
✅ [Router] Final route: CLARIFY
```

## API Integration

### FastAPI Endpoint

```python
from fastapi import APIRouter
from src.router.schemas import RouteRequest, RouteResponse, ClarifyResponse
from src.router.router_subgraph import route_query

router = APIRouter()

@router.post("/route")
async def route_endpoint(request: RouteRequest):
    result = await route_query(
        query=request.query,
        route_hint=request.route_hint
    )
    return result
```

### Frontend Integration

```jsx
// Send initial query
const response = await fetch('/route', {
  method: 'POST',
  body: JSON.stringify({ query: userInput })
});

const result = await response.json();

if (result.mode === 'clarify') {
  // Show clarification buttons
  showClarification(result.clarifying_question, result.options);
} else {
  // Route to agent
  routeToAgent(result.agent_id);
}

// User clicks clarification button
const followUp = await fetch('/route', {
  method: 'POST',
  body: JSON.stringify({
    query: originalQuery,
    route_hint: selectedOption.value
  })
});
```

## Troubleshooting

### Too many clarifications

Lower `clarify_margin_threshold` or increase `direct_margin_threshold`

### Wrong routes with high confidence

1. Check prototypes for overlap
2. Add heuristic blockers
3. Review margin analysis

### Equipment checkout getting "computer problems"

1. Verify heuristic gate is active
2. Check equipment prototypes have action verbs
3. Review blocked_agents in logs

### Slow routing

1. Reduce top_k in Weaviate search
2. Use heuristic fast-paths
3. Cache embeddings

## Performance

- **Heuristic Gate**: <1ms (regex patterns)
- **Weaviate Search**: ~50-100ms (5 prototypes)
- **Margin Decision**: <1ms (arithmetic)
- **LLM Triage**: ~500-1000ms (o4-mini)

**Total latency:**
- Fast path (heuristic): <1ms
- Vector path (no LLM): ~50-100ms
- Clarify path (with LLM): ~500-1000ms

## Best Practices

1. **Start with heuristics**: Add fast-path patterns for common queries
2. **Quality prototypes**: 8-12 distinctive examples per agent
3. **Test edge cases**: Focus on ambiguous queries
4. **Monitor margins**: Low margins = overlapping categories
5. **Iterate continuously**: Add/refine based on real usage
6. **Log everything**: Enable debugging and improvement
7. **Use clarification wisely**: Only when truly ambiguous

## Examples

### Example 1: Clear Equipment Checkout

```python
query = "can I borrow a laptop"

# Flow:
# 1. Heuristic Gate: No match (continue)
# 2. Weaviate: Top match = equipment_checkout (0.89)
# 3. Margin: High score + good margin
# 4. Result: Direct route (high confidence)

result = {
    "mode": "vector",
    "agent_id": "equipment_checkout",
    "confidence": "high",
    "reason": "Vector match (score: 0.89)"
}
```

### Example 2: Ambiguous Computer Query

```python
query = "who can I talk to for my computer problems"

# Flow:
# 1. Heuristic Gate: Entry-ambiguous + no action verb → Force triage
# 2. Weaviate: (skipped due to force_triage)
# 3. LLM Triage: Generate clarification
# 4. Result: Clarify

result = {
    "mode": "clarify",
    "confidence": "low",
    "clarifying_question": "What kind of computer help do you need?",
    "options": [
        {"label": "My own computer/software", "value": "out_of_scope"},
        {"label": "Library databases / VPN", "value": "google_site"},
        {"label": "Borrow laptop/equipment", "value": "equipment_checkout"},
        {"label": "None of these", "value": "other"}
    ]
}
```

### Example 3: Out-of-Scope Tech Support

```python
query = "my computer is not working"

# Flow:
# 1. Heuristic Gate: Tech support pattern → out_of_scope
# 2. Result: Direct route (high confidence, heuristic)

result = {
    "mode": "heuristic",
    "agent_id": "out_of_scope",
    "confidence": "high",
    "reason": "Out-of-scope: tech_support"
}
```
