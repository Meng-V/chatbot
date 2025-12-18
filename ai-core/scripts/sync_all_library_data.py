"""
Full Library Data Sync Orchestrator

Runs all sync scripts in the correct order:
1. MyGuide Subjects (subjects, course codes, dept codes)
2. LibGuides (guide pages and URLs)
3. Staff Directory (librarian contacts and subject mappings)

Run: python scripts/sync_all_library_data.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sync_myguide_subjects import main as sync_myguide
from scripts.sync_libguides import main as sync_libguides
from scripts.sync_staff_directory import main as sync_staff


async def main():
    """Run all sync scripts in order."""
    print("=" * 60)
    print("🚀 FULL LIBRARY DATA SYNC")
    print("=" * 60)
    print()
    
    try:
        # Step 1: Sync MyGuide subjects and course codes
        print("\n" + "=" * 60)
        print("STEP 1: MyGuide Subjects")
        print("=" * 60)
        await sync_myguide()
        
        # Step 2: Sync LibGuides
        print("\n" + "=" * 60)
        print("STEP 2: LibGuides")
        print("=" * 60)
        await sync_libguides()
        
        # Step 3: Sync Staff Directory
        print("\n" + "=" * 60)
        print("STEP 3: Staff Directory")
        print("=" * 60)
        await sync_staff()
        
        print("\n" + "=" * 60)
        print("✅ FULL SYNC COMPLETE!")
        print("=" * 60)
        print()
        print("Database is now up to date with:")
        print("  ✓ MyGuide subjects and course codes")
        print("  ✓ LibGuide pages and URLs")
        print("  ✓ Librarian contacts and subject mappings")
        print()
        
    except Exception as e:
        print(f"\n❌ Sync failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
