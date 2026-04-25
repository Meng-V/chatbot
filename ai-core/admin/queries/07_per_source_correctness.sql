-- =============================================================================
-- 07 — Per-source URL correctness rate
--
-- For each source URL the bot cited recently, what fraction of those
-- citations got a "wrong" or "should_refuse" librarian verdict? URLs at
-- the top of this list are pollution suspects -- the page itself is
-- wrong, stale, or being cited in the wrong context. Candidates for
-- ManualCorrection (suppress / replace / blacklist).
--
-- Parameter:
--   {{days}}  Metabase number, default 30
--   {{min_uses}}  Metabase number, default 3 -- only score URLs cited
--                 enough times for the rate to be meaningful.
--
-- See plan: Operations §Op 1 -- "per-source-URL %-correct sorted
-- descending (the polluted sources rise to the top)".
-- =============================================================================

WITH cited AS (
    SELECT
        cp."sourceUrl" AS source_url,
        m.id           AS message_id,
        m.timestamp    AS msg_ts
    FROM "Message" m
    JOIN LATERAL unnest(m."citedChunkIds") AS chunk_id ON TRUE
    JOIN "ChunkProvenance" cp ON cp."chunkId" = chunk_id
    WHERE m.type = 'chatbot'
      AND m.timestamp >= NOW() - ({{days}} || ' days')::INTERVAL
)
SELECT
    c.source_url,
    COUNT(DISTINCT c.message_id)                                          AS cite_count,
    COUNT(DISTINCT lr.id)                                                 AS reviews,
    COUNT(*) FILTER (WHERE lr.verdict = 'correct')                        AS verdict_correct,
    COUNT(*) FILTER (WHERE lr.verdict = 'partial')                        AS verdict_partial,
    COUNT(*) FILTER (WHERE lr.verdict = 'wrong')                          AS verdict_wrong,
    COUNT(*) FILTER (WHERE lr.verdict = 'should_refuse')                  AS verdict_should_refuse,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE lr.verdict IN ('wrong','should_refuse'))
              / NULLIF(COUNT(DISTINCT lr.id), 0),
        1
    ) AS pct_bad
FROM cited c
LEFT JOIN "LibrarianReview" lr ON lr."messageId" = c.message_id
GROUP BY c.source_url
HAVING COUNT(DISTINCT c.message_id) >= {{min_uses}}
ORDER BY pct_bad DESC NULLS LAST, cite_count DESC
LIMIT 100;
