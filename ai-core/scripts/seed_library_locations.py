"""Seed script to populate library location hierarchy in the database.

This script migrates LibCal location IDs from .env to the database structure:
- Campus (Oxford, Hamilton, Middletown)
- Library (King, Art & Architecture, Rentschler, Gardner-Harvey)
- LibrarySpace (Maker Space, Special Collections, etc.)

Run: python -m scripts.seed_library_locations
"""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent directory
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.prisma_client import get_prisma_client


async def seed_locations():
    """Populate the library location hierarchy."""
    client = get_prisma_client()
    
    try:
        await client.connect()
        print("🔌 Connected to database")
        
        # Clear existing data (in reverse order of dependencies)
        print("\n🧹 Clearing existing location data...")
        await client.libraryspace.delete_many()
        await client.library.delete_many()
        await client.campus.delete_many()
        print("✅ Existing data cleared")
        
        # ==================== CREATE CAMPUSES ====================
        print("\n🏫 Creating campuses...")
        
        oxford = await client.campus.create(
            data={
                "name": "oxford",
                "displayName": "Oxford Campus",
                "isMain": True
            }
        )
        print(f"  ✓ {oxford.displayName}")
        
        hamilton = await client.campus.create(
            data={
                "name": "hamilton",
                "displayName": "Hamilton Campus",
                "isMain": False
            }
        )
        print(f"  ✓ {hamilton.displayName}")
        
        middletown = await client.campus.create(
            data={
                "name": "middletown",
                "displayName": "Middletown Campus",
                "isMain": False
            }
        )
        print(f"  ✓ {middletown.displayName}")
        
        # ==================== CREATE LIBRARIES ====================
        print("\n📚 Creating libraries...")
        
        # Oxford Campus Libraries
        king = await client.library.create(
            data={
                "campusId": oxford.id,
                "name": "King Library",
                "displayName": "Edgar W. King Library",
                "shortName": "king",
                "libcalBuildingId": "2047",  # For reservations (Image 2)
                "libcalLocationId": "8113",   # For hours API (Image 1)
                "phone": "513-529-4141",
                "address": "151 S. Campus Ave, Oxford, OH 45056",
                "isMain": True
            }
        )
        print(f"  ✓ {king.displayName} (Reservations: {king.libcalBuildingId}, Hours: {king.libcalLocationId})")
        print(f"     📞 {king.phone} | 📍 {king.address}")
        
        art = await client.library.create(
            data={
                "campusId": oxford.id,
                "name": "Art & Architecture Library",
                "displayName": "Wertz Art & Architecture Library",
                "shortName": "art",
                "libcalBuildingId": "4089",  # For reservations (Image 2)
                "libcalLocationId": "8116",   # For hours API (Image 1)
                "phone": "513-529-6638",
                "address": "Alumni Hall, Oxford, OH 45056",
                "isMain": False
            }
        )
        print(f"  ✓ {art.displayName} (Reservations: {art.libcalBuildingId}, Hours: {art.libcalLocationId})")
        print(f"     📞 {art.phone} | 📍 {art.address}")
        
        # Hamilton Campus Library
        rentschler = await client.library.create(
            data={
                "campusId": hamilton.id,
                "name": "Rentschler Library",
                "displayName": "Rentschler Library",
                "shortName": "rentschler",
                "libcalBuildingId": "4792",  # For reservations (Image 2)
                "libcalLocationId": "9226",   # For hours API (Image 1)
                "phone": "(513) 785-3235",
                "address": "1601 University Blvd, Hamilton, Ohio 45011",
                "isMain": True
            }
        )
        print(f"  ✓ {rentschler.displayName} (Reservations: {rentschler.libcalBuildingId}, Hours: {rentschler.libcalLocationId})")
        print(f"     📞 {rentschler.phone} | 📍 {rentschler.address}")
        
        # Middletown Campus Library
        gardner_harvey = await client.library.create(
            data={
                "campusId": middletown.id,
                "name": "Gardner-Harvey Library",
                "displayName": "Gardner-Harvey Library",
                "shortName": "gardner-harvey",
                "libcalBuildingId": "4845",  # For reservations (Image 2)
                "libcalLocationId": "9227",   # For hours API (Image 1)
                "phone": "(513) 727-3222",
                "address": "4200 N. University Blvd., Middletown, Ohio 45042",
                "isMain": True
            }
        )
        print(f"  ✓ {gardner_harvey.displayName} (Reservations: {gardner_harvey.libcalBuildingId}, Hours: {gardner_harvey.libcalLocationId})")
        print(f"     📞 {gardner_harvey.phone} | 📍 {gardner_harvey.address}")
        
        # ==================== CREATE LIBRARY SPACES ====================
        print("\n🏛️  Creating library spaces...")
        
        # Spaces inside King Library
        # NOTE: These spaces have hours but NO RESERVABLE ROOMS
        # Only libcalLocationId is set (for hours checking), no libcalBuildingId
        makerspace = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "Makerspace",
                "displayName": "Makerspace",
                "shortName": "makerspace",
                "libcalLocationId": "11904",  # For hours API only - no reservable rooms
                "spaceType": "service"
            }
        )
        print(f"  ✓ {makerspace.displayName} (Hours: {makerspace.libcalLocationId}, No reservations) - inside {king.name}")
        
        special_collections = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "Special Collections & University Archives",
                "displayName": "Walter Havighurst Special Collections & University Archives",
                "shortName": "special collections",
                "libcalLocationId": "8424",   # For hours API only - no reservable rooms
                "spaceType": "collection"
            }
        )
        print(f"  ✓ {special_collections.displayName} (Hours: {special_collections.libcalLocationId}, No reservations) - inside {king.name}")
        
        # ==================== SUMMARY ====================
        print("\n" + "="*60)
        print("📊 LOCATION HIERARCHY SUMMARY")
        print("="*60)
        
        campuses = await client.campus.find_many(
            include={
                "libraries": {
                    "include": {
                        "spaces": True
                    }
                }
            }
        )
        
        for campus in campuses:
            main_indicator = " (FLAGSHIP)" if campus.isMain else ""
            print(f"\n🏫 {campus.displayName}{main_indicator}")
            for library in campus.libraries:
                lib_main = " (Main)" if library.isMain else ""
                print(f"  📚 {library.displayName}{lib_main}")
                print(f"     Building ID: {library.libcalBuildingId}, Location ID: {library.libcalLocationId}")
                if library.spaces:
                    for space in library.spaces:
                        print(f"       🏛️  {space.displayName} (ID: {space.libcalLocationId})")
        
        print("\n✅ Library location hierarchy seeded successfully!")
        print("\n📝 Next steps:")
        print("   1. Run: prisma generate (to update Python client)")
        print("   2. Update code to use database instead of .env variables")
        print("   3. Remove LibCal location IDs from .env file")
        
    except Exception as e:
        print(f"\n❌ Error seeding locations: {str(e)}")
        raise
    finally:
        await client.disconnect()
        print("\n🔌 Disconnected from database")


if __name__ == "__main__":
    asyncio.run(seed_locations())
