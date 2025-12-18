"""
Sync Librarians from CSV File

Reads staff-members.csv and populates Librarian table with all staff.
Maps librarians to their subjects based on liaison field.

Run: python scripts/sync_librarians_from_csv.py
"""

import asyncio
import csv
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

CSV_FILE = root_dir / "staff-members - staff-members.csv"


def parse_campus(library: str, office: str, department: str) -> tuple[str, bool]:
    """Determine campus from library, office, and department fields."""
    # Check library field
    if library in ["Hamilton", "Rentschler"]:
        return "Hamilton", True
    elif library in ["Middletown", "Gardner-Harvey"]:
        return "Middletown", True
    
    # Check office field
    office_lower = office.lower()
    if "rentschler" in office_lower or "hamilton" in office_lower:
        return "Hamilton", True
    elif "gardner" in office_lower or "middletown" in office_lower:
        return "Middletown", True
    
    # Check department field
    if department in ["Hamilton", "Middletown"]:
        return department, True
    
    # Default to Oxford
    return "Oxford", False


def parse_subjects(liaison_field: str) -> list[str]:
    """Parse liaison field to extract subject names."""
    if not liaison_field or liaison_field.strip() == "":
        return []
    
    # Split by semicolon
    subjects = [s.strip() for s in liaison_field.split(';')]
    return [s for s in subjects if s]


async def sync_from_csv():
    """Sync librarians from CSV file to database."""
    db = Prisma()
    await db.connect()
    
    try:
        stats = {
            "total_rows": 0,
            "librarians_added": 0,
            "librarians_updated": 0,
            "librarians_skipped": 0,
            "subject_mappings": 0,
            "oxford": 0,
            "hamilton": 0,
            "middletown": 0
        }
        
        print(f"📖 Reading CSV file: {CSV_FILE}")
        
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                stats["total_rows"] += 1
                
                first_name = row.get('first-name', '').strip()
                last_name = row.get('last-name', '').strip()
                email = row.get('email', '').strip()
                title = row.get('title', '').strip()
                phone = row.get('phone', '').strip()
                library = row.get('library', '').strip()
                office = row.get('office', '').strip()
                department = row.get('department', '').strip()
                liaison = row.get('liaison', '').strip()
                libguides_id = row.get('libguides-id', '').strip()
                pronouns = row.get('pronouns', '').strip()
                
                # Skip if no email
                if not email or not email.endswith('@miamioh.edu'):
                    stats["librarians_skipped"] += 1
                    continue
                
                # Skip if no name
                if not first_name or not last_name:
                    stats["librarians_skipped"] += 1
                    continue
                
                name = f"{first_name} {last_name}"
                
                # Determine campus
                campus, is_regional = parse_campus(library, office, department)
                
                # Count by campus
                if campus == "Oxford":
                    stats["oxford"] += 1
                elif campus == "Hamilton":
                    stats["hamilton"] += 1
                elif campus == "Middletown":
                    stats["middletown"] += 1
                
                # Upsert librarian
                librarian = await db.librarian.upsert(
                    where={"email": email},
                    data={
                        "create": {
                            "name": name,
                            "email": email,
                            "title": title,
                            "phone": phone if phone else None,
                            "campus": campus,
                            "isRegional": is_regional,
                            "libguideProfileId": libguides_id if libguides_id else None,
                            "isActive": True
                        },
                        "update": {
                            "name": name,
                            "title": title,
                            "phone": phone if phone else None,
                            "campus": campus,
                            "isRegional": is_regional,
                            "libguideProfileId": libguides_id if libguides_id else None,
                            "isActive": True
                        }
                    }
                )
                
                if librarian:
                    stats["librarians_updated"] += 1
                    print(f"✅ {name} ({campus})")
                
                # Parse and map subjects
                subjects = parse_subjects(liaison)
                
                for subject_name in subjects:
                    # Find matching subject in DB
                    subject = await db.subject.find_first(
                        where={"name": subject_name}
                    )
                    
                    if subject:
                        # Check if mapping already exists
                        existing = await db.librariansubject.find_first(
                            where={
                                "librarianId": librarian.id,
                                "subjectId": subject.id
                            }
                        )
                        
                        if not existing:
                            await db.librariansubject.create(data={
                                "librarianId": librarian.id,
                                "subjectId": subject.id,
                                "isPrimary": True
                            })
                            stats["subject_mappings"] += 1
                            print(f"   → Mapped to {subject_name}")
                    else:
                        print(f"   ⚠️ Subject not found: {subject_name}")
        
        print("\n📊 Sync Statistics:")
        print(f"  Total Rows: {stats['total_rows']}")
        print(f"  Librarians Synced: {stats['librarians_updated']}")
        print(f"  Librarians Skipped: {stats['librarians_skipped']}")
        print(f"  Subject Mappings: {stats['subject_mappings']}")
        print(f"\n  By Campus:")
        print(f"    Oxford: {stats['oxford']}")
        print(f"    Hamilton: {stats['hamilton']}")
        print(f"    Middletown: {stats['middletown']}")
        
        # Show final counts
        total = await db.librarian.count()
        regional = await db.librarian.count(where={"isRegional": True})
        mappings = await db.librariansubject.count()
        
        print(f"\n✅ Final Database State:")
        print(f"  Total Librarians: {total}")
        print(f"  Regional Campus: {regional}")
        print(f"  Subject Mappings: {mappings}")
        
    finally:
        await db.disconnect()


async def main():
    """Main sync function."""
    print("🚀 Starting Librarian Sync from CSV\n")
    
    if not CSV_FILE.exists():
        print(f"❌ CSV file not found: {CSV_FILE}")
        return
    
    await sync_from_csv()
    
    print("\n✅ Librarian Sync from CSV Complete!")
    print("\nNext Steps:")
    print("1. Restart server to load new data")
    print("2. Test subject librarian queries")
    print("3. Verify all contacts are from staff list")


if __name__ == "__main__":
    asyncio.run(main())
