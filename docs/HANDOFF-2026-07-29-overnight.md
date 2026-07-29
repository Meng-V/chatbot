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

### b) A corpus refresh is prepared and needs your signature

```
/opt/chatbot/ai-core/data/diffs/2026-07-29_2139.approval
```

Fill in `approved_by_email` and `approved_at`, then tell me (or run
`--phase apply --diff 2026-07-29_2139.md`).

**I did not sign it.** Self-signing would make the librarian gate
meaningless — that gate is the reason a bad index cannot reach patrons
without a human agreeing.

### c) Nothing patrons see has changed tonight

The bot is serving the **same May corpus** as this morning. `apply` writes a
new collection; **promotion is a separate manual step** and I did not take it.
Your code comments say a cron must never auto-promote, and the same applies
to me at 2am.

### d) The remote moved while I was working — not by me

At 21:07 `origin/main` advanced to `8c358fc`, so **13 of tonight's commits are
already on the remote**. I never ran `git push`; either you pushed before
sleeping or something automated did. Flagging it because I cannot tell which,
and because it means those commits went out **before** the eval number
existed.

**3 commits remain local** (both ETL fixes and this document). I have not
pushed them.

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

**You probably do not need a bigger instance.** If you want more resources,
ask Rachel for a temporary by-the-hour box for eval runs, not a permanently
doubled production one.

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
| 5 | 20,068 ✅ | — | completed, 0 failures |

I also committed the staff CSV — which holds legal names, pronouns and phone
numbers — **twice**, and caught it both times only because git printed a CRLF
warning. Both are stripped; the file was never pushed and appears in no
commit. `.gitignore` now covers `staff-members*`.

**The pattern: I am reliable when reporting a measurement and unreliable when
declaring something done.** Every claim in this document is backed by a
command I ran, because that is the part that held up.

The eval result is appended below when it finishes — that is the one number
that says whether tonight's 16 commits helped or hurt.
