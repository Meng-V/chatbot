# Canonical truth: Newspaper access at Miami University Libraries

**Date captured**: 2026-05-15
**Source** (verbatim verified): <https://libguides.lib.miamioh.edu/newspapers>
and its subpages.

**Why this doc exists**: the deleted `_REALISTIC_EVIDENCE["newspapers"]`
stopgap (and likely several gold-set `newspapers` cases) contained
real factual errors:
  - It claimed a direct "Cincinnati Enquirer" subscription. The
    newspapers page does NOT list that as a named direct
    subscription.
  - It said to "activate your NYT/WSJ pass through the library's
    databases page." **Wrong.** NYT and WSJ each have their OWN
    distinct activation URL + distinct rules (NYT must be done
    on-campus; WSJ can be done anywhere). Sending a user to "the
    databases page" would fail them.

This is the source of truth for newspaper questions until the ETL
crawls `libguides.lib.miamioh.edu/newspapers*` (currently not in the
discover set -- see "ETL coverage gap" below).

---

## TL;DR

Miami provides newspaper access via **three distinct mechanisms**.
The bot must not conflate them:

| Mechanism | Examples | How the user gets in |
|---|---|---|
| **Direct sponsored subscriptions** (per-user account) | New York Times, Wall Street Journal | Each has its OWN activation URL + rules (below) |
| **Newspaper databases** (full-text search across many papers) | NewsBank Access World News, Factiva, Newspaper Source, Ethnic NewsWatch, Alternative Press Index | Library database links; proxy login off-campus |
| **Local Oxford papers** (free, public web) | Oxford Free Press, The Miami Student, Oxford Observer | Just public websites; not a library subscription |

---

## New York Times — sponsored group pass

- **Activation URL**: `nytimes.com/grouppass`
  (proxied: `https://proxy.lib.miamioh.edu/login?url=https://ezmyaccount.nytimes.com/grouppass/redir`)
- **Method**: go to the group-pass URL, create a NYTimes.com account
  **using your @miamioh.edu university email address**.
- **Eligibility**: Miami University students, faculty, AND staff.
- **CRITICAL caveat (verbatim)**: "You need to be on campus when
  registering or renewing your account." AND "Faculty, staff, and
  students will need to renew their access every 6 months from an
  on-campus location."
  - The bot MUST surface the on-campus + 6-month-renewal
    requirement. Omitting it is the single highest-value mistake
    to avoid here -- a user who registers off-campus silently
    fails and blames the library.

## Wall Street Journal — sponsored partner account

- **Activation URL**: `https://partner.wsj.com/partner/miamiuniversity`
- **Method** (verbatim steps):
  1. Enter first and last name
  2. Select an Account Type from the dropdown: **Student, Professor,
     or Staff**
  3. Enter your email address and create a password
  4. Click Create to complete registration
  5. Afterward, go directly to `https://www.wsj.com/`
- **Eligibility**: current faculty, staff, and students.
- **Key difference from NYT**: WSJ activation works **from any
  location, on OR off campus**. (NYT requires on-campus; WSJ does
  NOT.) The bot must not copy the NYT on-campus rule onto WSJ.
- **Coverage note**: "Wall Street Journal (4 years ago - present)".

## Newspaper databases (full-text, many sources)

| Database | Covers | Access caveat | Library link |
|---|---|---|---|
| **NewsBank Access World News** | 7,500+ U.S. + global news sources, full-text | — | <https://libguides.lib.miamioh.edu/worldnews> |
| **Factiva** | Washington Post, LA Times, Chicago Tribune; TV/radio transcripts; business/trade journals | **Limited to 4 simultaneous users** | <https://libguides.lib.miamioh.edu/factiva> |
| **Newspaper Source** | USA Today, Times of London; CBS/CNN/FOX/NPR broadcast transcripts; some older content | — | <https://libguides.lib.miamioh.edu/newspaper-source> |
| **Ethnic NewsWatch** | African American, Caribbean, African, Arab/Middle Eastern, Asian/Pacific Islander, European/Eastern European, Hispanic, Native peoples press; full-text | — | <https://libguides.lib.miamioh.edu/ethnic-newswatch> |
| **Alternative Press Index** | 700+ international alternative/radical/left periodicals; 1969+ | **Oxford campus users only** | <https://libguides.lib.miamioh.edu/alternative-press-index> |

So Washington Post / LA Times / Chicago Tribune are reachable
**via Factiva**, not as standalone subscriptions. USA Today /
Times of London via Newspaper Source. The bot should answer "yes,
through [database]" -- not "yes, we subscribe to it directly."

## Historical / back-issue newspapers

The home page doesn't detail dedicated historical archives, but the
LibGuide has dedicated subpages for them. When asked about old /
archived issues, point to the relevant subpage:

- U.S. Newspapers, Historical: `https://libguides.lib.miamioh.edu/newspapers/Archives`
- International Newspapers, Historical: `https://libguides.lib.miamioh.edu/c.php?g=22080&p=11156343`
- Ohio Newspapers: `https://libguides.lib.miamioh.edu/newspapers/ohio`
- African American Newspapers: (subpage tab; URL not captured -- crawl will surface it)
- Newspapers in Print: (subpage tab)

## Local Oxford papers (free public web -- NOT a library subscription)

- Oxford Free Press: <https://www.oxfreepress.com/>
- The Miami Student: <https://miamistudent.net>
- Oxford Observer: <https://oxfordobserver.org>

The bot can mention these for hyper-local Oxford news but must not
imply the library "subscribes" to them -- they're free public sites.

---

## What the bot is allowed to say about newspapers

1. **NYT and WSJ are sponsored per-user accounts**, each with a
   DISTINCT activation flow. Never give one's URL/rules for the
   other.
2. **NYT requires on-campus registration + 6-month on-campus
   renewal.** Always surface this. WSJ does NOT (any location).
3. **Many major papers (WaPo, LA Times, Chicago Tribune, USA Today,
   Times of London) are reached via databases**, not direct
   subscriptions. Answer "via [Factiva / Newspaper Source]" with
   the database link.
4. **Factiva caps 4 simultaneous users**; **Alternative Press Index
   is Oxford-only.** Surface these access limits when relevant.
5. **Local Oxford papers are free public sites**, not subscriptions.

What the bot must **refuse / not invent**:
- A direct "Cincinnati Enquirer" subscription -- not listed on the
  page. (May exist via a database; do not assert a direct sub.)
- Any newspaper not named here as a direct sub or database-covered
  title. If unsure, point to NewsBank Access World News (the
  broadest, 7,500+ sources) and let the user search.
- Step-by-step that mixes NYT and WSJ flows.

---

## Gold-set corrections to file

| Pattern | Bug | Correction |
|---|---|---|
| Any `newspapers` case whose expected answer says "activate via the databases page" | Wrong | NYT -> `nytimes.com/grouppass` (on-campus); WSJ -> `partner.wsj.com/partner/miamiuniversity` (any location) |
| Any case asserting a direct Cincinnati Enquirer subscription | Wrong | Not a named direct sub; reachable (if at all) only via a database |
| NYT cases missing the on-campus + 6-month-renewal caveat | Incomplete | The caveat is load-bearing; expected answer must require it |
| WSJ cases that copy NYT's on-campus rule | Wrong | WSJ activates from ANY location |
| `allowed_urls` listing a generic "/databases/" page for NYT/WSJ | Wrong | Use the specific activation URLs above |

---

## ETL coverage gap (same as makerspaces.md)

`libguides.lib.miamioh.edu/newspapers*` is **not currently in the
ETL discover set** (the 396-URL crawl is `lib.miamioh.edu` +
`ham`/`mid` + regional). So none of these newspaper pages are in
Weaviate yet, and the bot can't ground newspaper answers on real
retrieved chunks until that's fixed.

Action (one follow-up PR, shared with the makerspaces gap): add
`libguides.lib.miamioh.edu` to `scripts/etl/discover.py` -- at
minimum the newspapers + makerspace LibGuides and their subpages.
Until then, `ManualCorrection` (action: `pin`) on these canonical
URLs is the cheapest interim workaround so the URL validator
doesn't reject legitimate LibGuide citations.
