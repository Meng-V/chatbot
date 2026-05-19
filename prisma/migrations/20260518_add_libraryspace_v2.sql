-- =============================================================================
-- ADDITIVE: create the v2 LibrarySpace truth table (plan §8).
--
-- WHY: the cross-campus "service not at this building" guard
-- (orchestrator `lookup_service_availability`, refusal trigger
-- SERVICE_NOT_AT_BUILDING) is the load-bearing deterministic defense
-- against the "MakerSpace at Hamilton" hallucination class. It needs a
-- per-(campus, library) services truth table. The live schema has none:
--   "Library"      = 4 buildings, no campus, no SWORD/Wertz
--   "LibrarySpace" = 4 King sub-spaces, services/equipment empty
-- and that legacy "LibrarySpace" is still read by the v1 booking path
-- during the 8-week rollout, so it must NOT be repurposed.
--
-- DESIGN: a NEW, FLAT table `LibrarySpace_v2`, exactly the shape
-- `ai-core/scripts/seed_library_spaces_v2.py` already targets
-- (`db.libraryspace_v2`, upsert key (campus, library)). Same risk
-- profile as 20260514 / 20260516 hotfixes but LOWER: this creates a
-- brand-new table and touches no existing column or row.
--
-- WHAT THIS DOES (idempotent -- safe to re-run):
--   * CREATE TABLE IF NOT EXISTS "LibrarySpace_v2"
--   * CREATE UNIQUE INDEX IF NOT EXISTS on (campus, library)
--   All additive. No table rewrite, no backfill, no NOT-NULL on
--   existing data (the table is new and empty until the seed runs).
--
-- WHAT THIS DOES NOT DO:
--   * Touch "LibrarySpace", "Library", or any v1 booking path.
--   * Backfill / migrate any row.
--
-- ROLLBACK (legacy unaffected):  DROP TABLE IF EXISTS "LibrarySpace_v2";
--
-- `id` has no DB default: every insert goes through Prisma, whose
-- `@default(uuid())` supplies it client-side (avoids depending on a
-- pgcrypto/pg-version-specific gen_random_uuid()). Column names are
-- snake_case to match seed_library_spaces_v2.py's asdict() keys
-- 1:1; createdAt/updatedAt are camelCase to match the Prisma
-- convention used by the legacy "LibrarySpace" table.
--
-- APPLY (one of):
--   psql "$DATABASE_URL" -f prisma/migrations/20260518_add_libraryspace_v2.sql
--   # or, from ai-core/ with the venv:
--   VIRTUAL_ENV=.../.venv .venv/bin/python -m prisma db execute \
--     --file ../prisma/migrations/20260518_add_libraryspace_v2.sql \
--     --schema ../prisma/schema.prisma
-- (This run applied it via the verified Prisma execute_raw connection,
--  statement-by-statement, each idempotent.)
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS "LibrarySpace_v2" (
    "id"               TEXT        PRIMARY KEY,
    "library"          TEXT        NOT NULL,
    "campus"           TEXT        NOT NULL,
    "name"             TEXT        NOT NULL,
    "building_role"    TEXT        NOT NULL,
    "address"          TEXT,
    "phone"            TEXT,
    "libcal_id"        TEXT,
    "capacity"         INTEGER,
    "equipment"        TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    "services_offered" TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    "hours_source"     TEXT,
    "source_url"       TEXT,
    "createdAt"        TIMESTAMP   NOT NULL DEFAULT now(),
    "updatedAt"        TIMESTAMP   NOT NULL DEFAULT now()
);

-- The seed upserts on (campus, library); Prisma's compound-unique
-- where-key is `campus_library` (field order in @@unique). A UNIQUE
-- index permits this; IF NOT EXISTS keeps the whole file idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS "LibrarySpace_v2_campus_library_key"
    ON "LibrarySpace_v2" ("campus", "library");

COMMIT;
