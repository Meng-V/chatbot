"""
Check Erica Freed's LibGuide Profile ID

Run: cd ai-core && .venv/bin/python -m scripts.check_erica_libguide_id
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv
from prisma import Prisma

root_dir = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=root_dir / ".env")


async def check_librarian():
    db = Prisma()
    await db.connect()
    
    try:
        # Check Erica Freed
        erica = await db.librarian.find_first(
            where={"email": "freede@miamioh.edu"}
        )
        
        if erica:
            print("Erica Freed:")
            print(f"  Name: {erica.name}")
            print(f"  Email: {erica.email}")
            print(f"  LibGuide Profile ID: {erica.libguideProfileId}")
            print(f"  Title: {erica.title}")
        
        # Check Abigail Morgan
        abigail = await db.librarian.find_first(
            where={"email": "morgan55@miamioh.edu"}
        )
        
        if abigail:
            print("\nAbigail Morgan:")
            print(f"  Name: {abigail.name}")
            print(f"  Email: {abigail.email}")
            print(f"  LibGuide Profile ID: {abigail.libguideProfileId}")
            print(f"  Title: {abigail.title}")
        
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(check_librarian())
