# Developer Documentation

**Miami University Libraries Smart Chatbot**
**Last Updated:** July 18, 2026

Everything in this folder describes the **current** system (the v2
rebuild — the only serving path since 2026-07-17). Anything describing
the retired v3.1 stack lives under [archive/](./archive/).

## Current docs

| Doc | What it covers |
|---|---|
| [01-SYSTEM-OVERVIEW.md](./01-SYSTEM-OVERVIEW.md) | Architecture, turn pipeline, model tiers, data stores, quality loop |
| [02-ENVIRONMENT-VARIABLES.md](./02-ENVIRONMENT-VARIABLES.md) | Every env var: model tiers, Springshare APIs, alerts, admin secrets |
| [03-SUBJECT-LIBRARIAN-SYSTEM.md](./03-SUBJECT-LIBRARIAN-SYSTEM.md) | Subject → librarian data layer (Postgres tables, course codes, fuzzy match) |
| [04-SERVER-MONITORING.md](./04-SERVER-MONITORING.md) | systemd, email alerts, probes, logs, cost cron |
| [05-DEPLOYMENT-GUIDE.md](./05-DEPLOYMENT-GUIDE.md) | build.sh flow, schema changes, post-deploy checks, host-level pieces |
| [06-CORRECTION-TICKETS.md](./06-CORRECTION-TICKETS.md) | Librarian "wrong answer" report form + operator queue |
| [librarian-services-truthtable-ask.md](./librarian-services-truthtable-ask.md) | Operator-verified service-availability truth table |
| [MAINTENANCE-2026-07-17-overnight.md](./MAINTENANCE-2026-07-17-overnight.md) | The post-legacy-removal audit report |

## Deeper / adjacent

- [../README.md](../README.md) — repo-level entry point
- [../ai-core/docs/OPERATOR.md](../ai-core/docs/OPERATOR.md) — operator runbook (endpoints, day-to-day tasks, alerts)
- [../ai-core/docs/eval/](../ai-core/docs/eval/) — dated eval reports, triage docs, gold-hygiene history
- [programmer-guide/00-INDEX.md](./programmer-guide/00-INDEX.md) — architecture deep-dive written during the rebuild

## Archive (historical — do NOT follow for the current system)

- [archive/legacy-v31/](./archive/legacy-v31/) — v3.1-era docs: old system
  overview, setup guide, Weaviate-as-correction-pool design, clarification
  buttons, old deployment guide/checklist, router refactor design, the
  watchdog-based monitoring doc
- [archive/reports/](./archive/reports/) — dated snapshots: accuracy audit,
  beta readiness, June deploy reports
- [eval/2026-05-22-wired-baseline/](./eval/2026-05-22-wired-baseline/) — the
  original eval-baseline archive

## Quick starts

**Deploy a change**: [05-DEPLOYMENT-GUIDE.md](./05-DEPLOYMENT-GUIDE.md)
**A librarian reports a wrong answer**: [06-CORRECTION-TICKETS.md](./06-CORRECTION-TICKETS.md)
**Alerts stopped / server questions**: [04-SERVER-MONITORING.md](./04-SERVER-MONITORING.md)
**New developer orientation**: 01 → programmer-guide → OPERATOR.md

---

**Developer:** Meng Qu, Miami University Libraries
