# 09 — Backlog & Deferred Enhancements

**Audience:** the operator (Meng) and any future engineer deciding "what's left to make this great?"

**Why this file exists.** During the v2 build + beta launch we made a stream of *"good enough for beta, do it properly later"* calls. This is the durable record of those calls so they don't get lost. Each item says **what**, **why it was deferred**, **rough effort**, **which files it touches**, and how it maps to the robustness-ladder thresholds in the plan (`~/.claude/plans/i-am-a-web-breezy-prism.md`, section "Robustness ladder").

**How to read the priority tags:**
- 🔴 **Ops-critical** — silent breakage or money/PII risk. Do before scaling traffic past beta.
- 🟠 **Trust/quality** — affects answer quality or librarian trust. Do during beta iteration.
- 🟢 **Polish** — nice-to-have; real users won't block on it.

**How to retire an item:** when you do it, delete it from this file in the same PR that lands the work, and reference this file in the commit. The git history of this file *is* the changelog of "deferred → done."

> Status snapshot is **2026-06-08** (beta on prod). Treat the priorities as a starting point, not gospel — re-rank as real-user signal arrives.

---

## A. Citations & answer UX

### A1. 🟢 Typed citations — the "Option 3" Live badge
**What.** Render live-API citations (hours, room availability, Ask Us status) visually distinct from prose citations — e.g. a green "Live · LibCal" badge — instead of the current uniform chip.

**Why deferred.** We shipped **Option 1** (2026-06-08): the backend writes an *honest* snippet for live-API citations (`_citation_snippet` in `ai-core/src/synthesis/synthesizer.py`) so the chip no longer masquerades the API value as a verbatim page quote, and the cited URL still points at the canonical page for verification. That's honest and sufficient for beta. Option 3 is pure polish.

**Why it's more work.** A citation crosses 5 hops backend→browser, and the source-type (`kind`) is dropped at hop ①:
```
EvidenceChunk(.kind="live_api")          ← corrections.py
  → ① parse_synthesizer_response          → Citation has NO kind field
  → ② post_processor
  → ③ _shape_response
  → ④ turnresponse_to_wire  → wire {n,url,snippet}   ← kind not forwarded
  → ⑤ Socket.IO → frontend CitationChip   ← can't tell live from prose
```
To render a styled badge the frontend must *know* the kind, so you add a `kind` field to `Citation` (`post_processor.py`), carry it in `parse_synthesizer_response`, include it in `turnresponse_to_wire` (`v2_serving.py`), and branch on it in `client/src/components/CitationChip.jsx`.

**Effort.** ~0.5–1 day, full-stack. **Touches:** `synthesis/post_processor.py`, `synthesis/synthesizer.py`, `graph/v2_serving.py`, `client/src/components/CitationChip.jsx` (+ maybe `ParseLinks.jsx`).

### A2. 🟠 Trace the `citation_invalid` post-processor escapes
**What.** When the post-processor downgrades a turn to a refusal because a URL/citation failed validation, log *which* URL/citation and why, so we can tell "model fabricated a URL" from "real URL just not in the `UrlSeen` allowlist."

**Why deferred.** Eval showed ~7 `citation_invalid` cases but we couldn't cheaply tell which were genuine fabrications vs. allowlist gaps. Needs structured logging in `post_processor.validate` (it already builds `ValidationFailure.detail` strings — just ship them to the turn log).

**Effort.** ~0.5 day. **Touches:** `synthesis/post_processor.py`, `graph/new_orchestrator.py` (`deps.log_turn`).

### A3. 🔴 Post-processor doesn't verify a cited URL came from real evidence
**What.** The post-processor's URL check (`post_processor.validate`, rule 3) accepts any URL that appears in `citations[].url` OR the (currently empty, see D4) `UrlSeen` allowlist. It does NOT cross-check that the cited URL is actually the `source_url` of an evidence chunk the agent retrieved. So the synthesizer LLM can fabricate a citation from the **hardcoded reference-URL list in `prompts/synthesizer_v1.py`** even when retrieval returned zero evidence — the model writes `...[1].` + `citations:[{n:1,url:<a prompt URL>}]`, and every post-processor check passes because the URL is "cited."

**How it surfaced (2026-06-08).** A user asked "where to checkout Adobe." Retrieval returned no Adobe evidence on most turns, yet the bot confidently answered citing `…/use/technology/software/adobe/` — a **404** that lived in the synthesizer prompt's reference list. Probed 5×: 4 refusals, 1 answer whose citation URL was a *prompt* URL, not an evidence `source_url`. This is exactly the "fabricated URL" failure the whole project exists to prevent, slipping through the citation contract.

**Fix direction.** In `post_processor.validate`, add: every URL the answer cites must equal the `source_url` of some chunk in the `evidence` bundle passed in (the function already receives `evidence`). A cited URL with no backing evidence chunk → `CITATION_INVALID` refusal. Consider also dropping the hardcoded URL list from the synthesizer prompt entirely (it's the enabler) — or keeping it only as a cache-anchor that the post-processor will still reject if used without evidence.

**Effort.** ~1 day incl. test + refusal-rate check (this WILL raise refusals on thin-evidence turns — that's correct, but measure it). **Touches:** `synthesis/post_processor.py`, `prompts/synthesizer_v1.py`.

### A4. 🟠 Hardcoded prompt URLs rot silently — wire the validator into deploy/CI
**What.** `scripts/validate_prompt_urls.py` (added 2026-06-08) extracts every URL from the prompt/source files and HTTP-checks it; it found 3 dead URLs in `synthesizer_v1.py` (Adobe, citation guide, technology checkout) that had been served to users. It's not yet run automatically. Wire it into the pre-deploy check (see C1) and a weekly cron so a rotted URL fails CI instead of reaching a user. `python scripts/validate_prompt_urls.py` exits non-zero on any non-200.

**Effort.** ~0.5 day (cron + pre-deploy hook). Also retrieval-quality sibling: the Adobe **Weaviate chunk exists** (`source_url=…/adobe/`, 200) but retrieval surfaced it only ~1/5 for "where to checkout Adobe" — featured-service retrieval is under-boosting; revisit the `featured_service` rank boost in `retrieval/scope_filter.py`.

---

## B. Telemetry & cost observability

### B1. 🔴 v2 turn telemetry is not persisted (ModelTokenUsage empty for v2)
**What.** The v2 socket handler `_v2_message` (`ai-core/src/main.py`) does **not** call `log_token_usage`, `update_conversation_tools`, or `log_tool_execution` the way the legacy v1 handler does. Also `turnresponse_to_wire` (`v2_serving.py`) drops the `tokens` dict that `TurnResponse` carries.

**Impact.** `ModelTokenUsage` has **zero rows for v2 traffic** → `scripts/cost_rollup.py` reports `$0` → the plan's cache-hit-rate gate (`cached_input_tokens / input_tokens ≥ 0.6`) is unverifiable on prod, and a prompt regression that tanks the cache burns budget silently. `ToolExecution` is also empty, so "what tools did this turn call?" is unanswerable forensically.

**Fix sketch.** Add `tokens` (and `tool_calls`/`agents_used`) to the `turnresponse_to_wire` payload; in `_v2_message`, after `handle_v2_message`, `await log_token_usage(...)` + `await update_conversation_tools(...)` mirroring the v1 block (`main.py` ~line 505–530).

**Effort.** ~0.5 day. **Touches:** `graph/v2_serving.py`, `graph/new_orchestrator.py` (TurnResponse already has tokens), `main.py`.

### B2. 🟠 Confirm ETL-prepare + cost_rollup crons actually run on prod
**What.** The weekly ETL-prepare cron and the daily `cost_rollup.py` cron exist as scripts but were never confirmed scheduled on `ulblwebp20`. Without ETL the index ages weekly; without cost_rollup the `DailyCost` table stays empty.

**Effort.** ~0.5 day (crontab + a freshness alert). **Touches:** prod crontab, `scripts/cost_rollup.py`, `scripts/etl/`.

### B3. 🟢 Weekly subject-librarian digest email
**What.** `scripts/digest_email.py` (Op 1 plan) exists but isn't cron'd. Sends each subject librarian their unreviewed/thumbs-down conversations Monday morning.

**Effort.** ~0.5 day, blocked on B-tier review surface being useful first.

---

## C. Deployment hardening (the "prod-only bugs" class)

> Context: beta launch surfaced a string of bugs that **passed locally but broke on prod** — nginx `/health` routing, a Responses-API conversation-shape 400 (only triggers on the *2nd* user turn), a missing 332 MB embedding cache, starlette/fastapi version drift. Root cause: our eval/test suite measures *answer quality* but never exercised the *deployment chain* or *multi-turn* paths. C1/C2 close that gap.

### C1. 🔴 `scripts/preflight.sh` — pre-deploy environment check
**What.** A script Rachel runs on the prod box *before* restarting the backend. Checks ~10 deployment-chain things and prints pass/fail:
nginx forwards `/health/*` and `/smartchatbot/socket.io` to `:8081`; `classifier_embeddings.json` present (or symlinked); `prisma generate` done; starlette/fastapi versions match `requirements.txt`; SSH tunnels up; required `.env` keys present; `ADMIN_API_TOKEN` set; disk space; `socketio_path` config; final `GET /smoketest/v2`.

**Why.** Every prod-only bug above would have been caught by one line in this script.

**Effort.** ~0.5 day. **New file:** `ai-core/scripts/preflight.sh`.

### C2. 🔴 `scripts/post_deploy_check.sh` — multi-turn smoke
**What.** After `systemctl restart`, connect a real Socket.IO client, send "hello" → expect greeting, then send a 2nd message "what time do you close?" → assert non-empty, has a citation, is NOT "I encountered an error."

**Why.** The 2026-05-28 Responses-API 400 only fired on the **second** turn (conversation-history shape). A single-turn smoketest (`/smoketest/v2`) passes while real users break. This catches exactly that.

**Effort.** ~0.5 day. **New file:** `ai-core/scripts/post_deploy_check.sh`.

### C3. 🟠 Persist the classifier embedding cache across deploys
**What.** `ai-core/data/eval/classifier_embeddings.json` is 332 MB (5,555 exemplars × 3,072 dims) — over GitHub's 100 MB limit, and `ai-core/data/` is gitignored. Each clean build loses it → cold-start re-embeds all exemplars live (~30–60 s, ~$0.50) and can time out uvicorn.
**Recommended fix:** move it to `/opt/chatbot/shared/` and symlink on every deploy (see the email to Rachel / `03-DEPLOYMENT.md`). Regenerate only when exemplars change: `python scripts/eval_classifier_v38.py`.

**Effort.** 15 min one-time on prod + 1 line in the deploy script.

### C4. 🟠 nginx `location /health` block + `ADMIN_API_TOKEN` on prod
**What.** Two ops tasks owned by Rachel: (a) nginx must forward `/health/*` to `localhost:8081` (frontend liveness probe depends on `/health/live`); (b) set `ADMIN_API_TOKEN` env so the Op 1 review surface mounts (it fail-closes when unset, which is why `/admin/review` 404s today).

**Effort.** Ops, ~30 min. Not code.

---

## D. Librarian operations surfaces (plan Op 1 / Op 2)

### D1. 🟠 ManualCorrection CRUD endpoints are 501 stubs
**What.** The 4 corrections endpoints (`/admin/corrections` create/list/update/delete) return `501 Not Implemented`. Librarians cannot file a correction through any UI — the *only* way to suppress a bad chunk / blacklist a fabricated URL / pin a canonical page today is hand-writing SQL into the `ManualCorrection` table.

**Why it matters.** The plan calls `ManualCorrection` the **safety net** for content the bot gets wrong, and the count of corrections filed is the #1 signal of healthy beta operation. With 501 stubs, that signal can't be generated by non-engineers. `apply_corrections()` (read side) IS wired — only the write path is missing.

**Effort.** ~1 day for the endpoints; +~1 week for a real React modal. MVP: a thin internal form or even a documented SQL snippet. **Touches:** `ai-core/src/api/admin/`, `client/src/admin/`.

### D2. 🟢 Op 1 review queue as a real React surface
**What.** Subject-librarian review queue + per-turn verdict UI + aggregate health view. Currently spec'd as a Metabase/spreadsheet MVP. The full React surface is the threshold-4 ("robust") deliverable.

**Effort.** ~1–2 weeks. Blocked on B1 (need real per-turn telemetry to populate it).

### D3. 🔴 ManualCorrection overrides silently don't apply on the v2 socket path
**What.** On the real production path (`handle_v2_message` → `run_turn` via `loop.run_in_executor(None, ...)`, a worker thread), `_safe_load_corrections()` calls `PrismaCorrectionsStore.load_active()`, which awaits a Prisma client bound to the **main** event loop. Accessed from the executor thread it raises *"<asyncio.locks.Event …> is bound to a different event loop"*, which `_safe_load_corrections` catches and logs as a WARNING, then returns `[]`. Net effect: **every v2 turn runs with zero corrections applied.**

**Why it's serious.** The plan designates `ManualCorrection` the operator's no-deploy safety net for wrong answers (suppress / replace / pin / blacklist). With this bug, a librarian can file corrections all day and **none take effect on prod**. It's silent — only a WARNING in the log, chat keeps working — so you'd never notice without reading logs. Confirmed 2026-06-08 (fires on the socket path; the `/smoketest/v2` path runs `run_turn` in the main loop and does NOT reproduce it, which is exactly why smoke tests miss it).

**Not introduced by the citation fix** — pre-existing in the async-bridge wiring.

**Fix directions (pick one).** (a) Give the corrections store its own persistent `_AsyncBridge` daemon-loop (same pattern `real_backends.py` uses for legacy LibCal/LibGuides tools) so DB access is loop-stable regardless of caller thread. (b) Load corrections in the async handler *before* dispatching to the executor, and pass the already-resolved list into `run_turn` as data (no DB call inside the thread). (b) is simpler and removes a per-turn DB round-trip from the hot path.

**Effort.** ~0.5–1 day. **Touches:** `graph/v2_serving.py`, possibly `database/` corrections store.

### D4. 🟠 `load_url_allowlist` is stubbed to an empty set on v2
**What.** `build_v2_deps` wires `load_url_allowlist=lambda: set()` (`v2_serving.py`). The post-processor's URL-validation rule therefore only ever accepts URLs that appear in `citations[].url`; the `UrlSeen` allowlist table is never consulted. In practice fine today (answers cite their URLs), but it means a legitimate non-cited URL the model surfaces would be flagged as fabricated. Wire it to the real `UrlSeen` query when that table is populated by the ETL.

**Effort.** ~0.5 day, coupled to the ETL `UrlSeen` sync (B2). **Touches:** `graph/v2_serving.py`, `database/urlseen_adapter.py`.

---

## E. Robustness at scale (plan "Beyond robust")

These only bite under months of real traffic — fine to defer past beta, but write them down.

- **E1. 🟠 Prompt-injection / adversarial red-team.** Not yet stress-tested. ~1 week.
- **E2. 🟠 Long-conversation memory pruning.** `conversation_history` grows unbounded; every gold case is single-turn so multi-turn cost/latency is unmeasured. Add a turn/token cap with summarization.
- **E3. 🟢 Concurrent-load test.** Singleton Weaviate/Prisma clients are fine at single-digit RPS, untested above. Load-test before any traffic spike.
- **E4. 🟠 OpenAI-outage fallback.** A `live_data_down` refusal exists for LibCal but there's no fallback if OpenAI itself is down — the bot 500s universally. At minimum, catch and return a templated "assistant temporarily unavailable" (the v2 deps-unavailable path already does this for deps; extend to LLM calls).
- **E5. 🟢 Schema-migration deploy hardening.** The first Prisma migration needed a hand-written hotfix; harden the process before the next one.

---

## F. Content & eval

- **F1. 🟠 Merge the 50 new gold cases.** `ai-core/src/eval/golden_set_v2_new.jsonl` (generated during beta prep, no overlap with the existing 184) is not yet folded into the regression suite. Review + merge to widen coverage.
- **F2. 🟢 Real-LLM eval cadence.** Decide a regular `run_eval.py --with-real-llm --with-judge` cadence (e.g. before each prod deploy) and record the verdict trend, remembering the judge is biased ~15–30% (use for trend, not absolute — see `06-EVAL-AND-QUALITY.md`).

---

## Quick triage if you have exactly one day

1. **B1** (v2 telemetry) — you're flying blind on cost/usage until this lands.
2. **C1 + C2** (preflight + post-deploy smoke) — stops the prod-only-bug bleeding.
3. **D1** (corrections write path) — turns librarians into your QA team.

Everything else is genuine polish.
