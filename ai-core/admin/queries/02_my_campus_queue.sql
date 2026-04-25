-- =============================================================================
-- 02 — "My campus queue"
--
-- All recent conversations resolved to a particular campus, regardless of
-- which librarian's subject they touched. Regional librarians (Hamilton,
-- Middletown) live here -- they own everything from their campus.
--
-- Parameter:
--   {{campus}}  Metabase dropdown: "oxford" | "hamilton" | "middletown"
--   {{days}}    Metabase number, default 7
--
-- See plan: Operations §Op 1 -- regional-librarian default queue.
-- =============================================================================

SELECT
    m.id                                AS message_id,
    m.timestamp,
    (SELECT content FROM "Message"
        WHERE "conversationId" = m."conversationId"
          AND timestamp < m.timestamp
          AND type = 'user'
        ORDER BY timestamp DESC LIMIT 1) AS question,
    LEFT(m.content, 280)                AS answer_preview,
    m.intent,
    m."scopeCampus"                     AS scope_campus,
    m."scopeLibrary"                    AS scope_library,
    m."scopeSource"                     AS scope_source,
    m.confidence,
    m."wasRefusal"                      AS was_refusal,
    m."refusalTrigger"                  AS refusal_trigger,
    m."modelUsed"                       AS model_used,
    m."isPositiveRated"                 AS thumbs_rating,
    array_length(m."citedChunkIds", 1)  AS citation_count
FROM "Message" m
WHERE m.type = 'chatbot'
  AND m."scopeCampus" = {{campus}}
  AND m.timestamp >= NOW() - ({{days}} || ' days')::INTERVAL
ORDER BY m.timestamp DESC
LIMIT 500;
