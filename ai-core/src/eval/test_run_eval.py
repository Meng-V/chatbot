

def test_every_judge_field_reaches_the_jsonl_row():
    """A field added to the dataclass alone stays null in the file -- that
    happened with bot_citation_urls on 2026-08-04, and the count appeared while
    the URLs were empty. Assert the whole path."""
    from src.eval.run_eval import EvalResult, _result_row
    r = EvalResult(question_id="q", category="c", scope_match=True,
                   actual_scope_campus="oxford", actual_scope_library=None,
                   judge_verdict="wrong",
                   judge_reason="omits which days the space is open",
                   judge_citation_validity="all_valid",
                   model_used="gpt-5.6-terra",
                   bot_citation_urls=["https://example.edu/a"])
    row = _result_row(r)
    assert row["judge_verdict"] == "wrong"
    assert row["judge_reason"] == "omits which days the space is open"
    assert row["judge_citation_validity"] == "all_valid"
    assert row["model_used"] == "gpt-5.6-terra"
    assert row["bot_citation_urls"] == ["https://example.edu/a"]
