"""
Subject Matcher Tool - Find LibGuides and Librarians for Academic Subjects

This tool matches user queries about subjects, majors, or academic topics to the 
appropriate LibGuides and subject librarians using the MuGuide mapping database.
"""

from typing import List, Dict, Any, Optional
from prisma import Prisma
from prisma.models import Subject
from difflib import SequenceMatcher


async def normalize_query(query: str) -> str:
    """Normalize query text for better matching."""
    return query.lower().strip()


async def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


async def find_subjects_by_name(db: Prisma, query: str, threshold: float = 0.7) -> List[Subject]:
    """Find subjects by name with fuzzy matching."""
    query_normalized = await normalize_query(query)
    
    # First try exact match
    exact_match = await db.subject.find_first(
        where={"name": {"equals": query, "mode": "insensitive"}},
        include={
            "libGuides": True,
            "regCodes": True,
            "majorCodes": True,
            "deptCodes": True
        }
    )
    
    if exact_match:
        return [exact_match]
    
    # Try fuzzy matching
    all_subjects = await db.subject.find_many(
        include={
            "libGuides": True,
            "regCodes": True,
            "majorCodes": True,
            "deptCodes": True
        }
    )
    
    matches = []
    for subject in all_subjects:
        similarity = await calculate_similarity(query_normalized, subject.name)
        if similarity >= threshold:
            matches.append((subject, similarity))
    
    # Sort by similarity
    matches.sort(key=lambda x: x[1], reverse=True)
    
    return [match[0] for match in matches[:5]]  # Return top 5 matches


async def find_subjects_by_major(db: Prisma, major: str) -> List[Subject]:
    """Find subjects by major code or major name."""
    major_normalized = await normalize_query(major)
    
    # Search by major code (exact)
    major_code_matches = await db.subjectmajorcode.find_many(
        where={
            "OR": [
                {"majorCode": {"contains": major, "mode": "insensitive"}},
                {"majorName": {"contains": major, "mode": "insensitive"}}
            ]
        },
        include={"subject": {"include": {"libGuides": True, "majorCodes": True, "deptCodes": True}}}
    )
    
    subjects = []
    seen_ids = set()
    
    for major_code in major_code_matches:
        if major_code.subject.id not in seen_ids:
            subjects.append(major_code.subject)
            seen_ids.add(major_code.subject.id)
    
    return subjects


async def find_subjects_by_department(db: Prisma, department: str) -> List[Subject]:
    """Find subjects by department code or department name."""
    dept_normalized = await normalize_query(department)
    
    # Search by department code or name
    dept_matches = await db.subjectdeptcode.find_many(
        where={
            "OR": [
                {"deptCode": {"contains": department, "mode": "insensitive"}},
                {"deptName": {"contains": department, "mode": "insensitive"}}
            ]
        },
        include={"subject": {"include": {"libGuides": True, "majorCodes": True, "deptCodes": True}}}
    )
    
    subjects = []
    seen_ids = set()
    
    for dept in dept_matches:
        if dept.subject.id not in seen_ids:
            subjects.append(dept.subject)
            seen_ids.add(dept.subject.id)
    
    return subjects


async def match_subject(query: str, db: Prisma) -> Dict[str, Any]:
    """
    Match a query to subjects and return LibGuides information.
    
    Args:
        query: User query about a subject, major, or topic
        db: Prisma database instance
    
    Returns:
        Dict containing matched subjects and their LibGuides
    """
    results = {
        "query": query,
        "matched_subjects": [],
        "lib_guides": [],
        "success": False
    }
    
    try:
        # Try different matching strategies
        subjects = []
        
        # Strategy 1: Match by subject name
        name_matches = await find_subjects_by_name(db, query)
        subjects.extend(name_matches)
        
        # Strategy 2: Match by major
        if not subjects:
            major_matches = await find_subjects_by_major(db, query)
            subjects.extend(major_matches)
        
        # Strategy 3: Match by department
        if not subjects:
            dept_matches = await find_subjects_by_department(db, query)
            subjects.extend(dept_matches)
        
        # Remove duplicates
        unique_subjects = {}
        for subject in subjects:
            if subject.id not in unique_subjects:
                unique_subjects[subject.id] = subject
        
        subjects = list(unique_subjects.values())
        
        if subjects:
            results["success"] = True
            
            # Extract LibGuides
            lib_guides_set = set()
            
            for subject in subjects:
                subject_info = {
                    "name": subject.name,
                    "regional": subject.regional,
                    "lib_guides": [],
                    "majors": [],
                    "departments": []
                }
                
                # Add LibGuides
                if subject.libGuides:
                    for lg in subject.libGuides:
                        subject_info["lib_guides"].append(lg.libGuide)
                        lib_guides_set.add(lg.libGuide)
                
                # Add majors
                if subject.majorCodes:
                    for mc in subject.majorCodes:
                        subject_info["majors"].append({
                            "code": mc.majorCode,
                            "name": mc.majorName
                        })
                
                # Add departments
                if subject.deptCodes:
                    for dc in subject.deptCodes:
                        subject_info["departments"].append({
                            "code": dc.deptCode,
                            "name": dc.deptName
                        })
                
                results["matched_subjects"].append(subject_info)
            
            results["lib_guides"] = list(lib_guides_set)
    
    except Exception as e:
        results["error"] = str(e)
    
    return results


async def get_subject_by_libguide(db: Prisma, libguide_name: str) -> List[Subject]:
    """Get subjects associated with a specific LibGuide."""
    libguide_matches = await db.subjectlibguide.find_many(
        where={"libGuide": {"equals": libguide_name, "mode": "insensitive"}},
        include={"subject": {"include": {"libGuides": True, "majorCodes": True, "deptCodes": True}}}
    )
    
    return [match.subject for match in libguide_matches]


# Tool function for LangChain integration
async def subject_matcher_tool(query: str) -> str:
    """
    Find LibGuides and librarian information for academic subjects, majors, or topics.
    
    Args:
        query: Subject, major, department, or academic topic to search for
        
    Returns:
        Formatted string with matching subjects and LibGuides
    """
    db = Prisma()
    await db.connect()
    
    try:
        result = await match_subject(query, db)
        
        if not result["success"]:
            return f"No subjects found matching '{query}'. Please try a different search term or be more specific."
        
        output = []
        output.append(f"Found {len(result['matched_subjects'])} subject(s) matching '{query}':\n")
        
        for subject in result["matched_subjects"]:
            output.append(f"\n📚 **{subject['name']}**")
            
            if subject["lib_guides"]:
                output.append(f"   LibGuides: {', '.join(subject['lib_guides'])}")
            
            if subject["majors"]:
                major_names = [m['name'] for m in subject["majors"][:3]]
                output.append(f"   Related Majors: {', '.join(major_names)}")
            
            if subject["departments"]:
                dept_names = [d['name'] for d in subject["departments"][:3]]
                output.append(f"   Departments: {', '.join(dept_names)}")
        
        if result["lib_guides"]:
            output.append(f"\n🔗 Recommended LibGuides to explore:")
            for guide in result["lib_guides"][:5]:
                output.append(f"   • {guide}")
        
        return "\n".join(output)
    
    finally:
        await db.disconnect()
