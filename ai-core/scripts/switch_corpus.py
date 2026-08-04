"""Switch which Weaviate collection serves patrons, and switch back.

WHY THIS EXISTS AS A REAL SCRIPT
    Promotion is one line in .env plus a restart, which is exactly why doing it
    by hand is dangerous. Three separate things have gone wrong around this:

      * 2026-07-29: a cleanup script deleted 19,972 freshly embedded chunks
        because its rule was "every Chunk_* that isn't serving is a failed-run
        leftover". The moment you promote, the PREVIOUS corpus becomes
        non-serving -- i.e. becomes a deletion candidate. So promoting without
        recording the predecessor is how you lose your own rollback.
      * 2026-07-31: two collections sat in the database looking like finished
        refreshes. One held 12,480 chunks against the serving 20,608.
        Promoting either would have silently cost 39% of the corpus.
      * A promotion that breaks retrieval is not obvious from `systemctl
        status`: the service comes up healthy and answers everything with a
        refusal.

    So: this records what was serving before, refuses to point at something
    that doesn't exist, shows the operator the numbers that matter (distinct
    pages, not chunk count -- 95.6% of the old corpus was binary PDF noise, so
    chunk counts are not comparable), verifies retrieval actually works after
    the switch, and rolls back by itself if it doesn't.

USAGE
    python -m scripts.switch_corpus --status
    python -m scripts.switch_corpus --list
    python -m scripts.switch_corpus --to Chunk_vv20260804_0246
    python -m scripts.switch_corpus --rollback
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ENV_PATH = Path("/opt/chatbot/.env")
STATE_PATH = Path("/opt/chatbot/ai-core/data/serving_corpus.json")
ENV_KEY = "WEAVIATE_CHUNK_COLLECTION"
WEAVIATE = os.getenv("WEAVIATE_URL", "http://127.0.0.1:8080")
HEALTH = "http://127.0.0.1:8081/health"
SERVICE = "chatbot"

# A collection this small cannot be a real corpus. The honest ceiling is set
# low on purpose: the point is to catch an empty or half-written collection,
# not to second-guess a deliberate rebuild. The 2026-08-04 rebuild is 173
# chunks and legitimate, so any threshold near the old 20,608 would block the
# very promotion it was meant to protect.
MIN_CHUNKS = 20


def _gql(query: str) -> dict:
    req = urllib.request.Request(
        f"{WEAVIATE}/v1/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collections() -> list[str]:
    with urllib.request.urlopen(f"{WEAVIATE}/v1/schema", timeout=30) as r:
        schema = json.load(r)
    return sorted(
        c["class"] for c in schema.get("classes", [])
        if c["class"].startswith("Chunk_")
    )


def stats(coll: str) -> dict:
    """Chunk count plus DISTINCT PAGES, which is the comparable number.

    Chunk counts across these collections are not comparable: the 2026-05-14
    corpus is 95.6% binary PDF bytes chunked into 4,201-character blobs, so it
    reads as 120x larger than a corpus with more real pages in it.
    """
    try:
        n = _gql("{Aggregate{%s{meta{count}}}}" % coll)
        count = n["data"]["Aggregate"][coll][0]["meta"]["count"]
    except Exception:
        return {"chunks": None, "pages": None, "pdf_chunks": None}
    urls: list[str] = []
    after = None
    while True:
        a = f',after:"{after}"' if after else ""
        try:
            d = _gql('{Get{%s(limit:1000%s){source_url _additional{id}}}}'
                     % (coll, a))
        except Exception:
            break
        rows = (d.get("data") or {}).get("Get", {}).get(coll) or []
        if not rows:
            break
        urls += [r.get("source_url") or "" for r in rows]
        after = rows[-1]["_additional"]["id"]
        if len(rows) < 1000 or len(urls) > 40000:
            break
    return {
        "chunks": count,
        "pages": len(set(urls)),
        "pdf_chunks": sum(1 for u in urls if u.lower().endswith(".pdf")),
    }


def env_current() -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{ENV_KEY}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def env_set(value: str) -> None:
    """Rewrite the one line, keeping a timestamped backup of .env."""
    backup = ENV_PATH.with_suffix(f".env.bak.{dt.datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(ENV_PATH, backup)
    lines = ENV_PATH.read_text().splitlines(keepends=True)
    out, found = [], False
    for line in lines:
        if line.startswith(f"{ENV_KEY}="):
            out.append(f"{ENV_KEY}={value}\n")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{ENV_KEY}={value}\n")
    ENV_PATH.write_text("".join(out))
    print(f"  .env updated (backup: {backup.name})")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"history": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def restart_and_verify(timeout: int = 120) -> tuple[bool, str]:
    """Restart, wait for health, then prove RETRIEVAL works.

    Health alone is not enough. A collection that exists but returns nothing
    leaves the service healthy while every content answer becomes a refusal --
    which is precisely the failure this whole script exists to catch.
    """
    subprocess.run(["systemctl", "restart", SERVICE], check=False)
    deadline = time.time() + timeout
    up = False
    while time.time() < deadline:
        time.sleep(5)
        try:
            with urllib.request.urlopen(HEALTH, timeout=10) as r:
                if r.status == 200:
                    up = True
                    break
        except Exception:
            continue
    if not up:
        return False, f"service did not become healthy within {timeout}s"

    coll = env_current()
    s = stats(coll)
    if not s["chunks"]:
        return False, f"{coll} answers no aggregate query -- retrieval is dead"
    return True, f"healthy; {coll} holds {s['chunks']} chunks across {s['pages']} pages"


def cmd_list() -> int:
    serving = env_current()
    print(f"serving: {serving or '(unset)'}\n")
    hdr = f"{'collection':30}{'chunks':>9}{'pages':>8}{'pdf chunks':>12}  "
    print(hdr)
    print("-" * (len(hdr) - 2))
    for c in collections():
        s = stats(c)
        mark = "  <- serving" if c == serving else ""
        pdf = s["pdf_chunks"]
        pdf_s = "-" if pdf is None else (
            f"{pdf} ({100*pdf/max(s['chunks'],1):.0f}%)" if pdf else "0")
        print(f"{c:30}{str(s['chunks']):>9}{str(s['pages']):>8}{pdf_s:>12}{mark}")
    st = load_state()
    if st["history"]:
        last = st["history"][-1]
        print(f"\nrollback would return to: {last['from']}"
              f"  (switched {last['at']})")
    return 0


def cmd_status() -> int:
    serving = env_current()
    s = stats(serving) if serving else {}
    print(f"serving      {serving or '(unset)'}")
    print(f"chunks       {s.get('chunks')}")
    print(f"pages        {s.get('pages')}")
    print(f"pdf chunks   {s.get('pdf_chunks')}")
    st = load_state()
    print(f"switches     {len(st['history'])} recorded")
    for h in st["history"][-5:]:
        print(f"  {h['at']}  {h['from']} -> {h['to']}  ({h.get('note','')})")
    return 0


def cmd_to(target: str, force: bool, note: str) -> int:
    avail = collections()
    if target not in avail:
        print(f"REFUSED: {target} does not exist.")
        print("available: " + ", ".join(avail))
        return 2
    current = env_current()
    if target == current:
        print(f"{target} is already serving. Nothing to do.")
        return 0

    cs, ts = stats(current), stats(target)
    print(f"  from  {current:30} {cs['chunks']} chunks / {cs['pages']} pages")
    print(f"  to    {target:30} {ts['chunks']} chunks / {ts['pages']} pages")

    if not ts["chunks"] or ts["chunks"] < MIN_CHUNKS:
        print(f"REFUSED: {target} holds {ts['chunks']} chunks "
              f"(minimum {MIN_CHUNKS}). That is a broken or half-written "
              f"collection, not a corpus.")
        return 2

    # Page coverage is the comparable measure. Report it loudly and require an
    # explicit --force for a big drop, rather than guessing whether the drop is
    # intentional: on 2026-08-04 a 419 -> 94 page drop WAS intentional (news,
    # PDFs and duplicate vanity URLs removed), and a similar-looking drop on
    # 2026-07-31 would have been a truncated build.
    if cs["pages"] and ts["pages"] and ts["pages"] < cs["pages"] * 0.5:
        pct = 100 * ts["pages"] / cs["pages"]
        if not force:
            print(f"REFUSED: page coverage drops to {pct:.0f}% of current "
                  f"({cs['pages']} -> {ts['pages']} pages).")
            print("  If that is intended, re-run with --force. If you are not "
                  "certain it is intended, it isn't.")
            return 2
        print(f"  WARNING: page coverage drops to {pct:.0f}% "
              f"-- proceeding because --force was given")

    st = load_state()
    st["history"].append({
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "from": current,
        "to": target,
        "note": note,
        "from_stats": cs,
        "to_stats": ts,
    })
    save_state(st)
    print(f"  recorded predecessor {current} in {STATE_PATH.name} "
          f"(this is also what protects it from cleanup)")

    env_set(target)
    ok, msg = restart_and_verify()
    print(f"  {msg}")
    if not ok:
        print("ROLLING BACK -- the switch did not verify")
        env_set(current)
        ok2, msg2 = restart_and_verify()
        print(f"  rollback: {msg2}")
        st["history"][-1]["rolled_back"] = True
        save_state(st)
        return 1
    print(f"\n{target} is now serving. Roll back any time with:")
    print("  sudo .venv/bin/python -m scripts.switch_corpus --rollback")
    return 0


def cmd_rollback(force: bool) -> int:
    st = load_state()
    hist = [h for h in st["history"] if not h.get("rolled_back")]
    if not hist:
        print("No recorded switch to roll back.")
        return 2
    last = hist[-1]
    print(f"Rolling back to {last['from']} (switched away {last['at']})")
    return cmd_to(last["from"], force=True, note="rollback")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="all collections + sizes")
    g.add_argument("--status", action="store_true", help="what is serving now")
    g.add_argument("--to", metavar="COLLECTION", help="promote this collection")
    g.add_argument("--rollback", action="store_true",
                   help="return to the previously serving collection")
    ap.add_argument("--force", action="store_true",
                    help="proceed despite a large page-coverage drop")
    ap.add_argument("--note", default="", help="why, recorded in the history")
    a = ap.parse_args(argv)

    if a.list:
        return cmd_list()
    if a.status:
        return cmd_status()
    if a.rollback:
        return cmd_rollback(a.force)
    return cmd_to(a.to, a.force, a.note)


if __name__ == "__main__":
    sys.exit(main())
