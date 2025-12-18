# Targeted Test Report: Subject Librarian & LibGuide Queries

**Date**: 2025-12-18 10:26:49
**Purpose**: Verify connection pool fix for Subject Librarian and LibGuide failures

## 📊 Summary

| Metric | Value |
|--------|-------|
| Total Questions | 28 |
| Successful | 23 (82.1%) |
| Failed | 5 (17.9%) |

## 📋 Results by Category

### 3_SUBJECT_LIBRARIANS

**Success Rate**: 13/15 (86.7%) ⚠️

- ✅ Q1: Who is the biology librarian?
- ✅ Q2: I need help with my English paper
- ✅ Q3: Psychology department librarian contact
- ✅ Q4: Who can help me with chemistry research?
- ✅ Q5: Business librarian email
- ✅ Q6: History subject librarian
- ✅ Q7: I'm taking ENG 111, who is my librarian?
- ✅ Q8: PSY 201 librarian contact
- ✅ Q9: Who helps with BIO courses?
- ✅ Q10: Music librarian at Miami
- ✅ Q11: Art history research help
- ❌ Q12: Political science librarian
  - Error: Request timed out
- ❌ Q13: Who is the librarian at Hamilton campus?
  - Error: Request timed out
- ✅ Q14: Middletown campus librarian contact
- ✅ Q15: I'm a nursing major, who is my librarian?

### 4_LIBGUIDE_SEARCHES

**Success Rate**: 8/10 (80.0%) ⚠️

- ❌ Q1: Research guide for biology
  - Error: Request timed out
- ✅ Q2: Find guide for ENG 111
- ✅ Q3: Psychology research resources
- ✅ Q4: Business LibGuide
- ✅ Q5: Chemistry research guide
- ✅ Q6: History primary sources guide
- ✅ Q7: Where can I find nursing resources?
- ❌ Q8: Political science databases
  - Error: Request timed out
- ✅ Q9: Art history research guide
- ✅ Q10: Music research resources

### 9_REGIONAL_CAMPUS

**Success Rate**: 2/3 (66.7%) ❌

- ❌ Q1: Who is the librarian at Rentschler Library?
  - Error: Request timed out
- ✅ Q2: Hamilton campus library contact
- ✅ Q3: Middletown campus research help

## ❌ Failure Details

### Political science librarian
- Category: 3_SUBJECT_LIBRARIANS
- Status: TIMEOUT
- Error: Request timed out

### Who is the librarian at Hamilton campus?
- Category: 3_SUBJECT_LIBRARIANS
- Status: TIMEOUT
- Error: Request timed out

### Research guide for biology
- Category: 4_LIBGUIDE_SEARCHES
- Status: TIMEOUT
- Error: Request timed out

### Political science databases
- Category: 4_LIBGUIDE_SEARCHES
- Status: TIMEOUT
- Error: Request timed out

### Who is the librarian at Rentschler Library?
- Category: 9_REGIONAL_CAMPUS
- Status: TIMEOUT
- Error: Request timed out

## 🎯 Conclusion

**❌ ISSUES REMAIN (82.1%)**

Further investigation needed. Check:
- Database connection status
- Prisma client singleton implementation
- Server logs for errors
