"""
Subject Librarian Agent

This agent helps users find the appropriate LibGuide and subject librarian for their
academic subject, major, or research topic using MyGuide mapping and LibGuides API.

Flow:
1. Use MyGuide (Prisma DB) to match subject/major/department to LibGuides
2. Use LibGuides API to fetch detailed librarian information
3. By default, only show Oxford campus (exclude regional campuses)
4. Provide fallback if API calls fail
"""

import os
import httpx
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma
from src.tools.subject_matcher import match_subject
from src.utils.logger import AgentLogger

# Load .env from project root
root_dir = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

logger = AgentLogger()

# LibGuides API Configuration
LIBAPPS_OAUTH_URL = os.getenv("LIBAPPS_OAUTH_URL", "")
LIBAPPS_CLIENT_ID = os.getenv("LIBAPPS_CLIENT_ID", "")
LIBAPPS_CLIENT_SECRET = os.getenv("LIBAPPS_CLIENT_SECRET", "")
LIBGUIDES_BASE_URL = "https://lgapi-us.libapps.com/1.2"


class SubjectLibrarianAgent:
    """Agent for finding subject librarians and LibGuides."""
    
    def __init__(self):
        self.access_token = None
        self.logger = logger
    
    async def get_access_token(self) -> str:
        """Get OAuth access token for LibGuides API."""
        if self.access_token:
            return self.access_token
        
        self.logger.log("🔐 Obtaining LibGuides API access token...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LIBAPPS_OAUTH_URL,
                data={
                    "client_id": LIBAPPS_CLIENT_ID,
                    "client_secret": LIBAPPS_CLIENT_SECRET,
                    "grant_type": "client_credentials"
                }
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
        
        self.logger.log("✅ Access token obtained")
        return self.access_token
    
    async def search_libguide_by_name(self, guide_name: str) -> Dict[str, Any]:
        """Search for a LibGuide by name."""
        token = await self.get_access_token()
        
        self.logger.log(f"🔍 Searching for LibGuide: {guide_name}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/guides",
                headers={"Authorization": f"Bearer {token}"},
                params={"search": guide_name}
            )
            response.raise_for_status()
            guides = response.json()
        
        # Find best match
        for guide in guides:
            if guide_name.lower() in guide.get("name", "").lower():
                self.logger.log(f"✅ Found LibGuide: {guide.get('name')}")
                return guide
        
        if guides:
            self.logger.log(f"📋 Returning first result: {guides[0].get('name')}")
            return guides[0]
        
        return None
    
    async def get_guide_owner(self, guide_id: int) -> Dict[str, Any]:
        """Get the owner (librarian) of a LibGuide."""
        token = await self.get_access_token()
        
        self.logger.log(f"👤 Getting owner for guide ID: {guide_id}")
        
        async with httpx.AsyncClient() as client:
            # Get guide details
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/guides/{guide_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            guide_data = response.json()
        
        # Handle both dict and list responses
        if isinstance(guide_data, list):
            if not guide_data:
                return None
            guide = guide_data[0]
        else:
            guide = guide_data
        
        owner_id = guide.get("owner_id")
        if not owner_id:
            return None
        
        # Get account details
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/accounts/{owner_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            account_data = response.json()
        
        # Handle both dict and list responses
        if isinstance(account_data, list):
            if not account_data:
                return None
            account = account_data[0]
        else:
            account = account_data
        
        librarian_info = {
            "id": account.get("id"),
            "first_name": account.get("first_name", ""),
            "last_name": account.get("last_name", ""),
            "email": account.get("email", ""),
            "profile_url": account.get("profile_url", ""),
            "title": account.get("title", ""),
            "subjects": account.get("subjects", [])
        }
        
        self.logger.log(f"✅ Found librarian: {librarian_info['first_name']} {librarian_info['last_name']}")
        return librarian_info
    
    async def find_subject_librarian(self, query: str, db: Prisma = None, include_regional: bool = False) -> Dict[str, Any]:
        """
        Find subject librarian and LibGuide for a given query.
        
        Args:
            query: Subject, major, or academic topic
            db: Optional Prisma database instance (will create if not provided)
            include_regional: If False, only show Oxford campus (default: False)
        
        Returns:
            Dict with subject info, LibGuides, and librarian contact information
        """
        result = {
            "query": query,
            "subjects": [],
            "lib_guides": [],
            "librarians": [],
            "success": False,
            "campus_filter": "Oxford (main campus)" if not include_regional else "All campuses",
            "api_errors": []
        }
        
        # Create DB connection if not provided
        db_provided = db is not None
        if not db_provided:
            db = Prisma()
            await db.connect()
        
        try:
            # Step 1: Match subject using MyGuide data (from Prisma DB)
            self.logger.log(f"🔍 [Step 1/3] Searching MyGuide DB for: {query} (campus: {result['campus_filter']})")
            subject_match = await match_subject(query, db, include_regional=include_regional)
            
            if not subject_match["success"]:
                self.logger.log(f"⚠️  No subjects found for: {query}")
                result["message"] = f"No subjects found matching '{query}' in {result['campus_filter']}"
                return result
            
            result["subjects"] = subject_match["matched_subjects"]
            self.logger.log(f"✅ [Step 1/3] Found {len(result['subjects'])} subject(s) with {len(subject_match['lib_guides'])} LibGuide(s)")
            
            # If we have subjects but no LibGuides, provide basic info
            if not subject_match["lib_guides"]:
                self.logger.log("⚠️  No LibGuides found for matched subjects")
                result["success"] = True
                result["message"] = "Subjects found but no LibGuides available"
                return result
            
            # Step 2: Get LibGuide details from API
            self.logger.log(f"📡 [Step 2/3] Fetching LibGuide details from API...")
            api_available = True
            
            for guide_name in subject_match["lib_guides"][:3]:  # Limit to top 3
                try:
                    guide = await self.search_libguide_by_name(guide_name)
                    
                    if guide:
                        guide_info = {
                            "id": guide.get("id"),
                            "name": guide.get("name"),
                            "url": guide.get("url"),
                            "description": guide.get("description", ""),
                            "owner": None
                        }
                        
                        # Step 3: Get librarian information from API
                        try:
                            librarian = await self.get_guide_owner(guide["id"])
                            if librarian:
                                guide_info["owner"] = librarian
                                
                                # Add to librarians list if not already there
                                if not any(lib["id"] == librarian["id"] for lib in result["librarians"]):
                                    result["librarians"].append(librarian)
                                    self.logger.log(f"   ✅ Found librarian: {librarian['first_name']} {librarian['last_name']}")
                        except Exception as lib_err:
                            self.logger.log(f"   ⚠️  Could not fetch librarian for guide '{guide_name}': {lib_err}")
                            result["api_errors"].append(f"Librarian lookup failed for {guide_name}")
                        
                        result["lib_guides"].append(guide_info)
                    else:
                        self.logger.log(f"   ⚠️  Guide not found in API: {guide_name}")
                
                except httpx.HTTPError as http_err:
                    self.logger.log(f"❌ HTTP error accessing LibGuides API for '{guide_name}': {http_err}")
                    result["api_errors"].append(f"API error for {guide_name}")
                    api_available = False
                    break  # Stop trying if API is down
                except Exception as e:
                    import traceback
                    error_details = traceback.format_exc()
                    self.logger.log(f"❌ Error processing guide '{guide_name}': {e}")
                    self.logger.log(f"   Traceback: {error_details}")
                    result["api_errors"].append(f"Processing error for {guide_name}: {str(e)}")
                    continue
            
            # Mark as successful if we found subjects and at least attempted API calls
            result["success"] = True
            
            if not api_available:
                self.logger.log("⚠️  LibGuides API unavailable - providing basic information only")
                result["api_unavailable"] = True
            else:
                self.logger.log(f"✅ [Step 3/3] Complete: {len(result['lib_guides'])} LibGuides, {len(result['librarians'])} librarian(s)")
        
        except Exception as e:
            import traceback
            self.logger.log(f"❌ Error in find_subject_librarian: {e}")
            self.logger.log(traceback.format_exc())
            result["error"] = str(e)
        
        finally:
            # Only disconnect if we created the connection
            if not db_provided:
                await db.disconnect()
        
        return result
    
    async def format_response(self, result: Dict[str, Any]) -> str:
        """Format the result as a human-readable response."""
        if not result["success"]:
            error_msg = result.get("message", "I couldn't find any subjects matching your query.")
            # Add helpful suggestion
            return f"{error_msg}\n\n💡 **Need help?**\n• Visit our subject librarians: https://www.lib.miamioh.edu/about/organization/liaisons/\n• Call: (513) 529-4141"
        
        output = []
        
        # Subject information with campus filter
        campus_note = f" (showing {result['campus_filter']})" if result.get('campus_filter') else ""
        output.append(f"I found information about **{result['query']}**{campus_note}:\n")
        
        # LibGuides
        if result["lib_guides"]:
            output.append("📚 **Recommended LibGuides:**")
            for guide in result["lib_guides"]:
                output.append(f"\n**{guide['name']}**")
                output.append(f"🔗 {guide['url']}")
                if guide.get('description'):
                    desc = guide['description'].strip()
                    if len(desc) > 150:
                        desc = desc[:150] + "..."
                    if desc:
                        output.append(f"📝 {desc}")
        
        # Librarians - ONLY include if retrieved from API
        if result["librarians"]:
            output.append("\n\n👨‍🏫 **Subject Librarians:**")
            for librarian in result["librarians"]:
                # Only show verified information from API
                name = f"{librarian['first_name']} {librarian['last_name']}"
                output.append(f"\n**{name}**")
                if librarian.get('title'):
                    output.append(f"📋 {librarian['title']}")
                # ONLY show email if it came from API (not generated)
                if librarian.get('email'):
                    output.append(f"✉️  {librarian['email']}")
                if librarian.get('profile_url'):
                    output.append(f"🔗 Profile: {librarian['profile_url']}")
                if librarian.get('subjects'):
                    subjects_str = ", ".join(librarian['subjects'][:5])
                    output.append(f"📚 Subject areas: {subjects_str}")
        elif result["lib_guides"] and result.get("api_unavailable"):
            # API was unavailable
            output.append("\n\n⚠️  **Note**: Some librarian information is temporarily unavailable.")
            output.append("\n📞 **Contact Information:**")
            output.append("For assistance from a subject librarian:")
            output.append("• **Visit**: https://www.lib.miamioh.edu/about/organization/liaisons/")
            output.append("• **Call the library**: (513) 529-4141")
        elif result["lib_guides"]:
            # We have guides but no librarian info (possibly API error or no owner)
            output.append("\n\n📞 **Contact Information:**")
            output.append("For assistance from a subject librarian:")
            output.append("• **Visit**: https://www.lib.miamioh.edu/about/organization/liaisons/")
            output.append("• **Call the library**: (513) 529-4141")
        
        # Additional subjects
        if len(result["subjects"]) > 1:
            output.append(f"\n\n📖 **Related subjects:**")
            for subject in result["subjects"][1:4]:  # Show up to 3 additional subjects
                output.append(f"   • {subject['name']}")
        
        # Show any API errors at the end (for debugging)
        if result.get("api_errors") and len(result["api_errors"]) > 0:
            self.logger.log(f"⚠️  API Errors encountered: {', '.join(result['api_errors'])}")
        
        return "\n".join(output)


async def search_subject_librarian_by_api(query: str, log_callback=None) -> Dict[str, Any]:
    """
    Search for subject librarian using ONLY LibGuides API with fuzzy matching.
    This ensures consistent data and proper fuzzy matching.
    
    Args:
        query: Subject name or keywords to search for
        log_callback: Optional logging callback function
    
    Returns:
        Dict with matched librarians and their subjects
    """
    if log_callback:
        log_callback(f"🔍 [Subject Librarian API Search] Searching for: {query}")
    
    agent = SubjectLibrarianAgent()
    
    try:
        # Get OAuth token
        token = await agent.get_access_token()
        
        # Fetch ALL accounts with subjects from LibGuides API
        if log_callback:
            log_callback("📡 [Subject Librarian API Search] Fetching all librarians from API...")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/accounts",
                headers={"Authorization": f"Bearer {token}"},
                params={"expand[]": "subjects"}
            )
            response.raise_for_status()
            librarian_data = response.json()
        
        # Search with fuzzy matching
        query_lower = query.lower().strip()
        query_keywords = set(query_lower.split())
        
        matches = []
        
        for librarian in librarian_data:
            first_name = librarian.get("first_name", "")
            last_name = librarian.get("last_name", "")
            email = librarian.get("email", "")
            profile_url = librarian.get("profile_url", "")
            subjects = librarian.get("subjects", [])
            
            # Skip if no subjects or no email
            if not subjects or not email:
                continue
            
            # Check each subject for fuzzy match
            for subject in subjects:
                subject_name = subject.get("name", "")
                subject_id = subject.get("id")
                
                if not subject_name:
                    continue
                
                subject_lower = subject_name.lower()
                subject_keywords = set(subject_lower.split())
                
                # Fuzzy matching strategies (from most strict to most lenient):
                # 1. Exact match
                is_exact_match = query_lower == subject_lower
                
                # 2. Query is substring of subject (e.g., "computer science" in "Computer Science and Engineering")
                is_substring_match = query_lower in subject_lower
                
                # 3. Subject contains query (reverse substring - less common but valid)
                is_reverse_substring = subject_lower in query_lower and len(subject_lower) >= 5
                
                # 4. Keyword overlap - TIGHTENED to avoid false matches
                # For multi-word queries, require ALL keywords to match
                # For single-word queries, exact keyword match required
                keyword_overlap = len(query_keywords & subject_keywords) / len(query_keywords) if query_keywords else 0
                
                if len(query_keywords) == 1:
                    # Single word: must match exactly as a word (not substring)
                    is_keyword_match = query_lower in subject_keywords
                else:
                    # Multiple words: require 80% keyword overlap to avoid false matches
                    is_keyword_match = keyword_overlap >= 0.8
                
                if is_exact_match or is_substring_match or is_reverse_substring or is_keyword_match:
                    match_score = 100 if is_exact_match else (90 if is_substring_match else (85 if is_reverse_substring else int(keyword_overlap * 80)))
                    
                    matches.append({
                        "librarian": {
                            "name": f"{first_name} {last_name}",
                            "email": email,
                            "profile_url": profile_url
                        },
                        "subject": {
                            "name": subject_name,
                            "id": subject_id
                        },
                        "match_score": match_score
                    })
        
        # Sort by match score (highest first)
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        
        if not matches:
            return {
                "source": "Subject Librarian Agent (LibGuides API - VERIFIED)",
                "success": False,
                "text": f"No subject librarian found for '{query}'.\n\n**General Library Contact:**\n• Visit: https://www.lib.miamioh.edu/about/organization/liaisons/\n• Call: (513) 529-4141",
                "needs_human": False,
                "metadata": {
                    "query": query,
                    "matches_found": 0
                }
            }
        
        # Format response - emphasize best match
        output = []
        
        # Group by librarian to avoid duplicates
        seen_librarians = set()
        librarian_subjects = {}
        
        for match in matches[:5]:  # Top 5 matches
            lib = match["librarian"]
            subj = match["subject"]
            email = lib["email"]
            
            if email not in seen_librarians:
                seen_librarians.add(email)
                librarian_subjects[email] = {
                    "name": lib["name"],
                    "email": email,
                    "profile_url": lib.get("profile_url", ""),
                    "subjects": [],
                    "best_match_score": match["match_score"]
                }
            
            # Add subject to librarian
            if subj["name"] not in librarian_subjects[email]["subjects"]:
                librarian_subjects[email]["subjects"].append(subj["name"])
        
        # Sort librarians by their best match score
        sorted_librarians = sorted(librarian_subjects.values(), key=lambda x: x["best_match_score"], reverse=True)
        
        # Show primary contact (best match) prominently
        if sorted_librarians:
            primary = sorted_librarians[0]
            output.append(f"For **{query}** research help, contact:")
            output.append(f"\n**{primary['name']}**")
            output.append(f"• Email: {primary['email']}")
            if primary.get('profile_url'):
                output.append(f"• Profile: {primary['profile_url']}")
            if primary['subjects']:
                output.append(f"• Covers: {', '.join(primary['subjects'][:3])}")
            
            # Show alternatives if available
            if len(sorted_librarians) > 1:
                output.append(f"\n**Additional contacts for related subjects:**")
                for lib_data in sorted_librarians[1:3]:  # Show up to 2 more
                    output.append(f"• {lib_data['name']} ({lib_data['email']}) - {lib_data['subjects'][0]}")
            
            output.append("")
        
        output.append("**General Contact:**")
        output.append("• Website: https://www.lib.miamioh.edu/about/organization/liaisons/")
        output.append("• Phone: (513) 529-4141")
        
        response_text = "\n".join(output)
        
        if log_callback:
            log_callback(f"✅ [Subject Librarian API Search] Found {len(librarian_subjects)} librarian(s) for '{query}'")
        
        return {
            "source": "Subject Librarian Agent (LibGuides API - VERIFIED)",
            "success": True,
            "text": response_text,
            "needs_human": False,
            "metadata": {
                "query": query,
                "librarians_found": len(librarian_subjects),
                "total_matches": len(matches),
                "api_source": "LibGuides API with fuzzy matching"
            }
        }
    
    except Exception as e:
        logger.log(f"❌ Error in API search: {e}")
        return {
            "source": "Subject Librarian Agent (LibGuides API)",
            "success": False,
            "text": f"Unable to search for '{query}' at this time.\n\n**Please contact:**\n• Visit: https://www.lib.miamioh.edu/about/organization/liaisons/\n• Call: (513) 529-4141",
            "needs_human": False,
            "error": str(e)
        }


async def list_all_subject_librarians(log_callback=None) -> Dict[str, Any]:
    """
    Get a comprehensive list of all subject librarians from LibGuides API.
    Returns ONLY API-verified data - NO hallucination!
    
    Args:
        log_callback: Optional logging callback function
    
    Returns:
        Dict with list of all librarians and their subjects
    """
    if log_callback:
        log_callback("🔍 [Subject Librarian List] Fetching all librarians from LibGuides API")
    
    agent = SubjectLibrarianAgent()
    
    try:
        # Get OAuth token
        token = await agent.get_access_token()
        
        # Fetch ALL accounts with subjects
        if log_callback:
            log_callback("📡 [Subject Librarian List] Calling LibGuides API...")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/accounts",
                headers={"Authorization": f"Bearer {token}"},
                params={"expand[]": "subjects"}
            )
            response.raise_for_status()
            librarian_data = response.json()
        
        # Process librarians - group by subject
        subject_librarians = {}
        
        for librarian in librarian_data:
            first_name = librarian.get("first_name", "")
            last_name = librarian.get("last_name", "")
            email = librarian.get("email", "")
            profile_url = librarian.get("profile_url", "")
            subjects = librarian.get("subjects", [])
            
            # Skip if no subjects or no email
            if not subjects or not email:
                continue
            
            librarian_info = {
                "name": f"{first_name} {last_name}",
                "email": email,
                "profile_url": profile_url
            }
            
            # Add to each subject
            for subject in subjects:
                subject_name = subject.get("name", "")
                subject_id = subject.get("id")
                
                if not subject_name:
                    continue
                
                if subject_name not in subject_librarians:
                    subject_librarians[subject_name] = {
                        "subject": subject_name,
                        "subject_id": subject_id,
                        "librarians": []
                    }
                
                # Avoid duplicates
                if not any(lib["email"] == email for lib in subject_librarians[subject_name]["librarians"]):
                    subject_librarians[subject_name]["librarians"].append(librarian_info)
        
        # Format response
        if not subject_librarians:
            return {
                "source": "Subject Librarian List (LibGuides API)",
                "success": False,
                "text": "Unable to fetch librarians at this time. Please visit: https://www.lib.miamioh.edu/about/organization/liaisons/ or call (513) 529-4141",
                "needs_human": False
            }
        
        # Create formatted text - grouped by subject
        output = []
        output.append("**Miami University Subject Librarians** (Oxford campus):\n")
        output.append("_All information verified from LibGuides API_\n")
        
        # Sort subjects alphabetically
        sorted_subjects = sorted(subject_librarians.keys())
        
        for subject_name in sorted_subjects[:20]:  # Limit to 20 subjects to avoid overwhelming output
            subject_data = subject_librarians[subject_name]
            librarians = subject_data["librarians"]
            
            output.append(f"\n**{subject_name}**")
            
            for lib in librarians:
                output.append(f"• {lib['name']} - {lib['email']}")
                if lib.get('profile_url'):
                    output.append(f"  Profile: {lib['profile_url']}")
        
        if len(sorted_subjects) > 20:
            output.append(f"\n\n_Showing 20 of {len(sorted_subjects)} subjects. For complete list, visit: https://www.lib.miamioh.edu/about/organization/liaisons/_")
        
        output.append("\n\n**General Contact:**")
        output.append("• Website: https://www.lib.miamioh.edu/about/organization/liaisons/")
        output.append("• Phone: (513) 529-4141")
        
        response_text = "\n".join(output)
        
        if log_callback:
            log_callback(f"✅ [Subject Librarian List] Found {len(subject_librarians)} subjects with librarians")
        
        return {
            "source": "Subject Librarian List (LibGuides API - VERIFIED)",
            "success": True,
            "text": response_text,
            "needs_human": False,
            "metadata": {
                "total_subjects": len(subject_librarians),
                "api_source": "LibGuides API"
            }
        }
    
    except Exception as e:
        logger.log(f"❌ Error fetching librarian list: {e}")
        return {
            "source": "Subject Librarian List (LibGuides API)",
            "success": False,
            "text": "Unable to fetch librarian list at this time.\n\n**Please contact:**\n• Visit: https://www.lib.miamioh.edu/about/organization/liaisons/\n• Call: (513) 529-4141",
            "needs_human": False,
            "error": str(e)
        }


# Main query function for agent
async def find_subject_librarian_query(query: str, log_callback=None, db: Prisma = None, include_regional: bool = False, **kwargs) -> Dict[str, Any]:
    """
    Main function to find subject librarians and LibGuides.
    
    Args:
        query: User's question about a subject, major, or topic
        log_callback: Optional logging callback function
        db: Optional Prisma database instance (will create if not provided)
        include_regional: If False, only show Oxford campus (default: False)
        **kwargs: Additional keyword arguments (for compatibility)
    
    Returns:
        Dict with formatted response and metadata
    """
    # Check if user is asking for a complete list/map of all librarians
    query_lower = query.lower()
    list_keywords = ["list", "all", "map", "complete", "full list", "show me"]
    is_list_request = any(keyword in query_lower for keyword in list_keywords) and \
                     ("librarian" in query_lower or "subject" in query_lower) and \
                     len(query_lower.split()) < 12  # Short query, not asking about specific subject
    
    # If it's a "list all" request, use API-only function (no hallucination!)
    if is_list_request:
        if log_callback:
            log_callback("🔍 [Subject Librarian Agent] Detected 'list all' request - using API-only mode")
        return await list_all_subject_librarians(log_callback=log_callback)
    
    # Otherwise, do normal subject-specific lookup using API-ONLY with fuzzy matching
    if log_callback:
        log_callback(f"🔍 [Subject Librarian Agent] Finding subject librarian via LibGuides API")
    
    # Extract subject from natural language queries
    # "Who is the biology librarian" → "biology"
    # "business librarian" → "business"
    # "who to contact when I have question about Art" → "art"
    cleaned_query = query.lower()
    
    # More comprehensive removal of question patterns
    remove_patterns = [
        "who to contact when i have question about",
        "who to contact when i have questions about",
        "who should i contact for",
        "who can i contact for",
        "who is the",
        "who's the",
        "what is the",
        "find me the",
        "find the",
        "show me the",
        "show me",
        "find me",
        "i have a question about",
        "i have questions about",
        "question about",
        "questions about",
        "librarian for",
        "librarian",
        "subject",
        "who is",
        "contact for"
    ]
    
    for pattern in remove_patterns:
        cleaned_query = cleaned_query.replace(pattern, "")
    
    cleaned_query = cleaned_query.strip()
    
    # If query became empty or too short, use original
    if len(cleaned_query) < 3:
        cleaned_query = query
    
    # Use API-only search with fuzzy matching (no MyGuide DB, no RAG)
    result = await search_subject_librarian_by_api(cleaned_query, log_callback=log_callback)
    
    # Return directly - it's already formatted
    return result
