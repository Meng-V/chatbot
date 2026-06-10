# Accuracy Audit — hand-verified, 2026-06-09 (evening)

**Question answered:** what is the bot's TRUE answer accuracy (not the
LLM-judge's floor), and what are the highest-value improvements?

**Method.** The 234-case gold-set run (real LLM + real retrieval + 3-shot
LLM-judge, completed overnight 2026-06-09) was re-audited by hand:
- **All 48 "bad" verdicts** (37 wrong + 10 refused_incorrectly + 1
  answered_should_have_refused) read one-by-one against the gold
  expectations and re-classified.
- **20 of 57 "partial" verdicts** (seeded random sample) re-classified the
  same way; the 57 are extrapolated from the sample.
- **Every URL in all 234 answers** (18 distinct) HTTP-checked.
- The judge's `correct`/`refused_correctly` buckets (129) were NOT
  re-audited — treat the headline as having ±3-4pt uncertainty from
  possible judge false-positives there.

---

## 1. Headline numbers

| Metric | LLM-judge said | **Hand-audited truth** |
|---|---|---|
| Fully right (correct answer or correct refusal) | 55% (129/234) | **~73%** (≈172/234) |
| At-least-helpful (incl. genuinely-partial answers) | 79% | **~88%** (≈207/234) |
| Genuinely bad (wrong, misleading, or wrongly refused) | 21% | **~11-12%** (≈27/234) |
| Fabricated or dead URLs in any answer | — | **0 / 18 distinct URLs (100% live)** |
| Hours/librarian/space tool answers (live data) | — | near-100% (failures are coverage, not wrongness) |

**Why the judge under-scores by ~18 points:** of the 48 "bad" verdicts,
**23 (48%) were judge/gold artifacts** — the bot was actually right:
- Gold cases that assume conditions that didn't hold live (LibCal-down
  refusal cases when LibCal was up; the gold text itself admits the fault
  injection doesn't exist).
- Correct cross-campus "no MakerSpace at Hamilton" answers judged wrong
  for *answering well instead of refusing*.
- Two circulation answers that match the gold text **nearly verbatim**
  (`circ_place_hold`, `circ_online_checkout`) still judged `wrong`.
- Long-period-hours answers that followed the operator rule exactly
  (point to the hours page, don't fake LibCal) judged `wrong`.
- Of the sampled partials, 7/20 (35%) were fully complete answers.

**The bot's failure mode is safe:** the genuinely-bad cases are dominated
by *refusing things it should answer* and *pointer-only answers* — not by
making things up. Zero fabricated URLs across the entire run.

---

## 2. The real failures, clustered (25 from "bad" + ~9 extrapolated from partials)

Ranked by count × user impact. Each has a concrete fix.

### C1. Regional-campus content & lookups — 8 cases 🔴 the biggest cluster
Middletown's **TEC Lab MakerSpace is not in the index** (3 cases answered
"no 3D printing at Middletown" — *factually wrong*, gold says it exists);
Hamilton **staff/librarian lookups** refuse (2); Hamilton **room
specifics** weak (2); Hamilton reserves evidence vague (1).
**Fix:** (a) index the TEC Lab guide + Hamilton staff page + Rentschler
rooms pages (a small, targeted ETL ingest — not the full re-crawl);
(b) extend `lookup_librarian` regional fallback to actually carry
Hamilton/Middletown staff rows in Postgres. **Effort: ~1-2 days.**
*This cluster alone is ~⅓ of all real failures.*

### C2. Pointer-only answers — ~6-8 cases (mostly in "partial") 🟠
Bot answers "use page X for the rates / the list / the workflow" without
stating the fact, even when asked a specific question (MakerSpace pricing,
HDMI cable, scan-to-email steps).
**Likely contributor (verify before tuning):** `_format_evidence_block`
truncates crawled chunks at **600 chars** — rate tables / step lists get
cut, so the synthesizer literally can't see the fact. **Fix:** raise to
~1200 + add a synthesizer rule "if the evidence states the specific fact
asked, state it — don't only point." A/B this against refusal +
citation-validity metrics (anti-Goodhart: don't tune blind). **Effort:
half a day + an eval pass.**

### C3. Operator-gold chunks leak meta-instructions — 2 confirmed + style issues 🟠
The bot recites *instructions meant for it* as if they were facts:
"the guide says to confirm access only if it appears in the databases
list; otherwise it should be refused" (`fs_cincinnati_enquirer`),
"training is required if stated on the MakerSpace page"
(`fs_makerspace_training`), plus "per the operator-verified answer" /
"staff's verified guidance document" phrasing. Root cause: the
operator-gold chunks ingested via `wire_gold_to_weaviate.py` contain
conditional/meta text, and the synthesizer quotes it.
**Fix:** (a) rewrite those gold chunks as plain facts; (b) synthesizer
rule: never reference "operator/verified guidance" meta-language.
**Effort: half a day.**

### C4. Capability/refusal template mis-routing — 3-4 cases 🟠
- "Submit ILL for me" → refused with the **holds** template + generic URL
  (should be: ILL form URL).
- "Put my book on course reserves" → refused with **"Catalog search is
  currently unavailable"** (untrue + irrelevant).
- Catalog handoff (`ref_catalog_search_handoff`) → same misleading
  "currently unavailable" copy instead of a clean Primo handoff.
- Events refusal omits the News page pointer the template should carry.
**Fix:** audit `intent_capabilities` / refusal template keys; the
"currently unavailable" copy should not exist for by-design handoffs.
**Effort: half a day.** Low risk, pure copy/routing.

### C5. Clarify over-trigger on answerable questions — 4 cases 🟠
"Late fees?", "lost book replacement", "recall a book", "view microfilm"
→ clarification chips instead of an answer (kNN margin lands in the
clarify band).
**Fix:** ~8-12 labeled exemplars for circulation-policy phrasings +
microfilm; same playbook as the parking-OOS fix that already worked.
**Effort: 1-2 hours + eval pass.**

### C6. MakerSpace live hours — 2 cases 🟡
"MakerSpace hours / open right now?" refuses even though LibCal id 11904
is documented in the agent prompt. The agent isn't mapping
makerspace→get_hours.
**Fix:** ensure `get_hours` accepts `makerspace` and the agent prompt
maps it; add a gold-pinned exemplar. **Effort: 1-2 hours.**

### C7. Misc singletons 🟡
King lockers info not retrieved (page likely unindexed); ILL *return*
policy answered with the *request* page; pet policy leaned on an event
post; "finals week" premise echoed back as if true; Saturday hours
refused although weekly data was in evidence.
**Fix:** mostly covered by C1/C2-style targeted ingests + one synthesizer
nudge ("don't adopt the user's premise (finals/summer) unless evidence
states it"). **Effort: opportunistic.**

---

## 3. What is verifiably strong

- **Citation integrity: 100%.** 18/18 distinct URLs across all 234
  answers live (HTTP 200); every citation evidence-backed (A3 guard).
  The "makes up links" era is over — structurally, not by luck.
- **Live-data answers** (hours all campuses, subject librarians, spaces):
  the failures above are *coverage* gaps, not wrong data. No instance of
  wrong hours or a wrong contact in the audited set.
- **Scope resolution 98%**, answers carrying citations 91%, prompt-cache
  hit 78% (cost target met).
- **Out-of-scope discipline:** parking/dining/sports/transcripts etc. all
  refused politely to Ask Us.

## 4. Caveats

- The `correct` bucket (99) was not re-audited; judge false-positives
  there would lower the ~73%. Symmetrically, judge noise in `partial` was
  measured (35% of partials are actually fine), so the two effects partly
  offset. Treat **73% ±4** as the honest band.
- The overnight run survived 3 tunnel drops via watchdog resume; a small
  number of refusals near those windows may be infra-flavored
  (`hr2_weekend_king` is a suspect).
- The 62-case colleague set (the set that blocked v1) is **queued to run
  automatically** the moment the Weaviate tunnel returns
  (`/tmp/colleague_watcher.sh`, results → `/tmp/colleague_eval.jsonl`);
  numbers to be appended here.

## 5. Recommended order of work

| # | Item | Cluster | Effort | Expected gain |
|---|---|---|---|---|
| 1 | Targeted regional ingest (TEC Lab, Hamilton staff/rooms) + regional librarian rows | C1 | 1-2 d | ~+3-4 pts true accuracy, kills the only *factually wrong* answers |
| 2 | Refusal/capability template copy + routing fixes | C4 | 0.5 d | removes the most embarrassing copy ("currently unavailable") |
| 3 | Clarify-band exemplars (circulation/microfilm) | C5 | 2 h | ~+1.5 pts |
| 4 | Evidence-truncation 600→1200 + "state the fact" rule, A/B'd | C2 | 0.5 d | converts pointer-only partials into real answers |
| 5 | Clean operator-gold chunks + ban meta-language | C3 | 0.5 d | removes the weirdest-reading answers |
| 6 | MakerSpace get_hours mapping | C6 | 2 h | 2 cases + a visible flagship service |

Items 2, 3, 5, 6 are low-risk and together ≈ 1.5 days; item 1 is the
single biggest accuracy lever; item 4 needs an eval A/B.

---
*Hand-audit performed autonomously 2026-06-09 evening; source data
`/tmp/eval_full.jsonl` (234 rows), audit worksheets `/tmp/audit_bad.txt`,
`/tmp/audit_partial.txt`.*
