-- =============================================================================
-- Smart chatbot rebuild: schema additions
-- =============================================================================
-- Turns the PR #12 `prisma db push` into a proper migration. Makes the
-- rebuild tables / columns reproducible in prod with a paper trail.
--
-- Safety notes:
--   * Conversation.updatedAt is added NOT NULL with DEFAULT CURRENT_TIMESTAMP
--     so existing rows backfill to now(). Runtime writes use Prisma's
--     @updatedAt to keep it current.
--   * ToolExecution, Subject*, Campus, Library, LibrarySpace, Librarian,
--     LibGuide*, UrlSeen, ChunkProvenance, ManualCorrection,
--     LibrarianReview, DailyCost are all new tables -- no existing-row
--     concerns.
--   * Building / Room are dropped below. They were unused by current
--     application code (grep turned up zero references in ai-core/ or
--     server/ outside the old Prisma-generated client). If a prod DB
--     nonetheless holds rows, back them up before running:
--         pg_dump --table='"Building"' --table='"Room"' <db> > legacy_rooms.sql
--     This migration is intentionally destructive for these two tables;
--     the rebuild replaces them with LibrarySpace (with richer metadata).
-- =============================================================================

-- --- Legacy table cleanup ----------------------------------------------------

-- DropForeignKey
ALTER TABLE "Room" DROP CONSTRAINT "Room_buildingId_fkey";

-- DropTable
DROP TABLE "Building";

-- DropTable
DROP TABLE "Room";

-- --- Existing table extensions -----------------------------------------------

-- Conversation: add createdAt/updatedAt (backfill existing rows to now()).
-- DEFAULT CURRENT_TIMESTAMP is required on ADD COLUMN NOT NULL against
-- populated tables; Prisma's @updatedAt handles subsequent writes.
ALTER TABLE "Conversation" ADD COLUMN     "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN     "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ALTER COLUMN "toolUsed" SET DEFAULT ARRAY[]::TEXT[];

-- After backfill, drop the default on updatedAt. The Prisma schema uses
-- @updatedAt (app-side trigger); leaving the SQL default in place would
-- cause future `prisma migrate` runs to see drift against the model.
ALTER TABLE "Conversation" ALTER COLUMN "updatedAt" DROP DEFAULT;

-- Message: rebuild telemetry columns (intent, scope, model, confidence,
-- wasRefusal, refusalTrigger, citedChunkIds). All nullable or defaulted so
-- legacy writes (which don't set these) succeed.
ALTER TABLE "Message" ADD COLUMN     "citedChunkIds" TEXT[] DEFAULT ARRAY[]::TEXT[],
ADD COLUMN     "confidence" TEXT,
ADD COLUMN     "intent" TEXT,
ADD COLUMN     "modelUsed" TEXT,
ADD COLUMN     "refusalTrigger" TEXT,
ADD COLUMN     "scopeCampus" TEXT,
ADD COLUMN     "scopeLibrary" TEXT,
ADD COLUMN     "scopeSource" TEXT,
ADD COLUMN     "wasRefusal" BOOLEAN NOT NULL DEFAULT false;

-- ModelTokenUsage: cachedInputTokens for the week-4 cache-hit gate;
-- callSite to attribute tokens to agent / synthesizer / clarifier / judge;
-- createdAt for time-series rollups.
ALTER TABLE "ModelTokenUsage" ADD COLUMN     "cachedInputTokens" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "callSite" TEXT,
ADD COLUMN     "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- --- New tables --------------------------------------------------------------

-- CreateTable
CREATE TABLE "ToolExecution" (
    "id" TEXT NOT NULL,
    "conversationId" TEXT NOT NULL,
    "agentName" TEXT NOT NULL,
    "toolName" TEXT NOT NULL,
    "parameters" TEXT NOT NULL DEFAULT '{}',
    "success" BOOLEAN NOT NULL,
    "executionTime" INTEGER NOT NULL DEFAULT 0,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ToolExecution_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Subject" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "regional" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Subject_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SubjectLibGuide" (
    "id" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "libGuide" TEXT NOT NULL,

    CONSTRAINT "SubjectLibGuide_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SubjectRegCode" (
    "id" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "regCode" TEXT NOT NULL,
    "regName" TEXT NOT NULL,

    CONSTRAINT "SubjectRegCode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SubjectMajorCode" (
    "id" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "majorCode" TEXT NOT NULL,
    "majorName" TEXT NOT NULL,

    CONSTRAINT "SubjectMajorCode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SubjectDeptCode" (
    "id" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "deptCode" TEXT NOT NULL,
    "deptName" TEXT NOT NULL,

    CONSTRAINT "SubjectDeptCode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Campus" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "displayName" TEXT NOT NULL,
    "isMain" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Campus_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Library" (
    "id" TEXT NOT NULL,
    "campusId" TEXT NOT NULL,
    "canonicalId" TEXT,
    "name" TEXT NOT NULL,
    "displayName" TEXT NOT NULL,
    "shortName" TEXT,
    "libcalBuildingId" TEXT NOT NULL,
    "libcalLocationId" TEXT,
    "phone" TEXT,
    "address" TEXT,
    "website" TEXT,
    "isMain" BOOLEAN NOT NULL DEFAULT false,
    "servicesOffered" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "buildingRole" TEXT,
    "sourceUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Library_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LibrarySpace" (
    "id" TEXT NOT NULL,
    "libraryId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "displayName" TEXT NOT NULL,
    "shortName" TEXT,
    "buildingLocation" TEXT,
    "libcalLocationId" TEXT NOT NULL,
    "libcalBuildingId" TEXT,
    "phone" TEXT,
    "email" TEXT,
    "website" TEXT,
    "spaceType" TEXT NOT NULL DEFAULT 'service',
    "equipment" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "services" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "capacity" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LibrarySpace_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Librarian" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "title" TEXT,
    "department" TEXT,
    "phone" TEXT,
    "photoUrl" TEXT,
    "profileUrl" TEXT,
    "libguideProfileId" TEXT,
    "campus" TEXT NOT NULL DEFAULT 'Oxford',
    "isRegional" BOOLEAN NOT NULL DEFAULT false,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Librarian_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LibGuide" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "description" TEXT,
    "guideId" TEXT,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "LibGuide_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LibrarianSubject" (
    "id" TEXT NOT NULL,
    "librarianId" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "isPrimary" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "LibrarianSubject_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LibGuideSubject" (
    "id" TEXT NOT NULL,
    "libGuideId" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,

    CONSTRAINT "LibGuideSubject_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "UrlSeen" (
    "url" TEXT NOT NULL,
    "httpStatus" INTEGER NOT NULL,
    "contentType" TEXT,
    "source" TEXT NOT NULL,
    "priority" TEXT NOT NULL DEFAULT 'normal',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "isBlacklisted" BOOLEAN NOT NULL DEFAULT false,
    "lastSeen" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "UrlSeen_pkey" PRIMARY KEY ("url")
);

-- CreateTable
CREATE TABLE "ChunkProvenance" (
    "chunkId" TEXT NOT NULL,
    "documentId" TEXT NOT NULL,
    "sourceUrl" TEXT NOT NULL,
    "topic" TEXT NOT NULL,
    "campus" TEXT NOT NULL,
    "library" TEXT,
    "audience" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "featuredService" TEXT,
    "contentHash" TEXT NOT NULL,
    "lastModified" TIMESTAMP(3),
    "ingestedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ChunkProvenance_pkey" PRIMARY KEY ("chunkId")
);

-- CreateTable
CREATE TABLE "ManualCorrection" (
    "id" TEXT NOT NULL,
    "scope" TEXT NOT NULL,
    "target" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "replacement" TEXT,
    "queryPattern" TEXT,
    "reason" TEXT NOT NULL,
    "createdBy" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "fireCount" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "ManualCorrection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LibrarianReview" (
    "id" TEXT NOT NULL,
    "messageId" TEXT NOT NULL,
    "librarianId" TEXT NOT NULL,
    "verdict" TEXT NOT NULL,
    "note" TEXT,
    "reviewedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "LibrarianReview_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DailyCost" (
    "id" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "model" TEXT NOT NULL,
    "callSite" TEXT NOT NULL,
    "inputTokens" INTEGER NOT NULL DEFAULT 0,
    "cachedTokens" INTEGER NOT NULL DEFAULT 0,
    "outputTokens" INTEGER NOT NULL DEFAULT 0,
    "callCount" INTEGER NOT NULL DEFAULT 0,
    "usd" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DailyCost_pkey" PRIMARY KEY ("id")
);

-- --- Indexes -----------------------------------------------------------------

-- CreateIndex
CREATE INDEX "ToolExecution_conversationId_idx" ON "ToolExecution"("conversationId");

-- CreateIndex
CREATE INDEX "ToolExecution_agentName_idx" ON "ToolExecution"("agentName");

-- CreateIndex
CREATE INDEX "ToolExecution_toolName_idx" ON "ToolExecution"("toolName");

-- CreateIndex
CREATE UNIQUE INDEX "Subject_name_key" ON "Subject"("name");

-- CreateIndex
CREATE INDEX "Subject_name_idx" ON "Subject"("name");

-- CreateIndex
CREATE INDEX "SubjectLibGuide_libGuide_idx" ON "SubjectLibGuide"("libGuide");

-- CreateIndex
CREATE UNIQUE INDEX "SubjectLibGuide_subjectId_libGuide_key" ON "SubjectLibGuide"("subjectId", "libGuide");

-- CreateIndex
CREATE INDEX "SubjectRegCode_regCode_idx" ON "SubjectRegCode"("regCode");

-- CreateIndex
CREATE UNIQUE INDEX "SubjectRegCode_subjectId_regCode_key" ON "SubjectRegCode"("subjectId", "regCode");

-- CreateIndex
CREATE INDEX "SubjectMajorCode_majorCode_idx" ON "SubjectMajorCode"("majorCode");

-- CreateIndex
CREATE INDEX "SubjectMajorCode_majorName_idx" ON "SubjectMajorCode"("majorName");

-- CreateIndex
CREATE UNIQUE INDEX "SubjectMajorCode_subjectId_majorCode_key" ON "SubjectMajorCode"("subjectId", "majorCode");

-- CreateIndex
CREATE INDEX "SubjectDeptCode_deptCode_idx" ON "SubjectDeptCode"("deptCode");

-- CreateIndex
CREATE INDEX "SubjectDeptCode_deptName_idx" ON "SubjectDeptCode"("deptName");

-- CreateIndex
CREATE UNIQUE INDEX "SubjectDeptCode_subjectId_deptCode_key" ON "SubjectDeptCode"("subjectId", "deptCode");

-- CreateIndex
CREATE UNIQUE INDEX "Campus_name_key" ON "Campus"("name");

-- CreateIndex
CREATE INDEX "Campus_name_idx" ON "Campus"("name");

-- CreateIndex
CREATE UNIQUE INDEX "Library_canonicalId_key" ON "Library"("canonicalId");

-- CreateIndex
CREATE UNIQUE INDEX "Library_libcalBuildingId_key" ON "Library"("libcalBuildingId");

-- CreateIndex
CREATE INDEX "Library_name_idx" ON "Library"("name");

-- CreateIndex
CREATE INDEX "Library_shortName_idx" ON "Library"("shortName");

-- CreateIndex
CREATE INDEX "Library_canonicalId_idx" ON "Library"("canonicalId");

-- CreateIndex
CREATE INDEX "Library_libcalBuildingId_idx" ON "Library"("libcalBuildingId");

-- CreateIndex
CREATE INDEX "Library_libcalLocationId_idx" ON "Library"("libcalLocationId");

-- CreateIndex
CREATE UNIQUE INDEX "LibrarySpace_libcalLocationId_key" ON "LibrarySpace"("libcalLocationId");

-- CreateIndex
CREATE UNIQUE INDEX "LibrarySpace_libcalBuildingId_key" ON "LibrarySpace"("libcalBuildingId");

-- CreateIndex
CREATE INDEX "LibrarySpace_name_idx" ON "LibrarySpace"("name");

-- CreateIndex
CREATE INDEX "LibrarySpace_shortName_idx" ON "LibrarySpace"("shortName");

-- CreateIndex
CREATE INDEX "LibrarySpace_libcalLocationId_idx" ON "LibrarySpace"("libcalLocationId");

-- CreateIndex
CREATE INDEX "LibrarySpace_libcalBuildingId_idx" ON "LibrarySpace"("libcalBuildingId");

-- CreateIndex
CREATE UNIQUE INDEX "Librarian_email_key" ON "Librarian"("email");

-- CreateIndex
CREATE INDEX "Librarian_email_idx" ON "Librarian"("email");

-- CreateIndex
CREATE INDEX "Librarian_name_idx" ON "Librarian"("name");

-- CreateIndex
CREATE INDEX "Librarian_campus_idx" ON "Librarian"("campus");

-- CreateIndex
CREATE INDEX "Librarian_isRegional_idx" ON "Librarian"("isRegional");

-- CreateIndex
CREATE UNIQUE INDEX "LibGuide_url_key" ON "LibGuide"("url");

-- CreateIndex
CREATE INDEX "LibGuide_name_idx" ON "LibGuide"("name");

-- CreateIndex
CREATE INDEX "LibGuide_guideId_idx" ON "LibGuide"("guideId");

-- CreateIndex
CREATE INDEX "LibrarianSubject_subjectId_idx" ON "LibrarianSubject"("subjectId");

-- CreateIndex
CREATE INDEX "LibrarianSubject_librarianId_idx" ON "LibrarianSubject"("librarianId");

-- CreateIndex
CREATE UNIQUE INDEX "LibrarianSubject_librarianId_subjectId_key" ON "LibrarianSubject"("librarianId", "subjectId");

-- CreateIndex
CREATE INDEX "LibGuideSubject_subjectId_idx" ON "LibGuideSubject"("subjectId");

-- CreateIndex
CREATE INDEX "LibGuideSubject_libGuideId_idx" ON "LibGuideSubject"("libGuideId");

-- CreateIndex
CREATE UNIQUE INDEX "LibGuideSubject_libGuideId_subjectId_key" ON "LibGuideSubject"("libGuideId", "subjectId");

-- CreateIndex
CREATE INDEX "UrlSeen_isActive_idx" ON "UrlSeen"("isActive");

-- CreateIndex
CREATE INDEX "UrlSeen_priority_idx" ON "UrlSeen"("priority");

-- CreateIndex
CREATE INDEX "UrlSeen_isBlacklisted_idx" ON "UrlSeen"("isBlacklisted");

-- CreateIndex
CREATE INDEX "ChunkProvenance_sourceUrl_idx" ON "ChunkProvenance"("sourceUrl");

-- CreateIndex
CREATE INDEX "ChunkProvenance_documentId_idx" ON "ChunkProvenance"("documentId");

-- CreateIndex
CREATE INDEX "ChunkProvenance_campus_idx" ON "ChunkProvenance"("campus");

-- CreateIndex
CREATE INDEX "ChunkProvenance_library_idx" ON "ChunkProvenance"("library");

-- CreateIndex
CREATE INDEX "ChunkProvenance_topic_idx" ON "ChunkProvenance"("topic");

-- CreateIndex
CREATE INDEX "ChunkProvenance_featuredService_idx" ON "ChunkProvenance"("featuredService");

-- CreateIndex
CREATE INDEX "ManualCorrection_active_idx" ON "ManualCorrection"("active");

-- CreateIndex
CREATE INDEX "ManualCorrection_scope_target_idx" ON "ManualCorrection"("scope", "target");

-- CreateIndex
CREATE INDEX "ManualCorrection_createdBy_idx" ON "ManualCorrection"("createdBy");

-- CreateIndex
CREATE INDEX "ManualCorrection_expiresAt_idx" ON "ManualCorrection"("expiresAt");

-- CreateIndex
CREATE INDEX "LibrarianReview_librarianId_idx" ON "LibrarianReview"("librarianId");

-- CreateIndex
CREATE INDEX "LibrarianReview_verdict_idx" ON "LibrarianReview"("verdict");

-- CreateIndex
CREATE INDEX "LibrarianReview_reviewedAt_idx" ON "LibrarianReview"("reviewedAt");

-- CreateIndex
CREATE UNIQUE INDEX "LibrarianReview_messageId_librarianId_key" ON "LibrarianReview"("messageId", "librarianId");

-- CreateIndex
CREATE INDEX "DailyCost_date_idx" ON "DailyCost"("date");

-- CreateIndex
CREATE INDEX "DailyCost_model_idx" ON "DailyCost"("model");

-- CreateIndex
CREATE UNIQUE INDEX "DailyCost_date_model_callSite_key" ON "DailyCost"("date", "model", "callSite");

-- CreateIndex
CREATE INDEX "Message_conversationId_idx" ON "Message"("conversationId");

-- CreateIndex
CREATE INDEX "Message_intent_idx" ON "Message"("intent");

-- CreateIndex
CREATE INDEX "Message_scopeCampus_idx" ON "Message"("scopeCampus");

-- CreateIndex
CREATE INDEX "Message_wasRefusal_idx" ON "Message"("wasRefusal");

-- CreateIndex
CREATE INDEX "ModelTokenUsage_conversationId_idx" ON "ModelTokenUsage"("conversationId");

-- CreateIndex
CREATE INDEX "ModelTokenUsage_llmModelName_idx" ON "ModelTokenUsage"("llmModelName");

-- CreateIndex
CREATE INDEX "ModelTokenUsage_callSite_idx" ON "ModelTokenUsage"("callSite");

-- CreateIndex
CREATE INDEX "ModelTokenUsage_createdAt_idx" ON "ModelTokenUsage"("createdAt");

-- --- Foreign keys ------------------------------------------------------------

-- AddForeignKey
ALTER TABLE "ToolExecution" ADD CONSTRAINT "ToolExecution_conversationId_fkey" FOREIGN KEY ("conversationId") REFERENCES "Conversation"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SubjectLibGuide" ADD CONSTRAINT "SubjectLibGuide_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SubjectRegCode" ADD CONSTRAINT "SubjectRegCode_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SubjectMajorCode" ADD CONSTRAINT "SubjectMajorCode_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SubjectDeptCode" ADD CONSTRAINT "SubjectDeptCode_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Library" ADD CONSTRAINT "Library_campusId_fkey" FOREIGN KEY ("campusId") REFERENCES "Campus"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibrarySpace" ADD CONSTRAINT "LibrarySpace_libraryId_fkey" FOREIGN KEY ("libraryId") REFERENCES "Library"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibrarianSubject" ADD CONSTRAINT "LibrarianSubject_librarianId_fkey" FOREIGN KEY ("librarianId") REFERENCES "Librarian"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibrarianSubject" ADD CONSTRAINT "LibrarianSubject_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibGuideSubject" ADD CONSTRAINT "LibGuideSubject_libGuideId_fkey" FOREIGN KEY ("libGuideId") REFERENCES "LibGuide"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibGuideSubject" ADD CONSTRAINT "LibGuideSubject_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "Subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LibrarianReview" ADD CONSTRAINT "LibrarianReview_messageId_fkey" FOREIGN KEY ("messageId") REFERENCES "Message"("id") ON DELETE CASCADE ON UPDATE CASCADE;
