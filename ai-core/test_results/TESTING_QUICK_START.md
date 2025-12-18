# Testing Quick Start Guide

## Prerequisites

1. **Server must be running**:
   ```bash
   cd ai-core
   .venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
   ```

2. **Environment variables configured** (`.env` file with API keys)

---

## Run the Final Comprehensive Test

This is the **ultimate test suite** that covers everything:

```bash
cd ai-core
python scripts/final_comprehensive_test.py
```

**What it tests**:
- ✅ Out-of-scope research questions (should hand off to librarian)
- ✅ Out-of-scope homework/university questions (should deny gracefully)
- ✅ Library hours and room reservations
- ✅ Subject librarian queries (main campus + course codes)
- ✅ LibGuide searches
- ✅ Regional campus queries (Hamilton, Middletown)
- ✅ Library policies and locations
- ✅ Human handoff requests
- ✅ Stress testing (realistic usage patterns)

**Duration**: ~15-20 minutes (includes rate limit delays)

**Output**:
- Detailed markdown report: `test_results/FINAL_COMPREHENSIVE_TEST_[timestamp].md`
- JSON data: `test_results/final_test_results_[timestamp].json`

---

## Test Results Location

All test results are saved in: `ai-core/test_results/`

Files include:
- `FINAL_COMPREHENSIVE_TEST_*.md` - Detailed test reports
- `final_test_results_*.json` - Raw test data
- `LIBRARIAN_TESTING_INVITATION.md` - Document for subject librarian team

---

## What to Look For

### ✅ GOOD: Research Questions Handled Correctly

**User**: "I need 3 articles 19 pages or more about the effects of economy, tourism/travel, and employments from 9/11"

**Bot Should Say**: 
- "I can see you're working on a research project that requires finding specific sources..."
- "Chat with a research librarian who can help you..."
- **Should NOT** suggest specific databases or search strategies

### ❌ BAD: Bot Provides Research Guidance

**Bot Should NOT Say**:
- "Here's how you can locate scholarly articles..."
- "Choose the right databases: Business Source Complete..."
- "Construct your search using these keywords..."

---

## Quick Manual Test

Test the problematic question from the screenshot:

```bash
# In a new terminal, with server running:
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "I need 3 articles 19 pages or more that talk about the affects of economy, tourism/travel, and employments from 9/11"}'
```

**Expected Response**: Should hand off to librarian, NOT provide database recommendations.

---

## Interpreting Results

### Success Rate Targets

- **95%+**: Production ready ✅
- **85-94%**: Mostly ready, review failures ⚠️
- **<85%**: Needs work ❌

### Response Time Targets

- **<3s**: Excellent ✅
- **3-5s**: Good ⚠️
- **>5s**: Needs optimization ❌

### Handoff Rate (Out-of-Scope Questions)

- **90%+**: Excellent - bot recognizes limitations ✅
- **70-89%**: Good but could improve ⚠️
- **<70%**: Bot is overconfident ❌

---

## Troubleshooting

### Server Not Responding

```bash
# Check if server is running
curl http://localhost:8000/health

# If not, start it:
cd ai-core
.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
```

### 429 Rate Limit Errors

The test suite includes delays to prevent this. If you still see 429 errors:
- Increase `DELAY_BETWEEN_REQUESTS` in the test script
- Wait a few minutes before re-running

### Import Errors

```bash
# Make sure you're in the right directory
cd ai-core

# Activate virtual environment if needed
source .venv/bin/activate  # or: source venv/bin/activate
```

---

## Next Steps After Testing

1. **Review the generated report** in `test_results/`
2. **Check for failures** - especially in out-of-scope handling
3. **Share results** with the team
4. **Invite subject librarian** for final testing using `LIBRARIAN_TESTING_INVITATION.md`

---

## Contact

Questions? Issues? Contact the development team.

**This is your FINAL test before production. Make it count!** 🚀
