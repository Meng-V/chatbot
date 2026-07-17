# Server Monitoring & Alerts

**Last Updated:** July 18, 2026
**Describes the CURRENT stack.** The pre-migration watchdog era
(`server_monitor.py`, local MTA on :25) is archived at
[archive/legacy-v31/09-SERVER-MONITORING.md](./archive/legacy-v31/09-SERVER-MONITORING.md).

## Process supervision

- **systemd** owns the process: `chatbot.service`, `Restart=on-failure`,
  uvicorn on port 8081.
- Useful commands:
  ```bash
  sudo systemctl status chatbot.service
  sudo journalctl -u chatbot.service -since "1 hour ago"
  sudo systemctl restart chatbot.service
  ```

## Email alerts (dependency down / recovered)

`ai-core/src/observability/alerting.py` emails the operator on health
state changes. Configured 2026-07-17 via an authenticated Gmail relay on
port 587 (AWS blocks outbound 25 — this is why alerts silently died for
three days after the migration). Env: the `ALERT_*` block in
[07-ENVIRONMENT-VARIABLES.md](./07-ENVIRONMENT-VARIABLES.md).

Re-verify anytime:
```bash
cd ai-core && .venv/bin/python -m src.observability.alerting   # sends a test email
```

## Probes (wire these to an external pinger)

| URL | What it proves |
|---|---|
| `/health/live` | process is up |
| `/health/ready` | Postgres, Weaviate, OpenAI, LibCal, LibGuides all reachable |
| `/smoketest` | a full turn answers WITH a citation under the latency budget |
| `/metrics` | Prometheus exposition (if prometheus-client installed) |

All also linked from the operator hub: `/admin/?key=<ADMIN_API_TOKEN>`.

## Logs

`ai-core/logs/`: `app.log` (JSON, rotated), `errors.log`, `access.log`.
Grep `alert email` in app.log to audit alert deliveries/failures.

## Cost monitoring

Nightly cron (root crontab, 02:00) runs `scripts/cost_rollup.py` →
`DailyCost` table → `/admin/cost` dashboard. Model prices live at the
top of that script — update them when models change.
