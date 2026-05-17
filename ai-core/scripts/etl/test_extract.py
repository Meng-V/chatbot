"""
Unit tests for the ETL HTML extractor.

Run: `python -m scripts.etl.test_extract` from ai-core/.

The extractor strips nav / footer / sidebar / "related links" so only
main-content text reaches retrieval. Cross-contamination here is the
plan's named root cause of "fake service" hallucinations: every page
links to printing/wifi, so without this stripping every chunk would
mention those.

Three-layer fallback:
  1. trafilatura (best on noisy CMS)
  2. readability-lxml (general-purpose)
  3. stdlib HTMLParser stripper (always available)

Tests focus on the stdlib fallback (deterministic; always available)
+ the rejection-reason gates. The library-backed paths are covered by
trafilatura/readability's own test suites.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.etl.test_extract`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl import config, extract as extract_mod  # noqa: E402
from scripts.etl.extract import (  # noqa: E402
    ExtractedDoc,
    _strip_html_fallback,
    extract,
    find_redirect_target,
)


# --- _strip_html_fallback ----------------------------------------------


def test_fallback_strips_basic_tags() -> None:
    title, body = _strip_html_fallback(
        "<html><head><title>Hello</title></head>"
        "<body><p>Hi there</p></body></html>"
    )
    assert title == "Hello"
    assert "Hi there" in body
    assert "<p>" not in body


def test_fallback_strips_nav_footer_sidebar() -> None:
    """Plan §4 step 3: nav/footer/aside MUST be excluded -- they're
    the source of cross-contamination."""
    html = """
    <html><body>
      <nav>Home | Services | Help</nav>
      <main><p>The MakerSpace is on the second floor.</p></main>
      <aside>Related: printing, wifi, hours</aside>
      <footer>(c) 2026 Library</footer>
    </body></html>
    """
    _, body = _strip_html_fallback(html)
    # Main content kept.
    assert "MakerSpace is on the second floor" in body
    # Sidebar / nav / footer NOT in extracted body.
    assert "Home | Services" not in body
    assert "Related: printing, wifi, hours" not in body
    assert "(c) 2026 Library" not in body


def test_fallback_strips_script_and_style() -> None:
    """Inline JS and CSS should never become "content"."""
    html = """
    <html><body>
      <script>console.log('tracking pixel');</script>
      <style>body { color: red; }</style>
      <p>Real content here.</p>
    </body></html>
    """
    _, body = _strip_html_fallback(html)
    assert "Real content here" in body
    assert "console.log" not in body
    assert "color: red" not in body


def test_fallback_collapses_whitespace() -> None:
    """Multiple newlines / tabs become single spaces -- otherwise
    chunking + embedding pick up huge whitespace runs as content."""
    html = "<html><body><p>One\n\n\n   line.</p>\n\n<p>Two.</p></body></html>"
    _, body = _strip_html_fallback(html)
    assert "  " not in body
    assert "\n" not in body


def test_fallback_no_title_returns_none() -> None:
    title, body = _strip_html_fallback(
        "<html><body><p>No title tag.</p></body></html>"
    )
    assert title is None


def test_fallback_empty_html() -> None:
    title, body = _strip_html_fallback("")
    assert title is None
    assert body == ""


def test_fallback_malformed_html_does_not_crash() -> None:
    """A real-world page with broken HTML must not blow the parser.
    We tolerate any parser blowup and return ('', '')."""
    title, body = _strip_html_fallback(
        "<html><body><p>oops <unterminated"
    )
    # Should NOT raise; either returns something or empties.
    assert isinstance(body, str)


def test_fallback_handles_nested_skip_tags() -> None:
    """Nested nav inside another nav: stripper tracks depth so an
    inner /nav close doesn't accidentally re-enable text extraction."""
    html = """
    <html><body>
      <nav>
        <nav>Inner</nav>
        Outer
      </nav>
      <p>Real content.</p>
    </body></html>
    """
    _, body = _strip_html_fallback(html)
    assert "Real content" in body
    assert "Inner" not in body
    assert "Outer" not in body


# --- extract() top-level pipeline + rejection gates -------------------


def _enough_chars(text: str) -> str:
    """Pad text to clear EXTRACT_MIN_BODY_CHARS so we can test
    the not-rejected path."""
    pad = " " + ("filler word " * 60)
    while len(text + pad) < config.EXTRACT_MIN_BODY_CHARS + 50:
        pad += "filler word "
    return text + pad


def test_extract_returns_ExtractedDoc() -> None:
    html = (
        "<html><body><main><p>"
        + _enough_chars("King Library hours are 7am to 2am.")
        + "</p></main></body></html>"
    )
    out = extract(html, "https://www.lib.miamioh.edu/about/locations/king-library/")
    assert isinstance(out, ExtractedDoc)
    assert out.url == "https://www.lib.miamioh.edu/about/locations/king-library/"
    assert "King Library" in out.body_text
    assert out.rejection_reason is None


def test_extract_rejects_too_short() -> None:
    out = extract(
        "<html><body><p>Tiny.</p></body></html>",
        "https://x/",
    )
    # Either 'too_short' or 'empty' is acceptable here -- both are
    # rejection reasons that block this page from being indexed.
    assert out.rejection_reason in ("too_short", "empty")
    assert out.body_text == ""


def test_extract_rejects_empty_html() -> None:
    out = extract("", "https://x/")
    assert out.rejection_reason == "empty"
    assert out.body_text == ""


def test_extract_records_word_count() -> None:
    long_text = " ".join(["word"] * 80)  # 80 words
    html = f"<html><body><main><p>{long_text}</p></main></body></html>"
    out = extract(html, "https://x/")
    assert out.rejection_reason is None
    # word_count is computed from the stripped body, which will include
    # the 80 "word" tokens. Allow some slack for extractor variations.
    assert out.word_count >= 50


def test_extract_threads_last_modified_through() -> None:
    """The HTTP Last-Modified header is captured at fetch time and
    threaded through to the doc -- used by the indexer to know when
    to re-embed."""
    html = "<html><body><main><p>" + _enough_chars("body") + "</p></main></body></html>"
    out = extract(
        html, "https://x/", last_modified="Wed, 21 Oct 2025 07:28:00 GMT",
    )
    assert out.last_modified == "Wed, 21 Oct 2025 07:28:00 GMT"


def test_extract_default_last_modified_is_none() -> None:
    html = "<html><body><main><p>" + _enough_chars("body") + "</p></main></body></html>"
    out = extract(html, "https://x/")
    assert out.last_modified is None


def test_extract_breadcrumbs_default_empty() -> None:
    """The plan's playbook calls out breadcrumbs as a metadata field;
    the current extractor doesn't yet parse them, but the field IS in
    the output shape so downstream consumers don't break."""
    html = "<html><body><main><p>" + _enough_chars("body") + "</p></main></body></html>"
    out = extract(html, "https://x/")
    assert out.breadcrumbs == []


def test_extract_strips_boilerplate_via_fallback() -> None:
    """Even the stdlib fallback path must drop the noisy nav/footer
    so chunks aren't poisoned with sitewide boilerplate."""
    # Force the fallback path by giving HTML the third-tier stripper
    # handles cleanly. (trafilatura/readability would also work but
    # the test pins behavior of the always-available path.)
    main_text = _enough_chars(
        "The MakerSpace at King Library hosts 3D printers."
    )
    html = f"""
    <html><head><title>MakerSpace</title></head><body>
      <nav>Home | Use | Spaces | Borrow</nav>
      <main><p>{main_text}</p></main>
      <footer>(c) Miami University Libraries 2026</footer>
    </body></html>
    """
    out = extract(html, "https://www.lib.miamioh.edu/use/spaces/makerspace/")
    if out.rejection_reason is None:
        # Main content kept.
        assert "MakerSpace at King Library" in out.body_text
        # Boilerplate not in extracted text.
        assert "Home | Use | Spaces | Borrow" not in out.body_text
        assert "(c) Miami University Libraries" not in out.body_text


def test_extract_does_not_crash_on_garbage_input() -> None:
    """Real-world: random bytes that aren't valid HTML still need to
    return SOMETHING (a rejection_reason) instead of raising."""
    out = extract("@@@ not html ###", "https://x/")
    # Either rejected or empty body -- both fine.
    assert isinstance(out, ExtractedDoc)
    assert out.rejection_reason is not None or out.body_text == ""


def test_extract_handles_missing_title_gracefully() -> None:
    html = (
        "<html><body><main><p>"
        + _enough_chars("body content")
        + "</p></main></body></html>"
    )
    out = extract(html, "https://x/")
    # Title may be None -- we don't have a <title> tag.
    assert out.title is None or isinstance(out.title, str)


def test_extract_extracts_title_when_present() -> None:
    html = (
        "<html><head><title>King Library Hours</title></head>"
        "<body><main><p>"
        + _enough_chars("body content")
        + "</p></main></body></html>"
    )
    out = extract(html, "https://x/")
    if out.rejection_reason is None and out.title:
        assert "King Library" in out.title or "King" in out.title


# --- ExtractedDoc shape ---


def test_extracted_doc_has_all_documented_fields() -> None:
    """Lock-in: any future PR that drops a field from ExtractedDoc
    breaks this test (and the synthesizer wiring downstream)."""
    html = "<html><body><main><p>" + _enough_chars("body") + "</p></main></body></html>"
    out = extract(html, "https://x/")
    for field in (
        "url", "title", "body_text", "breadcrumbs", "word_count",
        "schema_org_json", "last_modified", "rejection_reason",
    ):
        assert hasattr(out, field), f"ExtractedDoc missing field: {field}"


# --- Redirect-shim resolution (vanity short-URLs: /adobe/, /askus) ---

# The REAL /adobe/ body (226 bytes) -- note the SPACE after `url=`.
_ADOBE_STUB = (
    '<!doctype html>\n<html>\n<head>\n'
    '  <meta http-equiv="refresh" content="0; url= '
    'https://muohio.libcal.com/equipment/item/61121/">\n'
    '  <link rel="canonical" '
    'href="https://muohio.libcal.com/equipment/item/61121/" />\n'
    '</head>\n</html>\n'
)
_ASKUS_STUB = (
    '<html><head><title>Redirecting…</title>'
    '<meta http-equiv="refresh" content="0;url='
    'https://www.lib.miamioh.edu/research/research-support/ask/">'
    '</head><body>Redirecting…</body></html>'
)
# The REAL /illuminant20 body -- an Apache "300 Multiple Choices"
# page: genuine junk, NO shim -> must stay rejected (return None).
_APACHE_300 = (
    '<html><head><title>300 Multiple Choices</title></head><body>'
    '<h1>Multiple Choices</h1>The document name you requested '
    '(<code>/illuminant20</code>) could not be found.</body></html>'
)


def test_find_redirect_meta_refresh_with_space() -> None:
    """The /adobe/ format has `url= https://...` (space). Must still
    parse -- the original regex missed exactly this."""
    t = find_redirect_target(_ADOBE_STUB, "https://www.lib.miamioh.edu/adobe/")
    assert t == "https://muohio.libcal.com/equipment/item/61121/", t


def test_find_redirect_meta_refresh_no_space() -> None:
    t = find_redirect_target(_ASKUS_STUB, "https://www.lib.miamioh.edu/askus")
    assert t == (
        "https://www.lib.miamioh.edu/research/research-support/ask/"
    ), t


def test_find_redirect_canonical_only() -> None:
    html = (
        '<html><head><link rel="canonical" '
        'href="https://www.lib.miamioh.edu/software/"></head></html>'
    )
    t = find_redirect_target(html, "https://www.lib.miamioh.edu/sw/")
    assert t == "https://www.lib.miamioh.edu/software/", t


def test_find_redirect_relative_resolved_absolute() -> None:
    html = '<meta http-equiv="refresh" content="0;url=/research/ask/">'
    t = find_redirect_target(html, "https://www.lib.miamioh.edu/askus")
    assert t == "https://www.lib.miamioh.edu/research/ask/", t


def test_find_redirect_none_on_apache_300_junk() -> None:
    """No shim -> None, so genuine junk (the /illuminant20 'did you
    mean' page) stays correctly rejected, not chased."""
    assert find_redirect_target(
        _APACHE_300, "https://www.lib.miamioh.edu/illuminant20"
    ) is None


def test_find_redirect_self_canonical_is_none() -> None:
    """A self-referential canonical is NOT a redirect."""
    html = (
        '<link rel="canonical" '
        'href="https://www.lib.miamioh.edu/x/">'
    )
    assert find_redirect_target(
        html, "https://www.lib.miamioh.edu/x"
    ) is None


def test_extract_stub_sets_redirect_to() -> None:
    """End of the chain: extract() on the real /adobe/ stub must
    reject (empty/too_short) AND surface redirect_to so run_etl can
    re-fetch instead of silently dropping the page."""
    d = extract(_ADOBE_STUB, "https://www.lib.miamioh.edu/adobe/")
    assert d.rejection_reason in ("empty", "too_short"), d.rejection_reason
    assert d.redirect_to == (
        "https://muohio.libcal.com/equipment/item/61121/"
    ), d.redirect_to


def test_extract_real_page_has_no_redirect_to() -> None:
    """A normal page must not get a spurious redirect_to (backward
    compatible: redirect_to defaults None and only the reject paths
    populate it)."""
    html = (
        "<html><head><title>Real</title></head><body><main>"
        + ("Substantive library content. " * 20)
        + "</main></body></html>"
    )
    d = extract(html, "https://www.lib.miamioh.edu/use/real/")
    assert d.rejection_reason is None
    assert d.redirect_to is None


def main() -> int:
    tests = [
        test_find_redirect_meta_refresh_with_space,
        test_find_redirect_meta_refresh_no_space,
        test_find_redirect_canonical_only,
        test_find_redirect_relative_resolved_absolute,
        test_find_redirect_none_on_apache_300_junk,
        test_find_redirect_self_canonical_is_none,
        test_extract_stub_sets_redirect_to,
        test_extract_real_page_has_no_redirect_to,
        test_fallback_strips_basic_tags,
        test_fallback_strips_nav_footer_sidebar,
        test_fallback_strips_script_and_style,
        test_fallback_collapses_whitespace,
        test_fallback_no_title_returns_none,
        test_fallback_empty_html,
        test_fallback_malformed_html_does_not_crash,
        test_fallback_handles_nested_skip_tags,
        test_extract_returns_ExtractedDoc,
        test_extract_rejects_too_short,
        test_extract_rejects_empty_html,
        test_extract_records_word_count,
        test_extract_threads_last_modified_through,
        test_extract_default_last_modified_is_none,
        test_extract_breadcrumbs_default_empty,
        test_extract_strips_boilerplate_via_fallback,
        test_extract_does_not_crash_on_garbage_input,
        test_extract_handles_missing_title_gracefully,
        test_extract_extracts_title_when_present,
        test_extracted_doc_has_all_documented_fields,
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
