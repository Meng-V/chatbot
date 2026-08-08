"""Tests for the LibAnswers FAQ source.

No network: every test injects the HTTP callables.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

import pytest  # noqa: E402

from scripts.etl import libanswers  # noqa: E402


def _resp(status=200, payload=None):
    return SimpleNamespace(status_code=status, json=lambda: payload or {})


def _faq(fid=1, q="How do I print?", a="<p>Use the printers.</p>", **kw):
    base = {
        "faqid": fid,
        "question": q,
        "answer": a,
        "url": {"public": f"https://libanswers.lib.miamioh.edu/faq/{fid}",
                "admin": f"https://libanswers.lib.miamioh.edu/admin/faq?faqid={fid}"},
        "topics": [],
        "updated": "2026-06-24 09:00:00",
    }
    base.update(kw)
    return base


# --- html_to_text -----------------------------------------------------------


def test_a_link_keeps_its_destination():
    """125 of the 170 anchors in these answers have a prose label. Strip
    the tag naively and the answer says "renew your books here" with no
    "here" to go to."""
    out = libanswers.html_to_text(
        '<p>You can <a href="https://x.example/renew">renew online</a>.</p>')
    assert "renew online (https://x.example/renew)" in out


def test_a_link_whose_label_is_already_the_url_is_not_doubled():
    out = libanswers.html_to_text(
        '<a href="https://x.example/a">https://x.example/a</a>')
    assert out == "https://x.example/a"


def test_mailto_and_anchor_links_keep_only_their_label():
    assert libanswers.html_to_text(
        '<a href="mailto:a@b.edu">email us</a>') == "email us"
    assert libanswers.html_to_text('<a href="#top">back</a>') == "back"


def test_list_items_do_not_run_together():
    """A list of loan periods flattened into one line is a line the
    chunker then has to cut blind."""
    out = libanswers.html_to_text(
        "<ul><li>Laptops: 3 hours</li><li>Calculators: 24 hours</li></ul>")
    assert out == "Laptops: 3 hours\nCalculators: 24 hours"


def test_entities_and_nbsp_are_resolved():
    out = libanswers.html_to_text("<p>Mon&nbsp;&amp;&nbsp;Tue</p>")
    assert out == "Mon & Tue"


def test_script_and_style_are_dropped():
    out = libanswers.html_to_text(
        "<style>p{color:red}</style><p>hi</p><script>x=1</script>")
    assert out == "hi"


# --- documents --------------------------------------------------------------


def test_the_question_is_in_the_body_not_only_the_title():
    """Students phrase the query the way the FAQ phrases the question, so
    it is the strongest thing in the chunk to match on -- a title the
    chunker does not carry into the text would waste it."""
    doc = libanswers.to_document(_faq(q="How do I print?"))
    assert doc.title == "How do I print?"
    assert doc.body_text.startswith("How do I print?")
    assert "Use the printers." in doc.body_text


def test_only_the_public_url_is_ever_indexed():
    doc = libanswers.to_document(_faq(fid=42))
    assert doc.url == "https://libanswers.lib.miamioh.edu/faq/42"
    assert "admin" not in doc.url


def test_a_missing_url_block_falls_back_to_the_faq_id():
    doc = libanswers.to_document(_faq(fid=7, url=None))
    assert doc.url == "https://libanswers.lib.miamioh.edu/faq/7"


def test_an_answerless_faq_is_dropped():
    assert libanswers.to_document(_faq(a="")) is None
    assert libanswers.to_document(_faq(q="", a="text")) is None


def test_a_short_but_complete_answer_survives():
    """26 of the 116 FAQs are under the 200-character floor extract()
    applies to scraped pages. That floor detects page chrome; it has no
    business rejecting a librarian's one-sentence answer."""
    doc = libanswers.to_document(
        _faq(q="Can I bring food in?", a="<p>Yes, covered drinks and snacks.</p>"))
    assert doc is not None
    assert len(doc.body_text) < 200


def test_topics_map_onto_the_corpus_vocabulary():
    assert libanswers.topic_for(_faq(topics=[{"name": "Circulation"}])) == "borrow"
    assert libanswers.topic_for(_faq(topics=[{"name": "Printing"}])) == "technology"
    # unmapped or absent -> a FAQ is a question about using the library
    assert libanswers.topic_for(_faq(topics=[{"name": "Nonsense"}])) == "service"
    assert libanswers.topic_for(_faq()) == "service"


def test_to_classified_pairs_each_doc_with_its_metadata():
    pairs = libanswers.to_classified(
        [_faq(fid=1, topics=[{"name": "Printing"}]), _faq(fid=2, a="")])
    assert len(pairs) == 1, "the answerless FAQ is dropped"
    doc, meta = pairs[0]
    assert meta.topic == "technology"
    assert meta.campus == "oxford"
    assert doc.url.endswith("/faq/1")


# --- pagination -------------------------------------------------------------


def test_pagination_does_not_stop_at_the_first_short_page():
    """The API caps a page at 20 however large a `limit` we ask for. A
    `len(page) < limit` stop condition therefore ends after page 1 and
    silently indexes 20 of 116 FAQs -- which is exactly the bug the first
    version of this had."""
    pages = {1: [_faq(fid=i) for i in range(20)],
             2: [_faq(fid=100 + i) for i in range(16)],
             3: []}
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params["page"])
        return _resp(200, {"faqs": pages.get(params["page"], [])})

    faqs = libanswers.fetch_faqs(get=fake_get, token="t")
    assert len(faqs) == 36
    assert calls == [1, 2, 3]


def test_pagination_stops_when_a_page_repeats_itself():
    """Guards against an API that ignores `page` and serves page 1
    forever -- without this the loop runs to _MAX_PAGES every time."""
    def fake_get(url, headers=None, params=None, timeout=None):
        return _resp(200, {"faqs": [_faq(fid=1), _faq(fid=2)]})

    assert len(libanswers.fetch_faqs(get=fake_get, token="t")) == 2


def test_an_api_error_is_raised_not_silently_empty():
    def fake_get(url, headers=None, params=None, timeout=None):
        return _resp(500, {})

    with pytest.raises(libanswers.LibAnswersError):
        libanswers.fetch_faqs(get=fake_get, token="t")


def test_a_token_refusal_is_raised(monkeypatch):
    monkeypatch.setenv("LIBANS_OAUTH_URL", "https://x.example/oauth/token")
    with pytest.raises(libanswers.LibAnswersError):
        libanswers.get_token(post=lambda *a, **k: _resp(401, {}))


def test_api_base_is_derived_from_the_oauth_url(monkeypatch):
    monkeypatch.setenv(
        "LIBANS_OAUTH_URL",
        "https://libanswers.lib.miamioh.edu/api/1.1/oauth/token")
    assert libanswers.api_base() == "https://libanswers.lib.miamioh.edu/api/1.1"


def test_a_whole_short_faq_is_not_dropped_as_boilerplate():
    """CHUNK_MIN_TOKENS (50) exists to discard fragments left over from
    cutting up a scraped page. Applied to these it silently deleted ten
    complete answers, including what printing costs and when the library
    is open."""
    from scripts.etl import chunker

    faq = _faq(q="How much does it cost to print in the Libraries?",
               a="<p>$0.10/page for B&amp;W and $0.25/page for Color.</p>")
    doc = libanswers.to_document(faq)
    assert doc.min_chunk_tokens == 0

    chunks = chunker.chunk_document(doc, libanswers.to_classified([faq])[0][1])
    assert len(chunks) == 1
    assert "$0.10" in chunks[0].text and "$0.25" in chunks[0].text


def test_the_boilerplate_floor_still_applies_to_crawled_pages():
    """The override is per-document; nothing about the crawl changes."""
    from scripts.etl import chunker, classify, config, extract

    scraped = extract.ExtractedDoc(
        url="https://www.lib.miamioh.edu/x", title="x", body_text="Home About",
        breadcrumbs=[], word_count=2, schema_org_json=None,
        last_modified=None, rejection_reason=None,
    )
    assert scraped.min_chunk_tokens is None
    assert config.CHUNK_MIN_TOKENS == 50
    assert chunker.chunk_document(scraped, classify.DocMetadata(
        topic="about", campus="oxford", library=None, audience=[],
        featured_service=None)) == []
