-- =============================================================================
-- HOTFIX: reconcile entity-table column drift in smartchatbot_db.
--
-- DISCOVERED BY: wiring the eval's get_hours/get_room_availability to the
-- legacy LibCal tools. They go through LocationService, which queries
-- "Library" / "LibrarySpace". Every such query 500s with:
--     The column `Library.canonicalId` does not exist in the current database.
--
-- ROOT CAUSE: `20260424160000_rebuild_schema_additions` is recorded as
-- APPLIED in _prisma_migrations, but schema.prisma was later edited to add
-- columns WITHOUT a follow-up migration. Result: schema (and the generated
-- Prisma client, which SELECTs every model column) is ahead of the DB, and
-- `prisma migrate deploy` is a no-op because history says "all applied".
-- This is the same drift family as 20260514_hotfix_pr13_partial_apply.sql.
--
-- CONFIRMED DRIFT (information_schema vs schema.prisma, 2026-05-16):
--   "Library"      missing: canonicalId, servicesOffered, buildingRole, sourceUrl
--   "LibrarySpace" missing: equipment, services, capacity
--   "Campus"       no drift
--
-- WHAT THIS DOES (idempotent -- safe to re-run):
--   * Adds the 4 missing "Library" columns + the canonicalId unique index
--     and plain index that schema.prisma declares (@unique + @@index).
--   * Adds the 3 missing "LibrarySpace" columns.
--   All additive, all nullable or array-defaulted -> ZERO data-loss risk,
--   no table rewrite, no NOT-NULL backfill.
--
-- WHAT THIS DOES NOT DO:
--   * Touch any existing column or row.
--   * Backfill values. canonicalId / servicesOffered / equipment stay
--     NULL/empty until a librarian seeds them (that is data, not schema;
--     a UNIQUE index permits many NULLs in Postgres, so this is safe now).
--   * Affect the running legacy bot (these columns are read by the v2
--     surface; the legacy hours path only needs the query to stop 500ing).
--
-- WHAT IT UNBLOCKS: get_hours, get_room_availability, lookup_space, and the
-- plan §8 servicesOffered "service-not-at-this-building" truth-table.
--
-- BEFORE APPLYING:
--   1. Back up:
--        pg_dump "postgresql://...@ulblwebt04.lib.miamioh.edu/smartchatbot_db?sslmode=require" \
--          > /tmp/smartchatbot_db_pre_drift_hotfix.sql
--   2. Apply (one of):
--        psql "$DATABASE_URL" -f prisma/migrations/20260516_hotfix_entity_schema_drift.sql
--        # or, from ai-core/ with the venv:
--        VIRTUAL_ENV=.../.venv .venv/bin/python -m prisma db execute \
--          --file ../prisma/migrations/20260516_hotfix_entity_schema_drift.sql \
--          --schema ../prisma/schema.prisma
--   3. Re-run the eval; get_hours now reaches LibCal instead of 500ing.
-- =============================================================================

BEGIN;

-- --- Library: 4 missing columns ------------------------------------------
ALTER TABLE "Library" ADD COLUMN IF NOT EXISTS "canonicalId"     TEXT;
ALTER TABLE "Library" ADD COLUMN IF NOT EXISTS "servicesOffered" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "Library" ADD COLUMN IF NOT EXISTS "buildingRole"    TEXT;
ALTER TABLE "Library" ADD COLUMN IF NOT EXISTS "sourceUrl"       TEXT;

-- schema.prisma: canonicalId String? @unique  AND  @@index([canonicalId])
-- A UNIQUE index allows multiple NULLs in Postgres, so it is safe to create
-- before any backfill. IF NOT EXISTS keeps this idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS "Library_canonicalId_key" ON "Library"("canonicalId");
CREATE        INDEX IF NOT EXISTS "Library_canonicalId_idx" ON "Library"("canonicalId");

-- --- LibrarySpace: 3 missing columns -------------------------------------
ALTER TABLE "LibrarySpace" ADD COLUMN IF NOT EXISTS "equipment" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LibrarySpace" ADD COLUMN IF NOT EXISTS "services"  TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE "LibrarySpace" ADD COLUMN IF NOT EXISTS "capacity"  INTEGER;

COMMIT;
