# Weaviate RAG Correction Pool - Using RAG to Fix Bot Mistakes

**Last Updated:** December 16, 2025  
**Version:** 3.0.0

---

## Overview

Weaviate is **NOT** used as a primary information source for the chatbot. Instead, it serves as a **correction pool** - a quality control tool that allows librarians to fix incorrect bot responses by adding corrected question-answer pairs.

### Old Approach (Version 2.x)
❌ Bot searches Weaviate for every policy/general question  
❌ RAG results mixed with Google Site Search results  
❌ Potential for outdated or conflicting information  

### New Approach (Version 3.0)
✅ Bot uses LibCal, LibGuides, Google CSE as primary sources  
✅ Weaviate contains **only** librarian-approved corrections  
✅ Used to override incorrect responses with verified answers  
✅ Quality control tool, not a search engine  

---

## When to Use the Correction Pool

### Use Cases for Adding Corrections

**1. Bot Gives Wrong Answer**
```
User: "Can I check out laptops?"
Bot: "Yes, laptops are available for 7-day checkout."
❌ WRONG - Laptops are 4-hour checkout only

→ Add correction to Weaviate with accurate policy
```

**2. Bot Misses Important Exception**
```
User: "Do faculty have borrowing limits?"
Bot: "Faculty can borrow up to 150 items."
⚠️ INCOMPLETE - Doesn't mention exceptions for emeritus faculty

→ Add correction with complete information
```

**3. Bot Can't Find Specific Policy**
```
User: "What's the policy on interlibrary loan renewals?"
Bot: "I don't have that information."
❌ Should know this

→ Add Q&A pair to correction pool
```

**4. Outdated Information**
```
Bot refers to old fine amounts or outdated policies

→ Add correction with current information
```

### When NOT to Use Correction Pool

❌ **Don't add** general information already on website  
❌ **Don't add** information that changes frequently (hours, room availability)  
❌ **Don't add** personal opinions or interpretations  
❌ **Don't add** temporary announcements  

**For these:** Update the official website instead, Google will index it.

---

## How the Correction Pool Works

### Architecture

```
User asks question
       ↓
Bot uses primary sources (LibCal, LibGuides, Google)
       ↓
Bot generates response
       ↓
[Behind the scenes: Bot checks Weaviate for corrections]
       ↓
If correction exists for this topic:
   → Use correction instead of generated answer
If no correction:
   → Use generated answer
```

### Example Workflow

**Scenario:** Bot incorrectly says laptops are 7-day checkout

**Step 1:** Librarian discovers error
```
User report: "Bot told me I could keep laptop for a week but circulation desk said 4 hours"
```

**Step 2:** Librarian creates correction
```python
# Using add_correction_to_rag.py script
Question: "Can I check out a laptop? How long?"
Answer: "Yes, laptops are available for checkout at the circulation desk. 
         Laptops have a 4-hour checkout period and cannot be renewed. 
         Please return them to the circulation desk before closing time."
Topic: "laptop_checkout_policy"
```

**Step 3:** Correction added to Weaviate
```
Record created with:
- Question embedding (vector)
- Answer text
- Metadata (topic, confidence: high, date added)
```

**Step 4:** Future queries corrected
```
Next user: "Can I borrow a laptop?"
Bot: [Checks Weaviate, finds correction]
Bot: "Yes, laptops are available for checkout at the circulation desk.
      Laptops have a 4-hour checkout period..." ✅
```

---

## Adding Corrections to Weaviate

### Prerequisites

- SSH access to server
- Python virtual environment activated
- Weaviate API key in `.env` file

### Script: `add_correction_to_rag.py`

**Location:** `/ai-core/scripts/add_correction_to_rag.py`

**Usage:**
```bash
cd /Users/qum/Documents/GitHub/chatbot/ai-core
source venv/bin/activate
python scripts/add_correction_to_rag.py
```

**Interactive Prompts:**
```
Enter the question: Can I check out a laptop?
Enter the correct answer: Laptops are available for 4-hour checkout...
Enter a topic/category: laptop_checkout_policy
Confidence level (high/medium/low): high
```

**What It Does:**
1. Takes your question-answer pair
2. Creates vector embedding for question
3. Stores in Weaviate with metadata
4. Confirms successful addition
5. Provides Weaviate record ID for tracking

### Best Practices for Corrections

**1. Write Clear Questions**
```
✅ Good: "How long can I keep a checked-out laptop?"
❌ Bad: "Laptop stuff"
```

**2. Write Complete Answers**
```
✅ Good: "Laptops have a 4-hour checkout period and must be 
         returned to the circulation desk. They cannot be renewed. 
         Available at King Library circulation desk."

❌ Bad: "4 hours"
```

**3. Use Consistent Topics**
```
✅ Good: Use "laptop_checkout_policy" for all laptop questions
❌ Bad: Mix "laptop", "checkout", "laptops", "borrowing_laptop"
```

**4. Set Appropriate Confidence**
```
high   - Official policy, well-documented
medium - Interpretation of policy, some nuance
low    - Edge case, might need human verification
```

---

## Managing Corrections

### Viewing All Corrections

**Script:** `list_rag_corrections.py`

```bash
cd ai-core
source venv/bin/activate
python scripts/list_rag_corrections.py
```

**Output:**
```
Total corrections: 23

1. ID: 8f3b2a1c-...
   Topic: laptop_checkout_policy
   Question: Can I check out a laptop?
   Confidence: high
   Added: 2025-12-16

2. ID: 7e2c1b9d-...
   Topic: interlibrary_loan_renewal
   Question: Can I renew an ILL book?
   Confidence: medium
   Added: 2025-12-15
...
```

### Testing a Correction

**Script:** `verify_correction.py`

```bash
python scripts/verify_correction.py
```

**Interactive:**
```
Enter question to test: Can I check out a laptop?

Searching Weaviate...
✅ Found correction!

Topic: laptop_checkout_policy
Confidence: high
Similarity: 0.94

Answer:
Laptops are available for 4-hour checkout at the circulation desk...
```

### Deleting a Correction

**Script:** `delete_rag_correction.py`

```bash
python scripts/delete_rag_correction.py
```

**Interactive:**
```
Enter Weaviate record ID to delete: 8f3b2a1c-...

Found record:
Topic: laptop_checkout_policy
Question: Can I check out a laptop?

Confirm deletion? (yes/no): yes
✅ Deleted successfully
```

### Clearing All Corrections (Reset)

**Script:** `weaviate_cleanup.py`

```bash
python scripts/weaviate_cleanup.py
```

**⚠️ WARNING:** This deletes ALL corrections. Use with extreme caution.

```
This will DELETE ALL records in Weaviate.
Type "DELETE ALL" to confirm: DELETE ALL

Deleting all records...
✅ Deleted 23 records
✅ Weaviate collection cleared
```

---

## Weaviate Configuration

### Connection Settings

**Environment Variables:**
```bash
WEAVIATE_URL=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=your_api_key
```

**Collection Name:** `TranscriptQA`

### Schema

```python
{
    "class": "TranscriptQA",
    "properties": [
        {
            "name": "question",
            "dataType": ["text"],
            "description": "User question"
        },
        {
            "name": "answer", 
            "dataType": ["text"],
            "description": "Correct answer"
        },
        {
            "name": "topic",
            "dataType": ["string"],
            "description": "Category/topic"
        },
        {
            "name": "confidence",
            "dataType": ["string"],
            "description": "high/medium/low"
        },
        {
            "name": "date_added",
            "dataType": ["date"],
            "description": "When correction was added"
        }
    ]
}
```

---

## Troubleshooting

### "Cannot connect to Weaviate"

**Check:**
1. Is `WEAVIATE_URL` correct in `.env`?
2. Is `WEAVIATE_API_KEY` valid?
3. Is Weaviate Cloud accessible from server?

**Test connection:**
```bash
python scripts/test_weaviate_connection.py
```

### "Record not found"

**Possible causes:**
- Wrong record ID
- Record already deleted
- Weaviate cluster reset

**Solution:** List all records to verify ID exists

### "Low similarity score"

**Meaning:** Question phrasing doesn't match correction well

**Solutions:**
1. Add more question variations
2. Use more keywords in question
3. Adjust question wording to match user queries

### Bot not using correction

**Debug steps:**
1. Verify correction exists: `python scripts/list_rag_corrections.py`
2. Test similarity: `python scripts/verify_correction.py`
3. Check bot logs for RAG query
4. Ensure confidence is set to "high"
5. Try rewording question to match user phrasing

---

## Migration Guide: Cleaning Up Old RAG Data

If you have old RAG data from Version 2.x that included general website content, you should clean it up:

### Step 1: Backup Current Data (Optional)

```bash
python scripts/export_weaviate_backup.py > weaviate_backup.json
```

### Step 2: Clear All Records

```bash
python scripts/weaviate_cleanup.py
```

Type `DELETE ALL` to confirm.

### Step 3: Add Only Corrections

Now selectively add **only** corrections for known bot mistakes. Start with:

1. Most frequently asked questions with wrong answers
2. Complex policies the bot consistently gets wrong
3. Edge cases not covered by website

**Do not** try to reload all 1,500+ Q&A pairs from old transcripts.

---

## Best Practices Summary

### ✅ DO
- Add corrections for verified incorrect bot responses
- Write complete, accurate answers with citations
- Use consistent topic categories
- Set appropriate confidence levels
- Test corrections before deploying
- Document why correction was needed

### ❌ DON'T
- Add general information (use website instead)
- Add temporary announcements
- Add unverified information
- Duplicate information already from APIs
- Add hundreds of "just in case" Q&As
- Leave old/outdated corrections

---

## Maintenance Schedule

**Weekly:**
- Review bot error reports
- Add corrections for repeated mistakes
- Test high-traffic corrections

**Monthly:**
- Audit correction pool
- Remove outdated corrections
- Update policies that have changed
- Review confidence levels

**Quarterly:**
- Full correction pool review
- Remove unused corrections
- Add seasonal FAQs (start of semester, etc.)

---

## Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `add_correction_to_rag.py` | Add new correction | Interactive |
| `list_rag_corrections.py` | View all corrections | No args |
| `verify_correction.py` | Test a correction | Interactive |
| `delete_rag_correction.py` | Remove one correction | Interactive |
| `weaviate_cleanup.py` | Clear all corrections | Requires confirmation |
| `export_weaviate_backup.py` | Backup to JSON | Stdout |
| `test_weaviate_connection.py` | Test connectivity | No args |

All scripts located in `/ai-core/scripts/`

---

## Example Correction Workflow

### Real-World Example: Fixing Laptop Checkout Policy

**1. Error Discovered**
```
Date: Dec 10, 2025
User feedback: "Bot said I could keep laptop for 7 days but it's actually 4 hours"
Bot response reviewed: Confirmed incorrect
```

**2. Correction Created**
```bash
$ python scripts/add_correction_to_rag.py

Question: How long can I check out a laptop from the library?
Answer: Laptops are available for checkout at the King Library circulation desk. 
The checkout period is 4 hours and cannot be renewed. Please return laptops 
to the circulation desk before the library closes. Contact (513) 529-4141 for 
availability.

Topic: laptop_checkout_policy
Confidence: high
```

**3. Verified**
```bash
$ python scripts/verify_correction.py

Question: Can I borrow a laptop?
✅ Found! Similarity: 0.91
Answer: Laptops are available for checkout...
```

**4. Monitored**
```
Week 1: 12 users asked about laptops - all got correct answer ✅
Week 2: 8 users - correct ✅
Month 1: 45 users - 100% accuracy ✅
```

**5. Documented**
```
Added to correction log:
ID: 8f3b2a1c-4d5e-6f7g-8h9i-0j1k2l3m4n5o
Date: 2025-12-10
Reason: Bot was using outdated 7-day policy
Impact: High - frequent question
Status: Active, verified working
```

---

**Document Version:** 3.0.0  
**Last Updated:** December 16, 2025  
**Next Review:** March 2026
