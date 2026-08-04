"""Stale content must be excluded at CRAWL time, not tombstoned afterwards.

Tombstoning a collection does not survive a refresh: the pages are still live
on the website, so the next crawl collects them again. Proved 2026-07-29 --
the first completed re-crawl brought back all 418 chunks that had been
tombstoned the day before (COVID-era 14, closed music library 2, dated news
398, superseded annual goals 4). Promoting that collection would have undone
the fix the operator had just announced to colleagues.
"""

import pytest

from scripts.etl.discover import _is_excluded

BASE = "https://www.lib.miamioh.edu"


@pytest.mark.parametrize("path", [
    # COVID-era guidance, superseded
    "/libraryhealthy/",
    "/libraryhealthy/virtual/",
    # the Amos Music Library closed Sept 2023
    "/about/locations/music-library/",
    # dated news archive -- a prefix cannot express a date, hence the regex
    "/2026-06-16-celebrating-the-retirement-of-stan-brown",
    "/2014-01-01-some-old-post",
    # superseded annual goal documents
    "/strategic/2021-goals",
    "/strategic/2022-goals",
    "/strategic/2024-goals",
])
def test_stale_paths_never_enter_the_corpus(path):
    excluded, why = _is_excluded(BASE + path)
    assert excluded, f"{path} should be excluded"
    assert why, "the reason must be recorded for the diff report"


@pytest.mark.parametrize("path", [
    # Curbside READS as COVID-era but the operator confirmed 2026-07-27 that
    # the service is still running. Do not "clean this up".
    "/use/borrow/curbside/",
    # a CURRENT strategic document must not be caught by the 2021/22/24 rules
    "/strategic/2026-goals",
    # the music LIBRARIAN still exists; only the building's page is gone
    "/about/organization/staff/",
    "/research/research-support/ask/",
    "/about/locations/king/",
    "/use/borrow/home-delivery/",
])
def test_current_content_is_not_swept_up(path):
    excluded, why = _is_excluded(BASE + path)
    assert not excluded, f"{path} was wrongly excluded ({why})"


def test_the_serving_denylist_and_the_crawl_filter_agree():
    """Both layers exist on purpose -- the crawl filter keeps stale pages out
    of new collections, the serving denylist protects the collection already
    in production. They must not disagree, or a page filtered by one and
    allowed by the other becomes a surprise after a promotion."""
    from src.graph.new_orchestrator import _EVIDENCE_URL_DENYLIST

    for url in _EVIDENCE_URL_DENYLIST:
        if url.rstrip("/").endswith("/20"):
            continue          # the dated-news prefix; the crawl side is a regex
        excluded, _ = _is_excluded(url)
        assert excluded, (
            f"{url} is denied at serving time but would still be crawled and "
            f"embedded -- wasted index, and a trap after a promotion")


# --- operator rule 2026-08-03: navigation + research, not a history archive ---
#
# "This is a website-navigation and research-assistance bot, not a bot for
# recording history." Each URL below was taken from the live sitemap, which is
# why they are spelled out rather than described: the dated-post regex only
# matched when the date STARTED the path, so /carousel/2026-06-15-... slipped
# through, as did a bare "/news" (the rule was "/news/").


def _excluded(path: str) -> bool:
    ok, _ = _is_excluded("https://www.lib.miamioh.edu" + path)
    return ok


def test_news_and_celebration_pieces_are_excluded():
    for path in (
        "/carousel/2026-06-15-miami-university-libraries-honors-dr-glenn-platt",
        "/carousel/2026-06-16-celebrating-the-retirement-of-stan-brown",
        "/carousel/carousel-2024-digital-humanities",
        "/carousel-preview/",
        "/library-events",
        "/news",                 # bare -- the "/news/" prefix missed this
        "/MoveInMiami/",
        "/Illuminant20",         # newsletter
        "/past-digital-exhibits-archive/",
        "/2016-10-06-staff-spotlighttiffany-dogan",
    ):
        assert _excluded(path), path


def test_covid_era_pages_and_services_are_excluded():
    for path in ("/coronavirus/", "/library-healthy/", "/libraryhealthy/"):
        assert _excluded(path), path


def test_curbside_is_NOT_treated_as_covid_dead():
    """It reads like COVID-era language ("extra personal space") and I excluded
    it on that hunch. Wrong: the page returns real content describing a current
    service, and an existing test already pinned it. Verified 200 + real body
    on 2026-08-03."""
    assert not _excluded("/use/borrow/curbside/")
    assert not _excluded("/curbside/")


def test_the_news_rule_does_not_swallow_the_newspapers_guide():
    """"/news" as a plain PREFIX also matched libguides' /newspapers research
    guide -- real content, and exactly the over-exclusion that would only
    surface when a patron asked about the NYT. Hence a boundary-anchored
    regex instead of a prefix."""
    assert _excluded("/news")
    assert _excluded("/news/")
    ok, _ = _is_excluded("https://libguides.lib.miamioh.edu/newspapers")
    assert not ok
    assert not _excluded("/Newspapers")


def test_closed_music_library_aliases_are_excluded():
    for path in ("/system/amos-music-library", "/system/music-library",
                 "/about/locations/music-library/"):
        assert _excluded(path), path


def test_internal_and_machine_facing_pages_are_excluded():
    for path in (
        "/about/usability-home/",
        "/auto-search.html",
        "/auto-search-widget.html",
        "/book-search.html",
        "/eds-request.html",
        "/assets/fonts/adelle-cufonfonts-webfont/example.html",
        "/king-posts-test/",
        "/inclusive-excellence-unpublished/",
        "/tracking/admin/",
        "/reports/youtube_tags/",
        "/user/",
    ):
        assert _excluded(path), path


def test_binary_attachments_are_excluded():
    """No PDF text extraction exists, so a .pdf was indexed as mojibake --
    19,700 of the serving index's 20,608 chunks. Operator 2026-08-03: drop
    them permanently."""
    for path in ("/assets/docs/org-chart.pdf",
                 "/sites/default/files/Signage_Proposal.pdf",
                 "/assets/docs/policy.docx", "/files/data.xlsx"):
        assert _excluded(path), path


def test_widget_only_shells_are_excluded():
    """33KB of chrome around eight LibCal <script> embeds; "7:30" and "Sunday"
    appear zero times in the HTML. Hours come from the live API instead."""
    for path in ("/about/locations/hours/", "/hours/"):
        assert _excluded(path), path


def test_the_pages_the_bot_actually_answers_from_survive():
    """The other half of the rule. Over-excluding is the failure mode that
    would be invisible until a patron asked."""
    for path in (
        "/about/organization/liaisons/",
        "/about/organization/staff/",
        "/use/spaces/room-reservations/",
        "/use/technology/printing/",
        "/use/technology/tech-checkout/",
        "/research/research-support/ask/",
        "/databases/",
        "/policies/borrowing",
        "/policies/privacy",
        "/tech/equipment-for-checkout",
        "/theses/",
        "/Newspapers",
        "/about/locations/king-library/",
        "/strategic/",            # current plan; only the dated years are out
    ):
        assert not _excluded(path), path


def test_the_bare_music_vanity_path_is_excluded():
    """/music/ meta-refreshes to the 2023 closure announcement for a library
    that no longer exists. It was not excluded, and the news story reached the
    corpus through it."""
    assert _excluded("/music/")
    assert _excluded("/2023-08-02-amos-music-library-to-close-sept-1")


def test_a_redirect_cannot_smuggle_an_excluded_page_in():
    """run_etl re-checks the TARGET of a vanity shim. Discovery checks every
    URL it finds, but a shim's destination arrives later in the pipeline, and
    it used to go straight to extract -- so an exclusion list could be bypassed
    with one redirect. This pins the rule the orchestrator now enforces."""
    for target in (
        "https://www.lib.miamioh.edu/2023-08-02-amos-music-library-to-close-sept-1",
        "https://www.lib.miamioh.edu/news/",
        "https://www.lib.miamioh.edu/carousel/2026-06-15-something",
        "https://www.lib.miamioh.edu/assets/docs/org-chart.pdf",
    ):
        ok, why = _is_excluded(target)
        assert ok, f"{target} must be excluded wherever it is reached from"
        assert why
