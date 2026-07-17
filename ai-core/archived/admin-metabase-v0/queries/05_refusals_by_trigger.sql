-- =============================================================================
-- 05 — Refusals broken down by trigger
--
-- Aggregate view of why the bot is refusing, by category. Healthy
-- distribution: most refusals should be `out_of_scope` (catalog searches,
-- general-knowledge questions) and `capability_limit` (account ops). High
-- counts of `low_confidence` or `no_results` mean the corpus is missing
-- something -- candidate ETL backlog.
--
-- Parameter:
--   {{days}}  Metabase number, default 7
--
-- See plan: Citation contract §refusal triggers.
-- =============================================================================

SELECT
    COALESCE(m."refusalTrigger", '(unknown)') AS refusal_trigger,
    COUNT(*)                                  AS refusal_count,
    COUNT(*) FILTER (WHERE m."isPositiveRated" = true)  AS thumbs_up_count,
    COUNT(*) FILTER (WHERE m."isPositiveRated" = false) AS thumbs_down_count,
    array_agg(DISTINCT m."scopeCampus")       AS campuses_seen,
    array_agg(DISTINCT m.intent)              AS intents_seen
FROM "Message" m
WHERE m.type = 'chatbot'
  AND m."wasRefusal" = true
  AND m.timestamp >= NOW() - ({{days}} || ' days')::INTERVAL
GROUP BY m."refusalTrigger"
ORDER BY refusal_count DESC;
