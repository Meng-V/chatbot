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
