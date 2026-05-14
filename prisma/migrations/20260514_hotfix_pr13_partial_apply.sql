-- =============================================================================
-- HOTFIX: apply only the pieces of PR #13's migration that are missing from
-- smartchatbot_db (the DB had ~70% of the rebuild via an earlier `db push`
-- but never had the migration "applied" through Prisma's migration history).
--
-- WHAT THIS DOES (idempotent -- safe to re-run):
--   * Adds 9 missing columns to "Message"   (intent, scope*, modelUsed,
--                                           confidence, wasRefusal,
--                                           refusalTrigger, citedChunkIds)
--   * Adds 2 missing columns to "ModelTokenUsage" (cachedInputTokens, callSite)
--   * Creates 5 missing tables               (UrlSeen, ChunkProvenance,
--                                           ManualCorrection,
--                                           LibrarianReview, DailyCost)
--   * Creates the indexes + 1 FK that those tables/columns need
--
-- WHAT THIS DOES NOT DO:
--   * Touch any table or column already present in the DB
--   * Drop Building/Room (already gone)
--   * Affect the running legacy bot (none of these surfaces are read by
--     legacy code paths)
--
-- BEFORE APPLYING:
--   1. Take a backup:
--        pg_dump "postgresql://...@ulblwebt04.lib.miamioh.edu/smartchatbot_db?sslmode=require" \
--          > /tmp/smartchatbot_db_pre_hotfix.sql
--   2. Review this file end to end (you're doing that now).
--
-- AFTER APPLYING (one-shot, marks PR #13's migration as resolved in
--                 Prisma's history so future `prisma migrate deploy`
--                 doesn't try to re-apply it):
--        cd /Users/qum/Documents/GitHub/chatbot
--        prisma migrate resolve --applied 20260424160000_rebuild_schema_additions
--
-- VERIFICATION:
--   After running, re-run the Tier 2 smoke -- it should print a row count
--   (probably 0) instead of TableNotFoundError.
-- =============================================================================

BEGIN;

-- --- Column additions on existing tables -------------------------------------
-- All use IF NOT EXISTS (Postgres 9.6+) so re-running is a no-op.

ALTER TABLE "Message"
  ADD COLUMN IF NOT EXISTS "citedChunkIds"  TEXT[]  DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS "confidence"     TEXT,
  ADD COLUMN IF NOT EXISTS "intent"         TEXT,
  ADD COLUMN IF NOT EXISTS "modelUsed"      TEXT,
  ADD COLUMN IF NOT EXISTS "refusalTrigger" TEXT,
  ADD COLUMN IF NOT EXISTS "scopeCampus"    TEXT,
  ADD COLUMN IF NOT EXISTS "scopeLibrary"   TEXT,
  ADD COLUMN IF NOT EXISTS "scopeSource"    TEXT,
  ADD COLUMN IF NOT EXISTS "wasRefusal"     BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE "ModelTokenUsage"
  ADD COLUMN IF NOT EXISTS "cachedInputTokens" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "callSite"          TEXT;

-- --- New tables --------------------------------------------------------------

-- URL allowlist. The synthesizer's URL-validator reads from here; the ETL
-- writes here. is_blacklisted is librarian-controlled; isActive flips when
-- a URL drops out of the sitemap.
CREATE TABLE IF NOT EXISTS "UrlSeen" (
    "url"           TEXT         NOT NULL,
    "httpStatus"    INTEGER      NOT NULL,
    "contentType"   TEXT,
    "source"        TEXT         NOT NULL,
    "priority"      TEXT         NOT NULL DEFAULT 'normal',
    "isActive"      BOOLEAN      NOT NULL DEFAULT true,
    "isBlacklisted" BOOLEAN      NOT NULL DEFAULT false,
    "lastSeen"      TIMESTAMP(3) NOT NULL,
    "createdAt"     TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"     TIMESTAMP(3) NOT NULL,
    CONSTRAINT "UrlSeen_pkey" PRIMARY KEY ("url")
);

-- Bridge from Weaviate chunk_id back to source URL + audit metadata.
-- Append-only; GC'd after 90 days. Lets Message.citedChunkIds be joined
-- back to "what was the bot looking at when it answered".
CREATE TABLE IF NOT EXISTS "ChunkProvenance" (
    "chunkId"         TEXT         NOT NULL,
    "documentId"      TEXT         NOT NULL,
    "sourceUrl"       TEXT         NOT NULL,
    "topic"           TEXT         NOT NULL,
    "campus"          TEXT         NOT NULL,
    "library"         TEXT,
    "audience"        TEXT[]       DEFAULT ARRAY[]::TEXT[],
    "featuredService" TEXT,
    "contentHash"     TEXT         NOT NULL,
    "lastModified"    TIMESTAMP(3),
    "ingestedAt"      TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ChunkProvenance_pkey" PRIMARY KEY ("chunkId")
);

-- Librarian-set overrides on retrieval (suppress / replace / pin / blacklist).
-- Required for the post-launch correction workflow (Op 2 in the plan).
CREATE TABLE IF NOT EXISTS "ManualCorrection" (
    "id"           TEXT         NOT NULL,
    "scope"        TEXT         NOT NULL,
    "target"       TEXT         NOT NULL,
    "action"       TEXT         NOT NULL,
    "replacement"  TEXT,
    "queryPattern" TEXT,
    "reason"       TEXT         NOT NULL,
    "createdBy"    TEXT         NOT NULL,
    "createdAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt"    TIMESTAMP(3) NOT NULL,
    "active"       BOOLEAN      NOT NULL DEFAULT true,
    "fireCount"    INTEGER      NOT NULL DEFAULT 0,
    CONSTRAINT "ManualCorrection_pkey" PRIMARY KEY ("id")
);

-- Subject-librarian per-turn verdict (Op 1: dialog review queue).
CREATE TABLE IF NOT EXISTS "LibrarianReview" (
    "id"          TEXT         NOT NULL,
    "messageId"   TEXT         NOT NULL,
    "librarianId" TEXT         NOT NULL,
    "verdict"     TEXT         NOT NULL,
    "note"        TEXT,
    "reviewedAt"  TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "LibrarianReview_pkey" PRIMARY KEY ("id")
);

-- Daily cost rollup (Op 3: anomaly-alert if daily cost > 1.5x 7-day avg).
CREATE TABLE IF NOT EXISTS "DailyCost" (
    "id"           TEXT             NOT NULL,
    "date"         DATE             NOT NULL,
    "model"        TEXT             NOT NULL,
    "callSite"     TEXT             NOT NULL,
    "inputTokens"  INTEGER          NOT NULL DEFAULT 0,
    "cachedTokens" INTEGER          NOT NULL DEFAULT 0,
    "outputTokens" INTEGER          NOT NULL DEFAULT 0,
    "callCount"    INTEGER          NOT NULL DEFAULT 0,
    "usd"          DOUBLE PRECISION NOT NULL,
    "createdAt"    TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DailyCost_pkey" PRIMARY KEY ("id")
);

-- --- Indexes -----------------------------------------------------------------
-- All IF NOT EXISTS so re-running is a no-op.

-- Message: rebuild telemetry queries (filter by intent, scope, refusal).
CREATE INDEX IF NOT EXISTS "Message_conversationId_idx" ON "Message"("conversationId");
CREATE INDEX IF NOT EXISTS "Message_intent_idx"         ON "Message"("intent");
CREATE INDEX IF NOT EXISTS "Message_scopeCampus_idx"    ON "Message"("scopeCampus");
CREATE INDEX IF NOT EXISTS "Message_wasRefusal_idx"     ON "Message"("wasRefusal");

-- ModelTokenUsage: cost rollup queries (by model, by call site, by day).
CREATE INDEX IF NOT EXISTS "ModelTokenUsage_conversationId_idx" ON "ModelTokenUsage"("conversationId");
CREATE INDEX IF NOT EXISTS "ModelTokenUsage_llmModelName_idx"   ON "ModelTokenUsage"("llmModelName");
CREATE INDEX IF NOT EXISTS "ModelTokenUsage_callSite_idx"       ON "ModelTokenUsage"("callSite");
CREATE INDEX IF NOT EXISTS "ModelTokenUsage_createdAt_idx"      ON "ModelTokenUsage"("createdAt");

-- UrlSeen
CREATE INDEX IF NOT EXISTS "UrlSeen_isActive_idx"      ON "UrlSeen"("isActive");
CREATE INDEX IF NOT EXISTS "UrlSeen_priority_idx"      ON "UrlSeen"("priority");
CREATE INDEX IF NOT EXISTS "UrlSeen_isBlacklisted_idx" ON "UrlSeen"("isBlacklisted");

-- ChunkProvenance
CREATE INDEX IF NOT EXISTS "ChunkProvenance_sourceUrl_idx"       ON "ChunkProvenance"("sourceUrl");
CREATE INDEX IF NOT EXISTS "ChunkProvenance_documentId_idx"      ON "ChunkProvenance"("documentId");
CREATE INDEX IF NOT EXISTS "ChunkProvenance_campus_idx"          ON "ChunkProvenance"("campus");
CREATE INDEX IF NOT EXISTS "ChunkProvenance_library_idx"         ON "ChunkProvenance"("library");
CREATE INDEX IF NOT EXISTS "ChunkProvenance_topic_idx"           ON "ChunkProvenance"("topic");
CREATE INDEX IF NOT EXISTS "ChunkProvenance_featuredService_idx" ON "ChunkProvenance"("featuredService");

-- ManualCorrection
CREATE INDEX IF NOT EXISTS "ManualCorrection_active_idx"       ON "ManualCorrection"("active");
CREATE INDEX IF NOT EXISTS "ManualCorrection_scope_target_idx" ON "ManualCorrection"("scope", "target");
CREATE INDEX IF NOT EXISTS "ManualCorrection_createdBy_idx"    ON "ManualCorrection"("createdBy");
CREATE INDEX IF NOT EXISTS "ManualCorrection_expiresAt_idx"    ON "ManualCorrection"("expiresAt");

-- LibrarianReview
CREATE INDEX IF NOT EXISTS "LibrarianReview_librarianId_idx" ON "LibrarianReview"("librarianId");
CREATE INDEX IF NOT EXISTS "LibrarianReview_verdict_idx"     ON "LibrarianReview"("verdict");
CREATE INDEX IF NOT EXISTS "LibrarianReview_reviewedAt_idx"  ON "LibrarianReview"("reviewedAt");
CREATE UNIQUE INDEX IF NOT EXISTS "LibrarianReview_messageId_librarianId_key"
    ON "LibrarianReview"("messageId", "librarianId");

-- DailyCost
CREATE INDEX IF NOT EXISTS "DailyCost_date_idx"  ON "DailyCost"("date");
CREATE INDEX IF NOT EXISTS "DailyCost_model_idx" ON "DailyCost"("model");
CREATE UNIQUE INDEX IF NOT EXISTS "DailyCost_date_model_callSite_key"
    ON "DailyCost"("date", "model", "callSite");

-- --- Foreign keys ------------------------------------------------------------
-- ADD CONSTRAINT doesn't support IF NOT EXISTS, so wrap in DO blocks.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'LibrarianReview_messageId_fkey'
    ) THEN
        ALTER TABLE "LibrarianReview"
            ADD CONSTRAINT "LibrarianReview_messageId_fkey"
            FOREIGN KEY ("messageId")
            REFERENCES "Message"("id")
            ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

COMMIT;

-- =============================================================================
-- POST-RUN VERIFICATION (run these by hand to confirm)
-- =============================================================================
--
-- 1. All five missing tables now exist:
--      SELECT table_name FROM information_schema.tables
--      WHERE table_schema='public'
--        AND table_name IN ('UrlSeen', 'ChunkProvenance', 'ManualCorrection',
--                           'LibrarianReview', 'DailyCost')
--      ORDER BY table_name;
--    Expect: 5 rows.
--
-- 2. Message has all 9 new columns:
--      SELECT column_name FROM information_schema.columns
--      WHERE table_name='Message' AND column_name IN (
--          'intent','scopeCampus','scopeLibrary','scopeSource','modelUsed',
--          'confidence','wasRefusal','refusalTrigger','citedChunkIds')
--      ORDER BY column_name;
--    Expect: 9 rows.
--
-- 3. ModelTokenUsage has cachedInputTokens + callSite:
--      SELECT column_name FROM information_schema.columns
--      WHERE table_name='ModelTokenUsage'
--        AND column_name IN ('cachedInputTokens', 'callSite');
--    Expect: 2 rows.
--
-- 4. FK on LibrarianReview is in place:
--      SELECT conname FROM pg_constraint
--      WHERE conname='LibrarianReview_messageId_fkey';
--    Expect: 1 row.
-- =============================================================================
