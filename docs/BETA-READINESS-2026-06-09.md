# Smart Chatbot v2 — Beta-Readiness Report

**Date:** 2026-06-09 (overnight autonomous audit)
**Branch:** `main` (clean, pushed)
**Question this answers:** *Where is this version, and is it ready to launch beta?*

> TL;DR — **Functionally, yes, this is ready for a small/supervised beta.** This
> morning the bot could not answer half the questions it gets (prose retrieval
> was silently dead) and occasionally served fabricated/404 URLs. Both are now
> fixed and verified. The remaining blockers are **deployment steps**, not bot
> behaviour. The honest gaps are a few retrieval *recall* misses (the bot
> refuses safely rather than making things up) and operational blind spots
> (telemetry) that should be closed in the first week, not before launch.

---

## 1. The headline result (zero fabrication)

A 55-question audit spanning every category (hours, librarians, spaces,
printing, ILL, Adobe, databases, catalog, borrowing, renewals, fines, special
collections, scanning, reserves, wifi, cross-campus, out-of-scope, capability
limits):

| Metric | Result |
|---|---|
| Appropriate behaviour (correct answer or correct refusal) | **~52 / 55** |
| **Distinct URLs the bot emitted** | **27** |
| **Of those, dead/404 URLs** | **0** |
| **Of those, fabricated (not from real evidence)** | **0** |
| Orphan citation markers (`[n]` with no source) | **0** |
| Hard errors / crashes | **0** |

**The single most important line:** across 55 diverse questions the bot emitted
27 different URLs and **every one returns HTTP 200 and is backed by retrieved
evidence.** The "it makes up links" failure that blocked confidence is gone —
enforced in code (A3, below), not by prompt politeness.

Full real-LLM + LLM-judge eval over the 234-case gold set: **55% fully-right /
79% at-least-helpful by the (harsh) judge — and ~half the "wrong" verdicts are
judge artifacts where the bot was actually correct. See §6.**

Unit test suite: **541 passed, 1 known order-dependent test-isolation quirk**
(documented in §5; not a production bug).

---

## 2. What was broken this morning, and is now fixed

This session found and fixed a chain of issues, several of them serious:

| # | Issue | Severity | Fix (commit) |
|---|---|---|---|
| 1 | Every user message returned a 400 from OpenAI (legacy conversation-history shape) | 🔴 outage | `e24fa81` |
| 2 | **`search_kb` (prose retrieval) was never wired in production v2** — the bot could not answer printing, special collections, room-booking, Adobe, policies, any prose question; it refused or (pre-#4) fabricated | 🔴🔴 the deepest one | `b4ab1f9` |
| 3 | Citations were silently dropped by the frontend socket handler — chips/sources never displayed at all | 🔴 | `f8faf03` |
| 4 | Three **dead (404) URLs** hard-coded in the synthesizer prompt (Adobe, citation guide, tech-checkout); the judge prompt even rewarded the dead Adobe link | 🔴 | `91e23f7` |
| 5 | **A3:** the post-processor accepted any cited URL, so the model could fabricate a citation from its prompt's URL list even with zero evidence | 🔴 the root mechanism of "made-up URLs" | `91e23f7` |
| 6 | Citation UX: redundant Sources box, clipped popover, un-clickable URL, non-sequential `[5][2][10]` numbering, verbose ticket preview, auto-handoff box on uncertain answers | 🟠 | `f8faf03`, `fa51d74`, `436df03`, `4e1ea28` |
| 7 | Eager Weaviate adapter build crashed *all* deps if Weaviate hiccuped | 🟠 resilience | `fa51d74` |
| 8 | 4 order-dependent test failures (prompt-registry pollution) | 🟡 test hygiene | `d7e017f` |

**#2 + #5 together were the core of the "it makes things up" problem:** with
prose retrieval dead, the synthesizer had no evidence, so it pulled URLs from
its prompt — and one was a 404. Wiring `search_kb` gave it real evidence;
A3 made fabrication structurally impossible.

### A3 in one sentence
The post-processor now refuses any answer whose cited URL is **not** the
`source_url` of a chunk the agent actually retrieved. A made-up or
prompt-list URL can no longer ship — it forces a refusal instead.

---

## 3. What works well (verified)

- **Live tools** — hours (all 3 campuses, today/this week/specific buildings),
  subject librarians (Oxford), spaces/MakerSpace, room-availability — answer
  correctly via LibCal + Postgres, not prose guessing.
- **Prose retrieval** — printing, special collections, borrowing policy, Adobe,
  software, scanning, course reserves, wifi — now answer with real, live,
  evidence-backed pages (this is what #2 unlocked).
- **Authoritative pointers** — databases A-Z, ILL form, catalog (Primo),
  account/renewals, citation guide — return the correct canonical URL.
- **Safety guards all firing:** out-of-scope (parking, dining, sports, tuition,
  transcripts, registration, dorms) → polite refusal to Ask Us; cross-campus
  ("MakerSpace at Middletown") → correct refusal; capability limits ("renew/pay
  for me") → correct "I can't do that, here's where you can"; staff-privacy
  roster guard; campus-mismatch citation guard.
- **Citation UX** — inline `[1] [2]` chips (sequential), click → portal popover
  (never clipped) with a live, clickable source link.

---

## 4. The honest gaps (what still misses)

### 4a. Retrieval recall — a few topics/phrasings refuse when they shouldn't
The bot occasionally **refuses a legitimate question** because the relevant
chunk wasn't surfaced. Confirmed misses in the 55-question audit:

- *"who is the librarian at the Hamilton campus"* → refused (regional staff
  not retrieved; the Oxford liaison path works, regional doesn't reliably).
- *"can I reserve a group study room at King"* → refused, while *"how do I book
  a study room"* answered — same topic, phrasing-sensitive recall.
- *"I lost a book what do I do"* → answered about *account access* instead of
  lost-book procedure — misread the intent.

**Why this is acceptable for beta, not great:** these fail **safely** — the bot
refuses (or points to Ask Us) rather than inventing an answer. They are the
same class as the Adobe/printing miss that §2#2 mostly fixed; a few topics
still have thin recall. Root cause is partly a **broken index metadata**: 98.7%
of the 20,608 indexed chunks are tagged `topic=about` (the ETL classifier is
mis-labelling), so retrieval leans on raw text match and is phrasing-sensitive.

**Fix path (post-launch):** re-run the ETL with corrected `classify.py` topic
+ `featured_service` tagging, then re-tune the retrieval boost. This is a
data-pipeline job that needs the librarian-approval workflow — not a hot fix.

### 4b. Operational blind spots (close in week 1, not before launch)
- **v2 telemetry not persisted** — `ModelTokenUsage` is empty for v2 traffic,
  so cost/usage dashboards read `$0`. You are flying without a cost gauge.
- **ManualCorrection is dead on the v2 socket path** (event-loop binding bug);
  also its write-UI is a 501 stub. So the librarian "fix a wrong answer"
  loop is non-functional today. Low *practical* impact right now (no
  corrections exist to apply), but it's the safety net the plan relies on.

### 4c. Known limitations (document + monitor)
- A cited chunk's `source_url` is evidence-backed but not re-checked live —
  the audit found 0 dead links, but there's no standing guard on the *index's*
  URLs (only on the prompt's, via `scripts/validate_prompt_urls.py`).
- Adversarial / prompt-injection, long-conversation memory, and concurrent
  load are untested — months-of-production concerns, not launch blockers.

All of the above are tracked in `docs/programmer-guide/09-BACKLOG.md`.

---

## 5. Test suite status

`pytest src/` → **541 passed, 1 failed.** The 1 failure
(`test_search_adapter::test_hybrid_search_maps_documented_shape`) is an
order-dependent test-isolation artifact: it passes in isolation and in its own
module, and fails only in a specific multi-module combination due to shared
test state. **It is not a production bug** (the adapter mapping works — the
55-question audit exercised it live). The prompt-registry pollution that caused
the other 3 original failures was fixed this session (`d7e017f`, global
conftest baseline). Pinning the last one is tracked as test debt.

---

## 6. Gold-set eval (real LLM + LLM-judge, **full 234/234**)

The full run completed via a self-healing watchdog (it survived 3 separate
tunnel-drop stalls by killing + resuming with `--skip-ids-in` — vs. the first
attempt that hung 10 hours at case 68). **All 234 cases scored.**

**Judge verdicts (234):**

| Verdict | Count | % |
|---|---|---|
| correct | 99 | 42% |
| partial (answered, useful, incomplete) | 57 | 24% |
| refused_correctly | 30 | 13% |
| wrong | 37 | 16% |
| refused_incorrectly | 10 | 4% |
| answered_should_have_refused | 1 | 0.4% |

- **Fully right** (correct + refused_correctly): **129/234 = 55%**
- **At-least-helpful** (+ partial): **186/234 = 79%**
- **Reliable structural metrics:** scope resolution **98%** (229/234) ·
  answers carrying a citation **91%** (213/234) · intent classification
  **70%** (164/234) · bot refused 44/234 (19%).

### Crucial: 55% is a pessimistic *floor*, not the real quality
I hand-checked the `wrong` and low-scoring buckets. **Roughly half of the 48
"bad" verdicts are judge/gold artifacts where the bot was actually right:**

- **Gold cases that assume a condition that didn't hold live.**
  `hr_libcal_down_refusal` expects a refusal *when LibCal is down* — but LibCal
  was up, so the bot correctly gave live hours, and the judge marked it `wrong`.
- **Correct cross-campus refusals marked wrong.** `xc_makerspace_hamilton/
  middletown` — the bot correctly answered "no MakerSpace there" and listed
  what those libraries *do* have; judged `wrong` on format.
- **Correct service pointers marked wrong.** `svc_print_from_laptop`,
  `svc_food_drink`, `xc_regional_unspecified` — the bot pointed to the right
  canonical page; judged `wrong`.
- **Stale gold answers.** `hours` scored 2/11, yet spot-checking shows the bot
  gives accurate *live* hours ("King open today 7:30am–9:00pm"); the gold's
  expected text is from a different date, so the judge sees a mismatch. The §1
  deterministic audit confirms hours answer correctly.

**The genuinely-wrong cases (~half of the 48, so ~10% real error)** cluster in
exactly the spots §4a already named: **regional/Hamilton content** (Hamilton
librarian, MakerSpace hours) and a few specific topics (lockers). They fail by
**refusing**, never by fabricating.

### Weakest real categories (worth watching in beta)
| Category | good/total | Note |
|---|---|---|
| librarian | 3/7 | regional staff not retrieved (real gap) |
| circulation | 6/19 | mostly judge strictness on policy phrasing; spot-checks read OK |
| cross_campus | 18/35 | ~half are correct refusals judged `wrong` |
| hours | 2/11 | **judge/gold artifact** — bot's live hours are correct |
| out_of_scope | 15/20 | strong (correct refusals) |
| staff / instruction / capability | ~100% | strong |

**Bottom line:** the judge floor is 55% fully-right / 79% helpful, and the real
number is meaningfully higher once judge artifacts are removed — consistent
with the §1 audit. This is in the normal band for a grounded library bot at
beta. The reliable, non-judge signals (98% scope, 91% cited, **0 fabrication**)
are what should drive the go/no-go, and they are green.

---

## 7. Deploy checklist (what must happen to ship beta)

These are the **actual blockers** — all deployment, none are bot behaviour:

1. **Backend:** on prod, `git pull origin main` + restart the service. Picks up
   the 400 fix, `search_kb` wiring, A3, dead-URL fixes — i.e. everything that
   makes the bot work.
2. **Frontend:** `npm run build` + deploy the `dist/`. The citation display +
   all UI fixes are frontend — **a backend restart alone will NOT show
   citations.** This is the most-missed step.
3. **Embedding cache:** symlink `classifier_embeddings.json` (332 MB, gitignored)
   from a persistent path so a clean build doesn't lose it (see the email to
   Rachel / `03-DEPLOYMENT.md`).
4. **nginx + token (Rachel):** forward `/health/*` to `:8081`; set
   `ADMIN_API_TOKEN`.
5. **Run the URL guard pre-deploy:** `python scripts/validate_prompt_urls.py`
   (exits non-zero on any dead URL).

---

## 8. Recommendation & distance to "confident beta"

**Recommendation: ship a small, supervised beta now**, then fix in the order
below. This morning I would have said "no — the bot can't answer half its
questions." That is no longer true.

**Distance to a *confident* beta** (the version where you don't wince when a
librarian uses it):

- **Today → small beta:** the deploy checklist (§7). ~half a day of ops.
- **Week 1:** wire v2 telemetry (cost visibility) + watch the refusal rate on
  real questions to find the recall gaps (§4a) that the 55-question audit can't
  predict. *The single most useful number in week 1 is how often real users get
  a refusal on a legit question* — that, not the eval %, tells you where the
  index is thin.
- **Weeks 2–4:** re-run the ETL with fixed topic/featured tagging (closes most
  of §4a), and build the ManualCorrection write-path so librarians can fix
  wrong answers without a deploy (§4b).

**The one thing not to skip:** the ETL metadata fix. Retrieval works *despite*
98.7% of chunks being mis-tagged; that's a fragile foundation that will keep
producing phrasing-sensitive misses until the index is re-tagged.

---

*Generated by the overnight autonomous audit. Commit history on `main` is the
authoritative changelog; this file is a point-in-time snapshot.*
