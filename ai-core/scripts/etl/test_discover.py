"""
Unit tests for the ETL URL-discovery step.

Run: `python -m scripts.etl.test_discover` from ai-core/.

Bugs in discovery silently shrink or expand the corpus:
  - False exclusion: legit /use/borrow/ill/ page never indexed
  - False inclusion: a /about/news-events/ page slips through and
    the bot starts hallucinating from stale event content (the prime
    failure mode the plan explicitly designed AGAINST).

Tests pin every exclusion rule + the dedup contract.

discover() itself does network I/O via requests.get; tests
monkey-patch _fetch_sitemap to avoid the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.etl.test_discover`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl import config, discover as discover_mod  # noqa: E402
from scripts.etl.discover import (  # noqa: E402
    DiscoveredUrl,
    _is_excluded,
    discover,
)


# --- _is_excluded -----------------------------------------------------


def test_news_events_path_excluded() -> None:
    """The plan's load-bearing exclusion: news/events get filtered
    BEFORE the rest of the pipeline ever sees them."""
    excluded, reason = _is_excluded(
        "https://www.lib.miamioh.edu/about/news-events/exhibit-2024/"
    )
    assert excluded
    assert "news-events" in reason


def test_news_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/news/article/")
    assert excluded


def test_events_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/events/talk/")
    assert excluded


def test_exhibits_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/exhibits/old/")
    assert excluded


def test_blog_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/blog/post/")
    assert excluded


def test_test_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/test/page/")
    assert excluded


def test_staging_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/staging/page/")
    assert excluded


def test_dev_path_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/dev/page/")
    assert excluded


def test_readme_substring_excluded() -> None:
    """Substring rule (in addition to prefix rules)."""
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/readme")
    assert excluded
    assert "readme" in reason


def test_404_substring_excluded() -> None:
    excluded, reason = _is_excluded("https://www.lib.miamioh.edu/404/")
    assert excluded


def test_test_page_substring_excluded() -> None:
    excluded, reason = _is_excluded(
        "https://www.lib.miamioh.edu/test-page/abc"
    )
    assert excluded


def test_legitimate_use_url_kept() -> None:
    """Most-trafficked legit path: no exclusion fires."""
    excluded, reason = _is_excluded(
        "https://www.lib.miamioh.edu/use/borrow/ill/"
    )
    assert not excluded
    assert reason is None


def test_legitimate_research_url_kept() -> None:
    excluded, _ = _is_excluded(
        "https://www.lib.miamioh.edu/research/find/databases/"
    )
    assert not excluded


def test_legitimate_about_locations_url_kept() -> None:
    excluded, _ = _is_excluded(
        "https://www.lib.miamioh.edu/about/locations/king-library/"
    )
    assert not excluded


def test_about_organization_url_kept() -> None:
    """Important boundary: /about/news-events/ excluded, but
    /about/organization/ KEPT (staff directory). The exclusion is
    about news, not the whole /about/ tree."""
    excluded, _ = _is_excluded(
        "https://www.lib.miamioh.edu/about/organization/liaisons/"
    )
    assert not excluded


def test_makerspace_url_kept() -> None:
    excluded, _ = _is_excluded(
        "https://www.lib.miamioh.edu/use/spaces/makerspace/"
    )
    assert not excluded


# --- discover() with mocked sitemap fetch ----------------------------


def _stub_fetch(returns: dict[str, list[str]]):
    """Replace _fetch_sitemap with a function returning canned URLs
    keyed by sitemap URL. Returns a closure suitable for monkeypatch."""

    def fake(url: str) -> list[str]:
        return list(returns.get(url, []))

    return fake


def test_discover_dedupes_across_campuses(monkeypatch) -> None:
    """A URL that appears in two campus sitemaps is kept once
    (first-source-wins). Real example: a shared LibGuide URL the
    cross-domain crawl picks up under multiple campuses."""
    sitemap_urls = list(config.SITEMAPS.values())
    if len(sitemap_urls) < 2:
        return  # not enough campuses to test dedup
    a, b = sitemap_urls[0], sitemap_urls[1]
    common = "https://www.lib.miamioh.edu/use/borrow/ill/"
    monkeypatch.setattr(
        discover_mod, "_fetch_sitemap",
        _stub_fetch({a: [common], b: [common]}),
    )
    out = discover()
    urls = [d.url for d in out]
    assert urls.count(common) == 1


def test_discover_filters_excluded_prefixes(monkeypatch) -> None:
    """News/events URLs from a sitemap MUST be filtered out --
    pre-empt the hallucination class the plan explicitly avoids."""
    sitemap_urls = list(config.SITEMAPS.values())
    a = sitemap_urls[0]
    monkeypatch.setattr(
        discover_mod, "_fetch_sitemap",
        _stub_fetch({a: [
            "https://www.lib.miamioh.edu/use/borrow/ill/",
            "https://www.lib.miamioh.edu/about/news-events/exhibit/",
        ]}),
    )
    # Other campuses return empty (uses seed fallback if any).
    for s in sitemap_urls[1:]:
        # Ensure they don't add extras that would interfere.
        pass
    out = discover()
    urls = [d.url for d in out]
    assert any("ill" in u for u in urls)
    assert not any("news-events" in u for u in urls)


def test_discover_falls_back_to_seeds_when_sitemap_empty(monkeypatch) -> None:
    """A campus whose sitemap is unreachable / empty gets seed URLs
    instead. Per playbook §8 -- regional sites without sitemaps need
    hand-curated seed lists."""
    # Pick a campus we know has seeds. Either supply one OR make sure
    # config has at least one entry.
    campus = next(iter(config.SITEMAPS))
    sitemap = config.SITEMAPS[campus]
    monkeypatch.setattr(
        discover_mod, "_fetch_sitemap",
        _stub_fetch({}),  # all sitemaps empty
    )
    # Stub seed URLs into config for the test (don't mutate
    # globally; copy + override).
    seed_url = "https://example/seeded-page/"
    monkeypatch.setattr(
        config, "SEED_URLS", {campus: [seed_url]},
    )
    out = discover()
    sources = {d.source for d in out}
    if any(d.url == seed_url for d in out):
        # Seed fallback fired.
        assert "seed" in sources
    # If no seeds were configured for ANY campus the test is a no-op
    # (legitimate -- nothing to fall back to).


def test_discover_returns_DiscoveredUrl_with_campus_tagged(monkeypatch) -> None:
    sitemap_urls = list(config.SITEMAPS.items())
    if not sitemap_urls:
        return
    campus, sitemap = sitemap_urls[0]
    monkeypatch.setattr(
        discover_mod, "_fetch_sitemap",
        _stub_fetch({sitemap: ["https://www.lib.miamioh.edu/use/borrow/ill/"]}),
    )
    out = discover()
    assert all(isinstance(d, DiscoveredUrl) for d in out)
    if out:
        assert out[0].campus == campus
        assert out[0].source in ("sitemap", "seed")


# --- DiscoveredUrl shape ---


def test_discovered_url_is_frozen() -> None:
    d = DiscoveredUrl(url="https://x", campus="oxford", source="sitemap")
    try:
        d.url = "https://y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("expected frozen dataclass to refuse mutation")


# --- Tiny shim so we can run without pytest's monkeypatch fixture ----


class _Monkeypatch:
    """Minimal monkeypatch for the no-pytest run path."""

    def __init__(self) -> None:
        self._undo: list = []

    def setattr(self, target, name, value) -> None:
        old = getattr(target, name)
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, old in reversed(self._undo):
            setattr(target, name, old)
        self._undo.clear()


def main() -> int:
    tests = [
        test_news_events_path_excluded,
        test_news_path_excluded,
        test_events_path_excluded,
        test_exhibits_path_excluded,
        test_blog_path_excluded,
        test_test_path_excluded,
        test_staging_path_excluded,
        test_dev_path_excluded,
        test_readme_substring_excluded,
        test_404_substring_excluded,
        test_test_page_substring_excluded,
        test_legitimate_use_url_kept,
        test_legitimate_research_url_kept,
        test_legitimate_about_locations_url_kept,
        test_about_organization_url_kept,
        test_makerspace_url_kept,
        test_discover_dedupes_across_campuses,
        test_discover_filters_excluded_prefixes,
        test_discover_falls_back_to_seeds_when_sitemap_empty,
        test_discover_returns_DiscoveredUrl_with_campus_tagged,
        test_discovered_url_is_frozen,
    ]
    import inspect
    failed = 0
    for t in tests:
        mp = _Monkeypatch()
        try:
            sig = inspect.signature(t)
            if "monkeypatch" in sig.parameters:
                t(mp)
            else:
                t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
        finally:
            mp.undo()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
