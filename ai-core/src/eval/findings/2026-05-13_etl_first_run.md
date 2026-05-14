# ETL first prepare-run — findings

**Date:** 2026-05-13 06:14 UTC
**Command:** `python -m scripts.etl.run_etl --dry-run` (all three campuses)
**Runtime:** 1,776 s (~30 min) — fetch-bound, not extract-bound.
**Diff report:** `ai-core/data/diffs/2026-05-13_0614.md` (gitignored).

This is the first end-to-end run of the v2 ETL against the live
Miami sitemaps. Dry-run, no Weaviate writes. Goal: understand what
the pipeline actually sees before approving an apply phase.

## Headline numbers

| | Count |
|---|---|
| Discovered URLs (3 sitemaps + seeds) | **2,877** |
| Fetched OK | 2,612 |
| Fetch failures | 265 |
| Extracted docs | 2,514 |
| Extraction rejects | 98 (90 "empty", 8 "too_short") |
| **Chunks created** | **10,071** |
| Chunks dropped as too-short | 0 |

The pipeline runs cleanly to completion. The numbers look right at
the order of magnitude. The detail is where the work is.

## Where the URLs came from

| Sitemap | Status | Approx URLs |
|---|---|---|
| `lib.miamioh.edu/sitemap.xml` | 200 OK | ~580 — the planned Oxford corpus |
| `ham.miamioh.edu/sitemap.xml` | **404** | 0 — fell back to seed list per plan §9.5 |
| `mid.miamioh.edu/sitemap.xml` | 308 → TLS-skipped | small | per plan's per-host TLS allowlist (Middletown's cert expired) |
| `miamioh.edu/regionals/sitemap.xml` | 200 OK | ~2,300 — **this is the surprise** |

The fourth sitemap pulls in `miamioh.edu/regionals/*` URLs that
aren't library content at all — they're regional-campus marketing,
ECCOE pages, design services, etc. The plan §1 sources inventory
only mentions `ham.miamioh.edu/library/` and `mid.miamioh.edu/library/`
for regional content. The `regionals/sitemap.xml` should either be
removed from `discover.py` or path-filtered to keep only
`/library/`-prefixed entries.

## Fetch failures (265 total)

Sample of the 30 visible in the diff (the rest truncated as
"... and 235 more"):

- **23× TooManyRedirects on `miamioh.edu/regionals/marketing-communications/*`,
  `eccoe/*`, etc.** — infinite-redirect loop on regional marketing
  pages. Not library content; this is a content-filtering miss, not
  a real fetch problem.
- **7× HTTPError 404 on `lib.miamioh.edu/_*` paths** — stale internal
  paths from old strategic-plan structure (`_about/`, `_strategic/`).
  Should be added to the discover-step skip list.

Both failure classes are predictable + actionable, not data
integrity issues with the live sites.

## Extraction rejects (98)

### 90 "empty" — content extracted but body too short

Path prefix breakdown of the visible 10:

| Prefix | Count | Notes |
|---|---|---|
| `/carousel/` | 4 | Homepage carousel widgets — fragments, not pages. Correctly rejected. |
| `/about/organization/*/alumni-board/` | 2 | Stub pages with no body text. |
| `/system/amos-music-library` | 1 | Likely a redirect / pseudo-page. |
| `/computing/disabilities` | 1 | Likely a redirect to a new URL. |
| `/adobe/` | 1 | Likely a redirect. |
| `/Illuminant20`, others | 1+ | Misc redirects / stubs. |

The 80 not shown follow similar patterns. Most are defensible
rejects. A few (`/adobe/`, `/computing/disabilities`) merit a
follow-up — they're high-value short-URLs that users probably hit
directly; if they redirect, the ETL should follow the redirect, not
extract the empty redirect page.

### 8 "too_short" — body extracted but under threshold

All 8 are utility / verification HTML:
`/auto-search.html`, `/book-search.html`, `/eds-request.html`,
`/google15b5481ada6fe5aa.html` (Google site-verification), 2 regional
marketing carousel banners. Correct rejects.

## What didn't run (intentionally, dry-run)

- Embedding (`text-embedding-3-large`) — would have cost ~$0.04 for
  the 10,071 chunks.
- Weaviate upsert.
- Tombstoning (would only fire on a SECOND run since the prior index
  is empty in this worktree).
- `UrlSeen` allowlist update.

## Action items

| Action | Where | Priority |
|---|---|---|
| Filter `miamioh.edu/regionals/sitemap.xml` to `/library/` prefix only | `scripts/etl/discover.py` | high — drops most of the 265 fetch failures |
| Skip-list `lib.miamioh.edu/_*` paths in discover | `scripts/etl/discover.py` | high — drops 7 known-stale 404s |
| Follow redirects through empty-target pages | `scripts/etl/fetch.py` (or extract.py) | medium — recovers `/adobe/`, `/computing/disabilities`, `/system/amos-music-library` content |
| Cap `TooManyRedirects` retry to fail fast | `scripts/etl/fetch.py` | medium — speeds the run substantially |
| Path-prefix doubling bug: diffs land at `ai-core/ai-core/data/diffs/...` | `scripts/etl/config.py` `DIFF_REPORT_DIR` | low — cosmetic, but should be fixed |
| Crawl `ham.miamioh.edu/library/` seed-URL list | `scripts/etl/discover.py` | low — 0 Hamilton URLs in this run; plan §9.6 says hand-pick |

## What this run validates

- The pipeline runs end-to-end without crashes.
- The per-host TLS allowlist for Middletown works (the only
  warning, not an error).
- Extraction quality with `trafilatura` is reasonable: 90 empties
  out of 2,514 = 3.6% — defensible.
- 10,071 chunks from ~580 Oxford URLs ≈ 17 chunks/URL average. Plan
  §3 expected "single-digit thousands of chunks" — we're in range.
- The diff-report format is operator-readable; the FIRST_RUN.md
  workflow would work for a librarian sign-off cycle.

## Reproducing

```sh
# From ai-core/
python -m scripts.etl.run_etl --dry-run                          # full
python -m scripts.etl.run_etl --dry-run --limit 50 --campus oxford  # smoke
```

The diff is written to `ai-core/data/diffs/{date}_{HHMM}.md` and an
unsigned approval template is created alongside it. See
`scripts/etl/FIRST_RUN.md` for the librarian-handoff flow before
running `--phase apply`.

## What this run does NOT tell us

- **Content quality of the 10,071 chunks.** The chunks exist but
  are discarded by `--dry-run`. To audit chunks/URL distribution
  (plan §9.2: top-20 pollution offenders), we need either (a) an
  apply phase that writes to Weaviate, or (b) a dry-run mode that
  persists chunks to disk for inspection.
- **Whether the extracted text is hallucination-grade.** Plan §9.4:
  pick a featured-service page (printing, MakerSpace, etc.) and
  manually verify that what `trafilatura` extracted is the right
  paragraph. Worth doing before approving the apply phase.
- **Hamilton coverage.** The 404 on `ham.miamioh.edu/sitemap.xml`
  means we fall through to seed URLs, but the seed list isn't
  inspected here. Manual hand-pick per plan §9.6.

## Cost estimate for the apply phase

10,071 chunks × ~150 tokens/chunk × $0.13 / 1M tokens (text-embedding-
3-large) ≈ **$0.20** for the embedding portion. Weaviate write cost
depends on the deployment. Tombstone GC + allowlist update are
local DB writes — negligible.
