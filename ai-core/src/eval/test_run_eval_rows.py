"""The per-case row must carry everything needed to audit a run afterwards.

Recording only the citation COUNT made citation correctness uncheckable after
the fact: of 234 cases on 2026-08-04, 36 happened to carry a bare URL in the
answer text and the other 198 could only be judged by the judge's own
subjective `citation_validity` field. A run's per-case data is the one place
you can go back to.

There are TWO places a new field has to be added -- the dataclass and
_result_row, which deliberately lists columns explicitly so the incremental
writer and the final dump can never drift. Adding it in one place only is the
mistake this file exists to catch; I made it.
"""
from __future__ import annotations

from src.eval.run_eval import EvalResult, _result_row


def _blank(**kw):
    """EvalResult with the required scope fields filled in."""
    base = dict(question_id="q", category="service", scope_match=True,
                actual_scope_campus="oxford", actual_scope_library=None)
    base.update(kw)
    return EvalResult(**base)


def test_citation_urls_reach_the_row():
    r = _blank(question_id="q1")
    r.bot_citations_count = 2
    r.bot_citation_urls = ["https://a.invalid/x", "https://b.invalid/y"]
    row = _result_row(r)
    assert row["bot_citations_count"] == 2
    assert row["bot_citation_urls"] == ["https://a.invalid/x", "https://b.invalid/y"]


def test_a_row_with_no_citations_is_explicit_about_it():
    r = _blank(question_id="q2", category="out_of_scope")
    row = _result_row(r)
    assert "bot_citation_urls" in row, "the key must always be present"
    assert row["bot_citation_urls"] is None


def test_every_declared_bot_field_is_serialised():
    """Guards the drift the docstring on _result_row promises to prevent: a
    field added to the dataclass but not to the row writer is invisible in the
    output and nobody notices until they need it."""
    r = _blank(question_id="q3")
    row = _result_row(r)
    missing = [f for f in vars(r) if f.startswith("bot_") and f not in row]
    assert not missing, f"declared but never written: {missing}"
