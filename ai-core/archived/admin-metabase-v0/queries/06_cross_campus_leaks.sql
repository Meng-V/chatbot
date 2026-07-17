-- =============================================================================
-- 06 — Cross-campus citation leaks (must be ZERO)
--
-- Hard correctness check: every cited chunk's campus must match the
-- message's resolved scope.campus (or the chunk's campus is "all").
-- Anything in this query result is a post-processor escape -- the
-- synthesizer cited a chunk from the wrong campus and the cross-campus
-- guard didn't catch it. This is the load-bearing failure mode that
-- prevents King's hours being served as Hamilton's hours.
--
-- Expected output: zero rows. If non-empty, file an issue immediately
-- and inspect ai-core/src/synthesis/post_processor.py.
--
-- See plan: Verification §6 -- "zero answers cite a chunk from the wrong
-- campus" gate.
-- =============================================================================

SELECT
    m.id                                   AS message_id,
    m.timestamp,
    m."scopeCampus"                        AS message_campus,
    cp.campus                              AS chunk_campus,
    cp."sourceUrl"                         AS chunk_source_url,
    cp."chunkId"                           AS chunk_id,
    LEFT(m.content, 200)                   AS answer_preview,
    m."refusalTrigger"                     AS refusal_trigger,
    m."isPositiveRated"                    AS thumbs_rating
FROM "Message" m
JOIN LATERAL unnest(m."citedChunkIds") AS chunk_id ON TRUE
JOIN "ChunkProvenance" cp ON cp."chunkId" = chunk_id
WHERE m.type = 'chatbot'
  AND m."scopeCampus" IS NOT NULL
  AND cp.campus IS NOT NULL
  AND cp.campus <> 'all'
  AND cp.campus <> m."scopeCampus"
  AND m.timestamp >= NOW() - INTERVAL '30 days'
ORDER BY m.timestamp DESC
LIMIT 100;
