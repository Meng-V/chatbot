#!/usr/bin/env python3
"""Watch the service from OUTSIDE it, because it cannot report its own death.

    liveness_watchdog.py                 # check, alert on a change
    liveness_watchdog.py --dry-run       # print, send nothing, write nothing
    liveness_watchdog.py --try-restart   # also recover when systemd gave up

Run from cron every few minutes.

THE BLIND SPOT THIS CLOSES
Every other monitor we have runs INSIDE the app: `_health_alert_watcher`
probes Postgres, Weaviate, OpenAI, LibCal and LibGuides, and emails when one
of them flips. All of it dies with the process.

systemd has `Restart=always, RestartSec=5`, which covers an ordinary crash.
But it also has `StartLimitBurst=5, StartLimitIntervalSec=60`: if the service
fails to come up five times in a minute -- say Weaviate is down and startup
raises -- systemd **gives up and stops trying**. At that point:

  * the app is gone, so the in-app watcher sends nothing
  * systemd is no longer retrying, so nothing brings it back
  * and nobody is told, because the thing that would have told us is dead

That is the one failure mode where the bot is off and the operator's inbox is
silent. It matters more than usual right now: the operator's parental leave
starts 2026-09-04, and whoever is covering will not be watching a terminal.

WHAT COUNTS AS ALIVE
An HTTP 200 from /health. Not "the port accepts a connection" -- uvicorn can
be listening while the app is wedged -- and not systemd's own view alone,
because `active (running)` is true of a process stuck in a loop.

NOISE DISCIPLINE
Alerts fire on TRANSITIONS ONLY, after `--fails-before-alert` consecutive
bad checks, so one slow response during a restart does not mail anybody.
Recovery is also a transition and is also mailed, because "it came back" is
the other half of the information.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HEALTH_URL = os.getenv("WATCHDOG_HEALTH_URL", "http://127.0.0.1:8081/health")
UNIT = os.getenv("WATCHDOG_UNIT", "chatbot")
STATE_PATH = Path(os.getenv("WATCHDOG_STATE_PATH",
                            "/opt/chatbot/data/watchdog_state.json"))
TIMEOUT_S = float(os.getenv("WATCHDOG_TIMEOUT_S", "10"))

# Consecutive failures before we call it down. Two at a 5-minute cadence means
# roughly ten minutes of genuine unavailability, which is past any restart.
FAILS_BEFORE_ALERT = int(os.getenv("WATCHDOG_FAILS_BEFORE_ALERT", "2"))

# Never attempt recovery more often than this, even with --try-restart. A
# watchdog that restarts a service every five minutes turns a broken
# dependency into a restart loop and hides the real fault.
RESTART_COOLDOWN_S = int(os.getenv("WATCHDOG_RESTART_COOLDOWN_S", "1800"))


def _systemctl(*args: str) -> str:
    try:
        return subprocess.run(["systemctl", *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"<systemctl failed: {e}>"


def probe() -> tuple[bool, str]:
    """(alive, human-readable detail). Alive means HTTP 200 from /health."""
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "watchdog"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            code = r.status
            body = r.read(400).decode("utf-8", "replace")
        if code == 200:
            return True, f"HTTP 200 from {HEALTH_URL}"
        return False, f"HTTP {code} from {HEALTH_URL}: {body[:200]}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} from {HEALTH_URL}"
    except Exception as e:  # noqa: BLE001 -- connection refused, DNS, timeout
        return False, f"{type(e).__name__}: {e}"


def _load() -> dict:
    try:
        d = json.loads(STATE_PATH.read_text())
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001 -- a corrupt file must not stop the watch
        return {}


def _save(d: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, indent=2) + "\n")
        os.replace(tmp, STATE_PATH)
    except Exception as e:  # noqa: BLE001
        print(f"watchdog: could not write state: {e}", file=sys.stderr)


def _mail(subject: str, body: str) -> bool:
    """Send directly. Deliberately NOT through incident_alerts.

    incident_alerts routes non-urgent kinds into a digest queue that is mailed
    by a cron job -- useless here, where the point is to tell somebody the
    service is gone right now. alerting itself only needs smtplib, so it works
    with the app dead.
    """
    try:
        from src.observability.alerting import send_alert_email
        from src.observability.incident_alerts import urgent_recipients
        return bool(send_alert_email(subject, body, to=urgent_recipients()))
    except Exception as e:  # noqa: BLE001
        print(f"watchdog: could not send mail: {e}", file=sys.stderr)
        return False


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the verdict; write nothing, send nothing")
    ap.add_argument("--try-restart", action="store_true",
                    help=("attempt ONE recovery when systemd has given up "
                          "(state=failed), at most once per cooldown"))
    ap.add_argument("--fails-before-alert", type=int, default=FAILS_BEFORE_ALERT)
    args = ap.parse_args(argv)

    alive, detail = probe()
    unit_state = _systemctl("is-active", UNIT) or "unknown"
    # `failed` is the case this whole script exists for: systemd is no longer
    # retrying, so nothing else will bring the service back.
    gave_up = unit_state in ("failed", "inactive")

    state = _load()
    fails = 0 if alive else int(state.get("consecutive_fails", 0)) + 1
    was_down = bool(state.get("down", False))
    now = _dt.datetime.now().astimezone()

    print(f"health   : {'UP' if alive else 'DOWN'}  ({detail})")
    print(f"unit     : {unit_state}{'  <- systemd has stopped retrying' if gave_up else ''}")
    print(f"fails    : {fails} (alert at {args.fails_before_alert})")

    is_down = fails >= args.fails_before_alert
    action = ""

    if args.dry_run:
        print("\n(dry run -- nothing written, nothing sent)")
        return 0 if alive else 1

    if is_down and gave_up and args.try_restart:
        last = state.get("last_restart_at")
        cooled = True
        if last:
            try:
                cooled = (now - _dt.datetime.fromisoformat(last)
                          ).total_seconds() > RESTART_COOLDOWN_S
            except ValueError:
                cooled = True
        if cooled:
            _systemctl("reset-failed", UNIT)
            out = _systemctl("restart", UNIT)
            action = (f"systemd had given up (state={unit_state}); the watchdog "
                      f"reset it and issued one restart. {out}".strip())
            state["last_restart_at"] = now.isoformat()
            print(f"action   : {action}")
        else:
            action = (f"systemd has given up (state={unit_state}) but the "
                      f"watchdog restarted it less than "
                      f"{RESTART_COOLDOWN_S // 60} minutes ago -- NOT retrying. "
                      f"This needs a person.")
            print(f"action   : {action}")

    # Transitions only.
    if is_down and not was_down:
        body = [
            f"The chatbot did not answer {fails} consecutive health checks.",
            "",
            f"probe      {detail}",
            f"unit       {unit_state}",
            f"checked    {now:%Y-%m-%d %H:%M %Z}",
            "",
        ]
        if gave_up:
            body += [
                "systemd is NOT retrying. Restart=always only covers an",
                "ordinary crash; after 5 failed starts in 60 seconds systemd",
                "stops, and the in-app monitors died with the process. Nothing",
                "will bring this back on its own.",
                "",
            ]
        if action:
            body += [f"watchdog action: {action}", ""]
        body += [
            "To look:   systemctl status chatbot; journalctl -u chatbot -n 80",
            "To revive: sudo systemctl reset-failed chatbot && "
            "sudo systemctl restart chatbot",
        ]
        _mail(f"[chatbot] DOWN — {unit_state} — no answer from /health",
              "\n".join(body))
    elif alive and was_down:
        _mail("[chatbot] recovered",
              f"Answering again as of {now:%Y-%m-%d %H:%M %Z}.\n\n"
              f"{detail}\nunit: {unit_state}\n"
              + (f"\nwatchdog action taken earlier: "
                 f"{state.get('last_action', '(none)')}\n" if state.get("last_action") else ""))

    state.update({"down": is_down, "consecutive_fails": fails,
                  "last_check_at": now.isoformat(), "last_detail": detail,
                  "unit_state": unit_state})
    if action:
        state["last_action"] = action
    _save(state)
    return 0 if alive else 1


if __name__ == "__main__":
    raise SystemExit(main())
