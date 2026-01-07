"""Add buildingLocation field to Makerspace and Special Collections.

This script updates existing LibrarySpace records to add the correct physical location.

Run: python -m scripts.add_building_location
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


async def add_building_locations():
    """Add buildingLocation to Makerspace and Special Collections."""
    client = get_prisma_client()
    
    try:
        await client.connect()
        print("🔌 Connected to database")
        print("\n" + "="*60)
        print("ADDING BUILDING LOCATIONS TO LIBRARY SPACES")
        print("="*60)
        
        # Update Makerspace
        makerspace = await client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": "makerspace", "mode": "insensitive"}},
                    {"name": {"contains": "makerspace", "mode": "insensitive"}}
                ]
            }
        )
        
        if makerspace:
            updated_makerspace = await client.libraryspace.update(
                where={"id": makerspace.id},
                data={"buildingLocation": "Third floor"}
            )
            print(f"\n✅ Updated: {makerspace.displayName}")
            print(f"   Location: Third floor of King Library")
        else:
            print("\n⚠️  Makerspace not found in database")
        
        # Update Special Collections
        special_collections = await client.libraryspace.find_first(
            where={
                "OR": [
                    {"shortName": {"contains": "special collections", "mode": "insensitive"}},
                    {"name": {"contains": "special collections", "mode": "insensitive"}}
                ]
            }
        )
        
        if special_collections:
            updated_sc = await client.libraryspace.update(
                where={"id": special_collections.id},
                data={"buildingLocation": "Third floor"}
            )
            print(f"\n✅ Updated: {special_collections.displayName}")
            print(f"   Location: Third floor of King Library")
        else:
            print("\n⚠️  Special Collections not found in database")
        
        print("\n" + "="*60)
        print("📊 SUMMARY")
        print("="*60)
        print("Both spaces are now marked as located on the Third floor")
        print("Chatbot will use this accurate location information")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        raise
    finally:
        await client.disconnect()
        print("\n🔌 Disconnected from database")


if __name__ == "__main__":
    asyncio.run(add_building_locations())
