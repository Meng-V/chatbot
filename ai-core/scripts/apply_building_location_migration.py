"""
Apply SQL migration to add buildingLocation column to LibrarySpace table.
This script directly applies the SQL migration without using Prisma Migrate.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv('DATABASE_URL')

async def apply_migration():
    """Apply SQL migration to add buildingLocation column."""
    
    print("\n" + "="*60)
    print("APPLYING DATABASE MIGRATION: ADD buildingLocation COLUMN")
    print("="*60 + "\n")
    
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL not found in environment variables")
        return
    
    conn = None
    try:
        print("🔌 Connecting to database...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to database\n")
        
        sql_file = Path(__file__).parent / 'add_building_location_column.sql'
        with open(sql_file, 'r') as f:
            sql = f.read()
        
        print("📝 Executing SQL migration:")
        print("-" * 60)
        print(sql)
        print("-" * 60 + "\n")
        
        await conn.execute(sql)
        
        print("✅ Migration applied successfully!")
        print("✅ buildingLocation column added to LibrarySpace table\n")
        
    except FileNotFoundError:
        print("❌ Error: SQL file not found")
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
    finally:
        if conn:
            await conn.close()
            print("🔌 Disconnected from database\n")

if __name__ == "__main__":
    asyncio.run(apply_migration())
