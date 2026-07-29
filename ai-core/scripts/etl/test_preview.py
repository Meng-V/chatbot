"""The dry-run must show what WOULD change.

Before this, `--phase prepare` skipped the upsert step wholesale, so every
diff a librarian was asked to sign reported "new: 0, changed: 0,
tombstoned: 0" no matter how far the website had moved. The gate was asking
for a signature on an invisible change (found 2026-07-29).
"""

from scripts.etl.chunker import Chunk
from scripts.etl.upsert import preview_against_live
from src.weaviate_adapters.etl_adapter import _chunk_uuid


def _chunk(chunk_id: str, content_hash: str, url: str = "https://x/1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id, document_id="d1", source_url=url, text="t",
        position=0, content_hash=content_hash, topic="general",
        campus="oxford", library=None, audience="all", featured_service=None,
    )


class FakeWeaviate:
    """Only `snapshot_hashes` -- if the preview calls anything else it is
    touching a write path and the test should fail loudly."""

    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.calls = 0

    def snapshot_hashes(self, *, collection):
        self.calls += 1
        return dict(self._snapshot)

    def __getattr__(self, name):
        raise AssertionError(f"preview must not call {name}()")


def test_classifies_new_unchanged_and_orphaned():
    live = {
        _chunk_uuid("c-keep"): "hash-keep",      # unchanged
        _chunk_uuid("c-gone"): "hash-gone",      # page no longer crawled
    }
    crawled = [
        _chunk("c-keep", "hash-keep"),           # -> unchanged
        _chunk("c-brand-new", "hash-new"),       # -> new
    ]
    wv = FakeWeaviate(live)
    res = preview_against_live(wv, crawled, {"https://x/1"},
                               live_collection="Chunk_live")

    assert res.deduped_chunk_ids == ["c-keep"]
    assert res.new_chunk_ids == ["c-brand-new"]
    assert res.orphaned_chunk_count == 1          # c-gone
    assert res.total_chunks_in_index == 2
    assert wv.calls == 1, "must be ONE bulk read, not a probe per chunk"


def test_marks_itself_as_a_preview():
    """The diff report keys its wording off this, and `apply` must never be
    handed a preview result by mistake."""
    res = preview_against_live(FakeWeaviate({}), [], set(),
                               live_collection="Chunk_live")
    assert res.weaviate_collection_version == "(preview)"


def test_edited_text_reads_as_new_plus_orphan_not_changed():
    """chunk_id is derived from (url, position, content_hash), so an edit
    produces a NEW id and orphans the old one. `changed` can therefore never
    fire -- the report says so in prose, and this pins the behaviour."""
    live = {_chunk_uuid("c-old"): "hash-v1"}
    crawled = [_chunk("c-new", "hash-v2")]        # same page, rewritten
    res = preview_against_live(FakeWeaviate(live), crawled, set(),
                               live_collection="Chunk_live")
    assert res.new_chunk_ids == ["c-new"]
    assert res.orphaned_chunk_count == 1
    assert res.changed_chunk_ids == []


def test_an_empty_live_index_makes_everything_new():
    res = preview_against_live(FakeWeaviate({}), [_chunk("c-1", "h1")], set(),
                               live_collection="Chunk_live")
    assert res.new_chunk_ids == ["c-1"]
    assert res.orphaned_chunk_count == 0


def test_a_snapshot_failure_degrades_instead_of_raising():
    """A preview must never break the run that produces the diff."""
    class Broken(FakeWeaviate):
        def snapshot_hashes(self, *, collection):
            return {}          # adapter already swallows + logs its errors
    res = preview_against_live(Broken({}), [_chunk("c-1", "h1")], set(),
                               live_collection="Chunk_live")
    assert res.new_chunk_ids == ["c-1"]


# --- the fetch cache must not outlive one run --------------------------------

def test_fetch_cache_expires(tmp_path, monkeypatch):
    """A keep-forever cache silently defeats a re-crawl.

    The second run read the first run's HTML and reported "nothing changed"
    however much the website had moved -- which would have left the weekly
    watch cron permanently blind after its first run (found 2026-07-29 by
    overwriting a cached file with a sentinel; the sentinel survived).
    """
    import hashlib
    import os

    from scripts.etl import config, run_etl

    url = "https://www.lib.miamioh.edu/probe/"
    cache_file = tmp_path / f"{hashlib.sha256(url.encode()).hexdigest()}.html"
    cache_file.write_text("STALE", encoding="utf-8")

    fetched: list[str] = []

    class FakeResp:
        status_code = 200
        text = "FRESH"
        headers: dict = {}

        def __init__(self, final_url):
            self.url = final_url

        def raise_for_status(self):
            pass

    class FakeSession:
        headers: dict = {}
        max_redirects = 5

        def get(self, u, **kw):
            fetched.append(u)
            return FakeResp(u)

    monkeypatch.setattr("requests.Session", lambda: FakeSession())

    fetch = run_etl.build_requests_fetcher(cache_dir=tmp_path)

    # fresh cache -> served from disk, no network
    body, err, _final, _lm = fetch(url)
    assert body == "STALE" and not fetched

    # aged past the TTL -> refetched
    old = os.stat(cache_file).st_mtime - config.RAW_CACHE_MAX_AGE_SECONDS - 60
    os.utime(cache_file, (old, old))
    body, err, _final, _lm = fetch(url)
    assert fetched == [url], "an expired entry must trigger a real fetch"
    assert "FRESH" in body


def test_ttl_is_shorter_than_the_weekly_cadence():
    """The cache exists to resume ONE run, not to be reused by the next.
    If this ever exceeds the cron interval the watch goes blind again."""
    from scripts.etl import config

    one_week = 7 * 24 * 60 * 60
    assert 0 < config.RAW_CACHE_MAX_AGE_SECONDS < one_week / 2
