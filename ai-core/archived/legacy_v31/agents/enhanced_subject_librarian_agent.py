"""
Enhanced Subject Librarian Agent

Uses enhanced search with:
- Course code matching (ENG 111, PSY 201)
- Natural language understanding
- Fuzzy matching for typos
- Validated contacts from staff directory
- LibGuide page URLs

Returns both LibGuide pages AND verified librarian contacts.
"""

from typing import Dict, Any
from src.database.prisma_client import get_prisma_client
from src.tools.enhanced_subject_search import (
    search_subject,
    get_subject_librarians,
    get_subject_libguides,
    detect_campus
)
from src.utils.logger import AgentLogger

logger = AgentLogger()


class EnhancedSubjectLibrarianAgent:
    """Enhanced agent for finding subject librarians and LibGuides."""
    
    def __init__(self):
        self.logger = logger
    
    async def execute(self, query: str, log_callback=None, **kwargs) -> Dict[str, Any]:
        """
        Execute enhanced subject librarian search.
        
        Args:
            query: User query (e.g., "Who is the librarian for ENG 111?")
            log_callback: Optional logging callback
            
        Returns:
            {
                "tool": "enhanced_subject_librarian",
                "success": bool,
                "text": formatted response,
                "data": {
                    "subject": subject name,
                    "librarians": [...],
                    "libguides": [...]
                }
            }
        """
        if log_callback:
            log_callback(f"🔍 [Enhanced Subject Librarian] Searching for: {query}")
        
        # Use singleton Prisma client to avoid connection pool exhaustion
        db = get_prisma_client()
        if not db.is_connected():
            await db.connect()
        
        try:
            # Check for Special Collections or Makerspace queries first
            query_lower = query.lower()
            is_special_collections = any(word in query_lower for word in ["special collections", "special collection", "university archives", "archives"])
            is_makerspace = any(word in query_lower for word in ["makerspace", "maker space", "makespace"])
            
            if is_special_collections or is_makerspace:
                space_name = "special collections" if is_special_collections else "makerspace"
                if log_callback:
                    log_callback(f"🏛️ [Enhanced Subject Librarian] Detected {space_name} query")
                
                # Get space info from database
                from src.services.location_service import get_location_service
                location_service = get_location_service()
                
                # Get website URL from database
                website = await location_service.get_library_website(space_name)
                
                # Get space details including buildingLocation
                space = await db.libraryspace.find_first(
                    where={
                        "OR": [
                            {"shortName": {"contains": space_name, "mode": "insensitive"}},
                            {"name": {"contains": space_name, "mode": "insensitive"}}
                        ]
                    },
                    include={"library": True}
                )
                
                # Search for subject to get librarian contact
                result = await search_subject(space_name, db)
                
                display_name = space.displayName if space else ("Walter Havighurst Special Collections & University Archives" if is_special_collections else "Makerspace")
                
                response_text = f"**{display_name}**\n\n"
                
                # Add location if available
                if space and space.buildingLocation:
                    library_name = space.library.displayName if space.library else "King Library"
                    response_text += f"📍 **Location**: {space.buildingLocation} of {library_name}\n\n"
                
                # Add librarian contact if found
                if result:
                    subject = result["subject"]
                    librarians = await get_subject_librarians(subject.id, db, "Oxford")
                    
                    if librarians:
                        lib = librarians[0]  # Get first librarian
                        response_text += "👤 **Contact**:\n"
                        response_text += f"• **{lib['name']}**"
                        if lib.get('title'):
                            response_text += f" - {lib['title']}"
                        response_text += "\n"
                        if lib.get('email'):
                            response_text += f"  📧 {lib['email']}\n"
                        if lib.get('phone'):
                            response_text += f"  📞 {lib['phone']}\n"
                        response_text += "\n"
                
                # Always add website
                response_text += f"🌐 **Website**: {website}\n\n"
                
                # Add general contact info
                response_text += "For general questions:\n"
                response_text += "• Call: (513) 529-4141\n"
                response_text += "• Visit: https://www.lib.miamioh.edu/research/research-support/ask/"
                
                if log_callback:
                    log_callback(f"✅ [Enhanced Subject Librarian] Provided {space_name} info with website")
                
                return {
                    "tool": "enhanced_subject_librarian",
                    "success": True,
                    "text": response_text,
                    "data": {
                        "space": space_name,
                        "website": website
                    }
                }
            
            # Search for subject using enhanced search
            result = await search_subject(query, db)
            
            if not result:
                if log_callback:
                    log_callback("❌ [Enhanced Subject Librarian] No matching subject found")
                
                return {
                    "tool": "enhanced_subject_librarian",
                    "success": False,
                    "text": (
                        "I couldn't find a specific subject or course match for your query. "
                        "Please try:\n"
                        "• Using a course code (e.g., 'ENG 111', 'PSY 201')\n"
                        "• Using a subject name (e.g., 'Biology', 'Psychology')\n"
                        "• Or chat with a librarian: https://www.lib.miamioh.edu/research/research-support/ask/"
                    ),
                    "data": None
                }
            
            subject = result["subject"]
            match_type = result["match_type"]
            
            # Detect campus from query
            campus = detect_campus(query)
            
            if log_callback:
                log_callback(f"✅ [Enhanced Subject Librarian] Found subject: {subject.name} (via {match_type})")
                log_callback(f"🏫 [Enhanced Subject Librarian] Campus: {campus}")
            
            # Get librarians for this subject, filtered by campus
            librarians = await get_subject_librarians(subject.id, db, campus)
            
            # Get LibGuides for this subject
            libguides = await get_subject_libguides(subject.id, db)
            
            if not librarians and not libguides:
                if log_callback:
                    log_callback("⚠️ [Enhanced Subject Librarian] No librarians or guides found")
                
                return {
                    "tool": "enhanced_subject_librarian",
                    "success": True,
                    "text": (
                        f"**{subject.name}**\n\n"
                        f"I found the subject but don't have specific librarian or guide information yet. "
                        f"Please contact our general reference desk:\n\n"
                        f"• **Chat**: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                        f"• **Phone**: (513) 529-4141"
                    ),
                    "data": {
                        "subject": subject.name,
                        "librarians": [],
                        "libguides": []
                    }
                }
            
            # Format response
            response_text = f"**{subject.name} Research Help**"
            if campus != "Oxford":
                response_text += f" ({campus} Campus)"
            response_text += "\n\n"
            
            # Add LibGuides
            if libguides:
                response_text += "📚 **Research Guides**:\n"
                for guide in libguides[:3]:  # Limit to top 3
                    response_text += f"• [{guide['name']}]({guide['url']})\n"
                response_text += "\n"
            
            # Add Librarians (validated contacts only)
            if librarians:
                primary_librarians = [l for l in librarians if l.get("isPrimary")]
                other_librarians = [l for l in librarians if not l.get("isPrimary")]
                
                if primary_librarians:
                    # Use plural if multiple librarians
                    header = "👤 **Subject Librarian**:\n" if len(primary_librarians) == 1 else "👥 **Subject Librarians**:\n"
                    response_text += header
                    for lib in primary_librarians:  # Show ALL primary librarians
                        response_text += f"• **{lib['name']}**"
                        if lib.get('title'):
                            response_text += f" - {lib['title']}"
                        response_text += "\n"
                        if lib.get('campus') and lib['campus'] != "Oxford":
                            response_text += f"  🏫 {lib['campus']} Campus\n"
                        if lib.get('email'):
                            response_text += f"  📧 {lib['email']}\n"
                        if lib.get('phone'):
                            response_text += f"  📞 {lib['phone']}\n"
                        # Always show LibGuide profile URL when available
                        if lib.get('libguideProfileUrl'):
                            response_text += f"  📖 [LibGuide Profile]({lib['libguideProfileUrl']})\n"
                    response_text += "\n"
                
                if other_librarians and not primary_librarians:
                    response_text += "👤 **Contact Librarian**:\n"
                    lib = other_librarians[0]
                    response_text += f"• **{lib['name']}**"
                    if lib.get('title'):
                        response_text += f" - {lib['title']}"
                    response_text += "\n"
                    if lib.get('email'):
                        response_text += f"  📧 {lib['email']}\n"
                    response_text += "\n"
            
            response_text += "Need more help? [Chat with a librarian](https://www.lib.miamioh.edu/research/research-support/ask/)"
            
            if log_callback:
                log_callback(f"✅ [Enhanced Subject Librarian] Found {len(librarians)} librarians, {len(libguides)} guides")
            
            return {
                "tool": "enhanced_subject_librarian",
                "success": True,
                "text": response_text,
                "data": {
                    "subject": subject.name,
                    "librarians": librarians,
                    "libguides": libguides
                }
            }
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Enhanced Subject Librarian] Error: {str(e)}")
            
            return {
                "tool": "enhanced_subject_librarian",
                "success": False,
                "text": (
                    "I encountered an error searching for subject information. "
                    "Please contact our reference desk:\n\n"
                    "• **Chat**: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                    "• **Phone**: (513) 529-4141"
                ),
                "data": None
            }
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ [Enhanced Subject Librarian] Error: {str(e)}")
            
            return {
                "tool": "enhanced_subject_librarian",
                "success": False,
                "text": (
                    "I encountered an error searching for subject information. "
                    "Please contact our reference desk:\n\n"
                    "• **Chat**: https://www.lib.miamioh.edu/research/research-support/ask/\n"
                    "• **Phone**: (513) 529-4141"
                ),
                "data": None
            }
        # Note: Don't disconnect singleton client
