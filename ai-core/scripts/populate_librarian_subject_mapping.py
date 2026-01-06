"""
Populate Librarian-Subject Mapping from CSV

This script:
1. Reads staff-members.csv to extract all unique subjects
2. Creates missing subjects in the database
3. Maps librarians to their subjects
4. Ensures all data is up-to-date for "who is my librarian" queries

Run: python ai-core/scripts/populate_librarian_subject_mapping.py
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
    if library in ["Hamilton", "Rentschler"]:
        return "Hamilton", True
    elif library in ["Middletown", "Gardner-Harvey"]:
        return "Middletown", True
    
    office_lower = office.lower()
    if "rentschler" in office_lower or "hamilton" in office_lower:
        return "Hamilton", True
    elif "gardner" in office_lower or "middletown" in office_lower:
        return "Middletown", True
    
    if department in ["Hamilton", "Middletown"]:
        return department, True
    
    return "Oxford", False


def parse_subjects(liaison_field: str) -> list[str]:
    """Parse liaison field to extract subject names."""
    if not liaison_field or liaison_field.strip() == "":
        return []
    
    subjects = [s.strip() for s in liaison_field.split(';')]
    return [s for s in subjects if s]


async def ensure_subjects_exist(db: Prisma, subjects: set[str]) -> dict[str, str]:
    """
    Ensure all subjects exist in database.
    Returns mapping of subject name -> subject ID
    """
    subject_map = {}
    
    print(f"\n📚 Ensuring {len(subjects)} subjects exist in database...")
    
    for subject_name in sorted(subjects):
        subject = await db.subject.find_first(
            where={"name": subject_name}
        )
        
        if not subject:
            subject = await db.subject.create(
                data={
                    "name": subject_name,
                    "regional": False
                }
            )
            print(f"  ✅ Created subject: {subject_name}")
        else:
            print(f"  ✓ Exists: {subject_name}")
        
        subject_map[subject_name] = subject.id
    
    return subject_map


async def populate_mapping():
    """Main function to populate librarian-subject mapping."""
    db = Prisma()
    await db.connect()
    
    try:
        print("🚀 Starting Librarian-Subject Mapping Population\n")
        
        if not CSV_FILE.exists():
            print(f"❌ CSV file not found: {CSV_FILE}")
            return
        
        stats = {
            "total_rows": 0,
            "librarians_synced": 0,
            "subjects_found": set(),
            "subject_mappings_created": 0,
            "subject_mappings_existing": 0,
            "librarians_without_subjects": []
        }
        
        # Step 1: Read CSV and collect all unique subjects
        print(f"📖 Reading CSV file: {CSV_FILE}")
        
        librarian_data = []
        
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
                
                if not email or not email.endswith('@miamioh.edu'):
                    continue
                
                if not first_name or not last_name:
                    continue
                
                name = f"{first_name} {last_name}"
                campus, is_regional = parse_campus(library, office, department)
                subjects = parse_subjects(liaison)
                
                # Collect unique subjects
                for subject in subjects:
                    stats["subjects_found"].add(subject)
                
                librarian_data.append({
                    "name": name,
                    "email": email,
                    "title": title,
                    "phone": phone,
                    "campus": campus,
                    "is_regional": is_regional,
                    "libguides_id": libguides_id,
                    "subjects": subjects
                })
        
        print(f"✅ Parsed {len(librarian_data)} librarians with {len(stats['subjects_found'])} unique subjects")
        
        # Step 2: Ensure all subjects exist in database
        subject_map = await ensure_subjects_exist(db, stats["subjects_found"])
        
        # Step 3: Sync librarians and create mappings
        print(f"\n👥 Syncing {len(librarian_data)} librarians and their subject mappings...")
        
        for lib_data in librarian_data:
            # Upsert librarian
            librarian = await db.librarian.upsert(
                where={"email": lib_data["email"]},
                data={
                    "create": {
                        "name": lib_data["name"],
                        "email": lib_data["email"],
                        "title": lib_data["title"],
                        "phone": lib_data["phone"] if lib_data["phone"] else None,
                        "campus": lib_data["campus"],
                        "isRegional": lib_data["is_regional"],
                        "libguideProfileId": lib_data["libguides_id"] if lib_data["libguides_id"] else None,
                        "isActive": True
                    },
                    "update": {
                        "name": lib_data["name"],
                        "title": lib_data["title"],
                        "phone": lib_data["phone"] if lib_data["phone"] else None,
                        "campus": lib_data["campus"],
                        "isRegional": lib_data["is_regional"],
                        "libguideProfileId": lib_data["libguides_id"] if lib_data["libguides_id"] else None,
                        "isActive": True
                    }
                }
            )
            
            stats["librarians_synced"] += 1
            
            # Create subject mappings
            if lib_data["subjects"]:
                print(f"\n  {lib_data['name']} ({lib_data['campus']})")
                
                for subject_name in lib_data["subjects"]:
                    subject_id = subject_map.get(subject_name)
                    
                    if not subject_id:
                        print(f"    ⚠️ Subject not found: {subject_name}")
                        continue
                    
                    # Check if mapping already exists
                    existing = await db.librariansubject.find_first(
                        where={
                            "librarianId": librarian.id,
                            "subjectId": subject_id
                        }
                    )
                    
                    if not existing:
                        await db.librariansubject.create(
                            data={
                                "librarianId": librarian.id,
                                "subjectId": subject_id,
                                "isPrimary": True
                            }
                        )
                        stats["subject_mappings_created"] += 1
                        print(f"    ✅ Mapped to: {subject_name}")
                    else:
                        stats["subject_mappings_existing"] += 1
                        print(f"    ✓ Already mapped: {subject_name}")
            else:
                stats["librarians_without_subjects"].append(lib_data["name"])
        
        # Step 4: Show statistics
        print("\n" + "="*60)
        print("📊 FINAL STATISTICS")
        print("="*60)
        print(f"CSV Rows Processed: {stats['total_rows']}")
        print(f"Librarians Synced: {stats['librarians_synced']}")
        print(f"Unique Subjects: {len(stats['subjects_found'])}")
        print(f"Subject Mappings Created: {stats['subject_mappings_created']}")
        print(f"Subject Mappings Already Existed: {stats['subject_mappings_existing']}")
        print(f"Librarians Without Subjects: {len(stats['librarians_without_subjects'])}")
        
        # Database counts
        total_librarians = await db.librarian.count()
        total_subjects = await db.subject.count()
        total_mappings = await db.librariansubject.count()
        
        print("\n" + "="*60)
        print("📊 DATABASE STATE")
        print("="*60)
        print(f"Total Librarians in DB: {total_librarians}")
        print(f"Total Subjects in DB: {total_subjects}")
        print(f"Total Subject Mappings: {total_mappings}")
        
        # Show some examples
        print("\n" + "="*60)
        print("📝 SAMPLE MAPPINGS")
        print("="*60)
        
        sample_subjects = ["Biology", "Chemistry and Biochemistry", "English", "Business", "Psychology"]
        
        for subject_name in sample_subjects:
            subject = await db.subject.find_first(
                where={"name": subject_name},
                include={
                    "librarians": {
                        "include": {
                            "librarian": True
                        }
                    }
                }
            )
            
            if subject and subject.librarians:
                print(f"\n{subject_name}:")
                for ls in subject.librarians:
                    lib = ls.librarian
                    print(f"  • {lib.name} ({lib.email})")
                    if lib.libguideProfileId:
                        profile_url = f"https://libguides.lib.miamioh.edu/prf.php?account_id={lib.libguideProfileId}"
                        print(f"    Profile: {profile_url}")
            else:
                print(f"\n{subject_name}: No librarians found")
        
        print("\n" + "="*60)
        print("✅ POPULATION COMPLETE!")
        print("="*60)
        print("\n📌 Next Steps:")
        print("1. Test queries like 'Who is my librarian for Biology?'")
        print("2. Test queries like 'Who can help me with Chemistry?'")
        print("3. Verify LibGuide profile URLs are correct")
        
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(populate_mapping())
