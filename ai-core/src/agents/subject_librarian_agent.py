"""
Subject Librarian Agent

This agent helps users find the appropriate LibGuide and subject librarian for their
academic subject, major, or research topic using MuGuide mapping and LibGuides API.
"""

import os
import httpx
from typing import Dict, Any, List
from prisma import Prisma
from src.tools.subject_matcher import match_subject
from src.utils.logger import AgentLogger

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
        
        self.logger.info("🔐 Obtaining LibGuides API access token...")
        
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
        
        self.logger.success("✅ Access token obtained")
        return self.access_token
    
    async def search_libguide_by_name(self, guide_name: str) -> Dict[str, Any]:
        """Search for a LibGuide by name."""
        token = await self.get_access_token()
        
        self.logger.info(f"🔍 Searching for LibGuide: {guide_name}")
        
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
                self.logger.success(f"✅ Found LibGuide: {guide.get('name')}")
                return guide
        
        if guides:
            self.logger.info(f"📋 Returning first result: {guides[0].get('name')}")
            return guides[0]
        
        return None
    
    async def get_guide_owner(self, guide_id: int) -> Dict[str, Any]:
        """Get the owner (librarian) of a LibGuide."""
        token = await self.get_access_token()
        
        self.logger.info(f"👤 Getting owner for guide ID: {guide_id}")
        
        async with httpx.AsyncClient() as client:
            # Get guide details
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/guides/{guide_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            guide = response.json()
        
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
            account = response.json()
        
        librarian_info = {
            "id": account.get("id"),
            "first_name": account.get("first_name", ""),
            "last_name": account.get("last_name", ""),
            "email": account.get("email", ""),
            "profile_url": account.get("profile_url", ""),
            "title": account.get("title", ""),
            "subjects": account.get("subjects", [])
        }
        
        self.logger.success(f"✅ Found librarian: {librarian_info['first_name']} {librarian_info['last_name']}")
        return librarian_info
    
    async def find_subject_librarian(self, query: str) -> Dict[str, Any]:
        """
        Find subject librarian and LibGuide for a given query.
        
        Args:
            query: Subject, major, or academic topic
        
        Returns:
            Dict with subject info, LibGuides, and librarian contact information
        """
        result = {
            "query": query,
            "subjects": [],
            "lib_guides": [],
            "librarians": [],
            "success": False
        }
        
        db = Prisma()
        await db.connect()
        
        try:
            # Step 1: Match subject using MuGuide data
            self.logger.info(f"🔍 Searching for subject: {query}")
            subject_match = await match_subject(query, db)
            
            if not subject_match["success"]:
                self.logger.warning(f"⚠️  No subjects found for: {query}")
                result["message"] = f"No subjects found matching '{query}'"
                return result
            
            result["subjects"] = subject_match["matched_subjects"]
            
            # Step 2: Get LibGuide details and librarians
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
                        
                        # Get librarian information
                        librarian = await self.get_guide_owner(guide["id"])
                        if librarian:
                            guide_info["owner"] = librarian
                            
                            # Add to librarians list if not already there
                            if not any(lib["id"] == librarian["id"] for lib in result["librarians"]):
                                result["librarians"].append(librarian)
                        
                        result["lib_guides"].append(guide_info)
                
                except Exception as e:
                    self.logger.error(f"❌ Error processing guide '{guide_name}': {e}")
                    continue
            
            result["success"] = True
            self.logger.success(f"✅ Found {len(result['lib_guides'])} LibGuides and {len(result['librarians'])} librarians")
        
        except Exception as e:
            self.logger.error(f"❌ Error in find_subject_librarian: {e}")
            result["error"] = str(e)
        
        finally:
            await db.disconnect()
        
        return result
    
    async def format_response(self, result: Dict[str, Any]) -> str:
        """Format the result as a human-readable response."""
        if not result["success"]:
            return result.get("message", "I couldn't find any subjects matching your query.")
        
        output = []
        
        # Subject information
        output.append(f"I found information about **{result['query']}**:\n")
        
        # LibGuides
        if result["lib_guides"]:
            output.append("📚 **Recommended LibGuides:**")
            for guide in result["lib_guides"]:
                output.append(f"\n**{guide['name']}**")
                output.append(f"🔗 {guide['url']}")
                if guide['description']:
                    output.append(f"📝 {guide['description'][:150]}...")
        
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
        elif result["lib_guides"]:
            # If we have guides but no librarian info, provide general contact
            output.append("\n\n📞 **Contact Information:**")
            output.append("For assistance from a subject librarian:")
            output.append("• **Visit**: https://www.lib.miamioh.edu/librarians")
            output.append("• **Call the library**: (513) 529-4141")
        
        # Additional subjects
        if len(result["subjects"]) > 1:
            output.append(f"\n\n📖 This query also relates to:")
            for subject in result["subjects"][1:4]:  # Show up to 3 additional subjects
                output.append(f"   • {subject['name']}")
        
        return "\n".join(output)


# Main query function for agent
async def find_subject_librarian_query(query: str) -> str:
    """
    Main function to find subject librarians and LibGuides.
    
    Args:
        query: User's question about a subject, major, or topic
    
    Returns:
        Formatted response with LibGuides and librarian information
    """
    agent = SubjectLibrarianAgent()
    result = await agent.find_subject_librarian(query)
    response = await agent.format_response(result)
    return response
