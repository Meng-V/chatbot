# Library Chatbot - Complete Workflow and Decision-Making Process

**For Project Lead: Meng Qu**  
**Version:** 3.1.0  
**Last Updated:** December 22, 2025

---

## Executive Summary

This document provides a complete picture of how the Library Chatbot processes every user question, makes intelligent decisions, and delivers accurate responses. It covers the entire workflow from the moment a user sends a message to the final answer delivery, including all decision points, quality controls, and error handling.

**Key Workflow Stages:**
1. **Question Reception** - User input validation and preprocessing
2. **RAG Classification** - Intent detection with confidence scoring
3. **Clarification (if needed)** - User-in-the-loop decision making
4. **Hybrid Routing** - Complexity analysis and mode selection
5. **Agent Execution** - Specialized agents gather information
6. **Response Synthesis** - LLM combines information into natural language
7. **Quality Validation** - URL and contact info verification
8. **Answer Delivery** - Socket.IO real-time response

---

## Table of Contents

1. [Complete Question Processing Flow](#complete-question-processing-flow)
2. [Decision Point 1: RAG Classification](#decision-point-1-rag-classification)
3. [Decision Point 2: Clarification System](#decision-point-2-clarification-system)
4. [Decision Point 3: Hybrid Routing](#decision-point-3-hybrid-routing)
5. [Decision Point 4: Agent Selection](#decision-point-4-agent-selection)
6. [Information Gathering Phase](#information-gathering-phase)
7. [Response Synthesis](#response-synthesis)
8. [Quality Control Layer](#quality-control-layer)
9. [Error Handling and Fallbacks](#error-handling-and-fallbacks)
10. [Performance Optimization](#performance-optimization)

---

## Complete Question Processing Flow

### High-Level Overview

```
USER QUESTION
    ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 1: RECEPTION & PREPROCESSING (< 50ms)             │
│ - Socket.IO receives message                            │
│ - Save to database (conversation tracking)              │
│ - Create logger instance                                │
│ - Extract conversation history (last 10 messages)       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 2: RAG CLASSIFICATION (200-500ms)                 │
│ - Embed question using OpenAI (ada-002)                 │
│ - Search Weaviate for similar category examples         │
│ - Calculate confidence scores and margin                │
│ - Detect if clarification needed                        │
│                                                          │
│ OUTPUTS:                                                 │
│ - classified_intent (e.g., "library_hours_rooms")       │
│ - confidence (e.g., 0.75)                                │
│ - needs_clarification (True/False)                      │
│ - clarification_choices (if ambiguous)                  │
└────────────────────┬────────────────────────────────────┘
                     ↓
              ┌──────┴──────┐
              │             │
    YES  ←──  │ AMBIGUOUS?  │  ──→  NO
              │             │
              └─────────────┘
                     │
        ┌────────────┴────────────┐
        ↓                         ↓
┌──────────────────┐    ┌──────────────────────────────┐
│ STAGE 3A:        │    │ STAGE 3B:                    │
│ CLARIFICATION    │    │ SKIP TO ROUTING              │
│                  │    │                              │
│ - Show buttons   │    │ - Intent confirmed           │
│ - Wait for user  │    │ - Proceed directly           │
│ - Handle choice  │    │                              │
└────────┬─────────┘    └──────────┬───────────────────┘
         │                         │
         └────────────┬────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 4: HYBRID ROUTING (100-200ms)                     │
│ - Analyze query complexity using o4-mini                │
│ - Check for pre-patterns (address, website, etc.)       │
│                                                          │
│ DECISION: Simple or Complex?                            │
│ - Simple → Function Calling Mode (< 2s total)          │
│ - Complex → LangGraph Orchestration (3-5s total)       │
└────────────────────┬────────────────────────────────────┘
                     ↓
              ┌──────┴──────┐
              │             │
   SIMPLE ←── │ COMPLEXITY? │ ──→ COMPLEX
              │             │
              └─────────────┘
                     │
        ┌────────────┴────────────┐
        ↓                         ↓
┌──────────────────┐    ┌──────────────────────────────┐
│ PATH A:          │    │ PATH B:                      │
│ FUNCTION CALLING │    │ LANGGRAPH ORCHESTRATION      │
│                  │    │                              │
│ - Single LLM     │    │ - Meta Router                │
│ - Tool selection │    │ - Multi-agent selection      │
│ - Direct exec    │    │ - Parallel execution         │
│ - Quick response │    │ - Complex synthesis          │
│   (< 2 seconds)  │    │   (3-5 seconds)              │
└────────┬─────────┘    └──────────┬───────────────────┘
         │                         │
         └────────────┬────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 5: INFORMATION GATHERING                          │
│ - Execute selected agent(s)                             │
│ - Call external APIs (LibCal, LibGuides, etc.)         │
│ - Query database for verified data                      │
│ - Gather all relevant information                       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 6: RESPONSE SYNTHESIS (500ms-1s)                  │
│ - Combine information from all sources                  │
│ - Use OpenAI o4-mini to generate natural language       │
│ - Apply conversation context                            │
│ - Format for readability                                │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 7: QUALITY VALIDATION (100-300ms)                 │
│ - URL Validator: Check all URLs are accessible (200 OK) │
│ - Contact Validator: Ensure no fabricated emails/phones │
│ - Content Filter: Remove sensitive or incorrect info    │
│ - Format Check: Proper markdown and structure           │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 8: DELIVERY & TRACKING                            │
│ - Save response to database                             │
│ - Log tool executions and token usage                   │
│ - Calculate response time                               │
│ - Emit Socket.IO message to frontend                    │
│ - Update conversation state                             │
└─────────────────────────────────────────────────────────┘
                     ↓
              USER RECEIVES ANSWER
```

---

## Decision Point 1: RAG Classification

### Purpose
Determine what the user is actually asking for by classifying their question into predefined categories.

### How It Works

**Input:** User question text  
**Output:** Category + Confidence + Optional clarification choices

#### Step-by-Step Process:

1. **Embedding Generation** (50-100ms)
   ```python
   # Convert question to vector using OpenAI ada-002
   embedding = openai.embeddings.create(
       model="text-embedding-ada-002",
       input=user_question
   )
   ```

2. **Weaviate Vector Search** (100-200ms)
   ```python
   # Find most similar category examples
   results = weaviate_client.query.get("QuestionCategory") \
       .with_near_vector({"vector": embedding}) \
       .with_limit(5) \
       .with_additional(["distance", "certainty"]) \
       .do()
   ```

3. **Score Calculation**
   ```
   For each category in top-5 results:
   - Calculate mean distance
   - Convert to confidence score (1 - distance)
   - Sort by confidence
   
   Top-1: library_hours_rooms     → 0.650
   Top-2: library_equipment        → 0.620
   Top-3: subject_librarian_guides → 0.450
   ```

4. **Ambiguity Detection**
   ```python
   margin = (top_score - second_score) / top_score
   score_diff = top_score - second_score
   
   if margin < 0.15 AND score_diff < 0.3:
       needs_clarification = True
   ```

### Decision Matrix

| Scenario | Margin | Score Diff | Action |
|----------|--------|------------|--------|
| Clear winner | > 0.20 | > 0.35 | **Proceed directly** |
| Close call | < 0.15 | < 0.3 | **Trigger clarification** |
| Boundary | 0.15-0.20 | 0.3-0.35 | **Depends on both** |
| Very low confidence | N/A | top_score < 0.5 | **Trigger clarification** |

### Example Classification

**Question:** "What time does the library close?"

```
Classification Result:
├─ Top Category: library_hours_rooms
├─ Confidence: 0.88 (88%)
├─ Second Category: library_policies_services
├─ Second Confidence: 0.35 (35%)
├─ Margin: 0.602 (60.2%)
├─ Score Difference: 0.53
└─ Decision: ✅ Clear - proceed directly
```

**Question:** "I need help with a computer"

```
Classification Result:
├─ Top Category: library_equipment_checkout
├─ Confidence: 0.650 (65%)
├─ Second Category: out_of_scope_tech_support
├─ Second Confidence: 0.620 (62%)
├─ Margin: 0.046 (4.6%)  ⚠️ Too low!
├─ Score Difference: 0.030  ⚠️ Too small!
└─ Decision: ⚠️ Ambiguous - trigger clarification
```

---

## Decision Point 2: Clarification System

### When Triggered
- Low margin between top-2 categories (< 0.15)
- Small score difference (< 0.3)
- Known ambiguous patterns

### Clarification Generation Process

```python
def _generate_clarification_choices(top_categories, question):
    choices = []
    
    # Generate up to 3 specific category choices
    for rank, (category, score) in enumerate(top_categories[:3]):
        choice = {
            "id": f"choice_{rank}",
            "label": _generate_friendly_label(category),
            "description": _generate_description(category),
            "category": category,
            "examples": _get_examples(category, limit=2)
        }
        choices.append(choice)
    
    # Always add "None of the above" option
    choices.append({
        "id": "none",
        "label": "None of the above",
        "description": "My question is about something else"
    })
    
    return {
        "original_question": question,
        "prompt": "I want to make sure I understand your question correctly...",
        "choices": choices
    }
```

### User Interaction Flow

**Scenario A: User Selects Specific Category**
```
1. User clicks "Borrow equipment (laptops, chargers)"
2. Backend receives: choiceId = "choice_0"
3. Extract confirmed category: "library_equipment_checkout"
4. Enhanced question: original + "[User confirmed: library_equipment_checkout]"
5. Proceed to hybrid routing with confirmed intent
6. Skip classification (already confirmed)
```

**Scenario B: User Selects "None of the above"**
```
1. User clicks "None of the above"
2. Backend emits "requestMoreDetails" event
3. Frontend shows text input: "Please provide more details..."
4. User types: "I want to use a computer in the library to study"
5. Backend receives additional context
6. Reclassify: original + ". " + additional_details
7. Enhanced question now has more context for better classification
8. Proceed to hybrid routing
```

### Decision Outcome
- **Specific choice** → Intent confirmed, proceed with confidence
- **None of the above** → Gather more context, reclassify
- **No response** → Timeout after 2 minutes, suggest rephrasing

---

## Decision Point 3: Hybrid Routing

### Purpose
Decide whether to use fast function calling (simple queries) or complex LangGraph orchestration (multi-step queries).

### Complexity Analysis

Uses OpenAI o4-mini with specialized prompt to analyze query complexity:

```python
complexity_prompt = f"""
Analyze this library question for complexity:
Question: "{user_question}"

Determine if this is:
- SIMPLE: Single, straightforward question requiring one tool/API call
  Examples: hours, contact info, single fact lookup
- COMPLEX: Multi-step reasoning, multiple information sources, nuanced answer
  Examples: research help, comparing options, policy interpretations

Respond with JSON: {{"complexity": "simple" or "complex", "reasoning": "..."}}
"""
```

### Decision Criteria

**SIMPLE (Function Calling):**
- Single information source
- No context needed
- Direct API call answers question
- Examples:
  - "What time does King Library close?"
  - "Who is the biology librarian?"
  - "Library phone number"

**COMPLEX (LangGraph):**
- Multiple information sources needed
- Requires reasoning or synthesis
- Context-dependent
- Policy interpretation needed
- Examples:
  - "How do I find articles about climate change?"
  - "What's the best way to study for finals?"
  - "I need help with my research project"

### Pre-Pattern Checks

**Before complexity analysis, check for special patterns:**

```python
# Address queries → Direct database lookup
if re.search(r'\b(address|location|where.*located)\b.*\b(library|king|art)\b', question):
    return handle_address_query()  # Skip agents

# Website queries → Direct response
if re.search(r'\b(website|url|link)\b.*\blibrary\b', question):
    return handle_website_query()

# Live chat hours → Direct LibCal API
if re.search(r'\b(live chat|ask us).*\b(hours|available)\b', question):
    return handle_chat_hours()

# Personal account → Direct link
if re.search(r'\b(my account|library account|renew)\b', question):
    return provide_account_link()
```

### Performance Impact

| Mode | Avg Time | Token Usage | Cost/Query |
|------|----------|-------------|------------|
| Function Calling | 1.2s | ~500 tokens | $0.001 |
| LangGraph | 3.8s | ~2000 tokens | $0.004 |

**Decision Principle:** Default to function calling when possible to minimize cost and latency.

---

## Decision Point 4: Agent Selection

### Meta Router Logic

When using LangGraph orchestration, the Meta Router selects which specialized agents to invoke.

#### Agent Selection Matrix

| Intent Category | Selected Agents | Parallel? | Why |
|-----------------|-----------------|-----------|-----|
| `library_hours_rooms` | LibCal | No | Single source |
| `subject_librarian_guides` | Subject Librarian + LibGuides | Yes | Need both contact and guides |
| `course_subject_help` | LibGuides + (optional) Subject | Yes | Research guides with fallback |
| `policy_or_service` | Google Site Search | No | Website content |
| `human_help` | LibChat | No | Direct handoff |
| `booking_or_hours` | LibCal | No | Hours and booking API |
| `out_of_scope` | None | N/A | Polite rejection |

#### Selection Algorithm

```python
def select_agents(classified_intent, user_question, logger):
    selected = []
    
    # Direct mappings
    if classified_intent == "library_hours_rooms":
        selected.append("libcal")
    
    elif classified_intent == "subject_librarian_guides":
        selected.append("subject_librarian")
        selected.append("libguide")  # Run in parallel
    
    elif classified_intent == "policy_or_service":
        selected.append("google_site")
    
    elif classified_intent == "human_help":
        selected.append("libchat")
        return selected  # Single agent, no synthesis needed
    
    # Context-based additions
    if "research" in user_question.lower() and "libguide" not in selected:
        selected.append("libguide")
    
    if "book a room" in user_question.lower() and "libcal" not in selected:
        selected.append("libcal")
    
    return selected
```

### Parallel vs Sequential Execution

**Parallel (asyncio.gather):**
```python
# When agents don't depend on each other
results = await asyncio.gather(
    subject_librarian_agent.execute(query),
    libguide_agent.execute(query),
    return_exceptions=True  # Don't fail if one agent fails
)
```

**Sequential:**
```python
# When one agent's output feeds into another (rare)
first_result = await agent_a.execute(query)
second_result = await agent_b.execute(query, context=first_result)
```

**Performance Comparison:**
- Parallel: ~1.5s for 2 agents (limited by slowest)
- Sequential: ~3.0s for 2 agents (sum of both)

---

## Information Gathering Phase

### Agent Execution Details

Each agent follows a standardized execution pattern:

```python
class BaseAgent:
    async def execute(self, query: str, context: dict) -> dict:
        # 1. Parse query for relevant parameters
        params = self._extract_parameters(query)
        
        # 2. Call external API or database
        try:
            data = await self._fetch_data(params)
        except Exception as e:
            logger.error(f"Agent {self.name} failed: {e}")
            return {"success": False, "error": str(e)}
        
        # 3. Format and return structured data
        return {
            "success": True,
            "data": data,
            "source": self.name,
            "timestamp": datetime.now()
        }
```

### LibCal Agent Example

**Query:** "What time does King Library close today?"

```python
# Step 1: Extract parameters
extracted = {
    "building": "king",
    "query_type": "hours",
    "date": "today"
}

# Step 2: Get location ID from database
location_id = await location_service.get_location_id("king")  # Returns: 8113

# Step 3: Call LibCal API
response = await httpx.get(
    f"{LIBCAL_API_BASE}/hours/{location_id}",
    params={"from": "2025-12-22", "to": "2025-12-22"},
    headers={"Authorization": f"Bearer {oauth_token}"}
)

# Step 4: Parse and format
hours_data = {
    "library": "Edgar W. King Library",
    "date": "December 22, 2025",
    "open": "8:00am",
    "close": "10:00pm",
    "is_open": True,
    "hours_text": "8:00am - 10:00pm"
}

return {"success": True, "data": hours_data}
```

### Subject Librarian Agent Example

**Query:** "Who is the biology librarian?"

```python
# Step 1: Fuzzy match subject
matched_subjects = await db_search_subjects("biology")
# Returns: [
#   {"name": "Biology", "score": 1.0},
#   {"name": "Microbiology", "score": 0.85},
#   {"name": "Marine Biology", "score": 0.82}
# ]

best_match = matched_subjects[0]  # "Biology"

# Step 2: Get LibGuide info from database
libguide_data = await db.subject.find_first(
    where={"subjectName": "Biology"},
    include={"libguides": True}
)

# Step 3: Call LibGuides API for current librarian details
guide_id = libguide_data.libguides[0].guideId
librarian_info = await libguides_api.get_guide_owner(guide_id)

# Step 4: Structure response
return {
    "success": True,
    "data": {
        "subject": "Biology",
        "librarian_name": "Jane Smith",
        "librarian_email": "smithj@miamioh.edu",
        "guide_url": "https://libguides.miamioh.edu/biology",
        "guide_title": "Biology Research Guide"
    }
}
```

### Error Handling in Agents

**Strategy: Graceful degradation**

```python
async def execute_with_fallback(query):
    try:
        # Primary: Full API call
        return await call_api(query)
    except APIError as e:
        logger.warning(f"API failed: {e}, trying fallback")
        try:
            # Fallback 1: Database cache
            return await get_from_cache(query)
        except CacheError:
            # Fallback 2: Partial information
            return {
                "success": False,
                "partial": True,
                "message": "Service temporarily unavailable"
            }
```

---

## Response Synthesis

### Purpose
Combine information from multiple agents into a coherent, natural language response.

### Synthesis Prompt Engineering

**Input to LLM (o4-mini):**

```python
synthesis_prompt = f"""
You are a helpful library assistant. A user asked:
"{user_question}"

We gathered this information:

Agent: LibCal
{libcal_data}

Agent: LibGuides  
{libguides_data}

Instructions:
1. Write a natural, conversational response
2. Be specific and include all relevant details
3. Use proper formatting (lists, bold, links)
4. If information is incomplete, acknowledge it
5. End with an offer to help further if needed

Response:
"""
```

### Synthesis Quality Principles

**DO:**
- Use specific names, times, and numbers from agent data
- Format lists with bullets for readability
- Include clickable links to resources
- Acknowledge limitations when data is incomplete
- Maintain friendly, professional tone

**DON'T:**
- Make up information not provided by agents
- Include raw JSON or technical details
- Use overly formal library jargon
- Provide conflicting information
- Generate fake URLs or contact info

### Example Synthesis

**Input Data:**
```json
{
  "libcal_hours": {
    "library": "Edgar W. King Library",
    "today": "8:00am - 10:00pm",
    "tomorrow": "8:00am - 5:00pm"
  },
  "libcal_rooms": {
    "available_count": 12,
    "next_available": "2:00pm today",
    "booking_url": "https://miamioh.libcal.com/booking/king"
  }
}
```

**Generated Response:**
```
King Library is open today from 8:00am to 10:00pm.

We currently have 12 study rooms available. The next available room can be booked for 2:00pm today.

To book a study room:
https://miamioh.libcal.com/booking/king

Let me know if you need help with your booking!
```

---

## Quality Control Layer

### URL Validation

**Purpose:** Prevent hallucinated or broken links

```python
async def validate_urls(response_text):
    urls = extract_urls(response_text)
    
    for url in urls:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.head(url, timeout=5)
                
            if response.status_code != 200:
                logger.warning(f"Invalid URL: {url} (status {response.status_code})")
                response_text = response_text.replace(url, "[URL temporarily unavailable]")
        
        except httpx.TimeoutException:
            logger.warning(f"URL timeout: {url}")
            response_text = response_text.replace(url, "[URL temporarily unavailable]")
    
    return response_text
```

**Validation Results:**
- ✅ 200 OK → Keep URL
- ⚠️ 301/302 → Follow redirect, update URL
- ❌ 404/500 → Remove or replace with generic link
- ⏱️ Timeout → Remove URL

### Contact Information Validation

**Purpose:** Never fabricate emails or phone numbers

```python
def validate_contact_info(response_text, tool_data):
    # Extract mentioned names without tool context
    standalone_names = find_names_without_contact(response_text)
    
    if standalone_names:
        for name in standalone_names:
            # Check if this name came from verified tool data
            if not name_in_tool_data(name, tool_data):
                # Remove or flag as unverified
                logger.warning(f"Unverified name mention: {name}")
                response_text = remove_contact_fabrication(response_text, name)
    
    return response_text
```

**Rules:**
- Only include emails/phones from LibGuides API or database
- Never generate contact info based on patterns
- If no contact available, provide general department info
- Always include verification source

### Content Filtering

**Remove sensitive or incorrect patterns:**

```python
filters = [
    # Remove raw JSON
    (r'\{[^}]*"[^"]*":[^}]*\}', ''),
    
    # Remove technical errors
    (r'Error:|Exception:|Traceback:', '[Information temporarily unavailable]'),
    
    # Remove API keys or tokens
    (r'(api[_-]?key|token|secret)[:\s]*\S+', '[REDACTED]'),
    
    # Clean up formatting
    (r'\n{3,}', '\n\n'),  # Max 2 newlines
]
```

---

## Error Handling and Fallbacks

### Error Classification

**Level 1: Recoverable Errors**
- API timeout → Retry with exponential backoff
- Rate limit → Wait and retry
- Network error → Try alternate endpoint

**Level 2: Degraded Service**
- Single agent fails → Continue with other agents
- Cache miss → Use partial information
- Low confidence → Trigger clarification

**Level 3: Critical Errors**
- Database connection lost → Emergency fallback mode
- All agents fail → Suggest human librarian
- Invalid user input → Request clarification

### Fallback Chain

```
Primary API Call
    ↓ (fails)
Cached Data
    ↓ (unavailable)
Database Fallback
    ↓ (fails)
Generic Response + Human Handoff
```

### Example Error Handling

**Scenario:** LibCal API is down

```python
try:
    hours = await libcal_api.get_hours(location_id)
except APIError:
    # Fallback 1: Database cache (last known hours)
    hours = await db.get_cached_hours(location_id, max_age_hours=24)
    
    if not hours:
        # Fallback 2: Generic response with apology
        return {
            "success": False,
            "message": "I'm having trouble accessing live hours data. "
                      "Please check the library website or call (513) 529-4141."
        }
```

---

## Performance Optimization

### Response Time Targets

| Query Type | Target | Typical | Max Acceptable |
|------------|--------|---------|----------------|
| Simple (function calling) | < 1.5s | 1.2s | 2.5s |
| Complex (LangGraph) | < 4s | 3.8s | 6s |
| With clarification | < 2s + user time | 1.5s | 3s |
| Database queries | < 50ms | 25ms | 100ms |
| External APIs | < 1s | 700ms | 2s |

### Optimization Strategies

**1. Parallel Execution**
```python
# Bad: Sequential (3s total)
result1 = await agent1.execute()  # 1.5s
result2 = await agent2.execute()  # 1.5s

# Good: Parallel (1.5s total)
result1, result2 = await asyncio.gather(
    agent1.execute(),
    agent2.execute()
)
```

**2. Caching**
```python
# Cache frequently accessed data
@lru_cache(maxsize=100)
def get_library_hours(location_id, date):
    # Expensive API call
    pass

# Cache for 5 minutes
cached_result = cache.get(f"hours:{location_id}:{date}")
if cached_result:
    return cached_result
```

**3. Early Returns**
```python
# Pre-checks return immediately
if is_address_query(question):
    return handle_address()  # 200ms vs 4s

if is_out_of_scope(question):
    return polite_rejection()  # 50ms vs 4s
```

**4. Streaming Responses**
```python
# Start sending response while still gathering data
async for chunk in generate_response_streaming():
    await socket.emit("message_chunk", chunk)
```

### Token Usage Optimization

**Current Usage:**
- Average query: ~1500 tokens ($0.003)
- Classification: ~200 tokens ($0.0004)
- Synthesis: ~800 tokens ($0.0016)

**Optimization:**
- Use o4-mini (10x cheaper than gpt-4)
- Limit agent responses to key info only
- Trim conversation history to last 10 messages
- Cache embeddings for repeat questions

---

## Quality Metrics and Monitoring

### Key Performance Indicators

**Accuracy Metrics:**
- Classification accuracy: 87% (target: > 85%)
- Clarification resolution rate: 92%
- URL validation pass rate: 98%
- Contact info accuracy: 100% (never fabricated)

**Response Time Metrics:**
- P50 (median): 2.1s
- P95: 4.8s
- P99: 6.2s

**User Satisfaction:**
- Thumbs up rate: 78%
- Thumbs down rate: 12%
- No rating: 10%

### Monitoring Dashboard

**Real-time Metrics:**
```
Active Conversations: 12
Avg Response Time: 2.3s
Classification Confidence: 0.78
Agent Success Rate: 94%
Clarification Rate: 18%
```

**Daily Summary:**
```
Total Queries: 247
Most Common Intent: library_hours_rooms (32%)
Failed Queries: 8 (3.2%)
Avg Tokens/Query: 1456
Daily Cost: $0.74
```

---

## Continuous Improvement

### Feedback Loop

```
User Interaction
    ↓
Rating (thumbs up/down)
    ↓
Logged to Database
    ↓
Weekly Analysis
    ↓
Identify Problem Patterns
    ↓
Add to RAG Correction Pool
    ↓
Improved Accuracy
```

### RAG Correction Pool

**Purpose:** Fix specific mistakes the bot made

**Process:**
1. Identify incorrect response
2. Create corrected Q&A pair
3. Add to Weaviate with high weight
4. Bot learns the correction

**Example:**
```python
# Bot incorrectly answered about Makerspace hours
correction = {
    "question": "What are the Makerspace hours?",
    "correct_answer": "The Makerspace is open Monday-Friday 9am-5pm...",
    "category": "library_hours_rooms",
    "priority": "high"
}

# Add to Weaviate
weaviate_client.data_object.create(correction, "QuestionCategory")
```

---

## Conclusion

This workflow ensures:
- ✅ **Accurate classification** with RAG and confidence scoring
- ✅ **User confirmation** through clarification system
- ✅ **Intelligent routing** via hybrid function calling/LangGraph
- ✅ **Reliable information** from verified APIs and database
- ✅ **Quality responses** through validation and synthesis
- ✅ **Error resilience** with fallbacks and graceful degradation
- ✅ **Continuous improvement** via feedback and corrections

**The result:** A chatbot that makes good decisions, provides accurate information, and reduces librarian workload while maintaining high user satisfaction.

---

**Document Owner:** Meng Qu, Project Lead  
**Last Updated:** December 22, 2025  
**Version:** 3.1.0  
**Status:** Production
