"""Remove Weaviate chunk collections left behind by FAILED ETL runs.

WHY THIS EXISTS AS A REAL SCRIPT
    A throwaway version of this ran on 2026-07-29 with the rule "delete
    every `Chunk_*` that isn't currently serving". That rule is exactly
    inverted for this design. Promotion is deliberately manual, so at any
    moment the most valuable collection on the box is usually one that is
    NOT serving: the one an approved apply just wrote and a librarian has
    not yet promoted. The script deleted 19,972 freshly embedded chunks and
    reported it as clearing a failed-run leftover.

    So the safety rules live in code, with a dry run by default, instead of
    in whoever is typing at 2am.

WHAT IT REFUSES TO DELETE
    1. The serving collection (`WEAVIATE_CHUNK_COLLECTION`).
    2. Any collection named by a `.applied` marker in the diff directory
       that is not yet marked `promoted: yes` -- i.e. approved and waiting.
    3. Anything, unless `--yes` is passed. Default is a report.

    Rule 2 depends on `gate.mark_applied` recording the collection name.
    Markers written before that existed name no collection, so this script
    treats a nameless marker as "cannot prove it is safe" and keeps
    everything from that run's date. Refusing to guess is the point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


SERVING_STATE = Path("/opt/chatbot/ai-core/data/serving_corpus.json")


def _protected_as_rollback(
    state: "Optional[Path]" = None,
) -> tuple[set[str], list[str]]:
    """The collection we would roll back to, read from switch_corpus's state.

    THE 2026-07-29 FAILURE, closed properly. The rule that deleted 19,972 good
    chunks was "every Chunk_* that isn't serving is a failed-run leftover".
    Promotion makes the PREVIOUS corpus non-serving -- so under that rule,
    promoting anything schedules your own rollback for deletion. Marker files
    protect a collection *awaiting* promotion; this protects the one that has
    been *superseded by* one, which is the other half of the same hole.
    """
    state = state or SERVING_STATE
    if not state.exists():
        return set(), []
    try:
        hist = json.loads(state.read_text()).get("history", [])
    except Exception as e:  # noqa: BLE001
        return set(), [f"{state.name}: unreadable ({e}) -- a rollback target "
                       f"may therefore look deletable"]
    live = [h for h in hist if not h.get("rolled_back")]
    return ({live[-1]["from"]} if live and live[-1].get("from") else set()), []


def _protected_by_markers(diff_dir: Path) -> tuple[set[str], list[str]]:
    """(collections to protect, warnings about markers we cannot read)."""
    protected: set[str] = set()
    warnings: list[str] = []
    for marker in sorted(diff_dir.glob("*.applied")):
        try:
            text = marker.read_text(encoding="utf-8")
        except OSError as e:
            warnings.append(f"{marker.name}: unreadable ({e}) -- protecting nothing")
            continue
        name = ""
        promoted = ""
        for line in text.splitlines():
            if line.startswith("collection:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("promoted:"):
                promoted = line.split(":", 1)[1].strip().lower()
        if not name:
            warnings.append(
                f"{marker.name}: records no collection name (written before "
                f"that was tracked), so this script cannot tell which "
                f"collection it produced")
            continue
        if promoted == "yes":
            continue  # its content is live under another name; safe to drop
        protected.add(name)
    return protected, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true",
                    help="Actually delete. Without this, only report.")
    ap.add_argument("--diff-dir", default=None,
                    help="Directory holding .applied markers.")
    args = ap.parse_args()

    from dotenv import load_dotenv  # type: ignore
    load_dotenv("/opt/chatbot/.env")

    from scripts.etl import config  # type: ignore
    from src.utils.weaviate_client import get_weaviate_client  # type: ignore

    diff_dir = Path(args.diff_dir or config.DIFF_REPORT_DIR)
    serving = os.getenv("WEAVIATE_CHUNK_COLLECTION") or ""
    if not serving:
        print("REFUSING: WEAVIATE_CHUNK_COLLECTION is unset, so the serving "
              "collection cannot be identified. Nothing was deleted.")
        return 2

    protected, warnings = _protected_by_markers(diff_dir)
    rollback, rb_warnings = _protected_as_rollback()
    protected |= rollback
    warnings += rb_warnings
    client = get_weaviate_client()
    if client is None:
        print("REFUSING: no Weaviate client.")
        return 2

    try:
        names = sorted(n for n in client.collections.list_all()
                       if re.fullmatch(r"Chunk_v.+", n))
        if warnings:
            print("Markers this script could not interpret:")
            for w in warnings:
                print(f"  ! {w}")
            print("  -> Nothing is deleted while any marker is ambiguous.\n")
            print("Resolve by adding a `collection:` line to the marker, or "
                  "confirm by hand which collections are disposable.")
            return 3

        deletable = []
        for name in names:
            try:
                count = client.collections.get(name).aggregate.over_all(
                    total_count=True).total_count
            except Exception as e:  # noqa: BLE001
                count = f"?({e})"
            if name == serving:
                print(f"  KEEP   {name} ({count})  serving")
            elif name in rollback:
                print(f"  KEEP   {name} ({count})  rollback target")
            elif name in protected:
                print(f"  KEEP   {name} ({count})  approved, awaiting promotion")
            else:
                print(f"  DELETE {name} ({count})  no marker claims it")
                deletable.append(name)

        if not deletable:
            print("\nNothing to delete.")
            return 0
        if not args.yes:
            print(f"\n{len(deletable)} collection(s) would be deleted. "
                  f"Re-run with --yes to do it.")
            return 0
        for name in deletable:
            client.collections.delete(name)
            print(f"  deleted {name}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
