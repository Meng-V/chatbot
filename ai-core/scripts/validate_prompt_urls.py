#!/usr/bin/env python3
"""Validate every hard-coded URL in the prompt/source files actually resolves.

Why this exists
---------------
The synthesizer prompt (and a few other source files) carry a hard-coded
"stable reference" list of library URLs. Those URLs ROT: a page moves,
the path 404s, and the model -- which treats the list as authoritative --
keeps emitting the dead link. On 2026-06-08 a user hit a 404 Adobe URL
(`/use/technology/software/adobe/`) the bot served confidently. Three dead
URLs were found in `synthesizer_v1.py` alone.

This script is the guard: it extracts every URL from the scanned files,
HTTP-checks each (follow redirects), and exits non-zero if any is not 200.
Run it pre-deploy and on a cron so a rotted URL is caught by CI, not by an
angry user.

Usage
-----
    python scripts/validate_prompt_urls.py
    python scripts/validate_prompt_urls.py --files src/prompts/synthesizer_v1.py
    python scripts/validate_prompt_urls.py --timeout 15

Exit code 0 = all live; 1 = at least one dead URL (prints the offenders).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Files that carry hard-coded URLs the bot may surface. Add to this list
# when a new prompt/source file starts embedding canonical URLs.
_DEFAULT_TARGETS = [
    "src/prompts/synthesizer_v1.py",
    "src/prompts/agent_v1.py",
    "src/prompts/clarifier_v1.py",
    "src/prompts/judge_v1.py",
    "src/config/capability_scope.py",
    "src/synthesis/refusal_templates.py",
    "src/graph/new_orchestrator.py",
]

# Capture http(s) URLs; stop at whitespace, quotes, backslash, or closing
# bracket/paren so we don't grab trailing code punctuation. Then strip a
# few trailing sentence characters that still sneak in.
_URL_RE = re.compile(r"https?://[^\s\"'\\)\]}<>]+")
_TRAILERS = ".,;:"

# Reserved/placeholder domains (RFC 2606 + localhost). URLs on these are
# deliberate examples in prompts (e.g. the judge's "example.com/photoshop"
# illustration) and must NOT be flagged as dead.
_PLACEHOLDER_HOSTS = ("example.com", "example.org", "example.net", "localhost", "127.0.0.1")


def extract_urls(text: str) -> set[str]:
    out: set[str] = set()
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(_TRAILERS)
        # Skip templated placeholders (e.g. {campus}, %s, format vars).
        if "{" in url or "}" in url or "%s" in url:
            continue
        # Skip reserved placeholder domains used in examples.
        if any(("://" + h) in url or ("://www." + h) in url for h in _PLACEHOLDER_HOSTS):
            continue
        out.add(url)
    return out


def check(url: str, timeout: float) -> tuple[str, int | str]:
    """Return (url, status_code_or_error). GET (not HEAD) -- some servers
    405 a HEAD but 200 a GET; we want the user-visible result."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "smartchatbot-url-validator/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return url, resp.status
    except urllib.error.HTTPError as e:
        return url, e.code
    except Exception as e:  # noqa: BLE001 -- network/DNS/TLS all count as "dead"
        return url, f"ERR:{type(e).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", nargs="*", help="Override the default target files (paths relative to ai-core/).")
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    ai_core = Path(__file__).resolve().parents[1]  # .../ai-core
    targets = args.files or _DEFAULT_TARGETS

    # file -> set(urls)
    urls_by_file: dict[str, set[str]] = {}
    all_urls: set[str] = set()
    for rel in targets:
        p = ai_core / rel
        if not p.exists():
            print(f"⚠️  skip (missing): {rel}")
            continue
        urls = extract_urls(p.read_text(encoding="utf-8", errors="replace"))
        if urls:
            urls_by_file[rel] = urls
            all_urls |= urls

    if not all_urls:
        print("No URLs found in the scanned files.")
        return 0

    print(f"Checking {len(all_urls)} distinct URLs from {len(urls_by_file)} file(s)...\n")
    results: dict[str, int | str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for url, status in ex.map(lambda u: check(u, args.timeout), sorted(all_urls)):
            results[url] = status

    dead = {u: s for u, s in results.items() if s != 200}

    # Report, grouped by file so a maintainer knows where to edit.
    for rel, urls in sorted(urls_by_file.items()):
        bad = sorted(u for u in urls if results.get(u) != 200)
        if bad:
            print(f"❌ {rel}")
            for u in bad:
                print(f"     {results[u]}  {u}")
    if not dead:
        print(f"✅ All {len(all_urls)} URLs return 200.")
        return 0

    print(f"\n💥 {len(dead)} dead URL(s) found. Fix them before deploy.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
