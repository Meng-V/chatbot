"""
Sync Subject Librarian Liaisons from Website

This script ensures all librarian-subject mappings from the official liaisons page
are properly stored in the database.

Source: https://www.lib.miamioh.edu/about/organization/liaisons/

Run: python scripts/sync_liaisons_from_website.py
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Complete liaisons data from https://www.lib.miamioh.edu/about/organization/liaisons/
# Format: {subject_name: [librarian_emails]}
LIAISONS_DATA = {
    "Accountancy": ["freedea@miamioh.edu"],
    "American Studies": ["presnejl@miamioh.edu"],
    "Anthropology": ["morgana3@miamioh.edu"],
    "Architecture & Interior Design": ["hilless@miamioh.edu"],
    "Art": ["hilless@miamioh.edu"],
    "Asian/Asian-American Studies": ["gibsonkr@miamioh.edu"],
    "Biology": ["boehmemv@miamioh.edu"],
    "Black World Studies": ["gibsonkr@miamioh.edu"],
    "Business": ["freedea@miamioh.edu", "morgana3@miamioh.edu"],
    "Business Legal Studies": ["morgana3@miamioh.edu"],
    "Chemical, Paper, and Biomedical Engineering": ["adamskk@miamioh.edu"],
    "Chemistry and Biochemistry": ["adamskk@miamioh.edu"],
    "Classics, Latin, and Greek": ["obrier@miamioh.edu"],  # Rob O'Brien Withers
    "Computer Science and Software Engineering": ["justusra@miamioh.edu"],
    "Criminology": ["jaskowma@miamioh.edu"],
    "Economics": ["freedea@miamioh.edu"],
    "Education": ["morgana3@miamioh.edu"],
    "Educational Leadership": ["spraetjr@miamioh.edu"],
    "Educational Psychology": ["spraetjr@miamioh.edu"],
    "Electrical and Computer Engineering": ["justusra@miamioh.edu"],
    "English": ["dahlqumw@miamioh.edu"],
    "Entrepreneurship": ["freedea@miamioh.edu", "morgana3@miamioh.edu"],
    "Environmental Sciences": ["boehmemv@miamioh.edu"],
    "Family Science and Social Work": ["jaskowma@miamioh.edu"],
    "Finance": ["freedea@miamioh.edu"],
    "French": ["gibsonkr@miamioh.edu"],
    "Geography": ["adamskk@miamioh.edu"],
    "Geology": ["adamskk@miamioh.edu"],
    "German": ["gibsonkr@miamioh.edu"],
    "Gerontology": ["jaskowma@miamioh.edu"],
    "Government Information and Law": ["presnejl@miamioh.edu"],
    "History": ["presnejl@miamioh.edu"],
    "Individualized Studies - Western Program": ["gibsonkr@miamioh.edu"],
    "Information Systems & Analytics": ["justusra@miamioh.edu"],
    "Interactive Media Studies / Emerging Technology in Business and Design": ["hilless@miamioh.edu"],
    "International Studies": ["gibsonkr@miamioh.edu"],
    "Italian": ["gibsonkr@miamioh.edu"],
    "Juvenile Literature": ["morgana3@miamioh.edu"],
    "Kinesiology, Nutrition, and Health": ["boehmemv@miamioh.edu"],
    "Latin American Studies": ["gibsonkr@miamioh.edu"],
    "Law": ["presnejl@miamioh.edu"],
    "Management": ["freedea@miamioh.edu"],
    "Marketing": ["freedea@miamioh.edu", "morgana3@miamioh.edu"],
    "Mathematics": ["justusra@miamioh.edu"],
    "Mechanical and Manufacturing Engineering": ["adamskk@miamioh.edu"],
    "Media, Journalism, and Film": ["dahlqumw@miamioh.edu"],
    "Microbiology": ["boehmemv@miamioh.edu"],
    "Middle Eastern and Islamic Studies": ["gibsonkr@miamioh.edu"],
    "Military Studies": ["birkenla@miamioh.edu"],  # Laura Birkenhauer
    "Music": ["zaslowbj@miamioh.edu"],
    "Neuroscience": ["boehmemv@miamioh.edu"],
    "Nursing": ["boehmemv@miamioh.edu"],
    "Philosophy": ["obrier@miamioh.edu"],  # Rob O'Brien Withers
    "Physician Associate Studies": ["jaskowma@miamioh.edu"],
    "Physics": ["adamskk@miamioh.edu"],
    "Political Science": ["presnejl@miamioh.edu"],
    "Psychology": ["jaskowma@miamioh.edu"],
    "Religion": ["obrier@miamioh.edu"],  # Rob O'Brien Withers
    "Sociology": ["jaskowma@miamioh.edu"],
    "Spanish and Portuguese": ["gibsonkr@miamioh.edu"],
    "Speech Pathology and Audiology": ["jaskowma@miamioh.edu"],
    "Sports Leadership and Management": ["revellam@miamioh.edu"],
    "Statistics": ["justusra@miamioh.edu"],
    "Student Affairs": ["birkenla@miamioh.edu"],  # Laura Birkenhauer
    "Teacher Education": ["morgana3@miamioh.edu"],
    "Theater": ["hilless@miamioh.edu"],
    "Women's, Gender and Sexuality Studies": ["presnejl@miamioh.edu"],
}

# Librarian info for creating records if needed
LIBRARIAN_INFO = {
    "boehmemv@miamioh.edu": {"name": "Ginny Boehme", "title": "Science Librarian"},
    "adamskk@miamioh.edu": {"name": "Kristen Adams", "title": "Science & Engineering Librarian"},
    "justusra@miamioh.edu": {"name": "Roger A Justus", "title": "Science & Engineering Librarian"},
    "jaskowma@miamioh.edu": {"name": "Megan Jaskowiak", "title": "Health & Social Sciences Librarian"},
    "presnejl@miamioh.edu": {"name": "Jenny Presnell", "title": "Humanities & Social Sciences Librarian"},
    "freedea@miamioh.edu": {"name": "Erica Freed", "title": "Business Librarian"},
    "morgana3@miamioh.edu": {"name": "Abigail Morgan", "title": "Education & Social Sciences Librarian"},
    "gibsonkr@miamioh.edu": {"name": "Katie Gibson", "title": "Global & Intercultural Studies Librarian"},
    "dahlqumw@miamioh.edu": {"name": "Mark Dahlquist", "title": "Humanities Librarian"},
    "hilless@miamioh.edu": {"name": "Stefanie Hilles", "title": "Art & Architecture Librarian"},
    "zaslowbj@miamioh.edu": {"name": "Barry Zaslow", "title": "Music Librarian"},
    "spraetjr@miamioh.edu": {"name": "Jaclyn Spraetz", "title": "Education Librarian"},
    "revellam@miamioh.edu": {"name": "Andrew Revelle", "title": "Assessment Librarian"},
    "birkenla@miamioh.edu": {"name": "Laura Birkenhauer", "title": "Student Success Librarian"},
    "obrier@miamioh.edu": {"name": "Rob O'Brien Withers", "title": "Humanities Librarian"},
}


async def sync_liaisons():
    """Sync all liaison mappings to database."""
    db = Prisma()
    await db.connect()
    
    try:
        stats = {
            "subjects_found": 0,
            "subjects_created": 0,
            "subjects_not_found": [],
            "librarians_found": 0,
            "librarians_created": 0,
            "librarians_not_found": [],
            "mappings_created": 0,
            "mappings_existed": 0,
        }
        
        for subject_name, librarian_emails in LIAISONS_DATA.items():
            print(f"\n📚 Processing: {subject_name}")
            
            # Find or create subject
            subject = await db.subject.find_first(where={"name": subject_name})
            
            if not subject:
                # Try case-insensitive search
                all_subjects = await db.subject.find_many()
                for s in all_subjects:
                    if s.name.lower() == subject_name.lower():
                        subject = s
                        break
            
            if not subject:
                # Create the subject
                print(f"   ⚠️ Subject not found, creating: {subject_name}")
                subject = await db.subject.create(data={"name": subject_name})
                stats["subjects_created"] += 1
            else:
                stats["subjects_found"] += 1
            
            # Process each librarian for this subject
            for email in librarian_emails:
                # Clean email
                clean_email = email
                
                librarian = await db.librarian.find_first(where={"email": clean_email})
                
                if not librarian:
                    # Try partial email match
                    email_prefix = clean_email.split("@")[0]
                    all_librarians = await db.librarian.find_many()
                    for lib in all_librarians:
                        if email_prefix in lib.email:
                            librarian = lib
                            break
                
                if not librarian:
                    # Create librarian if we have info
                    info = LIBRARIAN_INFO.get(email, LIBRARIAN_INFO.get(clean_email))
                    if info:
                        print(f"   ⚠️ Librarian not found, creating: {info['name']}")
                        librarian = await db.librarian.create(data={
                            "name": info["name"],
                            "email": clean_email,
                            "title": info["title"],
                            "campus": "Oxford",
                            "isActive": True
                        })
                        stats["librarians_created"] += 1
                    else:
                        stats["librarians_not_found"].append(email)
                        print(f"   ❌ Librarian not found: {email}")
                        continue
                else:
                    stats["librarians_found"] += 1
                
                # Create mapping if it doesn't exist
                existing_mapping = await db.librariansubject.find_first(
                    where={
                        "librarianId": librarian.id,
                        "subjectId": subject.id
                    }
                )
                
                if not existing_mapping:
                    await db.librariansubject.create(data={
                        "librarianId": librarian.id,
                        "subjectId": subject.id,
                        "isPrimary": True
                    })
                    stats["mappings_created"] += 1
                    print(f"   ✅ Mapped {librarian.name} → {subject_name}")
                else:
                    stats["mappings_existed"] += 1
                    print(f"   ✓ Mapping exists: {librarian.name} → {subject_name}")
        
        # Print summary
        print("\n" + "="*60)
        print("📊 SYNC SUMMARY")
        print("="*60)
        print(f"Subjects found: {stats['subjects_found']}")
        print(f"Subjects created: {stats['subjects_created']}")
        print(f"Librarians found: {stats['librarians_found']}")
        print(f"Librarians created: {stats['librarians_created']}")
        print(f"Mappings created: {stats['mappings_created']}")
        print(f"Mappings already existed: {stats['mappings_existed']}")
        
        if stats["subjects_not_found"]:
            print(f"\n⚠️ Subjects not found: {stats['subjects_not_found']}")
        if stats["librarians_not_found"]:
            print(f"\n⚠️ Librarians not found (unique): {list(set(stats['librarians_not_found']))}")
        
        # Final counts
        total_subjects = await db.subject.count()
        total_librarians = await db.librarian.count(where={"isActive": True})
        total_mappings = await db.librariansubject.count()
        
        print(f"\n✅ Final Database State:")
        print(f"   Total Subjects: {total_subjects}")
        print(f"   Total Active Librarians: {total_librarians}")
        print(f"   Total Subject-Librarian Mappings: {total_mappings}")
        
    finally:
        await db.disconnect()


async def verify_critical_subjects():
    """Verify that critical subjects have librarians mapped."""
    db = Prisma()
    await db.connect()
    
    try:
        print("\n" + "="*60)
        print("🔍 VERIFICATION: Critical Subject Mappings")
        print("="*60)
        
        critical_subjects = [
            "Chemistry and Biochemistry",
            "Computer Science and Software Engineering",
            "Business",
            "Psychology",
            "Biology",
            "History",
            "Music",
        ]
        
        for subject_name in critical_subjects:
            subject = await db.subject.find_first(
                where={"name": subject_name},
                include={"librarians": {"include": {"librarian": True}}}
            )
            
            if subject:
                librarians = [ls.librarian.name for ls in subject.librarians if ls.librarian.isActive]
                if librarians:
                    print(f"✅ {subject_name}: {', '.join(librarians)}")
                else:
                    print(f"❌ {subject_name}: NO LIBRARIANS MAPPED!")
            else:
                print(f"❌ {subject_name}: SUBJECT NOT FOUND!")
    
    finally:
        await db.disconnect()


async def main():
    """Main sync function."""
    print("🚀 Starting Liaisons Sync from Website Data")
    print("Source: https://www.lib.miamioh.edu/about/organization/liaisons/\n")
    
    await sync_liaisons()
    await verify_critical_subjects()
    
    print("\n✅ Liaisons Sync Complete!")
    print("\nNext Steps:")
    print("1. Restart the server to load new data")
    print("2. Run retry tests: python scripts/retry_failed_tests.py")


if __name__ == "__main__":
    asyncio.run(main())
