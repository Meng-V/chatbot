"""Comprehensive LibGuide/MyGuide tools with fuzzy matching."""
import os
import json
import httpx
from typing import Dict, Any, List, Tuple, Optional
from src.tools.base import Tool
from src.services.libapps_oauth import get_libapps_oauth_service

LIBAPPS_OAUTH_URL = os.getenv("LIBAPPS_OAUTH_URL", "")
LIBAPPS_CLIENT_ID = os.getenv("LIBAPPS_CLIENT_ID", "")
LIBAPPS_CLIENT_SECRET = os.getenv("LIBAPPS_CLIENT_SECRET", "")
LIBAPPS_GRANT_TYPE = os.getenv("LIBAPPS_GRANT_TYPE", "client_credentials")

# Fallback message when API is unavailable
FALLBACK_CONTACT = """**Need Research Help?**

Please contact Miami University Libraries:
• **General Reference:** Ask-A-Librarian at https://www.lib.miamioh.edu/ask/
• **Subject Librarians:** https://www.lib.miamioh.edu/about/organization/liaisons/
• **Phone:** (513) 529-4141

We apologize for the inconvenience. Our librarians are happy to help!"""

async def _get_libapps_oauth_token() -> str:
    """Get LibApps OAuth token using centralized service."""
    oauth_service = get_libapps_oauth_service()
    return await oauth_service.get_token()

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    
    m, n = len(s1), len(s2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    
    for i in range(m + 1):
        dp[0][i] = i
    for i in range(n + 1):
        dp[i][0] = i
    
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if s1[j - 1] == s2[i - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(
                    dp[i - 1][j - 1],
                    dp[i - 1][j],
                    dp[i][j - 1]
                ) + 1
                
                # Damerau-Levenshtein: transposition
                if i > 1 and j > 1 and s1[j - 1] == s2[i - 2] and s1[j - 2] == s2[i - 1]:
                    dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 1)
    
    return dp[n][m]

def _fuzzy_best_match(
    query: str,
    choices: List[str],
    synonym_mapping: Dict[str, str],
    num_results: int = 2,
    threshold: float = 0.45
) -> List[Tuple[float, str]]:
    """Fuzzy match query to choices using Levenshtein distance."""
    query = query.lower().strip()
    
    # Check for exact match in synonyms first
    if query in synonym_mapping:
        return [(1.0, synonym_mapping[query])]
    
    # Fuzzy matching
    results = []
    for choice in choices:
        # Calculate match score
        distance = _levenshtein_distance(query, choice)
        match_score = max(
            1 - distance / max(len(query), len(choice)),
            0
        )
        
        # Also try synonym matching
        if choice.lower() in synonym_mapping:
            synonym = synonym_mapping[choice.lower()]
            synonym_distance = _levenshtein_distance(query, synonym)
            synonym_score = 1 - synonym_distance / max(len(query), len(synonym))
            match_score = max(match_score, synonym_score)
        
        if match_score >= threshold:
            results.append((match_score, choice))
    
    # Sort by score descending
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:num_results]

# Subject synonyms mapping
SUBJECT_SYNONYMS = {
    "biology": ["bio", "biol", "life sciences", "life science"],
    "computer science": ["cs", "comp sci", "computing", "csc"],
    "psychology": ["psych", "psyc"],
    "business": ["bus", "business admin", "management"],
    "english": ["eng", "engl", "literature", "lit"],
    "mathematics": ["math", "maths", "calc", "calculus"],
    "chemistry": ["chem"],
    "physics": ["phys"],
    "history": ["hist"],
    "economics": ["econ", "ec"],
    "political science": ["poli sci", "polisci", "govt", "government"],
    "sociology": ["soc", "socio"],
    "finance": ["fin"],
    "accounting": ["acct", "acc"],
    "marketing": ["mktg", "mrkt"],
    "environmental studies": ["env studies", "environmental science"],
}

def _get_synonym_mapping() -> Dict[str, str]:
    """Build synonym → main subject mapping."""
    mapping = {}
    for main_subject, synonyms in SUBJECT_SYNONYMS.items():
        for synonym in synonyms:
            mapping[synonym.lower().strip()] = main_subject
    return mapping

class LibGuideSubjectLookupTool(Tool):
    """Librarian subject lookup with fuzzy matching."""
    
    @property
    def name(self) -> str:
        return "libguide_subject_lookup"
    
    @property
    def description(self) -> str:
        return "Find librarians for a specific academic subject with fuzzy matching"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        subject_name: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Look up librarians by subject."""
        try:
            if not subject_name:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Please provide a subject name (e.g., 'Biology', 'Computer Science', 'Finance')."
                }
            
            if log_callback:
                log_callback(f"🔍 [LibGuide Subject Lookup Tool] Searching for '{subject_name}'")
            
            # Get synonym mapping
            synonym_mapping = _get_synonym_mapping()
            
            # Fetch librarian data from LibApps API
            token = await _get_libapps_oauth_token()
            
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://lgapi-us.libapps.com/1.2/accounts",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"expand": "subjects"}
                )
                
                # Handle 401 gracefully - return fallback
                if response.status_code == 401:
                    if log_callback:
                        log_callback("⚠️ [LibGuide Subject Lookup] API access denied - using fallback")
                    return {
                        "source": "LibGuide Subject Lookup (Fallback)",
                        "text": f"I'd be happy to help you find information about **{subject_name}**!\n\n{FALLBACK_CONTACT}",
                        "has_result": True
                    }
                
                response.raise_for_status()
                librarian_data = response.json()
            
            # Build subject → librarians mapping
            subject_to_librarians = {}
            subject_to_id = {}
            
            for librarian in librarian_data:
                first_name = librarian.get("first_name", "")
                last_name = librarian.get("last_name", "")
                email = librarian.get("email", "")
                subjects = librarian.get("subjects", [])
                
                if not subjects:
                    continue
                
                for subject in subjects:
                    subject_name_api = subject.get("name", "")
                    subject_id = subject.get("id")
                    slug_id = subject.get("slug_id")
                    
                    if subject_name_api not in subject_to_librarians:
                        subject_to_librarians[subject_name_api] = {
                            "librarians": [],
                            "subjectHomepage": ""
                        }
                    
                    subject_to_librarians[subject_name_api]["librarians"].append({
                        "name": f"{first_name} {last_name}",
                        "email": email
                    })
                    
                    if subject_id:
                        subject_to_id[subject_name_api] = {
                            "id": subject_id,
                            "slug_id": slug_id
                        }
            
            # Get all available subjects
            available_subjects = list(subject_to_librarians.keys())
            
            # First try exact match or synonym
            main_subject = synonym_mapping.get(subject_name.lower().strip())
            if not main_subject:
                main_subject = subject_name
            
            # Fuzzy match
            matches = _fuzzy_best_match(
                main_subject,
                available_subjects,
                synonym_mapping,
                num_results=1,
                threshold=0.45
            )
            
            if not matches:
                if log_callback:
                    log_callback(f"❌ [LibGuide Subject Lookup Tool] No match found for '{subject_name}'")
                return {
                    "tool": self.name,
                    "success": False,
                    "text": f"Sorry, no librarians found for subject '{subject_name}'. Please try a different subject or visit https://libguides.lib.miamioh.edu/"
                }
            
            # Get best match
            best_match_subject = matches[0][1]
            match_score = matches[0][0]
            
            result = subject_to_librarians[best_match_subject]
            
            # Generate subject homepage URL
            if best_match_subject in subject_to_id:
                subject_id = subject_to_id[best_match_subject]["id"]
                result["subjectHomepage"] = f"https://libguides.lib.miamioh.edu/sb.php?subject_id={subject_id}"
            else:
                result["subjectHomepage"] = "https://libguides.lib.miamioh.edu/"
            
            # Format response
            librarians_list = []
            for lib in result["librarians"]:
                librarians_list.append(f"• {lib['name']} - {lib['email']}")
            
            text = f"**Librarians for {best_match_subject}:**\n\n"
            text += "\n".join(librarians_list)
            text += f"\n\n**Subject Guide:** {result['subjectHomepage']}"
            
            if match_score < 1.0:
                text = f"_(Found close match: {best_match_subject})_\n\n" + text
            
            if log_callback:
                log_callback(f"✅ [LibGuide Subject Lookup Tool] Found {len(result['librarians'])} librarian(s)")
            
            return {
                "tool": self.name,
                "success": True,
                "text": text,
                "subject": best_match_subject,
                "librarians": result["librarians"],
                "homepage": result["subjectHomepage"]
            }
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibGuide Subject Lookup Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Error looking up librarians. Visit https://libguides.lib.miamioh.edu/"
            }

class LibGuideCourseLookupTool(Tool):
    """Course lookup by course code."""
    
    @property
    def name(self) -> str:
        return "libguide_course_lookup"
    
    @property
    def description(self) -> str:
        return "Find LibGuide and librarian for a specific course (e.g., ENG 111, BIO 201)"
    
    async def execute(
        self,
        query: str,
        log_callback=None,
        course_code: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Look up course guide."""
        try:
            if not course_code:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Please provide a course code (e.g., 'ENG 111', 'BIO 201', 'FIN 301')."
                }
            
            if log_callback:
                log_callback(f"📚 [LibGuide Course Lookup Tool] Looking up course '{course_code}'")
            
            # Parse course code to extract subject
            import re
            match = re.match(r'^([A-Z]{2,4})\s*(\d{3,4})?', course_code.upper())
            
            if not match:
                return {
                    "tool": self.name,
                    "success": False,
                    "text": "Invalid course code format. Please use format like 'ENG 111' or 'BIO 201'."
                }
            
            subject_code = match.group(1)
            course_number = match.group(2) if match.group(2) else ""
            
            # Map common course codes to subjects
            course_to_subject = {
                "ENG": "English",
                "BIO": "Biology",
                "CS": "Computer Science",
                "CSE": "Computer Science",
                "MTH": "Mathematics",
                "CHM": "Chemistry",
                "PHY": "Physics",
                "PSY": "Psychology",
                "ECO": "Economics",
                "FIN": "Finance",
                "ACC": "Accounting",
                "MKT": "Marketing",
                "BUS": "Business",
                "MGT": "Business",
                "HST": "History",
                "POL": "Political Science",
                "SOC": "Sociology",
            }
            
            subject_name = course_to_subject.get(subject_code, subject_code)
            
            # Use subject lookup tool
            subject_tool = LibGuideSubjectLookupTool()
            result = await subject_tool.execute(
                query=query,
                log_callback=log_callback,
                subject_name=subject_name
            )
            
            if result.get("success"):
                # Enhance with course-specific info
                text = f"**Course: {course_code}**\n\n" + result.get("text", "")
                result["text"] = text
                result["course_code"] = course_code
            
            return result
        
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [LibGuide Course Lookup Tool] Error: {str(e)}")
            return {
                "tool": self.name,
                "success": False,
                "error": str(e),
                "text": "Error looking up course. Visit https://libguides.lib.miamioh.edu/"
            }
