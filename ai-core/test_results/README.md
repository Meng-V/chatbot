# Test Results Directory

This directory contains all testing results and documentation for the Miami University Libraries Smart Chatbot.

---

## 📁 Directory Contents

### Test Reports
- `FINAL_COMPREHENSIVE_TEST_*.md` - Comprehensive test reports with detailed analytics
- `final_test_results_*.json` - Raw test data in JSON format
- `TARGETED_TEST_REPORT_*.md` - Targeted tests for specific functionality
- `targeted_test_results_*.json` - Targeted test data

### Documentation
- `LIBRARIAN_TESTING_INVITATION.md` - Invitation and guide for subject librarian testing
- `TESTING_QUICK_START.md` - Quick start guide for running tests
- `README.md` - This file

---

## 🚀 Quick Start

### Run the Final Comprehensive Test

```bash
cd ai-core
python scripts/final_comprehensive_test.py
```

This runs **ALL** tests including:
- Out-of-scope question handling
- All bot functions
- Regional campus coverage
- Stress testing
- Rate limit protection

**See**: `TESTING_QUICK_START.md` for detailed instructions

---

## 📊 Test Coverage

### 1. Out-of-Scope Questions ✅
- Research questions requiring librarian expertise
- Homework/assignment help requests
- General university questions

**Expected**: Bot should gracefully deny and hand off to appropriate service

### 2. Core Bot Functions ✅
- Library hours (LibCal API)
- Room reservations (LibCal API)
- Subject librarian lookup (Database + LibGuides)
- LibGuide searches (LibGuides API)
- Library policies (Google Site Search)
- Library locations and addresses

**Expected**: Accurate, helpful responses

### 3. Regional Campus Support ✅
- Hamilton campus (Rentschler Library)
- Middletown campus (Gardner-Harvey Library)

**Expected**: Correct regional campus information

### 4. Stress Testing ✅
- Rapid-fire questions
- Complex multi-turn conversations
- Realistic usage patterns

**Expected**: Graceful handling under load

---

## 🎯 Success Criteria

### Overall Success Rate
- **95%+**: Production ready ✅
- **85-94%**: Mostly ready ⚠️
- **<85%**: Needs work ❌

### Response Time
- **<3s**: Excellent ✅
- **3-5s**: Good ⚠️
- **>5s**: Needs optimization ❌

### Out-of-Scope Handoff Rate
- **90%+**: Excellent ✅
- **70-89%**: Good ⚠️
- **<70%**: Bot is overconfident ❌

---

## 🔍 Critical Test: Research Question Handling

**THE PROBLEM** (from screenshot):
```
User: "I need 3 articles 19 pages or more that talk about the affects 
       of economy, tourism/travel, and employments from 9/11"

Bot (WRONG): "Here's how you can locate three scholarly articles...
              Choose the right databases: Business Source Complete..."
```

**THE FIX**:
- Added research question detection system
- Bot now recognizes detailed research requests
- Bot hands off to librarians instead of providing guidance

**EXPECTED BEHAVIOR**:
```
Bot (CORRECT): "I can see you're working on a research project that 
                requires finding specific sources. This is exactly the 
                kind of detailed research help our librarians specialize in!
                
                Chat with a research librarian who can help you:
                - Find the right databases for your topic
                - Develop effective search strategies
                - Locate articles that meet your specific requirements
                
                Get help now: [contact information]"
```

---

## 📈 Understanding Test Reports

### Report Sections

1. **Executive Summary**: Overall pass/fail rates and performance metrics
2. **Test Coverage**: Breakdown by category
3. **Agent Usage Statistics**: Which agents were called and how often
4. **Critical Findings**: Important issues discovered
5. **Recommendations**: What to do next
6. **Extreme Conditions**: How to handle high load, API limits, etc.
7. **Detailed Test Results**: Sample responses for each category

### Key Metrics to Watch

- **Success Rate**: Percentage of tests that passed
- **Average Response Time**: How fast the bot responds
- **Handoff Rate**: How often bot correctly hands off to humans
- **Agent Usage**: Which agents are being used most

---

## 🚨 What to Do If Tests Fail

### High Failure Rate (>15%)

1. Review failed test cases in the report
2. Check server logs for errors
3. Verify API keys and database connections
4. Re-run tests after fixes

### Timeouts

1. Check server performance
2. Review database query efficiency
3. Check API response times
4. Consider increasing timeout values

### Out-of-Scope Handling Issues

1. Review `research_question_detection.py`
2. Check orchestrator routing logic
3. Test manually with problematic questions
4. Adjust detection patterns if needed

---

## 📝 Next Steps After Testing

### If Tests Pass (95%+)

1. ✅ Review the comprehensive report
2. ✅ Share results with team
3. ✅ Invite subject librarian for final testing
4. ✅ Prepare for soft launch

### If Tests Mostly Pass (85-94%)

1. ⚠️ Review failed test cases
2. ⚠️ Fix critical issues
3. ⚠️ Re-run tests
4. ⚠️ Proceed with caution

### If Tests Fail (<85%)

1. ❌ DO NOT proceed to production
2. ❌ Identify root causes
3. ❌ Fix all critical issues
4. ❌ Re-run comprehensive tests

---

## 👥 Subject Librarian Testing

After automated tests pass, invite subject librarians for final testing:

**See**: `LIBRARIAN_TESTING_INVITATION.md`

This document includes:
- What we've accomplished
- Current limitations (being honest)
- What we need from them
- How to test
- What to document
- Timeline and feedback process

---

## 🛠️ Troubleshooting

### Server Not Running

```bash
cd ai-core
.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
```

### Import Errors

```bash
cd ai-core
source .venv/bin/activate  # or: source venv/bin/activate
```

### Rate Limit Errors (429)

- Tests include delays to prevent this
- If still occurring, increase `DELAY_BETWEEN_REQUESTS` in test script
- Wait a few minutes before re-running

### Database Connection Issues

- Check `.env` file for correct DATABASE_URL
- Verify database is running
- Check Prisma client is generated

---

## 📞 Support

Questions or issues? Contact the development team.

---

## 🎯 Final Checklist Before Production

- [ ] Comprehensive tests pass (95%+)
- [ ] Out-of-scope questions handled correctly
- [ ] Subject librarian information accurate
- [ ] Regional campus support working
- [ ] Response times acceptable (<5s avg)
- [ ] Subject librarian testing completed
- [ ] Feedback addressed
- [ ] Documentation complete
- [ ] Monitoring set up
- [ ] Rollback plan ready

---

**This is your FINAL test. Make it comprehensive. Make it thorough. Make it count.** 🚀

---

*Last Updated: December 18, 2024*
