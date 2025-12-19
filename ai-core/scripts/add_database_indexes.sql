-- Database Performance Optimization - Add Indexes
-- This script adds indexes to improve query performance for subject/librarian searches
-- Run this against your PostgreSQL database

-- ============================================================================
-- SUBJECT TABLE INDEXES
-- ============================================================================

-- Index on subject name for faster fuzzy matching
CREATE INDEX IF NOT EXISTS idx_subject_name ON "Subject" (name);
CREATE INDEX IF NOT EXISTS idx_subject_name_lower ON "Subject" (LOWER(name));

-- ============================================================================
-- SUBJECT REG CODE INDEXES
-- ============================================================================

-- Index on regCode for exact course code matching (e.g., "ENG111")
CREATE INDEX IF NOT EXISTS idx_subjectregcode_regcode ON "SubjectRegCode" (regCode);
CREATE INDEX IF NOT EXISTS idx_subjectregcode_regcode_upper ON "SubjectRegCode" (UPPER(regCode));

-- Index on regName for fuzzy matching (e.g., "English")
CREATE INDEX IF NOT EXISTS idx_subjectregcode_regname ON "SubjectRegCode" (regName);
CREATE INDEX IF NOT EXISTS idx_subjectregcode_regname_lower ON "SubjectRegCode" (LOWER(regName));

-- Index on subjectId for faster joins
CREATE INDEX IF NOT EXISTS idx_subjectregcode_subjectid ON "SubjectRegCode" (subjectId);

-- ============================================================================
-- SUBJECT DEPT CODE INDEXES
-- ============================================================================

-- Index on deptCode for department code matching (e.g., "eng", "bio")
CREATE INDEX IF NOT EXISTS idx_subjectdeptcode_deptcode ON "SubjectDeptCode" (deptCode);
CREATE INDEX IF NOT EXISTS idx_subjectdeptcode_deptcode_lower ON "SubjectDeptCode" (LOWER(deptCode));

-- Index on deptName for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_subjectdeptcode_deptname ON "SubjectDeptCode" (deptName);
CREATE INDEX IF NOT EXISTS idx_subjectdeptcode_deptname_lower ON "SubjectDeptCode" (LOWER(deptName));

-- Index on subjectId for faster joins
CREATE INDEX IF NOT EXISTS idx_subjectdeptcode_subjectid ON "SubjectDeptCode" (subjectId);

-- ============================================================================
-- SUBJECT MAJOR CODE INDEXES
-- ============================================================================

-- Index on majorCode for major code matching
CREATE INDEX IF NOT EXISTS idx_subjectmajorcode_majorcode ON "SubjectMajorCode" (majorCode);
CREATE INDEX IF NOT EXISTS idx_subjectmajorcode_majorcode_upper ON "SubjectMajorCode" (UPPER(majorCode));

-- Index on subjectId for faster joins
CREATE INDEX IF NOT EXISTS idx_subjectmajorcode_subjectid ON "SubjectMajorCode" (subjectId);

-- ============================================================================
-- LIBRARIAN SUBJECT INDEXES
-- ============================================================================

-- Index on subjectId for faster librarian lookups
CREATE INDEX IF NOT EXISTS idx_librariansubject_subjectid ON "LibrarianSubject" (subjectId);

-- Index on librarianId for faster subject lookups
CREATE INDEX IF NOT EXISTS idx_librariansubject_librarianid ON "LibrarianSubject" (librarianId);

-- Composite index for primary librarian queries
CREATE INDEX IF NOT EXISTS idx_librariansubject_subject_primary ON "LibrarianSubject" (subjectId, isPrimary);

-- ============================================================================
-- LIBRARIAN INDEXES
-- ============================================================================

-- Index on isActive for filtering active librarians
CREATE INDEX IF NOT EXISTS idx_librarian_isactive ON "Librarian" (isActive);

-- Index on campus for campus-specific filtering
CREATE INDEX IF NOT EXISTS idx_librarian_campus ON "Librarian" (campus);

-- Composite index for active librarians by campus
CREATE INDEX IF NOT EXISTS idx_librarian_active_campus ON "Librarian" (isActive, campus);

-- Index on librarian name for direct name search
CREATE INDEX IF NOT EXISTS idx_librarian_name ON "Librarian" (name);
CREATE INDEX IF NOT EXISTS idx_librarian_name_lower ON "Librarian" (LOWER(name));

-- Index on email for quick librarian lookup
CREATE INDEX IF NOT EXISTS idx_librarian_email ON "Librarian" (email);

-- ============================================================================
-- LIBGUIDE SUBJECT INDEXES
-- ============================================================================

-- Index on subjectId for faster LibGuide lookups
CREATE INDEX IF NOT EXISTS idx_libguidesubject_subjectid ON "LibGuideSubject" (subjectId);

-- Index on libGuideId for faster subject lookups
CREATE INDEX IF NOT EXISTS idx_libguidesubject_libguideid ON "LibGuideSubject" (libGuideId);

-- ============================================================================
-- LIBGUIDE INDEXES
-- ============================================================================

-- Index on isActive for filtering active guides
CREATE INDEX IF NOT EXISTS idx_libguide_isactive ON "LibGuide" (isActive);

-- Index on name for searching
CREATE INDEX IF NOT EXISTS idx_libguide_name ON "LibGuide" (name);
CREATE INDEX IF NOT EXISTS idx_libguide_name_lower ON "LibGuide" (LOWER(name));

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Show all indexes created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND tablename IN ('Subject', 'SubjectRegCode', 'SubjectDeptCode', 'SubjectMajorCode', 
                      'LibrarianSubject', 'Librarian', 'LibGuideSubject', 'LibGuide')
ORDER BY tablename, indexname;

-- Show table sizes and index sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename IN ('Subject', 'SubjectRegCode', 'SubjectDeptCode', 'SubjectMajorCode', 
                      'LibrarianSubject', 'Librarian', 'LibGuideSubject', 'LibGuide')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
