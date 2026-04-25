-- =============================================================================
-- 03 — Low-confidence answers
--
-- Synthesizer self-reported `confidence = "low"`. These are the cases the
-- bot was honest about being unsure -- ideal review fodder because either
-- (a) the corpus is missing content -> add to ETL; (b) the retrieval
-- ranking is wrong -> tune; (c) the question was genuinely answerable but
-- the bot panicked -> reduce false-low rate.
--
-- Parameter:
--   {{days}}  Metabase number, default 7
--
-- See plan: Citation contract §refusal triggers / measurement.
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
    m."modelUsed"                       AS model_used,
    array_length(m."citedChunkIds", 1)  AS citation_count,
    m."isPositiveRated"                 AS thumbs_rating
FROM "Message" m
WHERE m.type = 'chatbot'
  AND m.confidence = 'low'
  AND m."wasRefusal" = false
  AND m.timestamp >= NOW() - ({{days}} || ' days')::INTERVAL
ORDER BY m.timestamp DESC
LIMIT 200;
