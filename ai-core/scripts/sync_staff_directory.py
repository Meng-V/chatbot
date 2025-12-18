"""
Sync Staff Directory to Database

Fetches librarian contacts from LibGuides API profiles and populates:
- Librarian table (verified contacts only)
- LibrarianSubject table (maps librarians to subjects)

Run: python scripts/sync_staff_directory.py
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


async def fetch_all_accounts(token):
    """Fetch Miami staff profiles from LibGuides API."""
    print("📡 Fetching Miami staff profiles from LibGuides API...")
    print("   Limiting to first 100 pages to avoid rate limits")
    
    import time
    all_accounts = []
    page = 1
    max_pages = 100  # Limit to avoid rate limits
    
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        while page <= max_pages:
            try:
                response = await client.get(
                    f"{LIBGUIDES_BASE_URL}/accounts",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"page": page}
                )
                
                if response.status_code == 429:
                    print(f"  ⚠️ Rate limit hit on page {page}, waiting 5 seconds...")
                    time.sleep(5)
                    continue
                
                response.raise_for_status()
                accounts = response.json()
                
                if not accounts or len(accounts) == 0:
                    break
                
                # Filter for Miami staff (miamioh.edu emails)
                miami_accounts = [
                    acc for acc in accounts
                    if acc.get('email', '').endswith('@miamioh.edu')
                ]
                
                all_accounts.extend(miami_accounts)
                print(f"  Page {page}: {len(miami_accounts)}/{len(accounts)} Miami staff (total: {len(all_accounts)})")
                page += 1
                
                # Small delay to avoid rate limits
                time.sleep(0.2)
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"  ⚠️ Rate limit hit, stopping at page {page}")
                    break
                else:
                    raise
    
    print(f"✅ Fetched {len(all_accounts)} Miami staff accounts")
    return all_accounts


async def fetch_account_subjects(token, account_id):
    """Fetch subjects for a specific account."""
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(
                f"{LIBGUIDES_BASE_URL}/accounts/{account_id}/subjects",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()
    except Exception:
        return []


async def sync_staff_to_db(accounts, token):
    """Sync staff directory to database."""
    db = Prisma()
    await db.connect()
    
    try:
        stats = {"created": 0, "updated": 0, "mapped": 0, "regional": 0}
        
        for account_data in accounts:
            account_id = str(account_data.get("id", ""))
            first_name = account_data.get("first_name", "")
            last_name = account_data.get("last_name", "")
            email = account_data.get("email", "")
            title = account_data.get("title", "")
            department = ""  # LibGuides API doesn't provide department field
            
            if not email or not (first_name or last_name):
                continue
            
            name = f"{first_name} {last_name}".strip()
            profile_url = account_data.get("profile_url", "")
            image_url = account_data.get("image_url", "")
            
            # Determine campus based on title or department
            campus = "Oxford"
            is_regional = False
            
            title_lower = title.lower() if title else ""
            dept_lower = department.lower() if department else ""
            
            if "hamilton" in title_lower or "rentschler" in title_lower:
                campus = "Hamilton"
                is_regional = True
            elif "middletown" in title_lower or "gardner" in title_lower or "gardner-harvey" in title_lower:
                campus = "Middletown"
                is_regional = True
            elif "regional" in title_lower:
                # Check if it mentions specific campus
                if "hamilton" in dept_lower:
                    campus = "Hamilton"
                elif "middletown" in dept_lower:
                    campus = "Middletown"
                is_regional = True
            
            # Upsert Librarian
            librarian = await db.librarian.upsert(
                where={"email": email},
                data={
                    "create": {
                        "name": name,
                        "email": email,
                        "title": title,
                        "profileUrl": profile_url,
                        "photoUrl": image_url,
                        "libguideProfileId": account_id,
                        "campus": campus,
                        "isRegional": is_regional,
                        "isActive": True
                    },
                    "update": {
                        "name": name,
                        "title": title,
                        "profileUrl": profile_url,
                        "photoUrl": image_url,
                        "libguideProfileId": account_id,
                        "campus": campus,
                        "isRegional": is_regional,
                        "isActive": True
                    }
                }
            )
            
            stats["updated"] += 1
            if is_regional:
                stats["regional"] += 1
            
            # Fetch and map subjects
            subjects = await fetch_account_subjects(token, account_id)
            
            for subject_data in subjects:
                subject_name = subject_data.get("name", "")
                
                # Find matching subject in DB
                db_subject = await db.subject.find_first(
                    where={"name": subject_name}
                )
                
                if db_subject:
                    await db.librariansubject.upsert(
                        where={
                            "librarianId_subjectId": {
                                "librarianId": librarian.id,
                                "subjectId": db_subject.id
                            }
                        },
                        data={
                            "create": {
                                "librarianId": librarian.id,
                                "subjectId": db_subject.id,
                                "isPrimary": True
                            },
                            "update": {"isPrimary": True}
                        }
                    )
                    stats["mapped"] += 1
        
        print("\n📊 Sync Statistics:")
        print(f"  Librarians: {stats['updated']} synced")
        print(f"  Regional Campus: {stats['regional']} librarians")
        print(f"  Subject Mappings: {stats['mapped']} created")
        
    finally:
        await db.disconnect()


async def main():
    """Main sync function."""
    print("🚀 Starting Staff Directory Sync\n")
    
    token = await get_access_token()
    accounts = await fetch_all_accounts(token)
    await sync_staff_to_db(accounts, token)
    
    print("\n✅ Staff Directory Sync Complete!")


if __name__ == "__main__":
    asyncio.run(main())
