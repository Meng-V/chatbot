# Compute capacity for the Libraries Smart Chatbot — options and request text

Written 2026-07-30 after two corpus-reindex attempts failed on the production
instance. Read §1 first: the cheapest option needs no request at all.

## The measured problem

The production instance cannot run the serving process and a corpus reindex at
the same time.

| Tenant | Resident memory |
|---|---|
| Chatbot service (uvicorn) | ~750 MB |
| Weaviate (vector index) | ~440 MB |
| Corpus reindex (ETL) — transient | 800 MB – 1,400 MB |
| Eval suite — transient | ~900 MB |
| Developer tooling / IDE agent | ~700 MB |

Instance: **t4g.medium — 2 vCPU, 3,823 MB usable RAM**, 2 GB swap,
`i-0be3f607aa59630ce`, `us-east-2`.

Measured effect on answer latency for one identical question:

| Box state | End-to-end answer time |
|---|---|
| idle | **7.0 s** |
| reindex running, memory-capped to 1,100 MB | **25.5 s** |
| reindex running, uncapped | **no answer within 30 s** (swap 100% full) |

In the third case the service process was alive and `systemctl is-active`
reported `active` — it had simply been paged out of RAM. To a patron that is
an outage.

## 1. Free option — no request needed (recommended first)

Take the bot out of service for the length of the reindex, so the two never
compete:

1. Open `/admin/service?key=<ADMIN_API_TOKEN>` and click **Take the bot out of
   service**. The widget on the library website keeps working and shows a
   maintenance notice pointing at Ask Us — nothing appears broken.
2. Run the reindex (~20 minutes for ~19,600 chunks).
3. Click **Put the bot back in service**.

Cost: nothing. Downtime: one maintenance window, schedulable at 3am. This is
the right answer for a reindex, which is an occasional operation.

## 2. Cheapest paid option — a temporary instance, per reindex/eval

The recurring need is not the reindex; it is the **eval suite**, which runs
~2 hours, needs ~900 MB, and gets re-run after every substantive change. Every
run degrades answer latency for two hours, and a maintenance window that long
is not acceptable once the service is announced.

Launch an instance only for these runs and terminate it afterwards.

- **Type:** `t4g.medium` is sufficient (the eval is one ~900 MB process); the
  point is that it is not shared with the serving process.
- **Usage:** a few hours per month.
- **Access needed:** the eval reads the vector index over the network, so the
  temporary instance needs to reach the production instance on the Weaviate
  ports (**8080/tcp**, **50051/tcp**) — a security-group rule scoped to that
  instance, not open to the internet.
- **Cost:** at roughly $0.03–0.04/hour for `t4g.medium` in `us-east-2`, a few
  hours a month is **single-digit dollars**. Confirm current on-demand rates
  when requesting.

## 3. Permanent upsize — only if reindexing must happen during service hours

`t4g.medium` → **`t4g.large` (2 vCPU, 8 GB)**. Same vCPU count, double the
memory, which is the only dimension that is short. Instance cost is
**exactly 2×** across `t4g` sizes.

This is the expensive option and the measurements do not require it: serving
patrons needs ~1.2 GB including Weaviate, which fits comfortably in 4 GB.
Ask for it only if option 1's maintenance window and option 2's temporary
instance are both unworkable.

---

## Request text you can send

> **Subject:** Chatbot server — capacity for reindexing and evaluation runs
>
> The Libraries Smart Chatbot runs on `i-0be3f607aa59630ce` (`t4g.medium`,
> 2 vCPU / 4 GB) in `us-east-2`.
>
> Serving patrons fits in that instance comfortably: the application uses
> about 750 MB and the vector database about 440 MB.
>
> What does not fit is our periodic maintenance work. Rebuilding the search
> index needs an additional 0.8–1.4 GB, and our evaluation suite (a two-hour
> automated quality test we run after changes) needs about 900 MB. When either
> runs alongside the live service, the box exhausts memory and swap: we
> measured the chatbot's answer time going from 7 seconds to 25 seconds, and
> in one case it stopped responding for over 30 seconds while the process was
> still technically running.
>
> **What I am asking for:** the ability to launch a second, temporary
> `t4g.medium` instance on demand for these maintenance runs — a few hours a
> month, terminated when finished — plus a security-group rule allowing it to
> reach `i-0be3f607aa59630ce` on TCP 8080 and 50051 (the vector database).
> Not open to the internet; scoped to that instance only.
>
> This is the cheapest option I could find: single-digit dollars a month,
> versus doubling the production instance permanently (`t4g.large`, 2× the
> instance cost) which the measurements do not justify — we do not need a
> bigger server to answer questions, only somewhere to run maintenance that
> is not on top of the live one.
>
> If a temporary instance is not workable, the fallback costs nothing: I take
> the bot out of service for a scheduled maintenance window and run the work
> then. I would rather not do that for the two-hour evaluation runs, which is
> why I am asking.

---

## Before the next reindex: a code prerequisite, not an infrastructure one

The prepared corpus refresh **should not be applied as-is.** It would drop 117
chunks of pages that are still live (all verified HTTP 200 on 2026-07-30):

| Content | Chunks | Cause |
|---|---|---|
| Databases A-Z (`libguides.lib.miamioh.edu/az/databases`) | 7 | not reached by crawl seeds |
| Hamilton hours + Rentschler staff (`www.ham.miamioh.edu/library/...`) | 6 | not reached by crawl seeds |
| LibCal spaces / equipment / reserve pages (`muohio.libcal.com`) | ~20 | host rejected by `_is_library_url` |
| APA + Zotero citation guides, Makerspace LibGuide | 6 | not reached by crawl seeds |
| ILLiad logon (`ill.lib.miamioh.edu`) | 2 | host rejected by `_is_library_url` |

Two fixes, both in `scripts/etl/`:

1. `discover._is_library_url` accepts only hosts starting `lib.` / `www.lib.`
   or paths containing `/library/`. `muohio.libcal.com` and
   `ill.lib.miamioh.edu` are genuine library services on other hostnames and
   need adding to `config.LIBRARY_HOST_PREFIXES`.
2. The sitemap is unusable — the ETL logs `sitemap fetch failed` and falls
   back to curated seeds — so the LibGuides and Hamilton pages above have to
   be added to the seed list explicitly.

Until then, **not** applying is the safer state: skipping the refresh costs
three service pages and some June/July news (~1.4% of the corpus), while
applying it would remove the page the bot cites for every database question.
