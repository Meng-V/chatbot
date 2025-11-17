# Knowledge Management: Training Your AI Chatbot

**A practical guide for correcting AI responses and updating chatbot knowledge**

---

## 📚 Overview

Your AI chatbot learns from three sources:
1. **Vector Database (Weaviate)** - Factual knowledge about your library
2. **System Prompts** - Instructions for behavior and formatting
3. **Few-Shot Examples** - Demonstration of correct responses

When the AI makes a mistake, you can correct it by updating the appropriate source.

---

## 🎯 Three Ways to Update AI Knowledge

### **Method 1: Vector Database (Weaviate) - For Facts & Documentation**

**Best for:** Library policies, procedures, FAQs, historical information, detailed guides

**When to use:**
- ❌ AI gives wrong hours or contact information
- ❌ AI doesn't know about a new service or policy
- ❌ AI provides outdated information

**How it works:** Your documents are chunked, embedded, and stored in Weaviate. When users ask questions, the Transcript RAG agent retrieves relevant information.

#### **Step-by-Step: Add New Knowledge**

**1. Create your knowledge document:**

```bash
cd ai-core/data
nano library_policies.md
```

Example content:
```markdown
# Library Borrowing Policies

## Student Borrowing
Students can borrow up to 50 books for 16 weeks.

## Faculty Borrowing
Faculty can borrow up to 150 books for 16 weeks.

## Renewal Policy
Books can be renewed 3 times online unless they are on hold by another patron.

## Late Fees
- Regular books: $0.25 per day
- Reserve items: $1.00 per hour
- Maximum fine: $10.00 per item

## Contact for Questions
Visit https://www.lib.miamioh.edu/research/research-support/ask/
```

**2. Convert to JSON format:**

The ingestion script expects JSON format:
```json
[
  {
    "question": "What is the borrowing limit for students?",
    "answer": "Students can borrow up to 50 books for 16 weeks.",
    "topic": "borrowing_policy",
    "source": "library_policies"
  },
  {
    "question": "How many times can I renew a book?",
    "answer": "Books can be renewed 3 times online unless they are on hold by another patron.",
    "topic": "renewals",
    "source": "library_policies"
  },
  {
    "question": "What are the late fees?",
    "answer": "Regular books are $0.25 per day, reserve items are $1.00 per hour, with a maximum fine of $10.00 per item.",
    "topic": "late_fees",
    "source": "library_policies"
  }
]
```

**3. Save to data directory:**
```bash
# Save as JSON file
cd ai-core/data
nano new_knowledge.json
# Paste your JSON content and save
```

**4. Ingest into Weaviate:**
```bash
cd ai-core
source .venv/bin/activate

# Ingest specific file
TRANSCRIPTS_PATH=/path/to/new_knowledge.json python scripts/ingest_transcripts.py

# Or place in default location
mv new_knowledge.json data/transcripts_clean.json
python scripts/ingest_transcripts.py
```

**5. Test the update:**
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the borrowing limit for students?"}'
```

#### **Tips for Weaviate Knowledge:**
- ✅ Write in Q&A format for best retrieval
- ✅ Include common variations of questions
- ✅ Be specific and factual
- ✅ Include sources and dates for policies
- ✅ Update regularly (quarterly recommended)

---

### **Method 2: System Prompts - For Behavior & Formatting**

**Best for:** Response style, specific instructions, contact methods, formatting rules

**When to use:**
- ❌ AI has correct info but formats it poorly
- ❌ AI doesn't follow specific procedures
- ❌ AI gives wrong contact methods
- ❌ AI tone is inappropriate

**Where to edit:** Two files need updates for consistency

#### **File 1: LangGraph Mode (Complex Queries)**

```bash
nano ai-core/src/graph/orchestrator.py
```

**Find the synthesis_prompt section (around line 186-202):**

```python
synthesis_prompt = f"""You are a helpful Miami University Libraries assistant.

User question: {user_msg}

Information from library systems:
{context}

FORMATTING GUIDELINES:
- Use **bold** for key information (names, times, locations, important terms)
- Keep responses compact - avoid excessive line breaks
- Use bullet points (•) for short lists, not numbered lists
- Provide specific details (exact times, room numbers, URLs)
- Always include next steps or actions the user can take

CRITICAL KNOWLEDGE - ALWAYS FOLLOW:
- NEVER suggest emailing library@miamioh.edu (this email doesn't exist)
- ALWAYS direct users to Ask a Librarian: https://www.lib.miamioh.edu/research/research-support/ask/
- King Library is the main library on Oxford campus
- Operating hours vary by semester - always check current hours via LibCal
- [ADD YOUR CORRECTIONS HERE]

CONTACT INFORMATION:
- Ask a Librarian: https://www.lib.miamioh.edu/research/research-support/ask/
- Web Services (technical issues): libwebservices@miamioh.edu
- [ADD OTHER CONTACTS]

Provide a clear, helpful answer based on the information above."""
```

#### **File 2: Function Calling Mode (Simple Queries)**

```bash
nano ai-core/src/graph/function_calling.py
```

**Find the system_message section (around line 181-193):**

```python
system_message = """You are a helpful Miami University Libraries assistant.
You have access to several tools to help users. Use the appropriate tool based on the user's question.

FORMATTING GUIDELINES:
- Use **bold** for key information (names, times, locations)
- Keep responses compact and scannable
- Always include actionable next steps

CRITICAL KNOWLEDGE - ALWAYS FOLLOW:
- NEVER suggest emailing library@miamioh.edu (this email doesn't exist)
- ALWAYS direct users to Ask a Librarian: https://www.lib.miamioh.edu/research/research-support/ask/
- [ADD YOUR CORRECTIONS HERE]

CONTACT INFORMATION:
- Ask a Librarian: https://www.lib.miamioh.edu/research/research-support/ask/
- Web Services: libwebservices@miamioh.edu

Always provide clear, helpful responses and cite sources when relevant."""
```

#### **After editing prompts:**

```bash
# Restart backend to load changes
cd ai-core
# If using --reload flag, changes apply automatically
# Otherwise, restart manually:
# Kill the process and restart with:
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload
```

---

### **Method 3: Few-Shot Examples - For Specific Patterns**

**Best for:** Teaching AI specific response patterns, handling edge cases

**When to use:**
- ❌ AI consistently makes the same type of mistake
- ❌ AI doesn't understand a specific query type
- ❌ You want to show exact format for responses

**Where to add:** In the same prompt files as Method 2

#### **Example Addition:**

```python
# Add to orchestrator.py or function_calling.py

system_message = """You are a helpful Miami University Libraries assistant.

EXAMPLE CONVERSATIONS - Follow these patterns:

Example 1: Contact Questions
User: "How do I contact a librarian?"
Assistant: "You can **connect with a librarian** in several ways:
• Visit our **Ask a Librarian** form: https://www.lib.miamioh.edu/research/research-support/ask/
• Use the **chat widget** on our website during business hours
• Visit any **library service desk** in person
Which method works best for you?"

Example 2: Hours Questions
User: "When does King Library close?"
Assistant: "**King Library** closes at **11:00 PM today** (Monday). 
Hours vary by day and semester. Would you like hours for:
• The rest of this week
• A specific date
• A different campus location?"

Example 3: Room Booking
User: "I need to book a study room"
Assistant: "I can help you **find and book study rooms**! 
**Quick questions:**
• Which campus? (Oxford/Hamilton/Middletown)
• Which building? (King Library/Art Library/etc.)
• How many people?
• Date and time needed?"

[ADD MORE EXAMPLES FOR YOUR COMMON SCENARIOS]

Now answer the user's question following these examples:"""
```

---

## 🔄 Correction Workflow

When AI makes a mistake, follow this process:

### **Step 1: Identify the Error Type**

| Error Type | Solution | Priority |
|------------|----------|----------|
| Wrong fact (hours, policy, contact) | Update **Weaviate** (#1) | High |
| Wrong behavior (format, tone) | Update **System Prompts** (#2) | High |
| Wrong procedure (steps, process) | Add **Few-Shot Example** (#3) | Medium |
| Missing knowledge (new service) | Update **Weaviate** (#1) | High |
| Incorrect contact method | Update **System Prompts** (#2) | Critical |

### **Step 2: Make the Correction**

```bash
# For Weaviate updates
cd ai-core
source .venv/bin/activate
python scripts/ingest_transcripts.py

# For prompt updates
nano ai-core/src/graph/orchestrator.py
nano ai-core/src/graph/function_calling.py
# Make edits, save, restart backend
```

### **Step 3: Test the Fix**

```bash
# Test with the exact query that failed
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"YOUR TEST QUESTION"}'

# Or test via frontend
open http://localhost:5173/smartchatbot
```

### **Step 4: Document the Change**

Keep a log of corrections:
```bash
nano ai-core/CORRECTION_LOG.md
```

Example entry:
```markdown
## 2024-11-10: Contact Method Correction
**Problem:** AI suggested library@miamioh.edu email
**Solution:** Updated system prompts in orchestrator.py and function_calling.py
**Files changed:** 
- ai-core/src/graph/orchestrator.py (line 195)
- ai-core/src/graph/function_calling.py (line 186)
**Tested:** ✅ Verified with "How do I contact a librarian?"
```

---

## 📊 Recommended Update Schedule

### **Regular Maintenance**

- **Weekly:** Check for new mistakes reported by users
- **Monthly:** Review conversation logs for patterns
- **Quarterly:** Update Weaviate with policy changes
- **Semester Start:** Update hours, room availability, semester-specific info

### **Priority Updates**

Update **immediately** for:
- ❗ Contact information changes
- ❗ Emergency closures or policy changes
- ❗ New services or locations
- ❗ Security or safety information

Update **within a week** for:
- ⚠️ Minor policy changes
- ⚠️ Formatting improvements
- ⚠️ New FAQ patterns

---

## 🎯 Practical Examples

### **Example 1: Correct Contact Information**

**Problem:** AI suggested non-existent email address

**Solution:**
```python
# File: ai-core/src/graph/orchestrator.py
# File: ai-core/src/graph/function_calling.py

CRITICAL KNOWLEDGE - ALWAYS FOLLOW:
- NEVER suggest emailing library@miamioh.edu (this email doesn't exist)
- ALWAYS direct users to: https://www.lib.miamioh.edu/research/research-support/ask/
- For technical issues, use: libwebservices@miamioh.edu
```

### **Example 2: Add New Service Information**

**Problem:** AI doesn't know about new 3D printing service

**Solution:** Add to Weaviate
```json
[
  {
    "question": "Do you have 3D printing?",
    "answer": "Yes! We offer 3D printing services at King Library. Located on the 2nd floor in the Makerspace. Cost is $0.10 per gram. Bring your STL file or we can help you design. Email makerspace@miamioh.edu to schedule.",
    "topic": "services",
    "source": "makerspace_services"
  },
  {
    "question": "How much does 3D printing cost?",
    "answer": "3D printing costs $0.10 per gram. We'll provide an estimate before printing. Payment accepted via student account or credit card.",
    "topic": "services",
    "source": "makerspace_services"
  }
]
```

### **Example 3: Improve Response Format**

**Problem:** AI gives too much information in one paragraph

**Solution:** Add formatting instruction
```python
FORMATTING GUIDELINES:
- Keep paragraphs to 2-3 sentences maximum
- Use bullet points for lists of 3+ items
- Put most important information first
- End with a clear call-to-action or next step
```

---

## 🛠️ Tools & Scripts

### **Check What's in Weaviate**

```python
# Create: ai-core/scripts/check_weaviate.py
import weaviate
import os

client = weaviate.Client(
    url=f"https://{os.getenv('WEAVIATE_HOST')}",
    auth_client_secret=weaviate.AuthApiKey(os.getenv('WEAVIATE_API_KEY'))
)

collection = client.collections.get("TranscriptQA")
result = collection.query.fetch_objects(limit=10)

for obj in result.objects:
    print(f"Q: {obj.properties['question']}")
    print(f"A: {obj.properties['answer']}")
    print(f"Topic: {obj.properties['topic']}\n")
```

### **Test Specific Agent**

```bash
# Test Transcript RAG agent directly
cd ai-core
source .venv/bin/activate
python -c "
from src.agents.transcript_rag_agent import transcript_rag_agent
import asyncio

async def test():
    state = {'user_message': 'What are the late fees?'}
    result = await transcript_rag_agent(state)
    print(result)

asyncio.run(test())
"
```

---

## 📝 Quick Reference Checklist

**When AI gives wrong answer:**

- [ ] Identify error type (fact vs behavior vs pattern)
- [ ] Choose correction method:
  - [ ] Weaviate for facts
  - [ ] System prompts for behavior
  - [ ] Few-shot for patterns
- [ ] Make the update
- [ ] Restart backend (if prompt change)
- [ ] Test with original failing query
- [ ] Document in correction log
- [ ] Monitor for recurrence

---

## 🔐 Best Practices

### **Do's:**
- ✅ Update both orchestrator.py AND function_calling.py for consistency
- ✅ Test changes before deploying to production
- ✅ Keep a log of all corrections
- ✅ Use specific, clear language in prompts
- ✅ Include examples in few-shot demonstrations
- ✅ Update Weaviate quarterly with policy changes

### **Don'ts:**
- ❌ Don't make prompts too long (LLM has token limits)
- ❌ Don't use contradictory instructions
- ❌ Don't forget to restart backend after prompt changes
- ❌ Don't assume one fix solves all similar issues
- ❌ Don't overload Weaviate with redundant information

---

## 📞 Support

If you need help with knowledge updates:
- **Technical issues:** libwebservices@miamioh.edu
- **Content questions:** Library administration
- **System bugs:** GitHub Issues

---

## 📚 Additional Resources

- **Developer Guide:** See `DEVELOPER_GUIDE.md` for technical setup
- **System Architecture:** See `README.md` for overview
- **Weaviate Docs:** https://weaviate.io/developers/weaviate
- **LangGraph Docs:** https://langchain-ai.github.io/langgraph/

---

**Keep your AI chatbot accurate and helpful with regular knowledge updates!**

**Version 2.0 | Last Updated: November 2025**
