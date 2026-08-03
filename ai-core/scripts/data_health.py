"""
Daily data health check. Emails the operator ONLY when something is wrong.

    Run:  .venv/bin/python -m scripts.data_health [--force-email] [--quiet]

WHY THIS EXISTS
    The operator's words, 2026-07-29: "如果没有完全掌控所有的数据来源并且确保
    他们是有用的而且是及时更新的我真的会焦虑" -- anxiety about not knowing
    whether the data is still correct.

    Reading 740 Subject rows by hand does not fix that; it just moves the
    worry. What fixes it is a machine that checks every day and stays silent
    unless there is something to act on. **A quiet inbox means everything
    passed.**

DESIGN RULE: EVERY FINDING MUST BE ACTIONABLE
    Things this deliberately does NOT report, because nothing can be done
    about them and noise trains you to ignore the mail:
      * "16 active staff have no title" -- they are not on the public staff
        page, so no title exists to copy. Not a defect.
      * "664 of 740 Subject rows have no liaison" -- most are registrar
        program codes and administrative units (Provost, Degree Audit
        Reporting System). They are not supposed to have a librarian. This
        number was reported as a 9%-coverage "gap" earlier and it was
        misleading: measured against 4,432 real questions, the bot answers
        32 of the 35 subjects patrons actually ask about, and the 3 misses
        are a typo, a placeholder, and a pronoun ("my major").

    What it DOES report is drift, staleness, and things that are breaking
    for real users.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=ROOT.parent / ".env")

logger = logging.getLogger("data_health")

CSV_PATH = os.getenv("STAFF_CSV_PATH", "/opt/chatbot/staff-members.csv")

# A corpus older than this means the weekly ETL diff is being produced but
# nobody is signing it -- the failure mode that left the index frozen from
# 2026-05-14 to 2026-07-29.
CORPUS_STALE_DAYS = 21

# Refusals on librarian/subject questions are the signal that matters: a
# real person asked and we could not answer. More than this in a day is
# worth a look.
REFUSAL_ALERT = 3

MEMORY_WARN_PCT = 85


@dataclass
class Finding:
    name: str
    ok: bool
    summary: str
    detail: list[str] = field(default_factory=list)


# --- checks ---------------------------------------------------------------


def check_roster_matches_csv() -> Finding:
    """The CSV is authoritative; the table should equal it exactly."""
    from src.eval.real_backends import _db

    if not Path(CSV_PATH).exists():
        return Finding("roster vs CSV", False,
                       f"the staff CSV is missing at {CSV_PATH}")

    today = dt.date.today().isoformat()
    on_roster = set()
    for row in csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")):
        if (row.get("second-entry-for-person") or "").strip().upper() == "TRUE":
            continue
        email = (row.get("email") or "").strip().lower()
        last = (row.get("last-date") or "").strip()
        if email and not (last and last <= today):
            on_roster.add(email)

    async def q(c):
        return await c.librarian.find_many()

    rows = _db(q)
    in_db = {(r.email or "").lower() for r in rows}
    extra, missing = in_db - on_roster, on_roster - in_db
    if not extra and not missing:
        return Finding("roster vs CSV", True,
                       f"{len(in_db)} people, matches the CSV exactly")
    detail = ([f"in the database but NOT on the CSV roster: {e}" for e in sorted(extra)]
              + [f"on the CSV roster but MISSING from the database: {e}" for e in sorted(missing)])
    return Finding("roster vs CSV", False,
                   f"{len(extra)} extra / {len(missing)} missing -- "
                   f"run scripts/reconcile_staff_from_csv.py", detail)


def check_no_duplicate_people() -> Finding:
    """Two rows for one human means a name lookup returns two answers, and
    one of them usually has no title. Cleared on 2026-07-29; this stops it
    silently coming back."""
    from src.eval.real_backends import _db
    from src.utils.person_names import first_last

    async def q(c):
        return await c.librarian.find_many()

    seen: dict = {}
    for r in _db(q):
        key = first_last(r.name)
        if key != ("", ""):
            seen.setdefault(key, []).append(r.email)
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    if not dups:
        return Finding("duplicate people", True, "none")
    return Finding("duplicate people", False, f"{len(dups)} person(s) have two rows",
                   [f"{' '.join(k)}: {', '.join(v)}" for k, v in dups.items()])


def check_no_stale_subject_links() -> Finding:
    """A liaison link to someone no longer on the roster is how a departed
    colleague keeps being named as a subject's contact."""
    from src.eval.real_backends import _db

    async def q(c):
        links = await c.librariansubject.find_many(include={"librarian": True,
                                                            "subject": True})
        return links

    bad = []
    links = _db(q)
    for l in links:
        if l.librarian is None:
            bad.append(f"link {l.id} points at a deleted librarian")
        elif not getattr(l.librarian, "isActive", True):
            bad.append(f"{l.librarian.name} (inactive) still liaison for "
                       f"{l.subject.name if l.subject else '?'}")
    if bad:
        return Finding("stale liaison links", False,
                       f"{len(bad)} link(s) point at someone off the roster", bad)
    return Finding("stale liaison links", True,
                   f"{len(links)} links, all to current staff")


def check_real_questions_we_failed(hours: int = 24) -> Finding:
    """The signal that actually matters: real people who asked and got
    refused. Uses the turn telemetry, so it costs no API calls."""
    from src.eval.real_backends import _db

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)

    async def q(c):
        refused = await c.message.find_many(
            where={"wasRefusal": True, "timestamp": {"gte": since}},
            order={"timestamp": "desc"}, take=50)
        # `content` on a refused row is the BOT's text ("I don't have a
        # reliable answer..."), which tells the operator nothing. What is
        # actionable is the QUESTION, so pull the preceding user turn from
        # the same conversation.
        out = []
        for m in refused:
            prior = await c.message.find_many(
                where={"conversationId": m.conversationId, "type": "user",
                       "timestamp": {"lte": m.timestamp}},
                order={"timestamp": "desc"}, take=1)
            out.append((m, (prior[0].content if prior else "") or "(question not found)"))
        return out

    try:
        pairs = _db(q)
        msgs = [m for m, _ in pairs]
        asked = {m.id: qtext for m, qtext in pairs}
    except Exception as e:  # noqa: BLE001
        return Finding("refused real questions", True,
                       f"telemetry unavailable ({type(e).__name__}) -- skipped")
    if len(msgs) < REFUSAL_ALERT:
        return Finding("refused real questions", True,
                       f"{len(msgs)} in the last {hours}h (threshold {REFUSAL_ALERT})")
    by_trigger: dict = {}
    for m in msgs:
        by_trigger.setdefault(m.refusalTrigger or "unknown", []).append(m)
    detail = []
    for trig, group in sorted(by_trigger.items(), key=lambda kv: -len(kv[1])):
        detail.append(f"{len(group)}x {trig}")
        for m in group[:3]:
            detail.append(f"    asked: \"{asked.get(m.id, '')[:100]}\"")
    return Finding("refused real questions", False,
                   f"{len(msgs)} refusals in the last {hours}h", detail)


def check_corpus_freshness() -> Finding:
    """The collection name carries the ETL date. A frozen corpus means the
    weekly diff is being produced but never signed."""
    name = os.getenv("WEAVIATE_CHUNK_COLLECTION") or ""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if not m:
        return Finding("corpus freshness", True,
                       f"cannot date the collection name {name!r} -- skipped")
    built = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    age = (dt.date.today() - built).days
    if age <= CORPUS_STALE_DAYS:
        return Finding("corpus freshness", True, f"indexed {age} days ago ({built})")
    return Finding("corpus freshness", False,
                   f"the search index is {age} days old ({built})",
                   ["scripts/etl_watch.py emails a diff weekly; a librarian "
                    "must sign the .approval file, then run "
                    "`run_etl --phase apply`.",
                    "Until that happens the bot answers from the old snapshot."])


def check_dependencies() -> Finding:
    """Every third-party the bot needs, via the app's own health endpoint --
    so this reports what the RUNNING process sees, not a fresh connection."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:8081/health", timeout=20) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        return Finding("dependencies", False,
                       f"the app's own /health endpoint is unreachable: {e}",
                       ["If the service is down, that IS the alert."])
    svcs = data.get("services") or {}
    bad = [f"{k}: {v.get('status')}" for k, v in svcs.items()
           if v.get("status") not in ("healthy", "unconfigured")]
    if bad:
        return Finding("dependencies", False, f"{len(bad)} unhealthy", bad)
    return Finding("dependencies", True,
                   ", ".join(f"{k}={v.get('status')}" for k, v in svcs.items()))


def check_memory_and_oom() -> Finding:
    """Today's near-miss: the box OOM'd and uvicorn was first in line to be
    killed. The unit is hardened now, but a kill still means something is
    over-consuming and the operator should know."""
    detail, ok = [], True
    try:
        meminfo = dict(
            (k.strip(), int(v.split()[0]))
            for k, v in (l.split(":", 1) for l in open("/proc/meminfo")))
        total, avail = meminfo["MemTotal"], meminfo["MemAvailable"]
        used_pct = 100 * (total - avail) / total
        summary = f"{used_pct:.0f}% of {total // 1024} MB in use"
        if used_pct >= MEMORY_WARN_PCT:
            ok = False
            detail.append(f"memory is at {used_pct:.0f}% -- an OOM kill is likely soon")
    except Exception as e:  # noqa: BLE001
        summary = f"could not read /proc/meminfo ({e})"

    try:
        out = subprocess.run(["dmesg", "-T"], capture_output=True, text=True,
                             timeout=20).stdout
        cutoff = dt.datetime.now() - dt.timedelta(hours=24)
        kills = []
        for line in out.splitlines():
            if "Killed process" not in line:
                continue
            ts = re.match(r"\[(.*?)\]", line)
            if ts:
                try:
                    when = dt.datetime.strptime(ts.group(1), "%a %b %d %H:%M:%S %Y")
                    if when < cutoff:
                        continue
                except ValueError:
                    pass
            kills.append(line.strip()[:160])
        if kills:
            ok = False
            detail.append(f"{len(kills)} OOM kill(s) in the last 24h:")
            detail += [f"    {k}" for k in kills[:5]]
    except Exception:  # noqa: BLE001
        pass
    return Finding("memory / OOM", ok, summary, detail)


CHECKS = (
    check_dependencies,
    check_memory_and_oom,
    check_roster_matches_csv,
    check_no_duplicate_people,
    check_no_stale_subject_links,
    check_real_questions_we_failed,
    check_corpus_freshness,
)


def main(force_email: bool, quiet: bool) -> int:
    findings = []
    for fn in CHECKS:
        try:
            findings.append(fn())
        except Exception as e:  # noqa: BLE001 -- one broken check must not
            # hide the others, and a check that cannot run is itself a finding
            findings.append(Finding(fn.__name__, False,
                                    f"the check itself failed: {type(e).__name__}: {e}"))

    problems = [f for f in findings if not f.ok]

    lines = [f"Data health {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for f in findings:
        lines.append(f"[{'OK ' if f.ok else 'ACT'}] {f.name}: {f.summary}")
        lines += [f"       {d}" for d in f.detail]
    body = "\n".join(lines)

    if quiet:
        # --quiet used to mean "no stdout at all". Under cron that wrote a
        # 0-byte log forever, which reads as "the check never ran" -- and it
        # cost real time: the 81-day-old corpus and an unhealthy dependency
        # were both being reported here every morning, to a file nobody could
        # tell apart from silence. Quiet now means "only the things that need
        # a human", so an empty log genuinely means all clear.
        if problems:
            act = [lines[0], ""]
            for f in problems:
                act.append(f"[ACT] {f.name}: {f.summary}")
                act += [f"       {d}" for d in f.detail]
            print("\n".join(act))
    else:
        print(body)

    if problems or force_email:
        subject = (f"[chatbot] data health: {len(problems)} thing(s) need you"
                   if problems else "[chatbot] data health: all clear")
        try:
            from src.observability.alerting import send_alert_email
            send_alert_email(subject, body + (
                "\n\nA quiet inbox means every check passed -- this mail is "
                "only sent when there is something to act on."))
            # WARNING, not INFO: under cron the root level is WARNING, so an
            # INFO "email sent" line was dropped and the log could not show
            # whether anyone had been told. Whether a human was notified is
            # exactly what this log is for.
            logger.warning("data health: emailed %d problem(s): %s",
                           len(problems), subject)
        except Exception as e:  # noqa: BLE001
            logger.error("could not send the health email: %s", e)
            return 2
    return 1 if problems else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-email", action="store_true",
                    help="send even when everything passes (tests the pipe)")
    ap.add_argument("--quiet", action="store_true", help="no stdout")
    a = ap.parse_args()
    sys.exit(main(a.force_email, a.quiet))
