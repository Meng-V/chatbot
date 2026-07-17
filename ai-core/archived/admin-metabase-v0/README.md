# Admin v0 — Metabase queries + shared spreadsheet

The custom React admin surface (Op 1 in the rebuild plan) is post-launch
work. This directory is the **interim** review surface librarians use
until then: nine saved Metabase queries + two CSV templates.

It's not pretty. It works. It ships in a day.

## What's here

```
admin/
├── README.md                         (this file)
├── queries/                          paste these into Metabase as "saved questions"
│   ├── 01_my_subject_queue.sql       a librarian's recent dialogs in their subject area
│   ├── 02_my_campus_queue.sql        all recent dialogs scoped to a campus (regional default)
│   ├── 03_low_confidence.sql         answers the bot self-flagged as uncertain
│   ├── 04_thumbs_down.sql            user marked the answer down
│   ├── 05_refusals_by_trigger.sql    why the bot refused (aggregate)
│   ├── 06_cross_campus_leaks.sql     hard correctness gate -- expected to be empty
│   ├── 07_per_source_correctness.sql which URLs are getting bad verdicts
│   ├── 08_cost_and_cache.sql         daily cost + cache-hit per call site
│   └── 09_active_corrections.sql     active ManualCorrection rows + fire counts
└── templates/
    ├── review_log_template.csv       librarians fill in verdicts here (until v1 UI)
    └── correction_log_template.csv   librarians log requested corrections here
```

## One-time setup (web dev, ~30 min)

1. **Stand up Metabase** (free tier covers small teams):
   ```bash
   docker run -d -p 3000:3000 --name metabase metabase/metabase
   ```
   Or use a hosted instance Miami IT already runs.
2. **Connect Metabase to the chatbot Postgres**:
   - Admin Settings → Databases → Add Database → PostgreSQL
   - Host: `<chatbot DB host>`
   - DB name: `smartchatbot_db`
   - **Use a read-only DB user** (don't reuse the app's RW credentials).
     Create one with:
     ```sql
     CREATE USER metabase_ro WITH PASSWORD '...';
     GRANT CONNECT ON DATABASE smartchatbot_db TO metabase_ro;
     GRANT USAGE ON SCHEMA public TO metabase_ro;
     GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_ro;
     ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_ro;
     ```
3. **Import each `.sql` file as a saved question**:
   - Metabase → New → SQL query → paste contents → save with the
     filename as the title.
   - For queries with `{{parameter}}` placeholders, Metabase prompts to
     declare them as variables. The comment header on each query lists
     what type to pick (text / dropdown / number / boolean).
4. **Build a dashboard per role**:
   - **Subject librarian**: 01 + 03 + 04 (their queue + uncertainty + thumbs-down).
   - **Regional librarian**: 02 (filtered to their campus) + 04 + 05.
   - **Program lead / web dev**: 05 + 06 + 07 + 08 + 09 (system health, pollution, cost, corrections).
5. **Create the shared spreadsheet** (Google Sheets, OneDrive, whatever
   the team already uses):
   - One tab from `review_log_template.csv` — librarians paste verdicts.
   - One tab from `correction_log_template.csv` — librarians request
     ManualCorrection inserts that the web dev applies (until the v1 UI
     wires this to a real form).
   - Link to it from the Metabase dashboard description.

## Daily / weekly use

**Subject librarian (10 min, weekly):**
1. Open the "My subject queue" dashboard. Skim the answers in your area.
2. For each answer, click the citation URLs in `cited_urls` and
   eyeball: does the answer match what's actually on that page?
3. For wrong answers: paste the `message_id` into the review-log sheet,
   pick a verdict, write a one-line note. If a fix is needed, also add
   a row to the correction-log sheet.
4. Forget it for the week.

**Regional librarian (Hamilton, Middletown):**
1. Open the "My campus queue" dashboard with campus filter set.
2. Same flow. Pay extra attention to anything cited from `lib.miamioh.edu`
   (Oxford content) — that's a cross-campus leak per query 06.

**Program lead (15 min, weekly):**
1. "Refusals by trigger" — is `low_confidence` or `no_results` climbing?
   That's a corpus gap. File an ETL backlog item.
2. "Cross-campus leaks" — must be **zero**. Anything here is a
   post-processor escape; open a GitHub issue immediately.
3. "Per-source correctness" — top of the list is your pollution
   shortlist. Coordinate with the librarian who owns that subject area
   to either correct or escalate to the web team.
4. "Cost + cache" — every call site individually >= 0.5 cache-hit,
   average >= 0.6. Sustained drop on one site = prefix drift; debug via
   the byte-stability log in `prompts/builder.py`.

## Migration to v1 React admin (post-launch)

When the React admin ships:
- The `LibrarianReview` table replaces the review-log spreadsheet. Same
  column shape — migrate the spreadsheet rows in via:
  ```sql
  INSERT INTO "LibrarianReview" ("messageId", "librarianId", verdict, note, "reviewedAt")
  SELECT message_id,
         (SELECT id FROM "Librarian" WHERE lower(email) = lower(librarian_email)),
         verdict, note, reviewed_at::timestamp
  FROM <staging table loaded from the CSV export>;
  ```
- The `ManualCorrection` table replaces the correction-log spreadsheet.
- The Metabase dashboards stay — they're useful complements to the
  custom UI for ad-hoc investigation, especially the cost/cache and
  cross-campus-leak gates.

## Why this and not something fancier

The plan explicitly calls for v0 to be Metabase + spreadsheet, not a
custom UI. Reasons:
- A librarian has to be in the loop from week 7. We don't have time to
  build (and then UAT) a real admin app before that.
- The data model needs to settle first. Building a UI against a
  schema that's still moving creates throwaway code.
- If Metabase can't answer a question, that's a signal the schema is
  missing a field. Fix the schema before fixing the UI.
- All review and correction *content* lives in Postgres tables already
  — the admin UI is just chrome. The chrome can be deferred.
