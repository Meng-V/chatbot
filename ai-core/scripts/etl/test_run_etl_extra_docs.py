"""The orchestrator seam for sources that arrive as finished documents.

LibAnswers FAQs do not come from the crawl -- they are fetched from an
API and handed to the pipeline already extracted and classified. They
still have to join the run early enough that chunking, the citation
allowlist and above all TOMBSTONING treat them like any other page: a
document missing from `seen_urls` is a page the tombstone step believes
has disappeared from the website, so it would be deleted on the same run
that wrote it.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

import pytest  # noqa: E402

from scripts.etl import classify, config, extract, run_etl, upsert  # noqa: E402

FAQ_URL = "https://libanswers.lib.miamioh.edu/faq/158197"


@pytest.fixture(autouse=True)
def _diffs_in_tmp(tmp_path, monkeypatch):
    """run() writes its diff report at the end; keep that out of the
    repo's data/ directory (which is root-owned on the server anyway)."""
    monkeypatch.setattr(config, "DIFF_REPORT_DIR", str(tmp_path / "diffs"))


def _doc(url=FAQ_URL, title="What can I check out?"):
    body = (title + "\n\n" + "Equipment is listed online. " * 20)
    return extract.ExtractedDoc(
        url=url, title=title, body_text=body, breadcrumbs=["Ask Us", "FAQ"],
        word_count=len(body.split()), schema_org_json=None,
        last_modified=None, rejection_reason=None,
    )


def _meta(topic="service"):
    return classify.DocMetadata(topic=topic, campus="oxford", library=None,
                                audience=["student"], featured_service=None)


class _Recorder:
    def __init__(self, extra):
        self.extra = extra
        self.tombstone_seen: set[str] = set()
        self.allowlisted: list = []
        self.upserted: list = []
        self.fetch_calls: list[str] = []

    def pipeline(self):
        def fetch(url):
            self.fetch_calls.append(url)
            return None, None, None, "should not be fetched"

        def embed(chunks):
            return [[0.0, 1.0] for _ in chunks]

        def upsert_chunks(chunks, vectors, version):
            self.upserted.extend(chunks)
            return upsert.UpsertResult(
                new_chunk_ids=[c.chunk_id for c in chunks])

        def tombstone(seen, version):
            self.tombstone_seen = set(seen)
            return upsert.UpsertResult()

        def allowlist(rows):
            self.allowlisted.extend(rows)
            return len(rows)

        return run_etl.Pipeline(
            fetch=fetch, embed=embed, upsert_chunks=upsert_chunks,
            tombstone=tombstone, update_allowlist=allowlist,
            discover_fn=lambda: [],
            extra_docs_fn=self.extra,
        )


def test_extra_documents_are_chunked_without_being_fetched():
    r = _Recorder(lambda: [(_doc(), _meta())])
    report = run_etl.run(pipeline=r.pipeline())

    assert r.fetch_calls == [], "these documents must not hit the network"
    assert report.chunks_created > 0
    assert all(c.source_url == FAQ_URL for c in r.upserted)


def test_extra_documents_survive_the_tombstone_step():
    """The failure this guards: an extra document that is not added to
    `seen_urls` looks to the tombstone step like a page that vanished
    from the site, so it is marked deleted on the very run that created
    it and never serves a single answer."""
    r = _Recorder(lambda: [(_doc(), _meta())])
    run_etl.run(pipeline=r.pipeline())
    assert FAQ_URL in r.tombstone_seen


def test_extra_documents_reach_the_citation_allowlist():
    """The answer validator rejects any URL that is not in UrlSeen, so a
    FAQ that is retrieved but not allowlisted gets its citation stripped
    and the student is told less than the bot knows."""
    r = _Recorder(lambda: [(_doc(), _meta())])
    run_etl.run(pipeline=r.pipeline())
    assert FAQ_URL in [row[0] for row in r.allowlisted]


def test_the_source_metadata_is_used_verbatim():
    """classify() infers topic from the URL path and `/faq/<id>` matches
    no prefix, so re-classifying here would relabel every FAQ as the
    "about" fallback."""
    r = _Recorder(lambda: [(_doc(), _meta(topic="technology"))])
    run_etl.run(pipeline=r.pipeline())
    assert {c.topic for c in r.upserted} == {"technology"}


def test_a_url_the_crawl_already_covered_is_not_indexed_twice():
    r = _Recorder(lambda: [(_doc(), _meta()), (_doc(), _meta())])
    run_etl.run(pipeline=r.pipeline())
    assert len({c.source_url for c in r.upserted}) == 1
    assert len([row for row in r.allowlisted if row[0] == FAQ_URL]) == 1


def test_the_faq_api_failing_does_not_take_down_the_site_crawl():
    """A FAQ outage should cost us the FAQs, not the whole corpus."""
    def boom():
        raise RuntimeError("libanswers 503")

    r = _Recorder(boom)
    report = run_etl.run(pipeline=r.pipeline())

    assert report.chunks_created == 0
    assert any("libanswers" in str(f[0]) for f in report.fetch_failures), \
        "the failure has to be visible in the diff report, not swallowed"


def test_no_extra_source_configured_is_a_normal_run():
    r = _Recorder(None)
    p = r.pipeline()
    p.extra_docs_fn = None
    report = run_etl.run(pipeline=p)
    assert report.chunks_created == 0
    assert report.fetch_failures == []
