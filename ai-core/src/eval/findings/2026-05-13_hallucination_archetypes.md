# Five hallucination archetypes — v2 stack prevention coverage

**Date:** 2026-05-13
**Plan reference:** §9.3 Day-1 Quick Wins — "Pick the 5 worst
hallucinations the bot has produced. For each, dump retrieval logs
and categorize: bad chunk content / bad chunk metadata / model
ignored evidence / model invented URL. The distribution tells you
whether week-1 effort goes into extraction (chunk quality) or
retrieval filters (metadata) or synthesis discipline (citation
enforcement)."

## Scope and method

The plan asks for analysis of historical hallucinations from
production conversation logs. I don't have access to those logs
from this terminal. Instead this document does the structurally-
equivalent exercise:

1. Take the four hallucination types the plan explicitly named in
   its problem statement, plus one common refusal-bypass case.
2. For each, identify the **v2 stack's prevention mechanism** —
   which layer catches it, what trigger fires, what the user sees.
3. Cite the test that proves the mechanism actually works.
4. Flag the case where the test coverage is weak.

Format per archetype: **what the legacy bot did** → **v2
mechanism** → **test proof** → **gap, if any**.

## Archetype 1 — Cross-campus wire-cross ("Wertz has the MakerSpace")

The plan names this in its intro: *"crosses wires between campuses
(e.g., claiming Wertz has the MakerSpace)"*. The MakerSpace is at
King (Oxford) only. Hamilton + Middletown + Wertz queries
historically returned the Oxford answer because the bot had no
campus awareness.

**v2 mechanism (two layers):**

1. `src/scope/resolver.py` resolves a `(campus, library)` scope
   from the user's message + session origin. "MakerSpace at Wertz"
   → `(oxford, wertz)`.
2. `src/router/intent_capabilities.py` short-circuits to a
   `service_not_at_building` refusal *if* the resolved building's
   `LibrarySpace.services_offered` doesn't include `makerspace`.

**Test proof:**
- `src/eval/test_smoke_e2e.py::test_makerspace_hamilton_path_refuses_with_service_not_at_building`
  — full-stack assertion that "MakerSpace at Hamilton?" produces
  the templated refusal naming the service + redirecting to King.
- `src/synthesis/test_refusal_templates.py::test_service_not_at_building_renders_with_full_context`
  — refusal text is grammatical, names the campus + the available-at
  alternative.

**Gap:** the `LibrarySpace` truth-table only matters for buildings
that explicitly enumerate `services_offered`. If Wertz's row exists
but its `services_offered` field is empty or stale, the guard
won't fire. This is a data-discipline problem, not a code problem
— the LibrarySpace seed needs librarian review.

## Archetype 2 — Fabricated LibGuide / policy URLs

The plan names this: *"fabricates URLs to LibGuides/policies that
don't exist"*. The legacy bot would produce plausible-looking URLs
like `https://libguides.lib.miamioh.edu/biology-2024-policies/`
that 404. Users clicking those URLs lost trust instantly.

**v2 mechanism (three layers):**

1. The ETL writes every successfully-fetched URL into a Postgres
   `UrlSeen` allowlist (`scripts/etl/upsert.py` + the Prisma
   migration in #13).
2. The synthesizer's `src/synthesis/post_processor.py` extracts
   every URL the model emits in its answer and validates each
   against the allowlist plus the retrieval-bundle's source_urls.
3. Any URL not in either set triggers a `citation_invalid` refusal.

**Test proof:**
- `src/synthesis/test_post_processor.py::test_url_not_cited_not_in_allowlist_refuses`
- `src/synthesis/test_post_processor.py::test_url_cited_not_in_allowlist_is_ok`
  (URLs the model cites from real retrieval evidence are OK even
  if not yet in the allowlist)
- `src/synthesis/test_post_processor.py::test_url_trailing_punctuation_stripped`
  (the validator is robust to "url." / "url," edge cases)
- `src/synthesis/test_post_processor.py::test_multiple_urls_all_cited_is_ok`

**Gap:** the allowlist is built by the ETL. If the ETL hasn't run
yet (or ran but the `UrlSeen` table is empty for cost / migration
reasons), the validator's allowlist is empty and EVERY URL the
model emits is rejected → blanket refusal. Operational: PR #13
must land + ETL must run + apply phase must succeed before this
mechanism is useful in prod. **#13 has landed; ETL has run
dry-run; apply phase hasn't.**

## Archetype 3 — Polluted printing/services content

The plan's intro: *"answers from polluted retrievals (especially
around printing/services)"*. Legacy bot mixed printing instructions
across libraries because nav/sidebar links to `/use/technology/printing/`
appeared on every page; the chunker indexed those repeated mentions
without distinguishing the canonical content page from the
boilerplate references.

**v2 mechanism (two layers):**

1. `scripts/etl/extract.py` uses `trafilatura` (with a fallback)
   to extract only the `<main>` content of each page — strips nav,
   footer, sidebar. Boilerplate residue is also filtered: chunks
   that are 80%+ sitewide-template text are dropped at
   `scripts/etl/chunker.py`.
2. Every chunk carries `(campus, library, topic, source_url)` so
   retrieval can filter to the canonical printing page rather than
   ranking every page that *mentions* printing.

**Test proof:**
- `scripts/etl/test_extract.py` — boilerplate-stripping tests
  against real Miami HTML fixtures.
- `scripts/etl/test_chunker.py` — short-chunk rejection threshold
  (50 tokens) tests.
- `src/retrieval/test_scope_filter.py` — proves scope-based
  filtering on chunk metadata is wired through hybrid search.

**Gap:** "polluted retrievals" is hard to test without a populated
Weaviate. The smoke-e2e fixture for printing isn't wired yet (see
the 6 fixtures in `src/eval/smoke_e2e.py` — printing isn't one of
them). After the ETL apply phase, the plan §9.2 quick win
"top-20 chunks-per-source_url offenders" is the natural way to
verify pollution is gone.

## Archetype 4 — Stale event/news content presented as current

The plan §1 sources inventory: *"`/about/news-events/*` (all news,
events, exhibits, social) ... Not ingested at all. ETL filters out
URL prefix `/about/news-events/`. News and event content is the
prime source of 'fake service' hallucinations (defunct programs,
expired hours, old exhibits)."*

**v2 mechanism (two layers):**

1. `scripts/etl/discover.py` filters `/about/news-events/*` URLs
   out of the crawl set entirely. The chunks don't exist to be
   retrieved.
2. If a user explicitly asks for news/events, the kNN classifier
   picks `events_news` → the capability registry short-circuits
   to a `NEWS_EXCLUDED` refusal pointing to the live News & Events
   page.

**Test proof:**
- `scripts/etl/test_discover.py` — proves news-events URL prefix
  is excluded.
- `src/router/test_intent_capabilities.py::test_events_news_is_refuse_with_news_excluded_trigger`
- `src/synthesis/test_refusal_templates.py::test_scope_free_triggers_render_without_context`
  (NEWS_EXCLUDED is in the scope-free list, renders cleanly).

**Gap:** none material. The `events_news` intent had 13 exemplars
in the labeled v38 set — fewer than the strong intents (218 for
newspapers, 166 for adobe) but enough to route reliably.

(**Correction from earlier draft:** the v3 gold set [PR #39] does
cover `events_news` with 3 cases: `events_this_week`,
`events_exhibits`, `events_workshop`. Re-running the classifier
eval against the full 184-case v3 gold set shows 2/3 correct on
this intent — the single miss routes to `out_of_scope`, which
still produces a refusal in the orchestrator, just via a less-
specific path.)

## Archetype 5 — Account-state hallucination ("Your fines are $14.50")

Not in the plan's intro, but a known legacy failure: when users
asked about their own checkouts / fines / holds, the bot would
sometimes fabricate plausible-sounding account state. The bot has
no access to user-specific account data at all; any answer was a
hallucination.

**v2 mechanism (one decisive layer):**

`src/router/intent_capabilities.py` registers the `account` intent
as REFUSE-tier with the `ACCOUNT_PRIVACY` trigger, pointing the
user to MyAccount login. The orchestrator short-circuits BEFORE
the agent / synthesizer runs — there is no path through the bot
where it could compose an account-state answer.

**Test proof:**
- `src/router/test_intent_capabilities.py::test_account_is_refuse_with_privacy_trigger`
- `src/eval/test_smoke_e2e.py::test_account_path_response_is_refusal_with_myaccount_link`
  (full-stack: input "what are my checkouts" → templated refusal
  with MyAccount URL, no agent invocation, no LLM tokens consumed).

**Gap:** none. This is the strongest preventive coverage in the
stack — the architecture rules out the answer at the routing
layer, not just at the synthesis layer.

## Summary table

| Archetype | Layer that catches it | Test ref | Gap |
|---|---|---|---|
| 1. Cross-campus wire-cross | Scope resolver + capability tier (`service_not_at_building`) | `test_makerspace_hamilton_path_refuses_with_service_not_at_building` | `LibrarySpace.services_offered` is data-dependent — librarian must seed |
| 2. Fabricated URLs | `UrlSeen` allowlist + post-processor citation validator | `test_url_not_cited_not_in_allowlist_refuses` | Apply phase hasn't run; `UrlSeen` empty in prod |
| 3. Polluted retrievals | `trafilatura` extraction + boilerplate filter + scope-tagged chunks | `test_extract.py` + `test_scope_filter.py` | No printing-specific smoke fixture; depends on apply phase |
| 4. Stale events/news | ETL excludes `/about/news-events/*` + `events_news` REFUSE | `test_events_news_is_refuse_with_news_excluded_trigger` | None material — v3 gold set covers `events_news` with 3 cases (2/3 correct on classifier eval) |
| 5. Account hallucination | `account` REFUSE before agent runs | `test_account_path_response_is_refusal_with_myaccount_link` | None — strongest coverage |

## What this exercise does NOT tell us

- **It doesn't replicate the plan §9.3 categorization** (bad chunk
  content / bad chunk metadata / model ignored evidence / model
  invented URL) because that requires production retrieval logs.
  When the v2 stack runs in shadow mode or behind the flag at 10%,
  the per-turn logs (`src/observability/logging.py` writes
  `ChunkProvenance`-joined turn records) will support that
  analysis directly.
- **It doesn't prove the smoke_e2e tests would catch every
  variant** — they test ARCHETYPE behavior, not every phrasing.
  The gold set (`src/eval/golden_set.jsonl`, 129 questions) is
  the broader-coverage harness; it's wired into
  `scripts/eval_classifier_v38.py` for the classifier path.
  Full bot wiring is still TODO in `src/eval/run_eval.py`.

## Operational checklist before launching at 10% flag

- [x] PR #13 (Prisma migration with `UrlSeen`) — landed
- [ ] ETL apply phase run + librarian-approved diff
- [ ] `LibrarySpace.services_offered` seeded for all 6 buildings
- [ ] `src/eval/run_eval.py` TODOs filled in (bot orchestrator +
      judge wiring) so the gold-set eval reports end-to-end
      citation validity rate, not just intent accuracy.
- [x] Add ≥2 gold-set cases for `events_news` intent — done in PR #39 (3 cases).
- [ ] Add a "printing pollution" smoke-e2e fixture once Weaviate
      has live chunks.
