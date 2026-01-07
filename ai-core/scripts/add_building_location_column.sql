-- Add buildingLocation column to LibrarySpace table
ALTER TABLE "LibrarySpace" ADD COLUMN IF NOT EXISTS "buildingLocation" TEXT;

-- Add comment
COMMENT ON COLUMN "LibrarySpace"."buildingLocation" IS 'Physical location within building (e.g., "Third floor", "Lower level")';
