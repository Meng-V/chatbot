"""
Sync LibGuides to Database

Fetches LibGuides from LibGuides API and populates:
- LibGuide table
- LibGuideSubject table (maps guides to subjects)

Run: python scripts/sync_libguides.py
"""

import asyncio
import httpx
import os
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

LIBGUIDE_OAUTH_URL = os.getenv("LIBGUIDE_OAUTH_URL", "")
LIBGUIDE_CLIENT_ID = os.getenv("LIBGUIDE_CLIENT_ID", "")
LIBGUIDE_CLIENT_SECRET = os.getenv("LIBGUIDE_CLIENT_SECRET", "")
LIBGUIDES_BASE_URL = "https://lgapi-us.libapps.com/1.2"


async def get_access_token():
    """Get OAuth access token for LibGuides API."""
    print("🔐 Obtaining LibGuides API access token...")
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(
            LIBGUIDE_OAUTH_URL,
            data={
                "client_id": LIBGUIDE_CLIENT_ID,
                "client_secret": LIBGUIDE_CLIENT_SECRET,
                "grant_type": "client_credentials"
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


async def fetch_all_guides(token):
    """Fetch only published guides from Miami University."""
    print("📡 Fetching Miami University LibGuides from API...")
    print("   Filtering: status=1 (published only)")
    
    all_guides = []
    page = 1
    
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        while True:
            try:
                response = await client.get(
                    f"{LIBGUIDES_BASE_URL}/guides",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "status": 1,  # Published only
                        "expand": "subjects",
                        "page": page
                    }
                )
                response.raise_for_status()
                guides = response.json()
                
                if not guides or len(guides) == 0:
                    break
                
                # Filter for Miami guides only (lib.miamioh.edu domain)
                miami_guides = [
                    g for g in guides 
                    if g.get('url', '').startswith('https://libguides.lib.miamioh.edu/')
                ]
                
                all_guides.extend(miami_guides)
                print(f"  Page {page}: {len(miami_guides)}/{len(guides)} Miami guides (total: {len(all_guides)})")
                
                page += 1
                
                # Stop if we got fewer than expected (end of results)
                if len(guides) < 100:
                    break
                    
                # Safety limit
                if len(all_guides) > 1000:
                    print("  ⚠️ Reached 1000 guides limit")
                    break
                    
            except Exception as e:
                print(f"  ❌ Error on page {page}: {str(e)}")
                break
    
    # Remove duplicates by URL
    unique_guides = {}
    for guide in all_guides:
        url = guide.get('url', '')
        if url and url not in unique_guides:
            unique_guides[url] = guide
    
    final_guides = list(unique_guides.values())
    print(f"✅ Fetched {len(final_guides)} unique Miami guides")
    return final_guides


async def sync_guides_to_db(guides):
    """Sync LibGuides to database."""
    db = Prisma()
    await db.connect()
    
    try:
        stats = {"created": 0, "updated": 0, "mapped": 0}
        
        for guide_data in guides:
            guide_id = str(guide_data.get("id", ""))
            name = guide_data.get("name", "")
            url = guide_data.get("url", "")
            description = guide_data.get("description", "")
            
            if not url or not name:
                continue
            
            # Upsert LibGuide
            guide = await db.libguide.upsert(
                where={"url": url},
                data={
                    "create": {
                        "name": name,
                        "url": url,
                        "description": description,
                        "guideId": guide_id,
                        "isActive": True
                    },
                    "update": {
                        "name": name,
                        "description": description,
                        "guideId": guide_id,
                        "isActive": True
                    }
                }
            )
            
            stats["updated"] += 1
            
            # Map to subjects based on SubjectLibGuide table
            subject_libguides = await db.subjectlibguide.find_many(
                where={"libGuide": name}
            )
            
            for subject_libguide in subject_libguides:
                await db.libguidesubject.upsert(
                    where={
                        "libGuideId_subjectId": {
                            "libGuideId": guide.id,
                            "subjectId": subject_libguide.subjectId
                        }
                    },
                    data={
                        "create": {
                            "libGuideId": guide.id,
                            "subjectId": subject_libguide.subjectId
                        },
                        "update": {}
                    }
                )
                stats["mapped"] += 1
        
        print("\n📊 Sync Statistics:")
        print(f"  LibGuides: {stats['updated']} synced")
        print(f"  Subject Mappings: {stats['mapped']} created")
        
    finally:
        await db.disconnect()


async def main():
    """Main sync function."""
    print("🚀 Starting LibGuides Sync\n")
    
    token = await get_access_token()
    guides = await fetch_all_guides(token)
    await sync_guides_to_db(guides)
    
    print("\n✅ LibGuides Sync Complete!")


if __name__ == "__main__":
    asyncio.run(main())
