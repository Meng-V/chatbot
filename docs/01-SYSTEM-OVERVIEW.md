# System Overview

**Last Updated:** July 18, 2026
**Describes:** the v2 rebuild — the ONLY serving path since 2026-07-17
(legacy v3.1 removed in commit e883073; its docs live in
[archive/legacy-v31/](./archive/legacy-v31/)).

## What this is

An AI chatbot for Miami University Libraries. Students ask about hours,
study rooms, subject librarians, course reserves, ILL, newspapers, the
MakerSpace, Special Collections; the bot answers with **cited,
operator-verified information**, live LibCal data, and can book study
rooms in-chat. When it doesn't reliably know, it refuses and hands off
to Ask Us.

## Architecture (one turn)

```
Browser widget (React, client/dist, served by nginx at /smartchatbot/)
  │  socket.io  /smartchatbot/socket.io
  ▼
main.py  _v2_message            rate limit + input validation
  ▼
src/graph/new_orchestrator.py   run_turn():
  1. scope resolution            campus/library from message + session origin
  2. intent classification       kNN over ~5.5k exemplars (embeddings)
  3. deterministic short-circuits hours, room booking pointers, staff
                                  directory, reserves, newspapers, equipment,
                                  tickets… (operator-verified answers, no LLM)
  4. agent loop                  REASONING-tier model + tools (search_kb/
                                  Weaviate, LibCal hours & room booking,
                                  librarian lookup/Postgres, URL validation)
  5. synthesizer                 BASIC-tier model; every claim cited;
                                  corrections pool applied; URL allowlist
  ▼
answer + citations + confidence  →  emitted back on the socket
```

Every turn logs conversation, tokens (`ModelTokenUsage`, callSite
`v2_turn`), and tool executions to Postgres.

## Model tiers (src/config/models.py — resolved at CALL time)

| Tier | Env var | Production value (2026-07) | Used for |
|---|---|---|---|
| reasoning | `LLM_MODEL_REASONING` | gpt-5.6-terra | agent loop, escalation |
| basic | `LLM_MODEL_BASIC` | gpt-5.6-luna | synthesizer, triage |
| cheap | `LLM_MODEL_CHEAP` | gpt-5.4-nano | eval judge, extraction |
| embedding | `LLM_MODEL_EMBEDDING` | text-embedding-3-large | kNN classifier, retrieval |

## Data stores

- **PostgreSQL** (Prisma; schema in `/prisma/schema.prisma`, synced copy in
  `ai-core/schema.prisma`): conversations, messages, ratings, feedback,
  librarians/subjects, library spaces, corrections, correction tickets,
  URL allowlist, daily cost rollup.
- **Weaviate** (Docker, localhost:8080): the retrieval corpus — ETL'd,
  librarian-gated chunks of lib.miamioh.edu + LibGuides content
  (collection `Chunk_vv*`), plus curated correction/exemplar data.

## Operations

- Runs as systemd `chatbot.service` (uvicorn, port 8081) behind nginx
  (HTTPS, path allowlist). Deploy: `./build.sh`.
- **Operator hub**: `/admin/?key=<ADMIN_API_TOKEN>` — tickets queue,
  flagged conversations, corrections CRUD, cost dashboard, probes.
- **Staff hub**: `/librarian/?key=<LIBRARIAN_TICKET_CODE>` — the
  "report a wrong answer" form ([13-CORRECTION-TICKETS.md](./13-CORRECTION-TICKETS.md)).
- Email alerts on dependency down/recovered: `src/observability/alerting.py`
  (Gmail relay, port 587; see [07-ENVIRONMENT-VARIABLES.md](./07-ENVIRONMENT-VARIABLES.md)).
- Probes: `/health/ready` (5 dependencies), `/smoketest` (full cited turn).

## Quality loop

Gold set of 234 operator-reviewed cases + LLM judge (judge_v2, reads the
operator's per-case notes). History and current numbers:
[../ai-core/docs/eval/](../ai-core/docs/eval/). Librarian correction
tickets feed new gold cases over time.

## Deeper reading

- [../ai-core/docs/OPERATOR.md](../ai-core/docs/OPERATOR.md) — runbook
- [programmer-guide/00-INDEX.md](./programmer-guide/00-INDEX.md) — rebuild deep-dive
- [08-SUBJECT-LIBRARIAN-SYSTEM.md](./08-SUBJECT-LIBRARIAN-SYSTEM.md) — subject data layer
