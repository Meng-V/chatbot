#!/usr/bin/env python3
"""Mail the queued non-urgent alerts as one message, then clear the queue.

    alert_digest.py              # send and clear
    alert_digest.py --dry-run    # print, keep the queue
    alert_digest.py --peek       # counts only

Run from cron once a day, on a working morning.

WHY THIS EXISTS
Before the handover the operator received 30-50 alert emails a day, almost
all of them individually unactionable: a thumbs-down, a refused injection
attempt, a rate-limit trip. Adding two colleagues to that stream would have
produced two more filter rules and nobody reading it. Anything that needs a
person tonight is in incident_alerts.URGENT_KINDS and does not come through
here; everything else arrives once, grouped, with counts.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability import incident_alerts as IA  # noqa: E402
from src.utils.logging_config import get_logger  # noqa: E402

log = get_logger("alert_digest")

# One kind's individual entries stop being useful past this many; the count
# carries the signal and the mail stays readable.
_MAX_DETAIL_PER_KIND = 5


def _read() -> list[dict]:
    try:
        rows = []
        for line in IA.DIGEST_PATH.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue          # one bad line must not lose the rest
        return rows
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        log.error("could not read the digest queue: %s", e)
        return []


def build(rows: list[dict]) -> tuple[str, str]:
    by_kind = collections.Counter(r.get("kind", "?") for r in rows)
    first, last = rows[0].get("at", "?"), rows[-1].get("at", "?")
    subject = (f"[chatbot] daily digest: {len(rows)} event(s) — "
               + ", ".join(f"{k} x{n}" for k, n in by_kind.most_common()))
    out = [
        f"{len(rows)} queued event(s) between {first} and {last}.",
        "",
        "Nothing in here needed anyone overnight. Anything that did would",
        "have been emailed at the time (see incident_alerts.URGENT_KINDS).",
        "",
        "SUMMARY",
    ]
    for kind, n in by_kind.most_common():
        out.append(f"  {kind:24s} {n:4d}")
    out.append("")
    for kind, _n in by_kind.most_common():
        items = [r for r in rows if r.get("kind") == kind]
        out += ["", "=" * 68, f"{kind.upper()}  ({len(items)})", "=" * 68]
        for r in items[:_MAX_DETAIL_PER_KIND]:
            out += ["", f"--- {r.get('at', '?')} — {r.get('subject', '')}",
                    str(r.get("body", "")).strip()]
        if len(items) > _MAX_DETAIL_PER_KIND:
            out.append("")
            out.append(f"... and {len(items) - _MAX_DETAIL_PER_KIND} more of "
                       f"this kind (count above is the signal).")
    return subject, "\n".join(out)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the digest, send nothing, keep the queue")
    ap.add_argument("--peek", action="store_true", help="counts only")
    args = ap.parse_args(argv)

    rows = _read()
    if not rows:
        print("digest queue is empty -- nothing to send")
        return 0

    if args.peek:
        import collections as _c
        for kind, n in _c.Counter(r.get("kind", "?") for r in rows).most_common():
            print(f"  {kind:24s} {n:4d}")
        return 0

    subject, body = build(rows)
    if args.dry_run:
        print(subject); print(); print(body)
        print(f"\n(dry run -- {len(rows)} row(s) left in the queue)",
              file=sys.stderr)
        return 0

    try:
        from src.observability.alerting import send_alert_email
        sent = bool(send_alert_email(subject, body))
    except Exception as e:  # noqa: BLE001
        log.error("could not send the digest: %s", e)
        sent = False

    if not sent:
        # Keep the queue. Losing a day of events to a transient SMTP failure
        # would be silent, and silence here reads as "nothing happened".
        print("digest NOT sent -- queue kept for the next run", file=sys.stderr)
        return 2

    try:
        IA.DIGEST_PATH.unlink()
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        log.error("digest sent but the queue could not be cleared: %s", e)
        return 2
    print(f"digest sent ({len(rows)} event(s)) and queue cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
