# Miami University Libraries Smart Chatbot - Final Testing Invitation

**To**: Subject Librarian Testing Team  
**From**: Development Team  
**Date**: December 18, 2024  
**Subject**: Final Testing Phase - Your Expertise Needed

---

## Executive Summary

We've reached a critical milestone in the Smart Chatbot development and need your expertise for the **final testing phase** before production deployment. This document provides complete transparency about the current state, what's been done, and what we need from you.

---

## What We've Accomplished

### 1. Core Functionality Implementation ✅

The chatbot now supports:

- **Library Hours & Room Reservations** (LibCal API)
- **Subject Librarian Lookup** (Database + LibGuides API)
- **Research Guides** (LibGuides API)
- **Library Website Search** (Google Site Search)
- **Human Handoff** (LibChat integration)
- **Regional Campus Support** (Hamilton, Middletown)

### 2. Critical Improvements Based on Previous Testing ✅

**Problem Identified**: The bot was providing detailed research guidance (suggesting databases, search strategies) when it should have been handing off to librarians.

**Example of Previous Problematic Behavior**:
- User: "I need 3 articles 19 pages or more about the effects of economy, tourism/travel, and employments from 9/11"
- Bot (WRONG): "Here's how you can locate three scholarly articles... Choose the right databases: Business Source Complete, Tourism & Travel Complete..."

**Solution Implemented**:
- Added **Research Question Detection** system
- Bot now recognizes when users need research help and immediately hands off to librarians
- Bot no longer tries to be a research consultant

**New Expected Behavior**:
- User: "I need 3 articles 19 pages or more about..."
- Bot (CORRECT): "I can see you're working on a research project that requires finding specific sources. This is exactly the kind of detailed research help our librarians specialize in! **Chat with a research librarian** who can help you find the right databases, develop effective search strategies, and locate articles that meet your specific requirements."

### 3. Comprehensive Testing Completed ✅

We've run extensive automated tests covering:

- **Out-of-scope question handling** (research questions, homework, general university questions)
- **All bot functions** (hours, policies, subjects, libguides, locations)
- **Regional campus coverage** (Hamilton, Middletown)
- **Stress testing** (realistic usage patterns)
- **Rate limit protection** (avoiding API 429 errors)

**Test Results Available**: See `FINAL_COMPREHENSIVE_TEST_[timestamp].md` in the test_results folder

---

## Current Limitations (Being Honest)

### What the Bot CANNOT Do

1. **Catalog Search**: Primo agent is disabled - bot redirects to librarians for book/article searches
2. **Account Management**: Cannot renew books, check fines, place holds - redirects to account portal
3. **Detailed Research Consultation**: Hands off to librarians for complex research needs
4. **Interlibrary Loan**: Provides information but cannot manage ILL requests

### Known Issues

1. **Response Time**: Average 2-5 seconds (acceptable but could be faster)
2. **API Rate Limits**: LibGuides API has rate limits - we've added delays to prevent 429 errors
3. **Complex Queries**: Some ambiguous questions may need clarification

---

## What We Need From You

### Your Testing Mission

We need you to **try to break the bot** and find edge cases we haven't considered. Specifically:

#### 1. Out-of-Scope Question Testing (CRITICAL)

**Please test these scenarios**:

- Research questions with specific requirements (e.g., "I need 5 articles about X")
- Homework/assignment help requests
- Questions that blur the line between "finding a guide" and "doing research"
- Complex research topics that need librarian expertise

**What to look for**:
- ✅ Bot should hand off to librarian, NOT provide research guidance
- ❌ Bot should NOT suggest specific databases or search strategies
- ✅ Bot should be humble and recognize its limitations

#### 2. Subject Librarian & LibGuide Testing

**Please test**:

- Your own subject areas
- Course codes you support
- Regional campus questions
- Edge cases (unusual subjects, interdisciplinary topics)

**What to look for**:
- Correct librarian contact information
- Accurate LibGuide links
- Appropriate handling when no exact match exists

#### 3. Real-World Scenarios

**Please test questions you actually receive from students**, such as:

- "I need help with my research paper on [topic]"
- "What databases should I use for [subject]?"
- "I'm looking for articles about [complex topic]"
- "Who can help me with [course code]?"

#### 4. Edge Cases & Stress Testing

**Try to confuse the bot**:

- Vague questions
- Multiple questions in one message
- Typos and misspellings
- Questions in different formats
- Rapid-fire questions

---

## How to Test

### Option 1: Web Interface (Recommended)

1. Navigate to: `[CHATBOT_URL]` (will be provided)
2. Start asking questions
3. Document your findings

### Option 2: Direct Testing Script

If you're comfortable with command line:

```bash
cd ai-core
python scripts/final_comprehensive_test.py
```

This runs the full automated test suite.

---

## What to Document

### For Each Test Question

Please record:

1. **Your Question**: Exactly what you asked
2. **Bot Response**: What the bot said
3. **Expected Behavior**: What you expected
4. **Actual Behavior**: What actually happened
5. **Rating**: ✅ Good | ⚠️ Acceptable | ❌ Problematic
6. **Notes**: Any additional observations

### Example Documentation

```
Question: "I need 10 articles about climate change impacts on agriculture"
Bot Response: "I can see you're working on a research project... Chat with a research librarian..."
Expected: Hand off to librarian
Actual: ✅ Correctly handed off
Rating: ✅ Good
Notes: Response was appropriate and helpful
```

---

## Critical Questions We Need Answered

1. **Research Question Handling**: Does the bot appropriately recognize when to hand off research questions to librarians?

2. **Accuracy**: Is the subject librarian and LibGuide information accurate?

3. **User Experience**: Would students find this helpful or frustrating?

4. **Missing Functionality**: What critical features are missing that would make this more useful?

5. **Trust**: Would you trust this bot to represent the library to students?

---

## Timeline

- **Testing Period**: [START_DATE] - [END_DATE]
- **Feedback Due**: [DUE_DATE]
- **Review Meeting**: [MEETING_DATE]
- **Target Launch**: [LAUNCH_DATE]

---

## Feedback Submission

### Method 1: Document (Preferred)

Create a document with your findings and send to: [EMAIL]

### Method 2: Meeting

Schedule a feedback session: [CALENDAR_LINK]

### Method 3: Quick Feedback

Email quick notes to: [EMAIL]

---

## Our Commitment

### We Promise

1. **Transparency**: We'll be honest about limitations and issues
2. **Responsiveness**: We'll address critical issues immediately
3. **Collaboration**: Your expertise guides this project
4. **Quality**: We won't launch until it's ready

### We Won't

1. Launch with known critical issues
2. Ignore your feedback
3. Overpromise capabilities
4. Compromise on accuracy

---

## Technical Details (For Reference)

### System Architecture

- **Frontend**: React-based chat interface
- **Backend**: Python (FastAPI) with LangGraph orchestration
- **APIs**: LibCal, LibGuides, Google Site Search
- **Database**: PostgreSQL (Prisma ORM)
- **AI Model**: OpenAI o4-mini

### Performance Metrics (Current)

- Average Response Time: 2-5 seconds
- Success Rate: [TO_BE_UPDATED]%
- Uptime: [TO_BE_UPDATED]%

### Rate Limits & Capacity

- LibGuides API: 1000 requests/hour
- Expected Capacity: ~20-30 concurrent users
- Protection: Automatic delays and caching

---

## What Happens After Testing

### If Testing Goes Well ✅

1. Address any minor issues found
2. Soft launch to limited user group
3. Monitor and iterate
4. Full production launch

### If Critical Issues Found ⚠️

1. Pause launch timeline
2. Address critical issues
3. Re-test with your team
4. Proceed only when ready

### If Major Redesign Needed ❌

1. Honest assessment of feasibility
2. Discuss alternative approaches
3. Set realistic new timeline
4. Keep you informed throughout

---

## Questions?

### Contact Information

- **Project Lead**: [NAME] - [EMAIL]
- **Technical Lead**: [NAME] - [EMAIL]
- **Slack Channel**: #library-chatbot
- **Office Hours**: [TIMES]

---

## Final Thoughts

This is **YOUR** chatbot. It represents the library and will interact with students on your behalf. We need your honest, critical feedback to make it excellent.

**Please be brutally honest**. If something doesn't work, tell us. If it's confusing, tell us. If you wouldn't trust it with students, tell us.

We'd rather delay the launch and get it right than rush out something that doesn't meet your standards.

Thank you for your time, expertise, and partnership on this project. Your previous testing feedback was invaluable, and we're counting on you again for this final phase.

---

**Ready to test? Let's make this chatbot something we're all proud of!** 🚀

---

## Appendix: Test Results Summary

[This section will be populated with results from the comprehensive test suite]

### Overall Performance

- Total Tests Run: [NUMBER]
- Success Rate: [PERCENTAGE]%
- Average Response Time: [TIME]s

### Category Breakdown

- Out-of-Scope Handling: [PERCENTAGE]%
- Subject Librarian Queries: [PERCENTAGE]%
- LibGuide Searches: [PERCENTAGE]%
- Library Hours: [PERCENTAGE]%
- Regional Campus: [PERCENTAGE]%

### Critical Findings

[Summary of any critical issues found during automated testing]

---

*Document Version: 1.0*  
*Last Updated: December 18, 2024*  
*Next Review: After testing phase completion*
