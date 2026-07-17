# Deployment Guide

**Last Updated:** July 18, 2026
**Describes the CURRENT flow** (AWS host, systemd, nginx). The
pre-migration guide is archived at
[archive/legacy-v31/10-DEPLOYMENT-GUIDE.md](./archive/legacy-v31/10-DEPLOYMENT-GUIDE.md).

## Standard deploy

```bash
cd /opt/chatbot
git pull                 # pull.rebase=true is set for this repo
./build.sh               # backend deps + prisma generate + frontend build + service restart
```

`build.sh` does, in order: venv `pip install -e .`, `prisma generate`,
`npm ci && npm run build` in `client/`, `systemctl restart chatbot.service`.

## Schema changes

1. Edit `/prisma/schema.prisma` (the source of truth).
2. `./local-auto-start.sh --sync-prisma` (copies models into
   `ai-core/schema.prisma` — do NOT edit that copy by hand).
3. `cd ai-core && .venv/bin/prisma generate && .venv/bin/prisma db push`
   (with `.env` loaded).

## Post-deploy verification

```bash
curl -s localhost:8081/health/ready | python3 -m json.tool   # 5 probes healthy
curl -s localhost:8081/smoketest                              # passed: true
sudo systemctl is-active chatbot.service
```
Then open the operator hub (`/admin/?key=…`) and click through the pages.

## Pieces OUTSIDE the repo (re-create if the host is rebuilt)

| Thing | Where | Notes |
|---|---|---|
| nginx site config | `/etc/nginx/sites-enabled/default` | path-allowlist proxy; `/librarian/` + `/admin/` blocks required (see [13-CORRECTION-TICKETS.md](./13-CORRECTION-TICKETS.md)) |
| `.env` | `/opt/chatbot/.env` | secrets incl. `ALERT_SMTP_*`, `ADMIN_API_TOKEN`, `LIBRARIAN_TICKET_CODE`, model tiers |
| cost rollup cron | root crontab | `0 2 * * *` → `scripts/cost_rollup.py` |
| systemd unit | `/etc/systemd/system/chatbot.service` | uvicorn `src.main:app_sio`, port 8081 |
| Weaviate + Postgres | Docker | `ai-core/docker-compose.weaviate.yml`; Postgres container `chatbot-postgres` |

## Rollback

Every change ships as a git commit; `git revert <sha> && ./build.sh`.
The removed legacy path can be restored the same way (commit e883073).
