-- =============================================================================
-- 08 — Daily cost + cache-hit ratio per call site
--
-- Reads from DailyCost (populated by ai-core/scripts/cost_rollup.py).
-- Per-call-site breakdown so a cache regression on one site (e.g.
-- synthesizer prefix drifted, dropping cache from 0.7 to 0.3) is
-- visible immediately rather than buried in a global average.
--
-- Week-4 gate: every call site individually >= 0.5 cache-hit, average
-- across all >= 0.6.
--
-- Parameter:
--   {{days}}  Metabase number, default 30
--
-- See plan: Layer 4 -- prompt shrinkage and caching strategy / measurement.
-- =============================================================================

SELECT
    date,
    "callSite"            AS call_site,
    model,
    "callCount"           AS call_count,
    "inputTokens"         AS input_tokens,
    "cachedTokens"        AS cached_tokens,
    "outputTokens"        AS output_tokens,
    ROUND(
        100.0 * "cachedTokens" / NULLIF("inputTokens", 0),
        1
    )                     AS cache_hit_pct,
    ROUND(usd::numeric, 4) AS cost_usd
FROM "DailyCost"
WHERE date >= (NOW() - ({{days}} || ' days')::INTERVAL)::date
ORDER BY date DESC, "callSite", model;
