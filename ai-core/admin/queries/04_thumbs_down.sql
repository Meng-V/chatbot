-- =============================================================================
-- 04 — Thumbs-down answers
--
-- Real users telling us we got it wrong. Highest-signal review queue.
-- Joined to ChunkProvenance so the librarian can see (and click) the
-- exact sources the bot cited when the user marked the answer down.
--
-- Parameter:
--   {{days}}  Metabase number, default 14
--
-- See plan: Operations §Op 1 -- "saved filter for user_rating=down".
-- =============================================================================

SELECT
    m.id                                AS message_id,
    m.timestamp,
    (SELECT content FROM "Message"
        WHERE "conversationId" = m."conversationId"
          AND timestamp < m.timestamp
          AND type = 'user'
        ORDER BY timestamp DESC LIMIT 1) AS question,
    LEFT(m.content, 400)                AS answer_preview,
    m.intent,
    m."scopeCampus"                     AS scope_campus,
    m."scopeLibrary"                    AS scope_library,
    m.confidence,
    m."modelUsed"                       AS model_used,
    -- Pull the source URLs the bot cited so the librarian can audit.
    (SELECT array_agg(DISTINCT cp."sourceUrl")
        FROM "ChunkProvenance" cp
        WHERE cp."chunkId" = ANY (m."citedChunkIds"))  AS cited_urls
FROM "Message" m
WHERE m.type = 'chatbot'
  AND m."isPositiveRated" = false
  AND m.timestamp >= NOW() - ({{days}} || ' days')::INTERVAL
ORDER BY m.timestamp DESC
LIMIT 200;
