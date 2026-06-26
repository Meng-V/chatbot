"""
Operator email alerting -- a heads-up when a dependency goes down (or recovers).

The bot is resilient (it degrades instead of crashing), but the operator still
needs to KNOW when something is wrong -- otherwise a down database is invisible
until a user complains. This sends a short email on a health state-change.

Contract:
  * NEVER raises. Alerting must not be able to crash the app it's watching --
    every failure only logs.
  * Env-configured, with defaults that work out of the box on the prod host
    (a local MTA on localhost:25) and go to the operator. Override per-deploy:
      ALERT_EMAIL_ENABLED   (default "true"; set "false" to silence)
      ALERT_EMAIL_TO        (default "qum@miamioh.edu")
      ALERT_EMAIL_FROM      (default "smartchatbot-alerts@lib.miamioh.edu")
      ALERT_SMTP_HOST       (default "localhost")
      ALERT_SMTP_PORT       (default "25")
      ALERT_SMTP_STARTTLS   (default "false")
      ALERT_SMTP_USER / ALERT_SMTP_PASSWORD  (optional auth)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("alerting")


def _cfg(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


def alert_enabled() -> bool:
    return _cfg("ALERT_EMAIL_ENABLED", "true").lower() not in ("0", "false", "no", "off")


def send_alert_email(subject: str, body: str) -> bool:
    """Send an alert email. Returns True on success, False otherwise. NEVER raises."""
    if not alert_enabled():
        logger.info("alert email disabled (ALERT_EMAIL_ENABLED=false): %s", subject)
        return False
    to_addr = _cfg("ALERT_EMAIL_TO", "qum@miamioh.edu")
    from_addr = _cfg("ALERT_EMAIL_FROM", "smartchatbot-alerts@lib.miamioh.edu")
    host = _cfg("ALERT_SMTP_HOST", "localhost")
    try:
        port = int(_cfg("ALERT_SMTP_PORT", "25") or "25")
    except ValueError:
        port = 25
    user = _cfg("ALERT_SMTP_USER")
    pw = _cfg("ALERT_SMTP_PASSWORD")
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as s:
            if _cfg("ALERT_SMTP_STARTTLS", "false").lower() in ("1", "true", "yes", "on"):
                s.starttls(context=ssl.create_default_context())
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        logger.info("alert email sent to %s: %s", to_addr, subject)
        return True
    except Exception as e:  # noqa: BLE001 -- alerting must never crash the app
        logger.warning(
            "alert email FAILED via %s:%s -> %s (subject: %s) -- %s",
            host, port, to_addr, subject, e,
        )
        return False


if __name__ == "__main__":
    # Verify alerting actually reaches the operator:
    #   python -m src.observability.alerting
    # (loads the repo-root .env so ALERT_SMTP_HOST / ALERT_EMAIL_TO apply.)
    import sys
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO)
    ok = send_alert_email(
        "✅ Smart Chatbot: alert test",
        "This is a test of the Smart Chatbot operator alert email. If you got "
        "this, dependency-down alerts will reach you.",
    )
    print("SENT" if ok else "FAILED -- check ALERT_SMTP_HOST (need a reachable MTA)")
    sys.exit(0 if ok else 1)
