# 07 — Data Pipeline

> How the knowledge base gets populated and refreshed. Includes the truth-table tables, Weaviate chunks, and the LibCal ID mapping.

## The 3 data tiers (recap)

| Tier | Storage | Refresh cadence | Example content |
|---|---|---|---|
| **Live API** | Never cached (>5min) | Per-request | LibCal hours, room availability, LibAnswers chat status |
| **Structured truth** | Postgres | Daily / on-demand | Librarians, library spaces, URL allowlist |
| **Prose** | Weaviate | Weekly (ETL) | Web pages, LibGuide content, operator-gold chunks |

If you're not sure where new data should go, the rule of thumb:
- Changes intra-day, has an authoritative API? → Live
- Has a primary key, looked up by name/ID? → Postgres
- Long-form text, searched semantically? → Weaviate

---

## Postgres truth tables

### `LibrarySpace_v2` — Buildings

The canonical record for each physical building. Used by `lookup_space` tool.

```sql
SELECT library, campus, name, address, phone, libcal_id, services_offered
FROM "LibrarySpace_v2"
ORDER BY library;
```

Expected rows (as of 2026-05-27):

| library | campus | name | libcal_id |
|---|---|---|---|
| king | oxford | Edward King Library | 8113 |
| wertz | oxford | Wertz Art & Architecture Library | 8116 |
| special | oxford | Walter Havighurst Special Collections & University Archives | 8424 |
| makerspace | oxford | MakerSpace at King Library | 11904 |
| rentschler | hamilton | Rentschler Library | 9226 |
| gardner_harvey | middletown | Gardner-Harvey Library | 9227 |
| sword | middletown | Southwest Ohio Regional Depository (SWORD) | NULL |

SWORD has no LibCal tracking because it's a depository, not a public-hours space.

### Adding a new building

Suppose Miami adds a new branch. Steps:

1. **Get the LibCal location ID.** Open `https://muohio.libcal.com/hours/` — your new building should appear in the Hours Preview if Springshare added it. Hover over the link to find the location ID, or ask Springshare admin.

2. **Insert into `LibrarySpace_v2`:**
   ```bash
   set -a; source /opt/chatbot/current/.env; set +a
   psql "$DATABASE_URL" <<'SQL'
   INSERT INTO "LibrarySpace_v2" (
     id, library, campus, name, building_role,
     address, phone, libcal_id, capacity, equipment, services_offered,
     hours_source, source_url, "createdAt", "updatedAt"
   ) VALUES (
     gen_random_uuid(),
     'new_branch', 'oxford', 'New Branch Name', 'sub_building',
     '123 Some St, Oxford, OH 45056',
     '(513) 529-XXXX',
     'NEW_LIBCAL_ID',
     NULL,
     ARRAY['computers', 'printers'],
     ARRAY['printing', 'study_rooms'],
     'https://muohio.libcal.com/hours/NEW_LIBCAL_ID',
     'https://www.lib.miamioh.edu/about/locations/new-branch/',
     NOW(), NOW()
   );
   SQL
   ```

3. **Add alias mappings in `ai-core/src/eval/real_backends.py`** in the `_ALIASES` dict inside `_make_lookup_space`:
   ```python
   "new branch": "new_branch",
   "new branch library": "new_branch",
   "the new branch": "new_branch",
   ```

4. **Add to `LibrarySpace` v1 table** (so legacy `LocationService.get_location_id` finds it for `get_hours`):
   ```sql
   INSERT INTO "LibrarySpace" (
     "libraryId", name, "displayName", "shortName", "libcalLocationId",
     "spaceType", website, phone, ...
   ) VALUES (
     '<library-uuid>', 'New Branch', 'Full Name', 'new_branch', 'NEW_LIBCAL_ID',
     'library', 'https://...', '(513) 529-XXXX'
   );
   ```

5. **Add alias to the scope resolver** in `ai-core/src/scope/aliases.py` so user phrases route there:
   ```python
   "new branch": ("oxford", "new_branch"),
   ```

6. **Add gold test cases** to confirm the bot answers correctly:
   ```bash
   # Add to ai-core/src/eval/golden_set.jsonl
   {"id":"newbr_hours","question":"What are the hours at the new branch?","intent":"hours","scope_campus":"oxford","scope_library":"new_branch","expected_answer":"Should call get_hours for new_branch and return today's hours from LibCal.","expected_outcome":"answer","allowed_urls":["https://www.lib.miamioh.edu/about/locations/new-branch/"],"category":"hours"}
   ```

7. **Re-run wire script** so the gold case URLs get into Weaviate:
   ```bash
   .venv/bin/python scripts/operator_wiring/wire_gold_to_weaviate.py
   ```

8. **Run a smoke eval** to confirm:
   ```bash
   .venv/bin/python -m src.eval.run_eval --with-real-llm --with-judge --filter hours
   ```

9. Commit + deploy.

---

### `Librarian` — Subject librarians

```sql
SELECT name, email, campus, "isRegional"
FROM "Librarian"
WHERE "isActive" = true
ORDER BY campus, name;
```

Linked to `Subject` via `LibrarianSubject` (many-to-many). Linked to `LibGuide` via `LibGuideSubject`.

These rows are populated by a separate sync script (not part of this guide) that pulls from the LibGuides API daily.

### `UrlSeen` — URL allowlist

Every URL the bot is allowed to cite. Populated by:
- The ETL crawl (any URL that returned 200 within last week)
- The operator-gold wiring script (every `allowed_urls` from gold cases)
- Manual inserts (rare, for unusual cases)

```sql
SELECT count(*) FROM "UrlSeen" WHERE "isActive" = true;
-- typical: 400-1000 rows
```

To add a URL manually:
```sql
INSERT INTO "UrlSeen" (url, "httpStatus", "contentType", source, priority, "isActive", "isBlacklisted", "lastSeen", "createdAt", "updatedAt")
VALUES (
  'https://www.lib.miamioh.edu/some/new/page/',
  200, 'text/html', 'manual', 'normal',
  true, false, NOW(), NOW(), NOW()
) ON CONFLICT (url) DO UPDATE SET "isActive" = true, "updatedAt" = NOW();
```

### `ManualCorrection` — Librarian overrides

See [08-OPERATIONS.md](08-OPERATIONS.md).

---

## Weaviate chunks

### Collection naming

Versioned: `Chunk_v<date>` (e.g., `Chunk_vv20260514_1929`). The active collection is set via env var:

```bash
echo $WEAVIATE_CHUNK_COLLECTION
# Chunk_vv20260514_1929
```

To rebuild from scratch with a new collection name:
1. Create new collection via Weaviate admin
2. Update `WEAVIATE_CHUNK_COLLECTION` in `.env`
3. Restart backend
4. Run ETL + operator-gold wiring to populate

### Chunk types

| chunk_id prefix | Source | Purpose |
|---|---|---|
| `operator-gold-<case_id>-<n>` | `wire_gold_to_weaviate.py` | High-priority Q+A pairs from gold cases. Match exact user wording. |
| `c-<hash>` | ETL crawl | Web page chunks from sitemap-driven crawl |
| `manual-<id>` | Manual injection | Rare; admin tool |

### Re-wiring operator-gold chunks

When `golden_set*.jsonl` files change:

```bash
cd /opt/chatbot/current/ai-core
.venv/bin/python scripts/operator_wiring/wire_gold_to_weaviate.py
```

This script:
1. Reads all gold cases from `golden_set.jsonl`
2. For each case with `allowed_urls`, generates a chunk per URL with text `"Question: <Q>\nAnswer (operator-verified): <expected_answer>"`
3. Embeds via `text-embedding-3-large`
4. Deletes prior `operator-gold-*` chunks (idempotent)
5. Upserts new chunks
6. Inserts any new URLs into `UrlSeen`

Expected output:
```
Loaded 234 gold cases
Cases with URLs: 217
Chunks to upsert: 276
Embedded 276 vectors
Removing prior operator-gold chunks (idempotent)...
Inserted OK: 276
UrlSeen rows added: 0  (or N if new URLs)
=== WIRING COMPLETE ===
```

Run after any gold-set change. Run on prod after any backend deploy that includes new gold cases.

---

## ETL pipeline (the weekly web-crawl)

> Status: scaffolded but not always cron'd in production. Confirm with ops.

`ai-core/scripts/etl/run_etl.py` orchestrates:

```
1. discover()  → pull sitemap.xml from 3 domains (Oxford, Hamilton, Middletown)
2. fetch(url)  → HTTP GET, follow redirects, cache to data/raw/
3. extract(html) → strip nav/footer with trafilatura, keep <main> content
4. classify(url, body) → assign topic, campus, library, featured_service tags
5. dedupe(content_hash) → skip unchanged content
6. chunk(body) → 400-token chunks, 50 overlap, structure-aware
7. embed(chunks) → text-embedding-3-large, batched
8. upsert() → Weaviate transactional batch
9. tombstone() → mark removed URLs as deleted
10. update_url_allowlist() → upsert UrlSeen
11. write_diff_report() → human-readable for librarian approval
```

Two phases: `--phase prepare` (compute diff, do NOT apply) and `--phase apply` (actually upsert). The prepare-phase output should be reviewed by a librarian before apply runs.

### Run the prepare phase manually

```bash
cd /opt/chatbot/current/ai-core
.venv/bin/python -m scripts.etl.run_etl --phase prepare
# Outputs:
#   data/diffs/<date>.md       — summary for the librarian
#   data/etl_state/pending.json — what would be applied
```

### Apply (after librarian approval)

```bash
.venv/bin/python -m scripts.etl.run_etl --phase apply
# Reads pending.json, runs steps 7-10
```

### Add a new source URL to the crawl

The crawl is driven by sitemaps. To add a source not in any sitemap:
1. Add the URL to `ai-core/scripts/etl/manual_seed_urls.txt` (or similar — check the file in your tree)
2. Re-run ETL

---

## LibCal API integration

### How `get_hours` works end-to-end

```
agent calls get_hours("makerspace")
   → ai-core/src/eval/real_backends.py::_make_get_hours
   → src/tools/libcal_comprehensive_tools.py::LibCalWeekHoursTool.execute
   → src/services/location_service.py::LocationService.get_location_id("makerspace")
     → queries OLD LibrarySpace table (v1, not v2)
     → returns libcal_id = "11904"
   → HTTP GET https://muohio.libcal.com/api/1.1/hours/11904
     (OAuth Bearer token cached in module-level singleton)
   → parses response, formats as text
   → returns {"success": true, "hours": "...", "source_url": "..."}
```

**Note the v1/v2 split:** `LocationService` reads from the OLD `LibrarySpace` table. The new `LibrarySpace_v2` table is for `lookup_space` only. If you add a building, add to BOTH or hours won't work.

### Add a new LibCal ID mapping

Same as "Adding a new building" above. Make sure step 4 (add to v1 `LibrarySpace`) is done.

### OAuth credentials

Stored in `.env`:
```bash
LIBCAL_OAUTH_URL=https://muohio.libcal.com/api/1.1/oauth/token
LIBCAL_CLIENT_ID=560
LIBCAL_CLIENT_SECRET=...
LIBCAL_GRANT_TYPE=client_credentials
```

Token is fetched once at first API call and cached in memory until expiry. If you rotate credentials, restart the backend.

### LibCal rate limits

Springshare: 5 RPS per OAuth client. The bot's natural traffic is far below this, but a runaway eval calling `get_hours` in tight loops can hit it. The `command_timeout` on `_bridge` calls is 30s, so a rate-limit will eventually result in a tool error.

---

## LibGuides API integration

Used by `lookup_librarian` for subject-based searches.

```
agent calls lookup_librarian(subject="geography")
   → real_backends.py::_make_lookup_librarian
   → src/tools/libguide_comprehensive_tools.py::LibGuideSubjectLookupTool.execute(subject_name="geography")
   → LibApps API call
   → returns list of librarian dicts
```

For unknown subjects (e.g., "MakerSpace" — not a real subject in LibGuides), the API returns empty. The orchestrator's evidence handler now provides a fallback URL to the appropriate staff page (see commit `1de6dab`).

### LibApps credentials

```bash
LIBAPPS_CLIENT_ID=...
LIBAPPS_CLIENT_SECRET=...
```

Same OAuth dance as LibCal.

---

## The `_bridge` pattern (you'll wonder why it exists)

`real_backends.py` has a daemon-thread event loop wrapper called `_AsyncBridge`. Some legacy tools (LibCal, LibGuides) use the `get_prisma_client()` SINGLETON pattern — the Prisma client binds to whatever asyncio loop first connected it.

If you use the simple "fresh loop per call" pattern (`asyncio.run()` each time), the singleton gets bound to a doomed loop and breaks on subsequent calls.

`_bridge` solves this by maintaining ONE persistent loop on a daemon thread that all legacy-tool coroutines run on. The singleton binds once and stays valid for the eval's lifetime.

You don't usually need to know about this. But if you add a new backend that touches Prisma or LocationService, route it through `_bridge`, not `asyncio.run()`.

---

## Connection pool patterns

| Backend | Pattern | Why |
|---|---|---|
| `lookup_librarian` (Prisma path) | `_db` connect-per-call | Self-contained, simple, low call volume |
| `lookup_librarian` (LibGuides API path) | `_bridge` | Uses singleton client |
| `lookup_space` | asyncpg pool (lazy-init in `_bridge` loop) | High volume in eval; without pooling, exhausts Postgres connections |
| `get_hours`, `get_room_availability` | `_bridge` (legacy LibCal tools) | Uses singleton LocationService |
| `validate_url` | `_db` connect-per-call (`_ConnectPerCallUrlSeenStore`) | Lookup is fast; pooling not worth complexity |

If you see "RuntimeError" or "too many connections" mid-eval, suspect connection pool exhaustion on whichever backend is new. The fix is to migrate it to a pooled pattern (see `_make_lookup_space` for the template).

---

## Data backup / disaster recovery

### Postgres

Standard Postgres backup. Take `pg_dump` snapshots regularly:
```bash
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d).sql
```

### Weaviate

Snapshot the whole collection before any major change:
```bash
# Via Weaviate's backup API
curl -X POST http://localhost:8888/v1/backups/filesystem \
  -H 'Content-Type: application/json' \
  -d '{"id":"snapshot-'"$(date +%Y%m%d)"'","include":["'"$WEAVIATE_CHUNK_COLLECTION"'"]}'
```

Restore is the inverse with the backup ID.

### What to back up before a major change

- Postgres: `LibrarySpace_v2`, `LibrarySpace`, `Librarian`, `UrlSeen`, `ManualCorrection`, `ChunkProvenance`
- Weaviate: the current `Chunk_v*` collection
- The repo (already in git)

---

## "What does this column / field mean" reference

A few non-obvious fields:

| Table.column | Meaning |
|---|---|
| `LibrarySpace_v2.building_role` | `main_building` / `sub_building` / `department` / `depository`. Used by some UI. |
| `LibrarySpace_v2.services_offered` | Array of service strings. The bot uses this for cross-campus refusals (e.g., MakerSpace not at Hamilton). |
| `LibrarySpace.shortName` | The KEY that `LocationService.get_location_id` matches against. |
| `Librarian.isRegional` | True if assigned to a regional campus (Hamilton/Middletown). Influences kNN-style answering. |
| `UrlSeen.source` | Where the URL came from: `sitemap`, `libguide_seed`, `operator_gold_2026-05-XX`, `manual`. Useful for cleanup. |
| `UrlSeen.priority` | `high` / `normal` / `low`. High-priority URLs survive a single ETL miss (don't get tombstoned for 1 missing crawl). |
| `ManualCorrection.scope` | `url` / `chunk` / `intent` / `global` — what the correction targets. |
| `ManualCorrection.action` | `suppress` / `replace` / `pin` / `blacklist_url`. |
| `ChunkProvenance.content_hash` | SHA-256 of cleaned chunk text. Used for dedupe in ETL. |
