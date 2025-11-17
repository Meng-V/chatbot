# LibGuide vs MyGuide - How the Bot Routes Between Them

**Date**: November 11, 2025  
**Version**: 1.0

---

## TL;DR - Quick Answer

The bot uses **BOTH** systems, but for different purposes:

| System | When Used | Trigger Intents | Best For |
|--------|-----------|----------------|----------|
| **MyGuide** | Finding subject librarian by major/department | `subject_librarian` | "Who's the biology librarian?", "Business major help" |
| **LibGuide** | Finding course guides or subject resources | `course_subject_help` | "ENG 111 guide", "Databases for psychology" |

**Both ultimately call the same LibApps API**, but MyGuide uses a local database first for better major/department matching.

---

## The Two Systems Explained

### 1. **MyGuide System** (Local Database → API)

**Files**:
- `src/agents/subject_librarian_agent.py`
- `src/tools/subject_matcher.py`
- Database: Prisma `Subject` table (710+ subjects)

**How It Works**:
```
User Query: "Who's the biology librarian?"
    ↓
Step 1: Query LOCAL MyGuide database
    - Match by subject name (Biology)
    - Match by major code (BIO)
    - Match by department name (Biological Sciences)
    - Returns: LibGuide names associated with that subject
    ↓
Step 2: Call LibApps API
    - Search for those LibGuide names
    - Get guide details (ID, URL, description)
    - Get guide owner (librarian info)
    ↓
Step 3: Format human-readable response
    - Librarian names and emails
    - Subject guide URLs
    - Related majors/departments
```

**Data Sources**:
- **Local database** with 710+ subjects from MyGuide
- Each subject has:
  - Major codes (e.g., "BIO", "BIOL")
  - Department codes (e.g., "BIO SCI")
  - LibGuide names (e.g., "Biology")
  - Regional campus info

**Advantages**:
- ✅ Better matching for major names ("Business Administration" → finds all business guides)
- ✅ Handles department codes (e.g., "MGT" → Management)
- ✅ Supports regional campuses (Hamilton, Middletown)
- ✅ Rich metadata (710+ subjects with cross-references)

**Example Queries**:
- "Who is the psychology librarian?"
- "I need help with my accounting major"
- "Biology subject librarian"
- "Business administration research help"

---

### 2. **LibGuide System** (Direct API)

**Files**:
- `src/agents/libguide_comprehensive_agent.py`
- `src/tools/libguide_comprehensive_tools.py`

**How It Works**:
```
User Query: "Research guide for ENG 111"
    ↓
Step 1: Call LibApps API directly
    - GET /1.2/accounts?expand[]=subjects
    - Parse all librarians and their subjects
    ↓
Step 2: Fuzzy match query to subjects
    - Uses Levenshtein distance
    - Synonym mapping (e.g., "bio" → "biology")
    - Returns top match(es)
    ↓
Step 3: Generate subject guide URL
    - https://libguides.lib.miamioh.edu/sb.php?subject_id={id}
    ↓
Step 4: Format human-readable response
    - Librarian names and emails
    - Subject guide URL
```

**Data Sources**:
- **LibApps API** (`/1.2/accounts`)
- Real-time data (always current)
- Synonym mapping in code

**Advantages**:
- ✅ Always up-to-date (live API)
- ✅ Simpler for straightforward subject queries
- ✅ Good fuzzy matching with synonyms
- ✅ Works for course codes (ENG 111 → English)

**Example Queries**:
- "ENG 111 research guide"
- "Find databases for chemistry"
- "Computer science subject guide"
- "Psychology resources"

---

## How the Router Decides

**File**: `src/graph/orchestrator.py` (Lines 114-122)

### Intent Classification

The LLM classifies user queries into one of these intents:

```python
agent_mapping = {
    "discovery_search": ["primo"],
    "subject_librarian": ["subject_librarian"],      # → Uses MyGuide
    "course_subject_help": ["libguide", "transcript_rag"],  # → Uses LibGuide
    "booking_or_hours": ["libcal"],
    "policy_or_service": ["google_site", "transcript_rag"],
    "human_help": ["libchat"],
    "general_question": ["transcript_rag", "google_site"]
}
```

### Classification Rules

**→ Routes to MyGuide (`subject_librarian` intent)**:
- "Who's the [subject] librarian?"
- "I need help with [major name]"
- "[Department] research help"
- "Subject librarian for [topic]"

**Examples**:
- ✅ "Who's the biology librarian?" → `subject_librarian` → **MyGuide**
- ✅ "I need help with my accounting major" → `subject_librarian` → **MyGuide**
- ✅ "Business librarian contact" → `subject_librarian` → **MyGuide**

---

**→ Routes to LibGuide (`course_subject_help` intent)**:
- "LibGuide for [subject]"
- "Research guide for [course code]"
- "Databases for [subject]"
- "What resources for [class]?"

**Examples**:
- ✅ "Research guide for ENG 111" → `course_subject_help` → **LibGuide**
- ✅ "Databases for psychology" → `course_subject_help` → **LibGuide**
- ✅ "Chemistry subject guide" → `course_subject_help` → **LibGuide**

---

## Router System Prompt (Lines 48-85)

```python
2. **subject_librarian** - Finding subject librarian, LibGuides for a specific major, 
   department, or academic subject
   Examples: "Who's the biology librarian?", "LibGuide for accounting", 
   "I need help with psychology research"

3. **course_subject_help** - Course guides, recommended databases for a specific class
   Examples: "What databases for ENG 111?", "Guide for PSY 201", "Resources for CHM 201"
```

**Key Difference**:
- **subject_librarian**: Focus on WHO (finding a person)
- **course_subject_help**: Focus on WHAT (finding resources)

---

## Under the Hood: Both Use LibApps API

**Important**: Both systems ultimately query the **same LibApps API v1.2**, but in different ways:

### MyGuide Flow:
```
User Query 
  → MyGuide database (local, 710 subjects)
  → Extract LibGuide names
  → LibApps API: GET /1.2/guides?search={name}
  → LibApps API: GET /1.2/guides/{id}
  → LibApps API: GET /1.2/accounts/{owner_id}
  → Return librarian info
```

### LibGuide Flow:
```
User Query
  → LibApps API: GET /1.2/accounts?expand[]=subjects
  → Parse all subjects and librarians
  → Fuzzy match to query
  → Generate subject guide URL
  → Return librarian info
```

**Both return**:
- Librarian name
- Librarian email
- Subject guide URL (libguides.lib.miamioh.edu/sb.php?subject_id={id})

---

## Comparison Table

| Feature | MyGuide | LibGuide |
|---------|---------|----------|
| **Data Source** | Local DB + API | Direct API only |
| **Number of Subjects** | 710+ with metadata | All from API |
| **Major Code Mapping** | ✅ Yes (BIO, MGT, etc.) | ❌ No |
| **Department Mapping** | ✅ Yes (BIO SCI, etc.) | ❌ No |
| **Regional Campus Support** | ✅ Yes | ❌ No |
| **Fuzzy Matching** | ✅ High quality | ✅ Good |
| **Synonym Support** | ✅ Via database | ✅ Via code |
| **Always Current** | ❌ Needs DB updates | ✅ Real-time |
| **Response Time** | Faster (local lookup) | Slower (API call) |
| **Best For** | Complex queries, majors | Simple subject queries |

---

## Example Scenarios

### Scenario 1: Biology Librarian

**Query**: "Who is the biology librarian?"

**Classification**: `subject_librarian` → **MyGuide**

**MyGuide Process**:
1. Query database: `Subject.name = "Biology"`
2. Found: Biology subject with LibGuide = "Biology"
3. Call API: Search for "Biology" guide
4. Get guide owner: Sarah Johnson
5. Return: Name, email, guide URL

**Why MyGuide?**: Intent is finding a PERSON (librarian)

---

### Scenario 2: English Course Guide

**Query**: "What databases should I use for ENG 111?"

**Classification**: `course_subject_help` → **LibGuide**

**LibGuide Process**:
1. Parse course code: ENG 111 → Subject = "English"
2. Call API: Get all accounts with subjects
3. Find "English" subject
4. Return librarians and subject guide URL

**Why LibGuide?**: Intent is finding RESOURCES (databases)

---

### Scenario 3: Accounting Major Help

**Query**: "I need help with research for my accounting major"

**Classification**: `subject_librarian` → **MyGuide**

**MyGuide Process**:
1. Query database: Match "accounting" to major codes (ACC, ACCT)
2. Found: Accounting subject with LibGuide = "Business & Accounting"
3. Call API: Search for guide
4. Get multiple librarians (Business, Accounting specialists)
5. Return: All relevant librarians

**Why MyGuide?**: Major name requires database mapping

---

### Scenario 4: Psychology Resources

**Query**: "What are the best databases for psychology research?"

**Classification**: `course_subject_help` → **LibGuide**

**LibGuide Process**:
1. Fuzzy match "psychology" to subjects
2. Call API: Get Psychology subject
3. Return librarian + subject guide

**Why LibGuide?**: Focus on databases (resources)

---

## When the Bot Might Get Confused

### Ambiguous Queries

Some queries could match either intent:

**Query**: "LibGuide for biology"

**Could be**:
- `subject_librarian`: User wants librarian for biology
- `course_subject_help`: User wants biology resources

**Current Behavior**: LLM will classify based on exact wording
- "LibGuide for biology" → Likely `course_subject_help` (LibGuide)
- "Biology librarian" → Likely `subject_librarian` (MyGuide)

**Both work!** They return similar information:
- Librarian contact
- Subject guide URL
- Resource information

---

## Improving Intent Classification

If you find the bot consistently misclassifies certain queries, you can:

### Option 1: Update Router Prompt

**File**: `src/graph/orchestrator.py` (Lines 60-64)

Add more specific examples:

```python
2. **subject_librarian** - Finding subject librarian, LibGuides for a specific major, 
   department, or academic subject
   Examples: "Who's the biology librarian?", "LibGuide for accounting", 
   "I need help with psychology research", "Contact person for business major",
   "Librarian for engineering"  # Added
```

### Option 2: Add Keywords

Add keyword detection before LLM classification:

```python
# In classify_intent_node()
query_lower = user_msg.lower()

# Strong signals for subject_librarian
if any(word in query_lower for word in ["librarian", "who is", "contact person", "major", "department"]):
    intent = "subject_librarian"
# Strong signals for course_subject_help  
elif any(word in query_lower for word in ["database", "resources for", "guide for", "help with"]):
    intent = "course_subject_help"
else:
    # Use LLM classification
    response = await llm.ainvoke(messages)
    intent = response.content.strip().lower()
```

### Option 3: Merge Both Agents

Call **both** MyGuide and LibGuide for maximum coverage:

```python
agent_mapping = {
    "subject_librarian": ["subject_librarian", "libguide"],  # Use both!
    "course_subject_help": ["libguide", "subject_librarian"],  # Use both!
}
```

**Pros**:
- More comprehensive results
- Handles ambiguous queries better

**Cons**:
- Slower (more API calls)
- Potentially duplicate information

---

## Recommendations

### Current Setup is Good! 

The current routing works well because:

1. **Clear separation of concerns**:
   - MyGuide = Finding people (librarians)
   - LibGuide = Finding resources (guides, databases)

2. **Complementary strengths**:
   - MyGuide excels at major/department mapping
   - LibGuide excels at real-time subject matching

3. **Both return similar information**:
   - If one fails, user still gets helpful response
   - Both include librarian contact + guide URL

### Potential Improvements

**Short-term** (Low effort):
1. Add more examples to router prompt for edge cases
2. Log misclassifications to identify patterns
3. Update MyGuide database quarterly

**Medium-term** (Moderate effort):
1. Add keyword detection for strong signals
2. Implement fallback: if MyGuide returns nothing, try LibGuide
3. Merge both agents for "subject_librarian" queries

**Long-term** (High effort):
1. Sync MyGuide database with LibApps API nightly
2. Unified subject lookup service
3. ML model for intent classification (if you get enough data)

---

## Testing Different Scenarios

### Test 1: Librarian Contact

**Query**: "Who is the biology librarian?"

**Expected**: MyGuide route (`subject_librarian`)

**Verify**:
```bash
# Check logs
tail -f ai-core/logs/server.log | grep "Meta Router"

# Should see:
# [Meta Router] Classified as: subject_librarian
# [Meta Router] Selected agents: subject_librarian
```

---

### Test 2: Course Resources

**Query**: "What databases for ENG 111?"

**Expected**: LibGuide route (`course_subject_help`)

**Verify**:
```bash
# Check logs
# Should see:
# [Meta Router] Classified as: course_subject_help
# [Meta Router] Selected agents: libguide, transcript_rag
```

---

### Test 3: Major Help

**Query**: "I need help with my accounting major"

**Expected**: MyGuide route (`subject_librarian`)

**Why**: "major" keyword + need "help" suggests finding a librarian

---

### Test 4: Subject Resources

**Query**: "Psychology research databases"

**Expected**: LibGuide route (`course_subject_help`)

**Why**: "databases" keyword suggests finding resources, not a person

---

## Monitoring & Analytics

### Track Intent Distribution

Add this to your analytics:

```sql
-- See which intents are most common
SELECT 
    te.toolName,
    te.agentName,
    COUNT(*) as usage_count
FROM ToolExecution te
WHERE te.agentName IN ('subject_librarian', 'libguide')
GROUP BY te.agentName, te.toolName
ORDER BY usage_count DESC;
```

### Track Routing Accuracy

Log user feedback by intent:

```sql
-- User satisfaction by routing decision
SELECT 
    c.id,
    te.agentName,
    AVG(CASE WHEN m.isPositiveRated THEN 1 ELSE 0 END) as satisfaction
FROM Conversation c
JOIN ToolExecution te ON c.id = te.conversationId
JOIN Message m ON c.id = m.conversationId
WHERE te.agentName IN ('subject_librarian', 'libguide')
GROUP BY c.id, te.agentName;
```

---

## Summary

### Key Differences

| Aspect | MyGuide | LibGuide |
|--------|---------|----------|
| **Intent** | `subject_librarian` | `course_subject_help` |
| **Focus** | Finding WHO (people) | Finding WHAT (resources) |
| **Data** | 710 subjects in database | Live API data |
| **Strength** | Major/dept mapping | Real-time subjects |
| **Query Type** | "Who's the X librarian?" | "Resources for X?" |

### When Each is Used

**MyGuide** (`subject_librarian`):
- ✅ "Who is the [subject] librarian?"
- ✅ "I need help with my [major]"
- ✅ "Contact for [department]"
- ✅ "Librarian for [regional campus]"

**LibGuide** (`course_subject_help`):
- ✅ "Databases for [subject]"
- ✅ "Guide for [course code]"
- ✅ "Resources for [class]"
- ✅ "Research help with [topic]"

### Both Systems Work Together

The beauty of this design:
1. **Complementary**: Each handles what it's best at
2. **Redundant**: Both can answer similar questions if needed
3. **Flexible**: Easy to route based on user intent
4. **Accurate**: Local database + live API = comprehensive coverage

---

## Quick Reference

**To check which system handled a query**:

```bash
# Check server logs
tail -f ai-core/logs/server.log | grep -E "(subject_librarian|libguide)"

# Look for:
# "Selected agents: subject_librarian" → MyGuide
# "Selected agents: libguide" → LibGuide
```

**To modify routing**:

Edit `src/graph/orchestrator.py`, lines 114-122:
```python
agent_mapping = {
    "subject_librarian": ["subject_librarian"],  # MyGuide
    "course_subject_help": ["libguide", "transcript_rag"],  # LibGuide
}
```

**To update router prompt**:

Edit `src/graph/orchestrator.py`, lines 48-85 (ROUTER_SYSTEM_PROMPT)

---

**Questions?** The routing logic is in `orchestrator.py` and both agents work together seamlessly! 🎯
