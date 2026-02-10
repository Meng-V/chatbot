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
        
        # Clear existing data (in reverse order of dependencies)
        await client.libraryspace.delete_many()
        await client.library.delete_many()
        await client.campus.delete_many()
        
        # ==================== CREATE CAMPUSES ====================
        
        oxford = await client.campus.create(
            data={
                "name": "oxford",
                "displayName": "Oxford Campus",
                "isMain": True
            }
        )
        
        hamilton = await client.campus.create(
            data={
                "name": "hamilton",
                "displayName": "Hamilton Campus",
                "isMain": False
            }
        )
        
        middletown = await client.campus.create(
            data={
                "name": "middletown",
                "displayName": "Middletown Campus",
                "isMain": False
            }
        )
        
        # ==================== CREATE LIBRARIES ====================
        
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
                "website": "https://www.lib.miamioh.edu/",
                "isMain": True
            }
        )
        
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
                "website": "https://www.lib.miamioh.edu/",
                "isMain": False
            }
        )
        
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
                "website": "https://www.ham.miamioh.edu/library/",
                "isMain": True
            }
        )
        
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
                "website": "https://www.mid.miamioh.edu/library/",
                "isMain": True
            }
        )
        
        # ==================== CREATE LIBRARY SPACES ====================
        
        # Spaces inside King Library
        # NOTE: These spaces have hours but NO RESERVABLE ROOMS
        # Only libcalLocationId is set (for hours checking), no libcalBuildingId
        makerspace = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "Makerspace",
                "displayName": "Makerspace",
                "shortName": "makerspace",
                "buildingLocation": "Third floor, room 303",  # Real physical location in King Library
                "libcalLocationId": "11904",  # For hours API only - no reservable rooms
                "phone": "(513) 529-2871",
                "email": "create@miamioh.edu",
                "website": "https://libguides.lib.miamioh.edu/create/makerspace",
                "spaceType": "service"
            }
        )
        
        special_collections = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "Special Collections",
                "displayName": "Walter Havighurst Special Collections",
                "shortName": "special collections",
                "buildingLocation": "Third floor",  # Real physical location in King Library
                "libcalLocationId": "8424",   # For hours API only - no reservable rooms
                "phone": "(513) 529-3323",
                "email": "SpecColl@MiamiOH.edu",
                "website": "https://spec.lib.miamioh.edu/home/",
                "spaceType": "collection"
            }
        )
        
        archives = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "University Archives",
                "displayName": "University Archives & Preservation",
                "shortName": "archives",
                "buildingLocation": "Third floor",  # Shares office with Special Collections
                "libcalLocationId": "8424_archives",  # Shares hours with Special Collections
                "phone": "(513) 529-6720",
                "email": "Archives@MiamiOH.edu",
                "website": "https://spec.lib.miamioh.edu/home/",
                "spaceType": "collection"
            }
        )
        
        digital_collections = await client.libraryspace.create(
            data={
                "libraryId": king.id,
                "name": "Digital Collections",
                "displayName": "Digital Collections",
                "shortName": "digital collections",
                "libcalLocationId": "digital_collections",  # No LibCal hours - online resource
                "website": "https://www.lib.miamioh.edu/digital-collections/",
                "spaceType": "collection"
            }
        )
        
        print("✅ Library location hierarchy seeded successfully.")
        
    except Exception as e:
        print(f"❌ Error seeding locations: {str(e)}")
        raise
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(seed_locations())
