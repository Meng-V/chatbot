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
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from prisma import Prisma
from src.database.prisma_client import get_prisma_client
from src.tools.subject_aliases import (
    SUBJECT_ALIASES,
    LIBRARIAN_SUBJECTS,
    COURSE_CODE_SUBJECTS,
    find_subject_by_alias,
    find_subjects_by_librarian_name,
    find_subject_by_course_code
)


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


def detect_campus(query: str) -> Optional[str]:
    """Detect which campus user is asking about."""
    query_lower = query.lower()
    
    # Check for explicit campus mentions
    if re.search(r'\b(hamilton|rentschler)\b', query_lower):
        return "Hamilton"
    elif re.search(r'\b(middletown|gardner|gardner-harvey)\b', query_lower):
        return "Middletown"
    elif re.search(r'\b(oxford|king|art|wertz)\b', query_lower):
        return "Oxford"
    
    # Check for regional campus indicators
    if re.search(r'\b(regional\s*campus|branch\s*campus)\b', query_lower):
        # Try to determine which one
        if 'hamilton' in query_lower:
            return "Hamilton"
        elif 'middletown' in query_lower:
            return "Middletown"
    
    # Default to Oxford (main campus)
    return "Oxford"


async def search_by_course_code(db: Prisma, course_codes: List[str]) -> Optional[Dict[str, Any]]:
    """Search subjects by course codes (exact match)."""
    for code in course_codes:
        # Try reg code
        reg_code = await db.subjectregcode.find_first(
            where={"regCode": code},
            include={"subject": True}
        )
        if reg_code:
            return {"subject": reg_code.subject, "match_type": "reg_code", "match_value": code}
        
        # Try dept code
        dept_code = await db.subjectdeptcode.find_first(
            where={"deptCode": code.lower()},
            include={"subject": True}
        )
        if dept_code:
            return {"subject": dept_code.subject, "match_type": "dept_code", "match_value": code}
        
        # Try major code
        major_code = await db.subjectmajorcode.find_first(
            where={"majorCode": code},
            include={"subject": True}
        )
        if major_code:
            return {"subject": major_code.subject, "match_type": "major_code", "match_value": code}
    
    return None


# Simple in-memory cache for subject search results
_subject_cache = {}
_cache_ttl = 300  # 5 minutes


async def search_by_fuzzy_match(db: Prisma, keywords: List[str], threshold: float = 0.7) -> Optional[Dict[str, Any]]:
    """Search subjects by fuzzy matching keywords - OPTIMIZED VERSION."""
    import time
    
    # Check cache first
    cache_key = f"fuzzy_{','.join(sorted(keywords))}_{threshold}"
    if cache_key in _subject_cache:
        cached_result, cached_time = _subject_cache[cache_key]
        if time.time() - cached_time < _cache_ttl:
            return cached_result
    
    # OPTIMIZATION: Load all data in ONE query with joins
    subjects = await db.subject.find_many(
        include={
            "regCodes": True,
            "deptCodes": True
        }
    )
    
    best_match = None
    best_score = 0.0
    
    for subject in subjects:
        for keyword in keywords:
            # Check subject name
            score = calculate_similarity(keyword, subject.name)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = {"subject": subject, "match_type": "fuzzy_name", "match_value": keyword, "score": score}
            
            # Check reg codes (already loaded)
            for reg_code in subject.regCodes:
                score = calculate_similarity(keyword, reg_code.regName)
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = {"subject": subject, "match_type": "fuzzy_reg_name", "match_value": keyword, "score": score}
            
            # Check dept codes (already loaded)
            for dept_code in subject.deptCodes:
                score = calculate_similarity(keyword, dept_code.deptName)
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = {"subject": subject, "match_type": "fuzzy_dept_name", "match_value": keyword, "score": score}
    
    # Cache result
    _subject_cache[cache_key] = (best_match, time.time())
    
    return best_match


async def search_by_alias(db: Prisma, query: str) -> Optional[Dict[str, Any]]:
    """
    Search using the comprehensive alias mapping system.
    This is the most reliable method for common search terms.
    """
    query_lower = query.lower().strip()
    
    # Strategy 1: Direct alias lookup
    subject_name = find_subject_by_alias(query_lower)
    if subject_name:
        subject = await db.subject.find_first(where={"name": subject_name})
        if subject:
            return {"subject": subject, "match_type": "alias", "match_value": query_lower, "score": 1.0}
    
    # Strategy 2: Check if searching for a librarian by name
    for librarian_name, subjects in LIBRARIAN_SUBJECTS.items():
        # Check if query contains librarian name parts
        name_parts = librarian_name.split()
        if any(part in query_lower for part in name_parts if len(part) > 2):
            # Return the first subject this librarian covers
            if subjects:
                subject = await db.subject.find_first(where={"name": subjects[0]})
                if subject:
                    return {"subject": subject, "match_type": "librarian_name", "match_value": librarian_name, "score": 1.0}
    
    # Strategy 3: Course code prefix lookup
    course_subject = find_subject_by_course_code(query)
    if course_subject:
        subject = await db.subject.find_first(where={"name": course_subject})
        if subject:
            return {"subject": subject, "match_type": "course_prefix", "match_value": query.upper(), "score": 1.0}
    
    return None


async def search_by_partial_match(db: Prisma, query: str) -> Optional[Dict[str, Any]]:
    """
    Search by partial/contains match on subject names.
    Useful when alias doesn't match but query is part of subject name.
    """
    query_lower = query.lower().strip()
    
    # Get all subjects and check for partial matches
    subjects = await db.subject.find_many()
    
    best_match = None
    best_score = 0
    
    for subject in subjects:
        subject_lower = subject.name.lower()
        
        # Check if query is contained in subject name
        if query_lower in subject_lower:
            # Score based on how much of the subject name the query covers
            score = len(query_lower) / len(subject_lower)
            if score > best_score:
                best_score = score
                best_match = {"subject": subject, "match_type": "partial", "match_value": query, "score": score}
        
        # Check if subject name words contain query
        subject_words = subject_lower.split()
        for word in subject_words:
            if query_lower in word or word in query_lower:
                score = min(len(query_lower), len(word)) / max(len(query_lower), len(word))
                if score > best_score and score >= 0.5:
                    best_score = score
                    best_match = {"subject": subject, "match_type": "word_partial", "match_value": query, "score": score}
    
    return best_match


async def search_subject(query: str, db: Prisma = None) -> Optional[Dict[str, Any]]:
    """
    Enhanced subject search with multiple strategies and timeout handling.
    
    Search order (most reliable to least):
    1. Alias mapping (comprehensive keyword -> subject mapping)
    2. Course code extraction (ENG 111, BIO, etc.)
    3. Partial/contains match on subject names
    4. Fuzzy matching (for typos)
    
    Returns:
        {
            "subject": Subject object,
            "match_type": "alias" | "course_prefix" | "reg_code" | "dept_code" | "partial" | "fuzzy_name",
            "match_value": matched string,
            "score": similarity score
        }
    """
    import asyncio
    
    if db is None:
        # Use singleton Prisma client to avoid connection pool exhaustion
        db = get_prisma_client()
        if not db.is_connected():
            await db.connect()
    
    try:
        # Wrap search in timeout to prevent hanging
        async def _search():
            # Strategy 1: Alias mapping (MOST RELIABLE - uses comprehensive keyword map)
            result = await search_by_alias(db, query)
            if result:
                return result
            
            # Strategy 2: Extract and search by course codes (exact match)
            course_codes = extract_course_codes(query)
            if course_codes:
                result = await search_by_course_code(db, course_codes)
                if result:
                    return result
            
            # Strategy 3: Partial/contains match on subject names
            result = await search_by_partial_match(db, query)
            if result and result.get("score", 0) >= 0.5:
                return result
            
            # Strategy 4: Extract keywords and fuzzy match (lower threshold for more matches)
            keywords = extract_keywords(query)
            if keywords:
                result = await search_by_fuzzy_match(db, keywords, threshold=0.6)  # Lowered from 0.7
                if result:
                    return result
            
            # Strategy 5: Try the partial match result even with lower score
            if result:
                return result
            
            return None
        
        # Add 10-second timeout to prevent hanging
        return await asyncio.wait_for(_search(), timeout=10.0)
        
    except asyncio.TimeoutError:
        # Query took too long - return None to trigger fallback
        return None
    except Exception:
        return None
    # Note: Don't disconnect singleton client


async def search_librarian_directly(db: Prisma, query: str) -> Optional[Dict[str, Any]]:
    """
    Search for a librarian directly by name.
    Returns librarian info with their subjects if found.
    """
    query_lower = query.lower().strip()
    
    # Get all active librarians
    librarians = await db.librarian.find_many(
        where={"isActive": True},
        include={"subjects": {"include": {"subject": True}}}
    )
    
    best_match = None
    best_score = 0
    
    for librarian in librarians:
        name_lower = librarian.name.lower()
        
        # Exact match
        if query_lower == name_lower:
            return {
                "librarian": {
                    "name": librarian.name,
                    "email": librarian.email,
                    "title": librarian.title,
                    "phone": librarian.phone,
                    "campus": librarian.campus
                },
                "subjects": [ls.subject.name for ls in librarian.subjects],
                "match_type": "exact_name",
                "score": 1.0
            }
        
        # Partial match (first name or last name)
        name_parts = name_lower.split()
        query_parts = query_lower.split()
        
        for query_part in query_parts:
            if len(query_part) < 3:
                continue
            for name_part in name_parts:
                if query_part in name_part or name_part in query_part:
                    score = min(len(query_part), len(name_part)) / max(len(query_part), len(name_part))
                    if score > best_score and score >= 0.7:
                        best_score = score
                        best_match = {
                            "librarian": {
                                "name": librarian.name,
                                "email": librarian.email,
                                "title": librarian.title,
                                "phone": librarian.phone,
                                "campus": librarian.campus
                            },
                            "subjects": [ls.subject.name for ls in librarian.subjects],
                            "match_type": "partial_name",
                            "score": score
                        }
    
    return best_match


async def get_subject_librarians(subject_id: str, db: Prisma, campus: str = "Oxford") -> List[Dict[str, Any]]:
    """Get all librarians for a subject, filtered by campus."""
    librarian_subjects = await db.librariansubject.find_many(
        where={"subjectId": subject_id},
        include={"librarian": True}
    )
    
    # Filter by campus - prefer matching campus, fall back to Oxford
    # Sort by isPrimary manually since order_by not supported
    matching_campus = []
    oxford_campus = []
    
    for ls in librarian_subjects:
        if not ls.librarian.isActive:
            continue
        
        librarian_data = {
            "name": ls.librarian.name,
            "email": ls.librarian.email,
            "title": ls.librarian.title,
            "phone": ls.librarian.phone,
            "profileUrl": ls.librarian.profileUrl,
            "campus": ls.librarian.campus,
            "isRegional": ls.librarian.isRegional,
            "isPrimary": ls.isPrimary
        }
        
        if ls.librarian.campus == campus:
            matching_campus.append(librarian_data)
        elif ls.librarian.campus == "Oxford":
            oxford_campus.append(librarian_data)
    
    # Sort by isPrimary (primary first)
    matching_campus.sort(key=lambda x: x['isPrimary'], reverse=True)
    oxford_campus.sort(key=lambda x: x['isPrimary'], reverse=True)
    
    # Return matching campus librarians first, fall back to Oxford
    return matching_campus if matching_campus else oxford_campus


async def get_subject_libguides(subject_id: str, db: Prisma) -> List[Dict[str, Any]]:
    """Get all LibGuides for a subject."""
    libguide_subjects = await db.libguidesubject.find_many(
        where={"subjectId": subject_id},
        include={"libGuide": True}
    )
    
    return [
        {
            "name": ls.libGuide.name,
            "url": ls.libGuide.url,
            "description": ls.libGuide.description
        }
        for ls in libguide_subjects
        if ls.libGuide.isActive
    ]
