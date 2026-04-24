"""
Weekly Monday-morning digest email to each subject librarian.

Send one email per active librarian summarizing unreviewed
conversations in their subject/campus area, plus any thumbs-down or
low-confidence flagged turns. A single "Click here to review" link
takes them into the admin queue.

Sustainability matters: librarians won't open a dashboard daily, but
they will click an email link on Monday. The whole Op 1 review loop
depends on this email actually going out reliably.

Run via cron: `0 8 * * 1` (Monday 8 AM local time).

Usage:
    python -m scripts.digest_email                    # full send
    python -m scripts.digest_email --dry-run          # preview only
    python -m scripts.digest_email --librarian 42     # one person

Status: SCAFFOLD. The SMTP send and the Prisma query both raise
NotImplementedError in this sandbox; the message-building logic is
pure and tested.

See plan: Operations -> Op 1 "Weekly Monday-morning digest email".
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional


logger = logging.getLogger("digest_email")


# --- Data shapes ---------------------------------------------------------


@dataclass(frozen=True)
class LibrarianSummary:
    """Aggregated review stats for one librarian over the reporting
    window. Computed from LibrarianReview + Message joins."""

    librarian_id: int
    librarian_email: str
    librarian_name: str
    campus: str
    unreviewed_count: int
    thumbs_down_count: int
    low_confidence_count: int
    refusal_count: int
    review_queue_url: str
    """Deep link into /admin/reviews filtered to this librarian."""


@dataclass(frozen=True)
class DigestEmail:
    """A rendered, ready-to-send digest message. Returned from
    `build_digest()` so the send step is just SMTP."""

    to_email: str
    subject: str
    text_body: str
    html_body: str


# --- Template builders ---------------------------------------------------


def build_subject(summary: LibrarianSummary) -> str:
    """Concrete subject line. Puts the unreviewed count up front
    because that's the signal the librarian uses to decide whether to
    open the email."""
    n = summary.unreviewed_count
    if n == 0:
        return f"Chatbot weekly digest -- nothing to review"
    return f"Chatbot weekly digest -- {n} conversation{'s' if n != 1 else ''} to review"


def build_text_body(summary: LibrarianSummary) -> str:
    """Plain-text digest body. Deliberately short -- a librarian
    scanning this on a phone should see the ask in two lines."""
    lines: list[str] = []
    lines.append(f"Hi {summary.librarian_name},")
    lines.append("")
    if summary.unreviewed_count == 0:
        lines.append(
            "No unreviewed chatbot conversations in your area this week."
        )
    else:
        lines.append(
            f"You have {summary.unreviewed_count} unreviewed chatbot "
            f"conversation{'s' if summary.unreviewed_count != 1 else ''} "
            f"in your subject/campus area."
        )
        if summary.thumbs_down_count:
            lines.append(
                f"  - {summary.thumbs_down_count} had user thumbs-down ratings"
            )
        if summary.low_confidence_count:
            lines.append(
                f"  - {summary.low_confidence_count} were low-confidence answers"
            )
        if summary.refusal_count:
            lines.append(
                f"  - {summary.refusal_count} were refusals worth spot-checking"
            )
        lines.append("")
        lines.append(f"Review them here: {summary.review_queue_url}")
    lines.append("")
    lines.append(
        "-- Miami University Libraries chatbot team\n"
        "(Reply to this email with any questions.)"
    )
    return "\n".join(lines)


def build_html_body(summary: LibrarianSummary) -> str:
    """Simple HTML digest. Mirrors the text body -- no fancy layout so
    bulk-email spam filters don't flag it and so mobile clients render
    consistently."""
    rows: list[str] = []
    if summary.unreviewed_count:
        if summary.thumbs_down_count:
            rows.append(
                f"<li>{summary.thumbs_down_count} had user thumbs-down ratings</li>"
            )
        if summary.low_confidence_count:
            rows.append(
                f"<li>{summary.low_confidence_count} were low-confidence answers</li>"
            )
        if summary.refusal_count:
            rows.append(
                f"<li>{summary.refusal_count} were refusals worth spot-checking</li>"
            )
    rows_html = f"<ul>{''.join(rows)}</ul>" if rows else ""

    body_html = (
        f"<p>Hi {_escape(summary.librarian_name)},</p>"
        + (
            f"<p>You have <b>{summary.unreviewed_count}</b> unreviewed "
            f"chatbot conversations in your subject/campus area.</p>"
            + rows_html
            + f'<p><a href="{_escape(summary.review_queue_url)}">'
            "Review them here</a></p>"
            if summary.unreviewed_count
            else "<p>No unreviewed chatbot conversations in your area this week.</p>"
        )
        + "<p>-- Miami University Libraries chatbot team</p>"
    )
    return body_html


def build_digest(summary: LibrarianSummary) -> DigestEmail:
    """Compose one digest email from a summary row."""
    return DigestEmail(
        to_email=summary.librarian_email,
        subject=build_subject(summary),
        text_body=build_text_body(summary),
        html_body=build_html_body(summary),
    )


def _escape(s: str) -> str:
    """Minimal HTML escape. No external dep."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# --- DB + SMTP gates -----------------------------------------------------


def _load_summaries(
    librarian_id: Optional[int] = None,
) -> list[LibrarianSummary]:
    """Query Postgres for each active librarian's review stats.

    Production query shape (pseudo-SQL, week 7 wiring):
      SELECT l.id, l.email, l.name, l.campus,
             count(m) FILTER (WHERE lr IS NULL)               AS unreviewed,
             count(m) FILTER (WHERE m.user_rating='down')     AS thumbs_down,
             count(m) FILTER (WHERE m.confidence='low')       AS low_conf,
             count(m) FILTER (WHERE m.was_refusal)            AS refusals
      FROM Librarian l
      LEFT JOIN librarian_subjects ls ON ls.librarian_id = l.id
      LEFT JOIN Message m ON ... (match by subject or campus)
      LEFT JOIN LibrarianReview lr ON lr.message_id = m.id
      WHERE m.created_at > now() - interval '7 days'
      GROUP BY l.id;
    """
    try:
        from prisma import Prisma  # type: ignore  # noqa: F401
    except ImportError as e:
        raise NotImplementedError(
            "Prisma client not generated. Cannot load librarian "
            "summaries in sandbox."
        ) from e
    raise NotImplementedError("DB wiring -- week 7 task")


def _send_email(email: DigestEmail) -> None:
    """SMTP send. Wired to the existing mail infra at deploy time."""
    try:
        import smtplib  # stdlib, always available  # noqa: F401
    except ImportError as e:
        raise NotImplementedError(str(e)) from e
    # TODO: real SMTP send via Miami's mail relay.
    raise NotImplementedError("SMTP wiring -- week 7 task")


# --- CLI -----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Weekly chatbot-review digest.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build digests but don't send; log preview to stderr.",
    )
    parser.add_argument(
        "--librarian",
        type=int,
        default=None,
        help="Send only to this librarian id (debug).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        summaries = _load_summaries(librarian_id=args.librarian)
    except NotImplementedError as e:
        logger.error("Cannot load summaries: %s", e)
        return 2

    sent = 0
    for summary in summaries:
        email = build_digest(summary)
        if args.dry_run:
            logger.info(
                "DRY RUN -> to=%s subject=%s",
                email.to_email,
                email.subject,
            )
            continue
        try:
            _send_email(email)
            sent += 1
        except Exception:
            logger.exception("Failed to send digest to %s", email.to_email)

    logger.info("Sent %d digests.", sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DigestEmail",
    "LibrarianSummary",
    "build_digest",
    "build_html_body",
    "build_subject",
    "build_text_body",
]
