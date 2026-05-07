"""
Unit tests for the weekly digest-email message builders.

Run: `python -m scripts.test_digest_email` from ai-core/.

The Op 1 review loop depends on this email actually going out and
being readable. The DB and SMTP layers are gated on Prisma + the
mail relay (NotImplementedError until week 7), but the message-
building logic is pure and testable today.

A bug in the subject line ("Chatbot weekly digest -- 0 conversations
to review") that fires every Monday for librarians with nothing to
do erodes trust fast -- they'll mark it as spam and miss the real
asks. Tests pin the contract.

Tests:
  1. Subject: zero -> "nothing to review" wording (no count).
  2. Subject: singular -> "1 conversation" (no plural-s).
  3. Subject: plural -> "N conversations".
  4. Text body: zero -> no review URL, friendly nothing-to-do line.
  5. Text body: with all flag types -> bullet list of each non-zero.
  6. Text body: includes the review_queue_url when unreviewed > 0.
  7. HTML body: zero -> short message, no link.
  8. HTML body: with content -> contains the link href.
  9. HTML body: librarian name with `<` is HTML-escaped.
 10. _escape: <, >, &, " all escaped.
 11. build_digest: composes all four DigestEmail fields.
 12. Single-flag bullet list (only thumbs_down) doesn't show empty rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.test_digest_email`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.digest_email import (  # noqa: E402
    DigestEmail,
    LibrarianSummary,
    _escape,
    build_digest,
    build_html_body,
    build_subject,
    build_text_body,
)


def _summary(
    *,
    name: str = "Jane Liaison",
    email: str = "jane@miamioh.edu",
    unreviewed: int = 0,
    thumbs_down: int = 0,
    low_conf: int = 0,
    refusal: int = 0,
    review_url: str = "https://lib.miamioh.edu/admin/reviews?librarian=42",
) -> LibrarianSummary:
    return LibrarianSummary(
        librarian_id=42,
        librarian_email=email,
        librarian_name=name,
        campus="oxford",
        unreviewed_count=unreviewed,
        thumbs_down_count=thumbs_down,
        low_confidence_count=low_conf,
        refusal_count=refusal,
        review_queue_url=review_url,
    )


# --- Subject ---


def test_subject_zero_unreviewed_says_nothing_to_review() -> None:
    s = build_subject(_summary(unreviewed=0))
    assert "nothing to review" in s
    # No count appears for the zero case.
    assert "0 conversation" not in s


def test_subject_singular_no_plural_s() -> None:
    s = build_subject(_summary(unreviewed=1))
    assert "1 conversation " in s
    assert "1 conversations" not in s  # no rogue 's'


def test_subject_plural_has_s() -> None:
    s = build_subject(_summary(unreviewed=12))
    assert "12 conversations" in s


# --- Text body ---


def test_text_body_zero_omits_review_link() -> None:
    body = build_text_body(_summary(unreviewed=0))
    assert "Hi Jane Liaison," in body
    assert "No unreviewed" in body
    # No URL when nothing to review.
    assert "https://" not in body
    # Sign-off still present.
    assert "Miami University Libraries" in body


def test_text_body_includes_review_url_when_nonzero() -> None:
    url = "https://lib.miamioh.edu/admin/reviews?librarian=42"
    body = build_text_body(_summary(unreviewed=5, review_url=url))
    assert url in body
    assert "5 unreviewed" in body
    assert "5 unreviewed chatbot conversations" in body  # plural-s present


def test_text_body_singular_no_plural_s() -> None:
    body = build_text_body(_summary(unreviewed=1))
    assert "1 unreviewed chatbot conversation " in body
    assert "1 unreviewed chatbot conversations" not in body


def test_text_body_renders_all_three_flags() -> None:
    body = build_text_body(
        _summary(unreviewed=10, thumbs_down=2, low_conf=3, refusal=4)
    )
    assert "2 had user thumbs-down ratings" in body
    assert "3 were low-confidence answers" in body
    assert "4 were refusals worth spot-checking" in body


def test_text_body_skips_zero_flags() -> None:
    """Bullet list omits flags that are 0 (don't show '0 thumbs-down')."""
    body = build_text_body(
        _summary(unreviewed=10, thumbs_down=2, low_conf=0, refusal=0)
    )
    assert "thumbs-down" in body
    assert "low-confidence" not in body
    assert "refusals worth" not in body


# --- HTML body ---


def test_html_body_zero_no_link() -> None:
    html = build_html_body(_summary(unreviewed=0))
    assert "No unreviewed" in html
    assert "<a href=" not in html
    assert "Hi Jane Liaison" in html


def test_html_body_nonzero_includes_link() -> None:
    url = "https://example/admin?librarian=42"
    html = build_html_body(_summary(unreviewed=3, review_url=url))
    assert f'<a href="{url}">' in html
    assert "Review them here" in html


def test_html_body_renders_flag_bullets() -> None:
    html = build_html_body(
        _summary(unreviewed=5, thumbs_down=2, low_conf=1, refusal=0)
    )
    assert "<li>2 had user thumbs-down ratings</li>" in html
    assert "<li>1 were low-confidence answers</li>" in html
    # refusal=0 -> no <li> for it.
    assert "refusals worth" not in html


def test_html_body_no_bullets_when_no_flags() -> None:
    """unreviewed > 0 but all flags zero -> still want the link, but
    NOT an empty <ul></ul>."""
    html = build_html_body(_summary(unreviewed=2))
    assert "<ul>" not in html
    assert "Review them here" in html


def test_html_body_escapes_librarian_name() -> None:
    """A name containing < or & in the HTML must be escaped --
    otherwise injecting attribute-breakers via librarian-name input
    becomes a vector. (No real attack surface today since names come
    from Postgres, but defense in depth.)"""
    html = build_html_body(_summary(name="<script>alert(1)</script>"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_body_escapes_review_url() -> None:
    """Same defense for the URL field -- a malformed URL with `"` would
    break out of the href attribute otherwise."""
    bad_url = 'https://x.com/" onclick="alert(1)'
    html = build_html_body(_summary(unreviewed=1, review_url=bad_url))
    # Quote in the URL is escaped.
    assert '"' not in bad_url or "&quot;" in html
    assert "onclick=" in html  # the literal text appears, but as escaped text
    # The href attribute opens with " and we don't break out of it.
    assert 'href="https://x.com/&quot; onclick=&quot;alert(1)"' in html


# --- _escape ---


def test_escape_handles_each_char() -> None:
    assert _escape("a < b") == "a &lt; b"
    assert _escape("a > b") == "a &gt; b"
    assert _escape('"hello"') == "&quot;hello&quot;"
    assert _escape("Tom & Jerry") == "Tom &amp; Jerry"
    # Combined.
    assert (
        _escape('<a href="x">Tom & Jerry</a>')
        == "&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&lt;/a&gt;"
    )


def test_escape_amp_first() -> None:
    """`&` must be escaped FIRST; otherwise &lt; becomes &amp;lt;."""
    assert _escape("<") == "&lt;"
    # If the order were wrong this would be &amp;lt;.


# --- build_digest composer ---


def test_build_digest_composes_all_fields() -> None:
    summary = _summary(unreviewed=7, thumbs_down=2, email="bob@x.edu",
                       review_url="https://x/admin")
    digest = build_digest(summary)
    assert isinstance(digest, DigestEmail)
    assert digest.to_email == "bob@x.edu"
    assert "7 conversations" in digest.subject
    assert "https://x/admin" in digest.text_body
    assert 'href="https://x/admin"' in digest.html_body


def main() -> int:
    tests = [
        test_subject_zero_unreviewed_says_nothing_to_review,
        test_subject_singular_no_plural_s,
        test_subject_plural_has_s,
        test_text_body_zero_omits_review_link,
        test_text_body_includes_review_url_when_nonzero,
        test_text_body_singular_no_plural_s,
        test_text_body_renders_all_three_flags,
        test_text_body_skips_zero_flags,
        test_html_body_zero_no_link,
        test_html_body_nonzero_includes_link,
        test_html_body_renders_flag_bullets,
        test_html_body_no_bullets_when_no_flags,
        test_html_body_escapes_librarian_name,
        test_html_body_escapes_review_url,
        test_escape_handles_each_char,
        test_escape_amp_first,
        test_build_digest_composes_all_fields,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
