# Routing Contract - Production System

## Overview

The Miami Libraries Smart Chatbot uses a **single, unified routing path** through LangGraph. All user queries flow through the same pipeline for deterministic and accurate classification.

**Last Updated:** January 16, 2026  
**Version:** 4.0 (Consolidated Routing)

---

## Production Entry Point

**ONLY ONE ENTRY POINT:**
```python
from src.graph.orchestrator import library_graph

result = await library_graph.ainvoke({
    "user_message": message,
    "messages": [],
    "conversation_history": history,
    "conversation_id": conversation_id,
    "_logger": logger
})
```

**Files:**
- `src/main.py` - HTTP and Socket.IO handlers call `library_graph` directly
- `src/graph/orchestrator.py` - LangGraph workflow definition
- `src/graph/rag_router.py` - Production RAG-based router

**Archived (DO NOT USE):**
- `archived/hybrid_router.py.deprecated` - Old pattern-based router
- `archived/hybrid_router_rag.py.deprecated` - Old hybrid routing system
- `archived/function_calling.py.deprecated` - Separate function calling mode

---

## Graph Flow

```
User Question
    ↓
understand_query (Query Understanding Layer)
    ↓
    ├─ needs_clarification? → clarify → END
    └─ clear query → rag_router
                        ↓
                        ├─ needs_clarification? → clarify → END
                        └─ has primary_agent_id → execute_agents
                                                      ↓
                                                  synthesize
                                                      ↓
                                                    END
```

---

## Routing Contract (State Fields)

### Input to Router
- `user_message`: str - Original user question
- `processed_query`: str - Cleaned/translated query from understanding layer
- `conversation_history`: List[Dict] - Last 10 messages for context

### Output from Router

**Required:**
- `primary_agent_id`: str | None - Primary agent to execute
- `needs_clarification`: bool - Whether clarification is needed

**Optional:**
- `secondary_agent_ids`: List[str] - Additional agents for multi-agent queries
- `clarification`: Dict - Structured clarification data
  ```python
  {
      "question": "I want to make sure I understand...",
      "options": [
          {"id": "libchat", "label": "Talk to a librarian"},
          {"id": "none", "label": "Let me rephrase"}
      ]
  }
  ```

**Metadata:**
- `classified_intent`: str - Category from RAG classifier
- `classification_confidence`: float - Confidence score (0-1)
- `classification_result`: Dict - Full RAG classification result

---

## Agent IDs (Standardized)

### In-Scope Library Services
- `equipment_checkout` - Borrow laptops, chargers, cameras, etc.
- `libcal_hours` - Library hours and schedules
- `libcal_rooms` - Study room reservations (currently mapped to libcal_hours)
- `subject_librarian` - Find subject librarians by discipline
- `libguides` - Research guides and course guides
- `policy_search` - Library policies and services (website search)
- `libchat_handoff` - Connect to human librarian

### Out-of-Scope
- `out_of_scope` - Questions outside library services (tech support, campus life, academics, etc.)

### Special
- `transcript_rag` - Correction pool (not used in routing)

---

## Category to Agent Mapping

Defined in `src/graph/rag_router.py`:

```python
CATEGORY_TO_AGENT = {
    # In-scope
    "library_equipment_checkout": "equipment_checkout",
    "library_hours_rooms": "libcal_hours",
    "subject_librarian_guides": "subject_librarian",
    "research_help_handoff": "libchat_handoff",
    "library_policies_services": "policy_search",
    "ticket_submission_request": "libchat_handoff",
    "human_librarian_request": "libchat_handoff",
    
    # Out-of-scope
    "out_of_scope_tech_support": "out_of_scope",
    "out_of_scope_academics": "out_of_scope",
    "out_of_scope_campus_life": "out_of_scope",
    "out_of_scope_financial": "out_of_scope",
    "out_of_scope_factual_trivia": "out_of_scope",
    "out_of_scope_inappropriate": "out_of_scope",
    "out_of_scope_nonsensical": "out_of_scope",
}
```

---

## Clarification Triggers

Clarification can originate from **two sources**:

### Source 1: Query Understanding Layer (Priority 1)
- Detects ambiguous/unclear user input before routing
- Sets `needs_clarification = True` and `clarifying_question` (string)
- **Takes priority** if both sources trigger clarification

### Source 2: RAG Router (Priority 2)
1. **RAG classifier flags ambiguity** - Multiple categories with similar scores
2. **Low confidence** - `confidence < 0.65` (threshold in `rag_router.py`)
3. **Unknown category** - Category not in `CATEGORY_TO_AGENT` mapping

**Clarification Flow:**
1. Query understanding OR router sets `needs_clarification = True`
2. Query understanding sets `clarifying_question` (simple string) OR router sets `clarification` dict with question and options
3. Neither node sets `final_answer` (that's the clarify node's job)
4. Clarify node checks `clarifying_question` first, then falls back to `clarification` dict
5. Clarify node formats the response for the user
6. Workflow ends (user must respond)

**Priority Order in clarify_node:**
```python
if state.get("clarifying_question"):  # From query understanding
    use this directly
elif state.get("clarification"):      # From router
    format question + options
else:                                  # Fallback
    generic clarification message
```

---

## Execute Agents Node

Maps `primary_agent_id` to actual agent instances:

```python
agent_map = {
    # LibCal
    "libcal_hours": libcal_agent,
    "libcal_rooms": libcal_agent,
    
    # Research & guides
    "subject_librarian": enhanced_subject_agent,
    "libguides": libguide_agent,
    
    # Policy & search
    "policy_search": google_site_agent,
    "equipment_checkout": google_site_agent,
    
    # Human handoff
    "libchat_handoff": libchat_handoff,
    
    # Special
    "out_of_scope": None,  # No execution needed
}
```

Agents with `None` are skipped (e.g., out_of_scope is handled in router).

---

## Testing

**Smoke Test:**
```bash
cd ai-core
source venv/bin/activate
python scripts/test_routing_smoke.py
```

**Test Coverage:**
- Equipment checkout (laptops, chargers)
- Out-of-scope detection (tech support, homework, campus life)
- Library hours and room booking
- Subject librarian lookup
- Policy search
- Human handoff

**Current Results:**
- 12/16 tests passing (75% success rate)
- 3 clarifications (acceptable)
- 1 failure: "Where is the dining hall?" → needs better out-of-scope examples

---

## Troubleshooting

### Issue: Too many clarifications
**Solution:** Adjust `CONFIDENCE_THRESHOLD` in `src/graph/rag_router.py` (currently 0.65)

### Issue: Wrong agent selected
**Solution:** 
1. Check `CATEGORY_TO_AGENT` mapping in `src/graph/rag_router.py`
2. Add more training examples to `src/classification/category_examples.py`
3. Re-initialize RAG classifier: `python scripts/initialize_rag_classifier.py`

### Issue: Out-of-scope not detected
**Solution:** Add more out-of-scope examples to `category_examples.py` for the specific category

---

## Migration Notes

**What Changed:**
- ✅ Removed `hybrid_router_rag.py` - No more dual routing paths
- ✅ Removed `function_calling.py` - No more separate function calling mode
- ✅ Centralized routing in `rag_router.py` - Single source of truth
- ✅ Standardized state contract - `primary_agent_id` + `secondary_agent_ids`
- ✅ Clarification centralized - Router sets flags, clarify node formats response

**Backward Compatibility:**
- `selected_agents` field still populated for legacy code
- External API response format unchanged

---

## Future Improvements

1. **Multi-agent queries** - Use `secondary_agent_ids` for complex questions requiring multiple agents
2. **Dynamic confidence threshold** - Adjust based on category (e.g., lower threshold for critical services)
3. **A/B testing** - Compare routing decisions with user feedback
4. **Active learning** - Use clarification choices to improve training data

---

## Contact

For questions or issues with routing:
- Check logs in `logger.get_logs()`
- Review `classification_result` in state for debugging
- Run smoke tests to verify changes

**Maintainer:** Meng Qu  
**Repository:** Miami Libraries Smart Chatbot
