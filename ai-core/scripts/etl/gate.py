"""
Librarian approval gate for ETL runs.

The plan (Data preparation playbook §4 + §5) requires that a librarian
review the diff report before a refresh is promoted into the live
Weaviate index. This module implements the gate as a two-phase flow
backed by a simple token file -- no UI, no web hook, just a path on
disk that records "this exact diff was approved by this person".

Phases:
  1. PREPARE  -- runs discover/fetch/extract/classify/chunk/embed but
                 writes the new chunks to a SHADOW Weaviate alias
                 (Chunk_pending), then writes:
                   * data/diffs/{stamp}.md          (human-readable diff)
                   * data/diffs/{stamp}.approval    (token template)
  2. APPROVE  -- the librarian opens the .approval file, fills in their
                 email + a one-line ack, saves. (Or runs `etl approve`
                 from CLI -- see scripts/etl/approve.py.)
  3. APPLY    -- re-reads the approval token, verifies its diff_hash
                 matches the .md it claims to approve, then performs
                 the atomic alias swap (Chunk_pending -> Chunk_current).

Why hash-bind approval to the diff:
  If the librarian approves Monday's diff and the operator runs
  `apply` Wednesday after a NEW prepare ran in between, we MUST NOT
  promote the new untouched diff using Monday's approval. The hash
  check makes that impossible.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


# Approval-token format: a tiny YAML-ish key/value file. Avoid actual
# YAML to keep the dependency footprint zero -- the format only needs to
# survive being opened in a text editor.
APPROVAL_FILENAME_SUFFIX = ".approval"
APPROVAL_TEMPLATE = """\
# ETL run approval token
#
# A librarian fills in the three fields below to approve the diff
# referenced by `diff_file` for promotion into the live Weaviate index.
#
# To approve: open this file, edit the three values, save. Then the
# operator runs:  python -m scripts.etl.run_etl --phase apply
#
# Anti-tamper note: `diff_hash` below is computed from the diff file at
# prepare time. If you re-run prepare, this token becomes invalid; if
# anyone edits the diff, this token becomes invalid. Re-approve from
# the new token if that happens.

diff_file: {diff_file}
diff_hash: {diff_hash}
prepared_at: {prepared_at}

# --- librarian fills in below ---
approved_by_email:
approved_at:
ack: I have read the diff and approve promotion to the live index.
"""

_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$")


@dataclass(frozen=True)
class ApprovalToken:
    """Parsed approval-file contents.

    `is_signed` is True only if the librarian filled in email + ack.
    """

    diff_file: str
    diff_hash: str
    prepared_at: str
    approved_by_email: str
    approved_at: str
    ack: str

    @property
    def is_signed(self) -> bool:
        return bool(
            self.approved_by_email
            and "@" in self.approved_by_email
            and self.ack.strip()
        )


def hash_diff_file(diff_path: Path) -> str:
    """Stable hash of a diff report. Bound to the bytes on disk -- if
    anyone edits the diff, the hash changes and the approval invalidates.
    """
    h = hashlib.sha256()
    h.update(diff_path.read_bytes())
    return h.hexdigest()[:16]


def write_approval_template(diff_path: Path, prepared_at: dt.datetime) -> Path:
    """Write the unsigned approval template alongside the diff."""
    token_path = diff_path.with_suffix(APPROVAL_FILENAME_SUFFIX)
    diff_hash = hash_diff_file(diff_path)
    body = APPROVAL_TEMPLATE.format(
        diff_file=diff_path.name,
        diff_hash=diff_hash,
        prepared_at=prepared_at.isoformat(timespec="seconds"),
    )
    token_path.write_text(body, encoding="utf-8")
    logger.info(
        "approval template written; librarian must edit + sign before apply",
        extra={"path": str(token_path), "diff_hash": diff_hash},
    )
    return token_path


def parse_approval(token_path: Path) -> ApprovalToken:
    """Parse a `.approval` file. Tolerates `# comment` lines and blanks.

    Raises FileNotFoundError if the path doesn't exist.
    """
    text = token_path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        m = _FIELD_RE.match(line)
        if not m:
            continue
        fields[m.group(1)] = m.group(2).strip()

    return ApprovalToken(
        diff_file=fields.get("diff_file", ""),
        diff_hash=fields.get("diff_hash", ""),
        prepared_at=fields.get("prepared_at", ""),
        approved_by_email=fields.get("approved_by_email", ""),
        approved_at=fields.get("approved_at", ""),
        ack=fields.get("ack", ""),
    )


@dataclass(frozen=True)
class GateDecision:
    """Outcome of `verify_gate`. `proceed` is the only field callers
    should branch on; the others are for log + error messages."""

    proceed: bool
    reason: str
    token: Optional[ApprovalToken] = None


def verify_gate(diff_path: Path, token_path: Optional[Path] = None) -> GateDecision:
    """Check whether an ETL apply may proceed for the given diff.

    Args:
        diff_path: The .md diff produced by `prepare`.
        token_path: The .approval file. Defaults to the diff's sibling.

    Returns:
        GateDecision. `proceed=True` only if all of:
          - approval token exists at expected path
          - librarian filled in email + ack (`token.is_signed`)
          - token's `diff_hash` matches `hash_diff_file(diff_path)`
          - token's `diff_file` matches `diff_path.name`

    Any miss -> `proceed=False` with a human-readable `reason` the CLI
    surfaces verbatim.
    """
    if token_path is None:
        token_path = diff_path.with_suffix(APPROVAL_FILENAME_SUFFIX)

    if not diff_path.exists():
        return GateDecision(False, f"diff file not found: {diff_path}")
    if not token_path.exists():
        return GateDecision(
            False,
            f"approval token not found: {token_path}. "
            "Run `--phase prepare` first; a librarian must then edit the "
            "generated .approval file to sign off.",
        )

    try:
        token = parse_approval(token_path)
    except OSError as e:
        return GateDecision(False, f"approval token unreadable: {e}")

    if not token.is_signed:
        return GateDecision(
            False,
            f"approval token at {token_path} is unsigned. "
            "Librarian must fill in `approved_by_email` and confirm the `ack` line.",
            token,
        )

    if token.diff_file != diff_path.name:
        return GateDecision(
            False,
            f"approval token references diff_file={token.diff_file!r}, "
            f"but operator is applying {diff_path.name!r}. Refusing -- "
            "re-prepare and re-approve.",
            token,
        )

    expected_hash = hash_diff_file(diff_path)
    if token.diff_hash != expected_hash:
        return GateDecision(
            False,
            f"diff_hash mismatch: token has {token.diff_hash!r}, current "
            f"diff hashes to {expected_hash!r}. The diff has been edited "
            "or a newer prepare overwrote it. Refusing -- re-approve.",
            token,
        )

    return GateDecision(
        True,
        f"approved by {token.approved_by_email} at {token.approved_at or '(no timestamp set)'}",
        token,
    )


def find_latest_pending_diff() -> Optional[Path]:
    """Return the most recent .md diff that has a sibling .approval file
    but no `.applied` marker. The CLI uses this when `--diff` isn't
    explicitly passed so that `apply` Just Works for the common case.
    """
    diff_dir = Path(config.DIFF_REPORT_DIR)
    if not diff_dir.exists():
        return None
    candidates: list[Path] = []
    for md in diff_dir.glob("*.md"):
        token = md.with_suffix(APPROVAL_FILENAME_SUFFIX)
        applied = md.with_suffix(".applied")
        if token.exists() and not applied.exists():
            candidates.append(md)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def mark_applied(diff_path: Path, token: ApprovalToken, applied_at: dt.datetime) -> Path:
    """Write a `.applied` marker so a future `apply` invocation can't
    double-promote the same diff.
    """
    marker = diff_path.with_suffix(".applied")
    marker.write_text(
        f"applied_at: {applied_at.isoformat(timespec='seconds')}\n"
        f"approved_by: {token.approved_by_email}\n"
        f"diff_hash: {token.diff_hash}\n",
        encoding="utf-8",
    )
    return marker
