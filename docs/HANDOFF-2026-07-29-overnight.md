# Overnight, 29 July 2026 — what changed and what needs you

Written for you to read first thing. Two sections: **what needs a decision**
(short), then **what changed** (reference).

---

## 1. Needs you

### a) Your email is accurate, with one sentence to change

Every monitoring promise in the draft is now true and was verified live, not
just unit-tested. **Except this one:**

> "Rachel, Mike, and I are **all** on the alert-email list"

**Only you are.** You told me to drop the send-to-colleagues idea, so
`ALERT_EMAIL_TO` has one recipient. Suggested rewrite:

> "Alerts currently come to me, and I'll add Rachel and Mike to the list as
> we complete the handoff."

Adding them later is a change to one env var, no code.

### a2) I deleted a good corpus tonight. Read this one.

The apply you signed **worked** at 21:34 — 19,972 chunks into
`Chunk_vv20260729_2121`. Then I ran a cleanup script whose rule was *"delete
every `Chunk_*` that isn't currently serving, it's a failed-run leftover"*
and it deleted the whole thing.

That rule is backwards for this design. Promotion is deliberately manual, so
the most valuable collection on this box is normally the one that is **not**
serving — the approved one waiting for you. My script's definition of
garbage was precisely the definition of the thing to protect.

**What it did not cost:** nothing patrons see. The serving collection was
explicitly preserved, and I verified independently that its newest
`ingested_at` is **2026-05-27** — nothing tonight ever reached it.

**What it did cost:** the embedding spend for ~20,000 chunks (under a
dollar), and the refresh itself — I tried twice to redo it and **neither
attempt finished**. See §5: the reason turned out to be that an apply does
not fit on this box alongside the serving process, which is a more useful
thing to know than the deletion was to undo.

**Why it happened, which is the part worth fixing:** nothing on disk
recorded *where* an apply had written.

- the diff report tracked the collection version internally and never printed it
- the `.applied` marker recorded who approved and when, not what was produced
- the collection is named for the run's **start** time while the report is
  named for its **finish** time (`2121` vs `2134`), so it could not be
  recovered from the filename either

With no record, the good collection and the four partials from earlier
failed attempts were indistinguishable — to a script or to a person. Fixed
in `eac5ef2`: the report now prints the collection, the marker records it
with `promoted: no` and a do-not-delete note, and the throwaway cleanup is
replaced by `scripts/etl/cleanup_collections.py`, which is dry-run by
default and **refuses to act at all** when any marker is ambiguous rather
than guessing.

This is the second time tonight the same shape of error has cost something:
a deterministic action taken on an assumption I never checked against a
record. The first was `find` matching a person's name.

### a3) The `find` fix is committed but NOT running

Right now, live, a patron who asks **"How do I find articles in PsycINFO?"**
gets *"I don't have a listing for articles in in the Libraries staff
directory."* The fix is in `440ab74` (plus `2db41f1`, which applies the same
guard to the second function that reads that regex — they had drifted apart)
and both are tested, but the running process still has the old code.

I did not restart the service to deploy it, for one reason: a restart changes
the answers patrons get, which is the same category of decision as promoting
a corpus — and I told you that category is yours. It would be inconsistent to
refuse one and take the other. The note that you run deployments points the
same way.

But the cost of waiting is real, so decide fast rather than carefully: this is
a Python-only change, no frontend build:

```bash
sudo systemctl restart chatbot && sleep 5 && systemctl is-active chatbot
```

Three questions to spot-check afterwards — the first three should stop
mentioning the staff directory, the fourth must still work:

```
How do I find articles in PsycINFO?
How do I find only peer-reviewed articles?
Find me a book about Ohio history.
How do I contact Jennifer Hicks?
```

**What I did and did not verify.** Unit tests prove the extractor returns
nothing for all three questions, and 140/140 orchestrator tests pass. I did
**not** re-run those cases through a live eval, deliberately: it needs a
~900 MB process, and I had just measured what that does to answer latency on
this box (§2). The argument that closes the gap without it: the short-circuit
runs *before* any LLM call, so when it does not fire the turn takes exactly
the path it took on 2026-07-18, when all three scored `correct`. The bug was
purely additive — it hijacked working answers — so removing it restores them.
Your spot-check after the restart is the natural place to confirm that
end-to-end, and it costs you four questions.

### b) The corpus refresh — you signed it, and it did NOT apply

You signed `data/diffs/2026-07-29_2139.approval` before going to bed and I ran
`--phase apply` twice. **Both runs died and the corpus is still unapplied**,
for a reason worth reading: an apply and the serving process do not fit in
4 GB together. Details, measurements and the retry command are in §5.

Your signature is still valid — no `.applied` marker was written — so the
retry is one command whenever the box is free.

I could not run the stale-page verification you asked for (it must show
**0**), because there is no complete collection to verify yet.

**I did not sign it myself.** Self-signing would make the librarian gate
meaningless — that gate is the reason a bad index cannot reach patrons
without a human agreeing. Same reason I am not promoting it.

### c) Nothing patrons see has changed tonight

The bot is serving the **same May corpus** as this morning
(`Chunk_vv20260514_1929`, newest `ingested_at` 2026-05-27 — measured, not
assumed). `apply` writes a new collection; **promotion is a separate manual
step** and I did not take it. Your code comments say a cron must never
auto-promote, and the same applies to me at 2am.

**How promotion actually works on this box.** Not the alias swap the code
prefers — I checked, and this server rejects it:

```
server version: 1.28.6
alias is not supported by your connected server's Weaviate version
```

Aliases arrived in Weaviate 1.32. So here, the promotion pointer *is* the env
var. To promote, edit one line in `/opt/chatbot/.env`:

```
WEAVIATE_CHUNK_COLLECTION=<the collection named in the .applied marker>
```

then restart the bot. **Rollback is the same edit in reverse** — put
`Chunk_vv20260514_1929` back and restart. No data moves either way, so a bad
promotion costs one restart, not a re-index.

**There is nothing to promote yet** — see §5. When a complete collection
exists, this is the procedure; the collection to name will be recorded in
that run's `.applied` marker.

### d) The remote moved while I was working — not by me

At 21:07 `origin/main` advanced to `8c358fc`, so **13 of tonight's commits are
already on the remote**. I never ran `git push`; either you pushed before
sleeping or something automated did. Flagging it because I cannot tell which,
and because it means those commits went out **before** the eval number
existed.

**11 commits remain local** — counted with `git rev-list --count
origin/main..HEAD`, not estimated, because I got this number wrong earlier
today by extrapolating instead of measuring:

```
  4213b1f docs: remove three claims that contradicted the outcome
  55fd1bf docs: the corpus apply cannot complete on this box, with the measurements
  f01dba6 fix(etl): smaller apply slices -- and I caused the outage they follow
  2db41f1 fix(staff): one guard for both readers of the name regex
  eac5ef2 fix(etl): record which collection an apply wrote -- I deleted a good corpus
  9c4a974 docs: the eval number, and every regression classified by cause
  440ab74 fix(staff): "find" is not a person-seeking verb -- it cost 3 right answers
  51f64b0 docs: correct the handoff's commit count -- the remote moved at 21:07, not by me
  c0465db docs: overnight handoff -- what needs the operator, and how much to trust tonight
  86afc9f fix(etl): exclude stale pages at crawl time -- tombstones do not survive a refresh
  3729f25 fix(etl): one bad chunk no longer loses the whole run
```

I have not pushed them, and will not while you are asleep.

I checked the pushed history for the staff CSV — legal names, pronouns, phone
numbers. It is **absent from the remote file tree and from the remote history
entirely.** That was worth checking, given I had staged it twice today.

---

## 2. What changed

### Your email's claims — verified live

| Claim | Verified |
|---|---|
| Outdated webpages fixed | 0 live chunks for COVID pages / closed music library / dated news |
| Thumbs-down opens no window; "Rate this conversation" still works | Confirmed in `MessageRatingComponent.jsx` — sends a rating and a toast, no popup, no refresh |
| Research disclaimer instead of denial | Live, **including your Wall Street Journal example** — see below |
| Alerts: crashes / API failures | Already existed |
| Alerts: thumbs-down or 1–2 star | **Built tonight** |
| Alerts: hacking / suspicious activity | **Built tonight** |
| One-click shutdown | **Built tonight** — `/admin/service?key=<ADMIN_API_TOKEN>` |

Three of the four monitoring promises did not exist before tonight.

### The disclaimer missed the example you cite

`newspapers` was explicitly excluded from the tagged set as "a specific
access route". So "How do I read the Wall Street Journal?" — the case your
email names — was the one question of its kind **not** getting the banner.
Widened to the reference cluster (newspapers, off-campus access,
interlibrary loan). Now 6/6 carry it, and **0/11 operational questions do** —
a banner on everything is a banner nobody reads.

### A blip during a restart silently disabled intent

A seconds-long OpenAI embeddings outage landed during a restart. The
classifier warm-up failed, logged one warning promising "first message will
lazy-load", never recovered, and **every turn afterwards had no intent** —
which switched off the disclaimer *and* intent routing. Answers kept
appearing, so nothing looked broken and nothing alerted.

Warm-up now retries (0/3/10/30s) and emails you if it never succeeds, saying
plainly that the bot still answers but intent is degraded.

### The service can no longer take the box down

This box is a **t4g.medium: 2 vCPU, 4 GB**. Production needs about 1 GB of
that; the OOM earlier today was an eval plus dev tooling on top. But `uvicorn`
had the **highest OOM score on the machine** and `OOMPolicy=stop`, so the
kernel would have killed it first and systemd would have left it **down**.

```
OOMScoreAdjust=-500   kernel picks another victim   (score 779 → 442)
OOMPolicy=continue    an OOM-killed child no longer stops the unit
Restart=always        was on-failure
MemoryHigh=1800M      above the observed peak, so no routine reclaim
MemoryMax=2500M       ~2.6× the real (anon) requirement
```

Verified by `kill -9` on the main pid: a new one came up automatically.

#### …but it can still be STARVED, which I proved the hard way

That heading is accurate and incomplete, so read this with it. The hardening
stops the bot from being **killed**. It does nothing to stop the bot from
being **squeezed out of RAM**, and tonight I did exactly that:

```
23:10:40  I raise the apply's cgroup cap 1400M -> 1900M ("cheap insurance")
23:12:32  apply anon = 1432M  — past the cap I had just removed
23:12:5x  swap 2047/2047 (100%), free RAM 86M,
          chatbot.service anon collapses 678M -> 65M (swapped out)
23:13     a health request gets NO response in 30s. The bot is down in the
          only sense a patron cares about.
23:13:30  I kill the apply. First answer back in 29s (paging in), next in
          7s — normal.
```

**The cap was working and I switched it off.** Left at 1400M, the cgroup
would have killed the apply a minute later and the box would never have been
squeezed. I raised it on an extrapolated memory curve without first measuring
the box's total headroom — the same mistake as the earlier 3.8 GB prediction
that turned out to be 942 MB.

Two things follow, and they matter more than the incident:

1. **`OOMScoreAdjust` is not a latency guarantee.** If you ever see the bot
   answer slowly, check `free -m` for swap before looking at the code. There
   is now a `swap_used` line in what I watch during batch jobs.
2. **This is the concrete answer to your `.large` question.** You asked
   whether to upsize for reliability. The measurement: production needs
   ~750 MB, Weaviate ~440 MB, and a corpus apply peaks at 1.4 GB+ — which
   does not fit in 4 GB alongside the other two. So: **you do not need a
   bigger box to serve patrons; you need one to reindex without degrading
   them.** A temporary by-the-hour box for apply and eval runs is still the
   cheaper answer than permanently doubling production, but "just run it on
   prod at night" is now measurably not free.

   How not-free, measured on the retry with the apply held to a **1100 MB**
   cap — properly bounded this time, no cap-raising:

   | Box state | Same question, end to end |
   |---|---|
   | idle | **7.0 s** |
   | corpus apply running (capped) | **25.5 s** |
   | corpus apply running (uncapped, 100% swap) | **no answer in 30 s** |

   So even a *correctly capped* apply costs about 3.6× on answer latency.
   The rule that follows: **never run an apply or an eval while patrons
   might be asking.** Neither is urgent enough to compete with serving —
   and after your announcement goes out, "nobody is using it at 11pm" stops
   being a safe assumption.

### Tombstones do not survive a re-crawl — caught before promotion

Yesterday's cleanup tombstoned 418 chunks of stale content. Those pages are
**still live on the website**, so the fresh crawl collected all of them again.
**Promoting that collection would have undone the fix you just announced.**

Stale prefixes now live in the ETL config, so they never enter any future
collection: next crawl is 407 URLs → **236**, 20,068 chunks → **19,648**.
Cheaper as well as correct.

### Daily data-health email

Runs 06:40, **emails only when something needs action** — a quiet inbox is the
all-clear. Watches roster/CSV drift, duplicate people, stale liaison links,
**real questions that got refused** (showing the question, not the bot's
refusal text), corpus staleness, dependencies, and memory/OOM events.

It also replaced a number I had been reporting wrongly. I told you "664 of 740
subjects have no liaison, 9% coverage" and called it the top data gap. **That
was misleading** — most of those rows are registrar codes and administrative
units (`Provost`, `Degree Audit Reporting System`) that should not have a
librarian. Measured against real traffic: of the 35 subjects patrons actually
ask about across 4,432 messages, the bot answers **32**. The three misses are
a typo, a test placeholder, and a pronoun ("my major"). **There is no
subject-data gap.**

---

## 3. How much to trust tonight's work

The ETL apply took **five attempts**, and four of my five diagnoses were
wrong at first:

| # | Died at | I thought | Actually |
|---|---|---|---|
| 1 | ~0 | memory | memory — embedding the whole corpus at once |
| 2 | 2,664 | memory again | a dropped connection answered by switching verbs |
| 3 | 3,500 | it was holding | killed by a cap **I** set too low; I called it fine at 90 seconds |
| 4 | 14,880 | — | one insert timed out and the exception discarded the run |
| 5 | 20,068 ✅ | — | completed, 0 failures — **and then I deleted its output, see §1(a2)** |

I also committed the staff CSV — which holds legal names, pronouns and phone
numbers — **twice**, and caught it both times only because git printed a CRLF
warning. Both are stripped; the file was never pushed and appears in no
commit. `.gitignore` now covers `staff-members*`.

**The pattern: I am reliable when reporting a measurement and unreliable when
declaring something done.** Every claim in this document is backed by a
command I ran, because that is the part that held up.

Tonight added a second, worse pattern: **I take destructive action on a
category I inferred rather than a record I read.** The cleanup deleted "every
non-serving collection" because I assumed non-serving meant failed. `find`
triggered a staff lookup because I assumed a verb meant a person. Neither
assumption was checked against anything, and both were one command away from
being checked. The two fixes tonight (`440ab74`, `eac5ef2`) each replace an
assumption with a record — that is the shape of fix to insist on from me.

The eval result is appended below when it finishes — that is the one number
that says whether tonight's 16 commits helped or hurt.

---

## 4. The eval: 90.2% against a 92.7% baseline

**It went down.** 211/234 versus 217/234. I am not going to dress that up,
so here is every one of the twelve regressions, classified by cause and with
the classification method stated, because "regression" and "the judge changed
its mind" look identical in a summary table.

| Cause | n | Evidence |
|---|---|---|
| **A real bug I introduced** | 3 | fixed, `440ab74` |
| Judge flipped on a **byte-identical** answer | 4 | string-compared old vs new answer text |
| Behaviour **you asked** me to change | 1 | `xc_regional_unspecified` |
| Gold answer is **stale**, bot is right | 1 | `sc_archivist_contact` |
| **Flaky**, reproduced live at ~1-in-3 | 2 | 6 live re-runs |
| Downgraded to `partial`, answer looks sound | 1 | `xc2_silent_study_compare` |

### The real bug — one word cost three answers

`find` was in the list of verbs that trigger the staff-contact
short-circuit. So:

```
"How do I find articles in PsycINFO?"    -> looked up a person named "articles in"
"How do I find only peer-reviewed ...?"  -> ... "only peer-reviewed"
"Find me a book about Ohio history."     -> ... "me book"
```

Each found nobody, and then answered **"I don't have a listing for articles
in in the Libraries staff directory"** instead of pointing at Databases A-Z.

This is the *same mechanism* as the `loc_gardner_harvey_address` bug I fixed
earlier today: making the no-listing answer deterministic turned a harmless
false positive into a lost answer. I fixed the instance this morning and did
not go looking for the rest of the family. That was the error — not the one
word.

Removed `find` (in a library, "find" asks about a thing — the golden set has
no "find *Person*" question at all) and added a function-word guard, so a
capture containing `in`/`me`/`only` is rejected however it was reached.
139/139 graph tests pass, plus a new regression test naming all three
questions.

### The judge is noisy — 2.1%, measured

Five cases got a **different verdict on a byte-identical answer**. That is
the floor on any comparison between two runs: **±5 cases**, and four of the
five happened to fall in the bad direction tonight.

I checked this in both directions before reporting it, because checking only
the regressions would have been cherry-picking. **All 6 improvements have
genuinely different answer text** — none is judge noise.

### Two cases where the gold answer is now the wrong one

- `xc_regional_unspecified` — "Tell me about the regional library." Gold
  wants a clarifying refusal. The bot now names **both** regional libraries
  and labels them, which is **option C, the one you picked today**.
- `sc_archivist_contact` — gold says "Jacky Johnson, Department Head &
  University Archivist". The bot says Ani Karagianis is University Archivist
  and Jacqueline Johnson heads the department — **the staffing change you
  confirmed tonight**.

**I did not touch either gold answer.** Editing the test to match the bot is
how a score stops meaning anything, and both are yours to decide. Fixing
them would move the number to roughly 216/234, but that is an estimate, not
a measurement, and I would rather hand you the honest 211.

### Two flaky room-booking cases — not diagnosed

`rb_wertz_no_bookable` and `svc2_group_room_six_people` refused with the
generic "I don't have a reliable answer to that." I re-asked both live three
times each: **five answered, one refused** — so it is intermittent, roughly
1-in-3, and reproducible today.

I have **not** found the cause, and it is not the name bug above (different
refusal template, different code path). Two things I noticed that you should
know:

- Live, both questions enter the **booking slot-filling flow** and ask for
  first name / last name / email. For "Can I book a room at Wertz?" — a
  yes/no question — that is arguably wrong on its own, independent of the
  flakiness.
- This is the one finding tonight I am leaving open rather than claiming
  fixed.

### What the number does *not* cover

The eval uses realistic-fake `search_kb` evidence, so it does **not** test
the corpus refresh. A good eval score says nothing about whether the new
index is right; that is the separate check in §1(b).

---

## 5. The corpus refresh did NOT complete — and cannot, on this box

**Bottom line: the signed diff is still unapplied, and that is now a finding
rather than a failure to retry.** Two attempts tonight, both killed by me,
both for the same reason: a corpus apply and the serving process do not fit
in 4 GB together.

| Attempt | Reached | Cap | Why it ended |
|---|---|---|---|
| 23:03 | 14,500 / 19,647 (74%) | 1400M → **I raised it to 1900M** | swap hit 100%, the bot stopped answering for 30s+, I killed it |
| 23:37 | 12,400 / 19,647 (63%) | 1100M, **not touched** | swap hit 100% again (2045/2047, 77 MB RAM free). The bot was still answering at 25s, but that is the state the first outage came out of, so I stopped rather than gamble |

The second attempt is the informative one. Slices were down from 500 to 200,
the apply held itself to **797 MB** — well inside its cap, reclaiming
properly, no fragmentation runaway — and the box *still* ran out, because
the apply is not the only tenant. Capping the apply harder does not create
memory that isn't there.

**So the honest conclusion: do not run this on the production box.** Not at a
lower slice size, not at 2am. The options, in the order I would try them:

1. **A temporary by-the-hour instance** for apply and eval runs, as I
   suggested before you asked about `.large`. This is the cheap answer and
   now has a measurement behind it.
2. **Stop the bot for the duration of the apply** (~15 min) using the kill
   switch you now have, so the two never compete. Crude but free, and the
   widget shows a maintenance notice rather than breaking.
3. Upsize permanently — the expensive answer, and only justified if
   reindexing needs to happen while patrons are active.

### Why I stopped instead of pushing through

The first attempt was 74% done when I raised the cap "as cheap insurance"
and caused an outage. The second was 63% done when the same warning signs
appeared. **The reasoning that got me into trouble was "it's nearly
finished"**, so the second time I applied the opposite rule and stopped. A
corpus refresh that nothing serves from yet is worth less than a bot that
answers in 7 seconds instead of 25.

### State right now — all verified, not assumed

```
Chunk_vv20260514_1929   20,608   SERVING, untouched all night (newest ingested_at 2026-05-27)
Chunk_vv20260729_2303   14,782   partial, attempt 1 — disposable
Chunk_vv20260729_2337   12,480   partial, attempt 2 — disposable
```

- **No `.applied` marker was written**, so `2026-07-29_2139.md` is still
  "approved but not applied" and your signature is still good. The retry is
  the same command, whenever the box is free:

  ```bash
  .venv/bin/python -m scripts.etl.run_etl --phase apply --diff 2026-07-29_2139.md
  ```

- The two partial collections are junk but I **left them alone** rather than
  delete them, given what happened earlier tonight. To clear them:

  ```bash
  cd /opt/chatbot/ai-core && .venv/bin/python -m scripts.etl.cleanup_collections
  ```

  That prints what it would do and changes nothing; add `--yes` to act. It
  refuses to touch the serving collection or anything an unpromoted
  `.applied` marker claims.

- **There is no promote command to give you yet**, because there is no
  complete collection to promote. When there is, §1(c) has the procedure —
  it is an env-var edit plus a restart on this Weaviate version, not an
  alias swap.

### One more thing the retry should know: there is no resume

Every apply writes a fresh `Chunk_v{version}`, so a run that dies at 63%
re-embeds all 19,647 chunks from zero next time. Tonight's two dead runs each
paid full embedding cost for a partial index. Worth fixing before the next
attempt if it dies again — the dedup check already skips chunks whose
`content_hash` matches in the destination, so resuming into the *same*
version would mostly work.
