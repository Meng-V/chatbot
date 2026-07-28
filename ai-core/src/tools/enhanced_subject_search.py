"""
Enhanced Subject Search with Course Code and Fuzzy Matching

Supports:
- Course codes: "ENG 111", "PSY 201", "BIO"
- Department codes: "bio", "eng", "psy"
- Major codes: "ASBI", "BU01"
- Natural language: "biology", "english", "psychology"
- Fuzzy matching for typos: "biologee" -> "biology"
"""

import re
from typing import List

from src.tools.subject_aliases import COURSE_CODE_SUBJECTS


def extract_course_codes(query: str) -> List[str]:
    """
    Extract course codes from query.
    
    Patterns:
    - "ENG 111" -> ["ENG", "ENG111", "ENG 111"]
    - "PSY201" -> ["PSY", "PSY201"]
    - "BIO" -> ["BIO"] (only if followed by numbers or end of word)
    """
    codes = []
    
    # Pattern: 2-4 UPPERCASE letters followed by 3-4 digits (with optional space)
    # Must have digits to be considered a course code
    pattern = r'\b([A-Z]{2,4})\s*(\d{3,4})\b'
    matches = re.findall(pattern, query.upper())
    
    for dept, num in matches:
        codes.append(dept)
        codes.append(f"{dept}{num}")
        codes.append(f"{dept} {num}")
    
    # Also check for standalone department codes (2-4 uppercase letters)
    # But only if they look like real course codes (common departments)
    standalone_pattern = r'\b([A-Z]{2,4})\b'
    standalone_matches = re.findall(standalone_pattern, query.upper())
    
    # Common department codes to include
    valid_depts = {'ENG', 'BIO', 'PSY', 'CHM', 'MTH', 'HIS', 'ART', 'MUS', 'BUS', 'NUR', 'CSE', 'PHY', 'ECO', 'SOC', 'POL'}
    
    for match in standalone_matches:
        if match in valid_depts and match not in codes:
            codes.append(match)
    
    return codes


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings (0-1)."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def extract_keywords(query: str) -> List[str]:
    """Extract potential subject keywords from query."""
    # Remove common words
    stop_words = {
        'i', 'need', 'help', 'with', 'my', 'for', 'the', 'a', 'an',
        'who', 'is', 'can', 'find', 'librarian', 'subject', 'class',
        'course', 'major', 'department'
    }
    
    words = re.findall(r'\b[a-z]{3,}\b', query.lower())
    keywords = [w for w in words if w not in stop_words]
    
    return keywords


# ---------------------------------------------------------------------------
# REMOVED 2026-07-28 -- a whole second implementation of subject search.
#
# detect_campus, search_by_course_code, search_by_fuzzy_match,
# search_by_alias, search_by_partial_match, search_subject,
# search_librarian_directly, get_subject_librarians and
# get_subject_libguides had ZERO consumers outside this file: the serving
# path resolves subjects through src/eval/real_backends.lookup_librarian
# (LibGuides API + Postgres) instead. They also held a SECOND copy of the
# "which librarian covers what" mapping and a second name-matching
# heuristic with the same substring flaw that made the live bot hand out
# the wrong person's contact details twice in one day.
#
# Only the two pure query-understanding helpers above are live:
# extract_course_codes (2 callers) and extract_keywords (10 callers).
# Full implementations remain in git history.
# ---------------------------------------------------------------------------
