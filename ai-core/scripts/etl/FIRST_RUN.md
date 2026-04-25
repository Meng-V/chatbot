# First ETL Run — Operator + Librarian Runbook

The first time the ETL pipeline writes into the live Weaviate index is
a **gated** action: a librarian must read the diff and sign off before
anything is upserted, tombstoned, or alias-swapped. This file is the
runbook for that handshake.

After the first run goes well, the same flow becomes the weekly cron —
the librarian still gets the diff, but only intervenes if something
looks wrong.

## Two roles

- **Operator** (web dev / on-call engineer) — runs the CLI, watches
  logs, applies after approval.
- **Librarian** (subject lead / program lead) — reads the diff, decides
  whether the ETL's view of the website matches reality, signs the
  approval token.

## The flow

```
       OPERATOR                            LIBRARIAN
       ────────                            ─────────
1.  --phase prepare   ────────►  diff.md + diff.approval (unsigned)
                                            │
                                            │  reads diff
                                            │  decides: approve / refuse
                                            │  edits .approval, fills in
                                            │  email + ack, saves
                                            ▼
2.  --phase apply     ◄────────  signed .approval
       │
       ├─ verify_gate (hash + signature)
       ├─ if PASS → run pipeline (writes Weaviate)
       └─ write .applied marker
```

## Step-by-step (first run)

### Step 1 — Prepare (operator)

```bash
cd ai-core
.venv/bin/python -m scripts.etl.run_etl --phase prepare
```

Expect:
- HTTP fetches across all three campus sitemaps (~600 URLs).
- One diff Markdown written to `ai-core/data/diffs/{date}_{HHMM}.md`.
- One unsigned approval template at `ai-core/data/diffs/{date}_{HHMM}.approval`.
- The CLI prints both paths and the next-step command at the end.

**Do not skip the prepare phase even if you're certain.** The approval
token's `diff_hash` is computed from the prepare-time diff and is
verified at apply time — there's no way to bypass it without editing
the diff (which the hash check catches).

### Step 2 — Hand off to a librarian

Send the librarian:
1. The diff path (or paste its contents into Slack / email).
2. The approval token path.
3. A two-sentence ask:
   > "Please read the diff. If you're OK with it, edit the
   > `.approval` file — fill in your email and confirm the ack
   > line — then save. I'll apply once you've signed."

### Step 3 — Librarian reads + signs

The librarian opens the `.md` file. They look for:
- **Tombstoned URLs** — pages that were in the index and are now gone.
  Are any of them pages we genuinely lost? Or are they all expected
  removals?
- **Fetch failures** — pages we tried to crawl that 5xx'd or timed out.
  Patterns? (Middletown TLS expired again?)
- **Extraction rejects** — pages that returned <200 chars of body text
  or matched the boilerplate-residue heuristic. Any of these surprising?
- **New chunks** — broadly: does the count look right? A 600-URL
  refresh that produces 50 new chunks vs 5,000 new chunks tells two
  very different stories.

If everything looks right, they edit the `.approval` file:

```diff
- approved_by_email:
- approved_at:
+ approved_by_email: jane.librarian@miamioh.edu
+ approved_at: 2026-04-25T13:30:00
  ack: I have read the diff and approve promotion to the live index.
```

Save the file. Done.

If something looks wrong, they don't sign — they reply to the operator
and the apply phase blocks until prepared again.

### Step 4 — Apply (operator)

```bash
cd ai-core
.venv/bin/python -m scripts.etl.run_etl --phase apply
```

The CLI:
1. Finds the most recent diff with `.approval` and no `.applied` marker.
2. Verifies the signature is filled in.
3. Verifies the diff bytes hash to the value in the approval token
   (rejects if anyone edited the diff after the librarian read it).
4. Runs the full pipeline (this time with embed + upsert + tombstone +
   allowlist update — destructive).
5. Writes `{date}_{HHMM}.applied` so a future apply on the same diff
   no-ops.

If the gate refuses, **do not work around it**. Re-prepare and
re-approve. The gate is the only safeguard.

## What "approval" binds to

The approval token contains:
- `diff_file` — must match the .md filename being applied
- `diff_hash` — first 16 hex chars of SHA-256 of the diff file contents

Both are verified at apply time. So:
- ✅ Approve diff A, apply diff A → proceeds.
- ❌ Approve diff A, edit diff A, apply → refused (hash mismatch).
- ❌ Approve diff A, run prepare again, apply → refused (new diff, no
     approval — old approval references the old diff_hash).
- ❌ Approve diff A, apply diff B → refused (filename mismatch).

There's intentionally no override flag. If the gate is wrong, fix the
gate.

## Failure modes & recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `gate refused: approval token not found` | Operator skipped prepare or moved files | Re-run `--phase prepare` |
| `gate refused: ... is unsigned` | Librarian didn't fill in email/ack | Ping librarian; ack in template |
| `gate refused: diff_hash mismatch` | Diff was edited or re-prepared | Re-prepare, re-approve |
| Apply runs but Weaviate writes look wrong | `_build_prod_pipeline` mis-wired | Check OpenAI / Weaviate creds; abort + restore from snapshot |
| Apply succeeds but the index is missing pages | ETL fetch/extract dropped them silently | Read the diff's "Fetch failures" + "Extraction rejects" sections |

## Recurring use (after first run)

Once the team is comfortable, the prepare phase runs as a weekly cron
(Sunday 2 AM). The cron:
1. Runs `--phase prepare`.
2. Posts the diff path + approval path to Slack / email.
3. Waits for a human signature.
4. A separate cron / on-call action runs `--phase apply` after the
   librarian signs.

The gate code is exactly the same — only the trigger changes.

## See also

- `gate.py` — the verifier
- `test_gate.py` — proves the gate refuses the right things
- `diff_report.py` — shapes the Markdown the librarian reads
- Plan: Data preparation playbook §4 (the 11-step pipeline) and §5
  (refresh cadence + ownership).
