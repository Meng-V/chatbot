"""
Weekly ETL watch: re-crawl the website, email the operator what CHANGED.

    Run:  .venv/bin/python -m scripts.etl_watch [--force-email]

WHY
    The corpus had been frozen since 2026-05-14 -- two and a half months --
    because the ETL is a two-phase gated pipeline (prepare -> a librarian
    signs -> apply) and nobody was running `prepare`. No diff, no signature,
    no refresh. The bot went on answering from a May snapshot of the site.

    This closes the loop at the only point that was actually missing: it
    runs `prepare` on a schedule and puts the diff in front of a human. It
    deliberately does NOT apply anything. The signature gate stays.

WHAT IT COSTS
    A full prepare is ~410 page fetches of our own public site, about 25
    seconds, and **no API spend** -- dry-run skips embedding entirely.

WHEN IT EMAILS
    Only when something changed, or on failure. A week where the website
    stood still produces no mail, so a message in the inbox always means
    "there is something to look at". `--force-email` overrides that for
    testing the pipe.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(dotenv_path=ROOT.parent / ".env")

from src.observability.alerting import send_alert_email  # noqa: E402

logger = logging.getLogger("etl_watch")

DIFF_DIR = ROOT / "data" / "diffs"

# Numbers worth waking the operator for. A handful of chunks moving is
# normal editorial churn on a site this size; a large swing usually means
# a template change or a section moving, which is exactly when a human
# should look before anything is indexed.
_NOTABLE_CHANGE = 1


def _run_prepare() -> tuple[int, str]:
    """Run `--phase prepare` and return (exit_code, combined_output)."""
    proc = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), "-m",
         "scripts.etl.run_etl", "--phase", "prepare"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=1800,
        env={**os.environ},
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _latest_diff() -> Path | None:
    if not DIFF_DIR.is_dir():
        return None
    diffs = sorted(DIFF_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime)
    return diffs[-1] if diffs else None


def _summary_block(diff_path: Path) -> tuple[str, dict]:
    """Extract the Summary section and parse its `**n**` counts."""
    text = diff_path.read_text(encoding="utf-8")
    lines, keep, counts = text.splitlines(), [], {}
    inside = False
    for line in lines:
        if line.startswith("## Summary"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            keep.append(line)
            if line.startswith("- ") and "**" in line:
                label = line.split(":")[0].lstrip("- ").strip()
                raw = line.split("**")
                if len(raw) > 1:
                    try:
                        counts[label] = int(raw[1].replace(",", ""))
                    except ValueError:
                        pass
    return "\n".join(keep).strip(), counts


def main(force_email: bool) -> int:
    code, output = _run_prepare()
    diff = _latest_diff()

    if code != 0 or diff is None:
        send_alert_email(
            "[chatbot] ETL watch FAILED",
            "The weekly website re-crawl did not complete, so the corpus is "
            "still serving whatever it served before.\n\n"
            f"exit code: {code}\n\n{output[-4000:]}",
        )
        logger.error("prepare failed with %s", code)
        return 1

    summary, counts = _summary_block(diff)
    new = next((v for k, v in counts.items() if k.startswith("New or")), 0)
    gone = next((v for k, v in counts.items() if k.startswith("No longer")), 0)

    if not force_email and new < _NOTABLE_CHANGE and gone < _NOTABLE_CHANGE:
        logger.info("website unchanged (new=%s gone=%s) -- no email", new, gone)
        return 0

    body = (
        f"The website re-crawl found changes the search index does not have "
        f"yet.\n\n"
        f"{summary}\n\n"
        f"NOTHING HAS BEEN INDEXED. This was a dry run. To apply it, a "
        f"librarian signs the approval file and the operator runs the apply "
        f"phase:\n\n"
        f"  diff:     {diff}\n"
        f"  approval: {diff.with_suffix('.approval')}\n\n"
        f"  cd /opt/chatbot/ai-core\n"
        f"  .venv/bin/python -m scripts.etl.run_etl --phase apply "
        f"--diff {diff.name}\n\n"
        f"If the numbers look wrong -- a whole section vanishing, or "
        f"thousands of chunks moving at once -- do not sign. That usually "
        f"means the site changed shape, not content, and re-indexing it "
        f"would degrade answers.\n\n"
        f"See docs/07-DATA-SOURCES.md and scripts/etl/FIRST_RUN.md.\n"
    )
    ok = send_alert_email(f"[chatbot] website changed: {new} new, {gone} stale",
                          body)
    logger.info("emailed=%s new=%s gone=%s", ok, new, gone)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-email", action="store_true",
                    help="send even when nothing changed (tests the pipe)")
    sys.exit(main(ap.parse_args().force_email))
