-- =============================================================================
-- 01 — "My subject queue"
--
-- Recent bot conversations whose cited chunks came from a source URL that
-- belongs to a subject this librarian liaises. Filtered to the last
-- 7 days by default. Use this as the daily/weekly review entry point.
--
-- Parameter:
--   {{librarian_email}}  Metabase text variable. The librarian enters
--                        their @miamioh.edu address; we resolve to their
--                        Librarian row + subject set in-query.
--
-- Output columns:
--   message_id, timestamp, question, answer (truncated), confidence,
--   was_refusal, refusal_trigger, scope_campus, scope_library,
--   intent, model_used, cited_urls (array), thumbs_rating,
--   subject_match (which of the librarian's subjects matched).
--
-- Sort: newest first.
--
-- See plan: Operations §Op 1 -- librarian-facing review surface.
-- =============================================================================

WITH liaison AS (
    SELECT id, name, email, campus
    FROM "Librarian"
    WHERE lower(email) = lower({{librarian_email}})
      AND "isActive" = true
),
liaison_subjects AS (
    SELECT s.id AS subject_id, s.name AS subject_name
    FROM "LibrarianSubject" ls
    JOIN "Subject" s ON s.id = ls."subjectId"
    WHERE ls."librarianId" IN (SELECT id FROM liaison)
),
-- Cited chunks per recent message, expanded to URLs + featured-service tags.
recent_cited AS (
    SELECT
        m.id          AS message_id,
        m.timestamp   AS msg_ts,
        m."conversationId" AS conv_id,
        m.content     AS answer,
        m.intent,
        m."scopeCampus"  AS scope_campus,
        m."scopeLibrary" AS scope_library,
        m.confidence,
        m."wasRefusal"   AS was_refusal,
        m."refusalTrigger" AS refusal_trigger,
        m."modelUsed"    AS model_used,
        m."isPositiveRated" AS thumbs_rating,
        cp."sourceUrl"   AS source_url,
        cp."featuredService" AS featured_service
    FROM "Message" m
    LEFT JOIN LATERAL unnest(m."citedChunkIds") AS chunk_id ON TRUE
    LEFT JOIN "ChunkProvenance" cp ON cp."chunkId" = chunk_id
    WHERE m.timestamp >= NOW() - INTERVAL '7 days'
      AND m.type = 'chatbot'
)
SELECT
    rc.message_id,
    rc.msg_ts                  AS timestamp,
    -- The user's question is the prior message in the conversation.
    (SELECT content FROM "Message"
        WHERE "conversationId" = rc.conv_id
          AND timestamp < rc.msg_ts
          AND type = 'user'
        ORDER BY timestamp DESC
        LIMIT 1)                AS question,
    LEFT(rc.answer, 280)        AS answer_preview,
    rc.confidence,
    rc.was_refusal,
    rc.refusal_trigger,
    rc.scope_campus,
    rc.scope_library,
    rc.intent,
    rc.model_used,
    array_agg(DISTINCT rc.source_url) FILTER (WHERE rc.source_url IS NOT NULL) AS cited_urls,
    rc.thumbs_rating,
    -- Which of the librarian's subjects this message touched. Heuristic v0:
    -- match the cited URL prefix to the LibGuide URLs owned by the subject.
    -- Tighten to a real classifier output once the v2 stack ships.
    array_agg(DISTINCT ls.subject_name) FILTER (WHERE ls.subject_name IS NOT NULL)
                                AS matched_subjects
FROM recent_cited rc
LEFT JOIN "LibGuide" lg ON rc.source_url ILIKE lg.url || '%'
LEFT JOIN "LibGuideSubject" lgs ON lgs."libGuideId" = lg.id
LEFT JOIN liaison_subjects ls ON ls.subject_id = lgs."subjectId"
GROUP BY
    rc.message_id, rc.msg_ts, rc.conv_id, rc.answer,
    rc.confidence, rc.was_refusal, rc.refusal_trigger,
    rc.scope_campus, rc.scope_library, rc.intent,
    rc.model_used, rc.thumbs_rating
HAVING
    -- Keep only rows that touched at least one of the librarian's subjects.
    -- Comment this HAVING out to see ALL recent conversations (campus-wide
    -- queue rather than subject-specific).
    COUNT(DISTINCT ls.subject_id) > 0
ORDER BY rc.msg_ts DESC
LIMIT 200;
