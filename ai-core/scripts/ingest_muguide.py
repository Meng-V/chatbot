#!/usr/bin/env python3
"""
Ingest MuGuide subject mapping data into database.

This script fetches subject-to-libguide mappings from Miami University's MuGuide API
and stores them in the database for efficient subject matching and librarian routing.
"""
import os
import asyncio
import httpx
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma

# Load .env from project root
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# MuGuide API Configuration - Load from environment variables
MUGUIDE_API_URL = os.getenv("MUGUIDE_API_URL", "https://myguidedev.lib.miamioh.edu/api/subjects")
MUGUIDE_ID = os.getenv("MUGUIDE_ID")
MUGUIDE_API_KEY = os.getenv("MUGUIDE_API_KEY")

# Validate required credentials
if not MUGUIDE_ID or not MUGUIDE_API_KEY:
    raise ValueError(
        "MuGuide API credentials not found. Please set MUGUIDE_ID and MUGUIDE_API_KEY "
        "in your .env file. See .env.example for details."
    )


async def fetch_muguide_data():
    """Fetch subject mapping data from MuGuide API."""
    print("📡 Fetching MuGuide data from API...")
    
    params = {
        "id": MUGUIDE_ID,
        "apiKey": MUGUIDE_API_KEY
    }
    
    # Disable SSL verification for development server
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        response = await client.get(MUGUIDE_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    
    print(f"✅ Fetched {len(data['content']['subjects'])} subjects")
    return data['content']['subjects']


async def clear_existing_data(db: Prisma):
    """Clear existing MuGuide data from database."""
    print("🗑️  Clearing existing MuGuide data...")
    
    # Delete in reverse order due to foreign key constraints
    await db.subjectlibguide.delete_many()
    await db.subjectregcode.delete_many()
    await db.subjectmajorcode.delete_many()
    await db.subjectdeptcode.delete_many()
    await db.subject.delete_many()
    
    print("✅ Existing data cleared")


async def ingest_subjects(db: Prisma, subjects_data: list):
    """Ingest subjects into database."""
    print(f"\n📥 Ingesting {len(subjects_data)} subjects...")
    
    ingested_count = 0
    skipped_count = 0
    
    for subject_data in subjects_data:
        try:
            subject_name = subject_data.get("name")
            if not subject_name:
                skipped_count += 1
                continue
            
            # Create subject
            subject = await db.subject.create(
                data={
                    "name": subject_name,
                    "regional": subject_data.get("regional", False)
                }
            )
            
            # Add LibGuides
            lib_guides = subject_data.get("libguides") or []
            for lib_guide in lib_guides:
                await db.subjectlibguide.create(
                    data={
                        "subjectId": subject.id,
                        "libGuide": lib_guide
                    }
                )
            
            # Add Registration Codes
            reg_codes = subject_data.get("regCodes") or []
            for reg_code_data in reg_codes:
                await db.subjectregcode.create(
                    data={
                        "subjectId": subject.id,
                        "regCode": reg_code_data.get("regCode", ""),
                        "regName": reg_code_data.get("regName", "")
                    }
                )
            
            # Add Major Codes
            major_codes = subject_data.get("majorCodes") or []
            for major_code_data in major_codes:
                await db.subjectmajorcode.create(
                    data={
                        "subjectId": subject.id,
                        "majorCode": major_code_data.get("majorCode", ""),
                        "majorName": major_code_data.get("majorName", "")
                    }
                )
            
            # Add Department Codes
            dept_codes = subject_data.get("deptCodes") or []
            for dept_code_data in dept_codes:
                await db.subjectdeptcode.create(
                    data={
                        "subjectId": subject.id,
                        "deptCode": dept_code_data.get("deptCode", ""),
                        "deptName": dept_code_data.get("deptName", "")
                    }
                )
            
            ingested_count += 1
            
            # Progress indicator
            if ingested_count % 50 == 0:
                print(f"  ⏳ Processed {ingested_count} subjects...")
        
        except Exception as e:
            print(f"⚠️  Error ingesting subject '{subject_name}': {e}")
            skipped_count += 1
            continue
    
    print(f"\n✅ Ingestion complete!")
    print(f"   Ingested: {ingested_count}")
    print(f"   Skipped:  {skipped_count}")
    return ingested_count, skipped_count


async def print_statistics(db: Prisma):
    """Print database statistics."""
    print("\n📊 Database Statistics:")
    
    total_subjects = await db.subject.count()
    total_libguides = await db.subjectlibguide.count()
    total_reg_codes = await db.subjectregcode.count()
    total_major_codes = await db.subjectmajorcode.count()
    total_dept_codes = await db.subjectdeptcode.count()
    
    print(f"   Total Subjects:      {total_subjects}")
    print(f"   Total LibGuides:     {total_libguides}")
    print(f"   Total Reg Codes:     {total_reg_codes}")
    print(f"   Total Major Codes:   {total_major_codes}")
    print(f"   Total Dept Codes:    {total_dept_codes}")
    
    # Sample some subjects
    print("\n📝 Sample Subjects:")
    sample_subjects = await db.subject.find_many(
        take=5,
        include={
            "libGuides": True,
            "majorCodes": True
        }
    )
    
    for subject in sample_subjects:
        guides = [lg.libGuide for lg in subject.libGuides] if subject.libGuides else []
        majors = [mc.majorName for mc in subject.majorCodes] if subject.majorCodes else []
        print(f"   • {subject.name}")
        if guides:
            print(f"     LibGuides: {', '.join(guides[:3])}{'...' if len(guides) > 3 else ''}")
        if majors:
            print(f"     Majors: {', '.join(majors[:3])}{'...' if len(majors) > 3 else ''}")


async def main():
    """Main ingestion workflow."""
    print("=" * 70)
    print("MuGuide Subject Mapping Ingestion")
    print("=" * 70)
    print()
    
    # Initialize database
    db = Prisma()
    await db.connect()
    
    try:
        # Fetch data
        subjects_data = await fetch_muguide_data()
        
        # Clear existing data
        await clear_existing_data(db)
        
        # Ingest subjects
        await ingest_subjects(db, subjects_data)
        
        # Print statistics
        await print_statistics(db)
        
        print("\n" + "=" * 70)
        print("✅ MuGuide ingestion completed successfully!")
        print("=" * 70)
    
    except Exception as e:
        print(f"\n❌ Error during ingestion: {e}")
        raise
    
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
