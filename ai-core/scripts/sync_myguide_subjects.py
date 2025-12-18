"""
Sync MyGuide Subjects to Database

Fetches subjects from MyGuide API and populates:
- Subject table
- SubjectRegCode, SubjectMajorCode, SubjectDeptCode tables
- SubjectLibGuide table (legacy, will be replaced by LibGuideSubject)

Run: python scripts/sync_myguide_subjects.py
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

MYGUIDE_API_URL = "https://myguidedev.lib.miamioh.edu/api/subjects"
MYGUIDE_ID = os.getenv("MYGUIDE_ID")
MYGUIDE_API_KEY = os.getenv("MYGUIDE_API_KEY")

if not MYGUIDE_ID or not MYGUIDE_API_KEY:
    raise ValueError("MYGUIDE_ID and MYGUIDE_API_KEY must be set in environment variables. Please check your .env file.")


async def fetch_myguide_subjects():
    """Fetch all subjects from MyGuide API."""
    print("📡 Fetching subjects from MyGuide API...")
    
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        response = await client.get(
            MYGUIDE_API_URL,
            params={"id": MYGUIDE_ID, "apiKey": MYGUIDE_API_KEY}
        )
        response.raise_for_status()
        data = response.json()
    
    subjects = data.get("content", {}).get("subjects", [])
    print(f"✅ Fetched {len(subjects)} subjects from MyGuide")
    return subjects


async def sync_subjects_to_db(subjects):
    """Sync subjects to database."""
    db = Prisma()
    await db.connect()
    
    try:
        stats = {
            "subjects_created": 0,
            "subjects_updated": 0,
            "reg_codes": 0,
            "major_codes": 0,
            "dept_codes": 0,
            "libguides": 0
        }
        
        for subject_data in subjects:
            name = subject_data.get("name")
            if not name:
                continue
            
            regional = subject_data.get("regional", False)
            
            # Upsert subject
            subject = await db.subject.upsert(
                where={"name": name},
                data={
                    "create": {"name": name, "regional": regional},
                    "update": {"regional": regional}
                }
            )
            
            if subject:
                stats["subjects_updated"] += 1
            else:
                stats["subjects_created"] += 1
            
            # Sync reg codes
            for reg_code_data in subject_data.get("regCodes", []):
                reg_code = reg_code_data.get("regCode")
                reg_name = reg_code_data.get("regName", "")
                
                if reg_code:
                    await db.subjectregcode.upsert(
                        where={
                            "subjectId_regCode": {
                                "subjectId": subject.id,
                                "regCode": reg_code
                            }
                        },
                        data={
                            "create": {
                                "subjectId": subject.id,
                                "regCode": reg_code,
                                "regName": reg_name
                            },
                            "update": {"regName": reg_name}
                        }
                    )
                    stats["reg_codes"] += 1
            
            # Sync major codes
            for major_code_data in subject_data.get("majorCodes", []):
                major_code = major_code_data.get("majorCode")
                major_name = major_code_data.get("majorName", "")
                
                if major_code:
                    await db.subjectmajorcode.upsert(
                        where={
                            "subjectId_majorCode": {
                                "subjectId": subject.id,
                                "majorCode": major_code
                            }
                        },
                        data={
                            "create": {
                                "subjectId": subject.id,
                                "majorCode": major_code,
                                "majorName": major_name
                            },
                            "update": {"majorName": major_name}
                        }
                    )
                    stats["major_codes"] += 1
            
            # Sync dept codes
            for dept_code_data in subject_data.get("deptCodes", []):
                dept_code = dept_code_data.get("deptCode")
                dept_name = dept_code_data.get("deptName", "")
                
                if dept_code:
                    await db.subjectdeptcode.upsert(
                        where={
                            "subjectId_deptCode": {
                                "subjectId": subject.id,
                                "deptCode": dept_code
                            }
                        },
                        data={
                            "create": {
                                "subjectId": subject.id,
                                "deptCode": dept_code,
                                "deptName": dept_name
                            },
                            "update": {"deptName": dept_name}
                        }
                    )
                    stats["dept_codes"] += 1
            
            # Sync libguides (legacy table)
            libguides = subject_data.get("libguides") or []
            for libguide_name in libguides:
                if libguide_name:
                    await db.subjectlibguide.upsert(
                        where={
                            "subjectId_libGuide": {
                                "subjectId": subject.id,
                                "libGuide": libguide_name
                            }
                        },
                        data={
                            "create": {
                                "subjectId": subject.id,
                                "libGuide": libguide_name
                            },
                            "update": {}
                        }
                    )
                    stats["libguides"] += 1
        
        print("\n📊 Sync Statistics:")
        print(f"  Subjects: {stats['subjects_updated']} updated")
        print(f"  Reg Codes: {stats['reg_codes']}")
        print(f"  Major Codes: {stats['major_codes']}")
        print(f"  Dept Codes: {stats['dept_codes']}")
        print(f"  LibGuides: {stats['libguides']}")
        
    finally:
        await db.disconnect()


async def main():
    """Main sync function."""
    print("🚀 Starting MyGuide Subjects Sync\n")
    
    subjects = await fetch_myguide_subjects()
    await sync_subjects_to_db(subjects)
    
    print("\n✅ MyGuide Subjects Sync Complete!")


if __name__ == "__main__":
    asyncio.run(main())
