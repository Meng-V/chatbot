-- =============================================================================
-- 09 — Active manual corrections + fire counts
--
-- Lists every active ManualCorrection (suppress / replace / pin /
-- blacklist_url) with how often it has fired in retrieval. Many
-- corrections concentrated on one source URL is the signal that the
-- underlying page needs editorial work from the web team -- escalate,
-- don't just keep correcting.
--
-- Sorted by fire_count desc -- most-impactful corrections at the top.
--
-- Parameter:
--   {{include_expired}}  Metabase boolean, default false. Set true to
--                        also see corrections that auto-expired (the
--                        librarian was emailed at expiresAt and didn't
--                        renew).
--
-- See plan: Operations §Op 2 -- correction workflow.
-- =============================================================================

SELECT
    mc.id,
    mc.scope,
    mc.target,
    mc.action,
    LEFT(mc.replacement, 200) AS replacement_preview,
    mc."queryPattern"          AS query_pattern,
    LEFT(mc.reason, 200)       AS reason,
    mc."createdBy"             AS created_by,
    mc."createdAt"             AS created_at,
    mc."expiresAt"             AS expires_at,
    mc.active,
    mc."fireCount"             AS fire_count,
    -- How many days until auto-expiry (negative = already expired but
    -- still active=true; chase the librarian).
    EXTRACT(EPOCH FROM (mc."expiresAt" - NOW())) / 86400 AS days_to_expiry
FROM "ManualCorrection" mc
WHERE ({{include_expired}} = true)
   OR (mc.active = true AND mc."expiresAt" > NOW())
ORDER BY mc."fireCount" DESC, mc."createdAt" DESC
LIMIT 200;
