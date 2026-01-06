"""
Comprehensive Librarian-Subject Mapping Sync

This script syncs ALL librarian-subject mappings from the authoritative source:
https://www.lib.miamioh.edu/about/organization/liaisons/

It also adds special services:
- Special Collections → Jacqueline Johnson
- Makerspace (Oxford) → Sarah Nagle
- Makerspace (Middletown) → URL reference

Run: cd ai-core && .venv/bin/python -m scripts.sync_all_librarian_subject_mappings
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma
from typing import Dict, List, Set

# Load environment
root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Complete mapping from https://www.lib.miamioh.edu/about/organization/liaisons/
# Format: Subject -> List of librarian emails
SUBJECT_LIBRARIAN_MAPPING = {
    "Accountancy": ["freede@miamioh.edu"],
    "American Studies": ["presnejl@miamioh.edu"],
    "Anthropology": ["morgan55@miamioh.edu"],
    "Architecture & Interior Design": ["hillessa@miamioh.edu"],
    "Art": ["hillessa@miamioh.edu"],
    "Asian/Asian-American Studies": ["gibsonke@miamioh.edu"],
    "Biology": ["boehmemv@miamioh.edu"],
    "Black World Studies": ["gibsonke@miamioh.edu"],
    "Business Legal Studies": ["morgan55@miamioh.edu"],
    "Business": ["freede@miamioh.edu", "morgan55@miamioh.edu"],
    "Chemical, Paper, and Biomedical Engineering": ["adamsk3@miamioh.edu"],
    "Chemistry and Biochemistry": ["adamsk3@miamioh.edu"],
    "Classics, Latin, and Greek": ["witherre@miamioh.edu"],
    "Computer Science and Software Engineering": ["justusra@miamioh.edu"],
    "Criminology": ["jaskowma@miamioh.edu"],
    "Economics": ["freede@miamioh.edu"],
    "Education": ["morgan55@miamioh.edu"],
    "Educational Leadership": ["spraetj@miamioh.edu"],
    "Educational Psychology": ["spraetj@miamioh.edu"],
    "Electrical and Computer Engineering": ["justusra@miamioh.edu"],
    "English": ["dahlqumj@miamioh.edu"],
    "Entrepreneurship": ["freede@miamioh.edu", "morgan55@miamioh.edu"],
    "Environmental Sciences": ["boehmemv@miamioh.edu"],
    "Family Science and Social Work": ["jaskowma@miamioh.edu"],
    "Finance": ["freede@miamioh.edu"],
    "French": ["gibsonke@miamioh.edu"],
    "Geography": ["adamsk3@miamioh.edu"],
    "Geology": ["adamsk3@miamioh.edu"],
    "German": ["gibsonke@miamioh.edu"],
    "Gerontology": ["jaskowma@miamioh.edu"],
    "Government Information and Law": ["presnejl@miamioh.edu"],
    "History": ["presnejl@miamioh.edu"],
    "Individualized Studies - Western Program": ["gibsonke@miamioh.edu"],
    "Information Systems & Analytics": ["justusra@miamioh.edu"],
    "Interactive Media Studies / Emerging Technology in Business and Design": ["hillessa@miamioh.edu"],
    "International Studies": ["gibsonke@miamioh.edu"],
    "Italian": ["gibsonke@miamioh.edu"],
    "Juvenile Literature": ["morgan55@miamioh.edu"],
    "Kinesiology, Nutrition, and Health": ["boehmemv@miamioh.edu"],
    "Latin American Studies": ["gibsonke@miamioh.edu"],
    "Law": ["presnejl@miamioh.edu"],
    "Management": ["freede@miamioh.edu"],
    "Marketing": ["freede@miamioh.edu", "morgan55@miamioh.edu"],
    "Mathematics": ["justusra@miamioh.edu"],
    "Mechanical and Manufacturing Engineering": ["adamsk3@miamioh.edu"],
    "Media, Journalism, and Film": ["dahlqumj@miamioh.edu"],
    "Microbiology": ["boehmemv@miamioh.edu"],
    "Middle Eastern and Islamic Studies": ["gibsonke@miamioh.edu"],
    "Military Studies": ["crosbylm@miamioh.edu"],
    "Music": ["zaslowbj@miamioh.edu"],
    "Neuroscience": ["boehmemv@miamioh.edu"],
    "Nursing": ["boehmemv@miamioh.edu"],
    "Philosophy": ["witherre@miamioh.edu"],
    "Physician Associate Studies": ["jaskowma@miamioh.edu"],
    "Physics": ["adamsk3@miamioh.edu"],
    "Political Science": ["presnejl@miamioh.edu"],
    "Psychology": ["jaskowma@miamioh.edu"],
    "Religion": ["witherre@miamioh.edu"],
    "Sociology": ["jaskowma@miamioh.edu"],
    "Spanish and Portuguese": ["gibsonke@miamioh.edu"],
    "Speech Pathology and Audiology": ["jaskowma@miamioh.edu"],
    "Sports Leadership and Management": ["revellaa@miamioh.edu"],
    "Statistics": ["justusra@miamioh.edu"],
    "Student Affairs": ["crosbylm@miamioh.edu"],
    "Teacher Education": ["morgan55@miamioh.edu"],
    "Theater": ["hillessa@miamioh.edu"],
    "Women's, Gender and Sexuality Studies": ["presnejl@miamioh.edu"],
}

# Special services mapping
SPECIAL_SERVICES = {
    "Special Collections": {
        "librarian_email": "johnsoj@miamioh.edu",
        "description": "Special Collections and Archives"
    },
    "Makerspace": {
        "librarian_email": "pricesb@miamioh.edu",
        "description": "Makerspace (Oxford Campus)",
        "url": "https://libguides.lib.miamioh.edu/create/makerspace",
        "hours": "Monday - Friday 9 a.m. - 5 p.m., Closed Sunday",
        "location": "Third floor of King Library",
        "contact": "create@miamioh.edu, (513) 529-2871"
    },
    "Makerspace Middletown": {
        "description": "Makerspace (Middletown Campus)",
        "url": "https://libguides.lib.miamioh.edu/middletown_tec_lab/home"
    }
}


async def ensure_subject_exists(db: Prisma, subject_name: str) -> str:
    """Ensure a subject exists in the database, return its ID."""
    subject = await db.subject.find_first(where={"name": subject_name})
    
    if not subject:
        print(f"  + Creating subject: {subject_name}")
        subject = await db.subject.create(data={"name": subject_name})
    
    return subject.id


async def sync_mappings():
    """Sync all librarian-subject mappings from the liaisons webpage."""
    db = Prisma()
    await db.connect()
    
    try:
        print("="*80)
        print("COMPREHENSIVE LIBRARIAN-SUBJECT MAPPING SYNC")
        print("="*80)
        print(f"Source: https://www.lib.miamioh.edu/about/organization/liaisons/")
        print(f"Subjects to sync: {len(SUBJECT_LIBRARIAN_MAPPING)}")
        print(f"Special services: {len(SPECIAL_SERVICES)}")
        
        # Step 1: Ensure all subjects exist
        print(f"\n{'='*80}")
        print("STEP 1: Ensuring all subjects exist")
        print('='*80)
        
        subject_ids = {}
        for subject_name in SUBJECT_LIBRARIAN_MAPPING.keys():
            subject_id = await ensure_subject_exists(db, subject_name)
            subject_ids[subject_name] = subject_id
        
        # Also create special service subjects
        for service_name in SPECIAL_SERVICES.keys():
            subject_id = await ensure_subject_exists(db, service_name)
            subject_ids[service_name] = subject_id
        
        print(f"\n✅ {len(subject_ids)} subjects ready")
        
        # Step 2: Get all librarians by email
        print(f"\n{'='*80}")
        print("STEP 2: Loading librarian records")
        print('='*80)
        
        all_emails = set()
        for emails in SUBJECT_LIBRARIAN_MAPPING.values():
            all_emails.update(emails)
        
        # Add special service librarians
        for service_data in SPECIAL_SERVICES.values():
            if "librarian_email" in service_data:
                all_emails.add(service_data["librarian_email"])
        
        librarians = await db.librarian.find_many(
            where={"email": {"in": list(all_emails)}}
        )
        
        librarian_map = {lib.email: lib for lib in librarians}
        print(f"✅ Loaded {len(librarian_map)} librarians")
        
        # Check for missing librarians
        missing_emails = all_emails - set(librarian_map.keys())
        if missing_emails:
            print(f"\n⚠️ WARNING: {len(missing_emails)} librarian(s) not found in database:")
            for email in missing_emails:
                print(f"   - {email}")
        
        # Step 3: Clear old mappings for these subjects
        print(f"\n{'='*80}")
        print("STEP 3: Clearing old mappings")
        print('='*80)
        
        subject_id_list = list(subject_ids.values())
        deleted = await db.librariansubject.delete_many(
            where={"subjectId": {"in": subject_id_list}}
        )
        print(f"✅ Removed {deleted} old mappings")
        
        # Step 4: Create new mappings
        print(f"\n{'='*80}")
        print("STEP 4: Creating new mappings from liaisons webpage")
        print('='*80)
        
        mappings_created = 0
        mappings_skipped = 0
        
        for subject_name, librarian_emails in SUBJECT_LIBRARIAN_MAPPING.items():
            subject_id = subject_ids[subject_name]
            
            print(f"\n{subject_name}:")
            for email in librarian_emails:
                if email not in librarian_map:
                    print(f"  ⚠️ Skipped: {email} (not found)")
                    mappings_skipped += 1
                    continue
                
                librarian = librarian_map[email]
                
                # Create mapping
                await db.librariansubject.create(
                    data={
                        "librarianId": librarian.id,
                        "subjectId": subject_id,
                        "isPrimary": True
                    }
                )
                
                print(f"  ✅ {librarian.name} ({email})")
                mappings_created += 1
        
        # Step 5: Add special services
        print(f"\n{'='*80}")
        print("STEP 5: Adding special services")
        print('='*80)
        
        # Special Collections → Jacqueline Johnson
        if "Special Collections" in subject_ids and "johnsoj@miamioh.edu" in librarian_map:
            jackie = librarian_map["johnsoj@miamioh.edu"]
            await db.librariansubject.create(
                data={
                    "librarianId": jackie.id,
                    "subjectId": subject_ids["Special Collections"],
                    "isPrimary": True
                }
            )
            print(f"\n✅ Special Collections → Jacqueline Johnson")
            print(f"   {jackie.name} ({jackie.email})")
            if jackie.libguideProfileId:
                print(f"   Profile: https://libguides.lib.miamioh.edu/prf.php?account_id={jackie.libguideProfileId}")
            mappings_created += 1
        
        # Makerspace (Oxford) → Sarah Nagle
        if "Makerspace" in subject_ids and "pricesb@miamioh.edu" in librarian_map:
            sarah = librarian_map["pricesb@miamioh.edu"]
            await db.librariansubject.create(
                data={
                    "librarianId": sarah.id,
                    "subjectId": subject_ids["Makerspace"],
                    "isPrimary": True
                }
            )
            print(f"\n✅ Makerspace (Oxford) → Sarah Nagle")
            print(f"   {sarah.name} ({sarah.email})")
            if sarah.libguideProfileId:
                print(f"   Profile: https://libguides.lib.miamioh.edu/prf.php?account_id={sarah.libguideProfileId}")
            print(f"   URL: {SPECIAL_SERVICES['Makerspace']['url']}")
            print(f"   Hours: {SPECIAL_SERVICES['Makerspace']['hours']}")
            print(f"   Location: {SPECIAL_SERVICES['Makerspace']['location']}")
            print(f"   Contact: {SPECIAL_SERVICES['Makerspace']['contact']}")
            mappings_created += 1
        
        # Makerspace Middletown (no specific librarian, just URL)
        print(f"\n✅ Makerspace (Middletown)")
        print(f"   URL: {SPECIAL_SERVICES['Makerspace Middletown']['url']}")
        
        # Summary
        print(f"\n{'='*80}")
        print("SYNC COMPLETE")
        print('='*80)
        print(f"Subjects synced: {len(subject_ids)}")
        print(f"Mappings created: {mappings_created}")
        print(f"Mappings skipped: {mappings_skipped}")
        
        # Verification samples
        print(f"\n{'='*80}")
        print("VERIFICATION SAMPLES")
        print('='*80)
        
        sample_subjects = ["Business", "Marketing", "Biology", "Special Collections", "Makerspace"]
        
        for subject_name in sample_subjects:
            if subject_name not in subject_ids:
                continue
            
            subject = await db.subject.find_first(
                where={"id": subject_ids[subject_name]},
                include={
                    "librarians": {
                        "include": {"librarian": True}
                    }
                }
            )
            
            if subject and subject.librarians:
                print(f"\n{subject_name}:")
                for ls in subject.librarians:
                    lib = ls.librarian
                    print(f"  • {lib.name} ({lib.email})")
                    if lib.libguideProfileId:
                        print(f"    Profile: https://libguides.lib.miamioh.edu/prf.php?account_id={lib.libguideProfileId}")
        
        print(f"\n{'='*80}")
        print("✅ ALL MAPPINGS SYNCED SUCCESSFULLY")
        print('='*80)
        
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(sync_mappings())
