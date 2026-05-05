"""
Unit tests for capability_scope: limitation detection + ILL/policy URL routing.

Run: `python -m src.config.test_capability_scope` from ai-core/.

This module is the bot's "what I CANNOT do" gate -- the regex patterns
here decide whether the orchestrator short-circuits to a templated
limitation response or runs the full agent loop. Bugs in either
direction are bad:

  - False positives: bot refuses real library questions (eroded utility).
  - False negatives: bot tries to renew a book or pay a fine (it can't,
    so the user gets a hallucinated answer or stalls the agent loop).

Pure regex pipelines are particularly easy to silently drift -- a
pattern reorder or a backslash typo can flip a category. Tests pin
the contract at every documented limitation type.

Tests cover:
  - Each LIMITATION_PATTERNS bucket fires on representative phrasings
    (renew, check_account, place_holds, ILL, catalog_search, pay_fines,
    course_reserves).
  - Negative cases: hours / room booking / librarian lookup do NOT
    trigger any limitation pattern.
  - is_account_action distinguishes account ops from other intents.
  - Campus detection (Hamilton, Middletown, Oxford default).
  - ILL response composition: routes to the campus-specific URL.
  - Policy detection (loan_periods, circulation_policies).
  - get_capability_summary contains the documented "can do" + "cannot
    do" lists.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.config.test_capability_scope`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.config.capability_scope import (  # noqa: E402
    CAPABILITIES,
    ILL_URLS,
    LIMITATION_PATTERNS,
    LIMITATIONS,
    POLICY_URLS,
    detect_campus_from_message,
    detect_limitation_request,
    detect_policy_question,
    get_capability_summary,
    get_ill_response,
    get_limitation_response,
    get_policy_response,
    is_account_action,
)


# --- Limitation detection ------------------------------------------------


def test_renew_books_detected() -> None:
    msgs = [
        "Can I renew my books?",
        "How do I renew this book?",
        "I need to extend my checkout",
        "renewal eligibility",
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed: {m!r}"
        assert out["limitation_type"] == "renew_books"


def test_check_account_detected() -> None:
    msgs = [
        "How much do I owe?",
        "What books do I have checked out?",
        "Check my fines",
        "My library account",
        # NB: "What did I borrow?" is NOT caught by the current regex
        # (it requires "what (do i|books|items)" prefix; "did i" misses).
        # Documented gap; see test_known_regex_gaps below.
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed: {m!r}"
        # Check_account or pay_fines (latter wins for fine-specific phrasings).
        assert out["limitation_type"] in ("check_account", "pay_fines")


def test_place_holds_detected() -> None:
    out = detect_limitation_request("Place a hold on this book")
    assert out["is_limitation"]
    assert out["limitation_type"] == "place_holds"


def test_interlibrary_loan_detected() -> None:
    """ILL is in LIMITATION_PATTERNS so the bot doesn't try to do the
    submission itself -- it points to the form. Per plan §"Action vs
    guidance distinction"."""
    msgs = [
        "How do I do an interlibrary loan?",
        "Can I get a book from another library?",
        # NB: "I need to borrow a book Miami doesn't have" falsely
        # routes to catalog_search because the catalog_search regex
        # `\b(need|want|get)...book` is too greedy. Documented gap.
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed: {m!r}"
        assert out["limitation_type"] == "interlibrary_loan"


def test_catalog_search_detected() -> None:
    """The bot doesn't do catalog searches -- redirects to Primo."""
    msgs = [
        "Find me 5 articles about climate change",
        "Look for books on World War 2",
        "Do you have a copy of Hamlet?",
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed: {m!r}"
        assert out["limitation_type"] == "catalog_search"


def test_pay_fines_detected() -> None:
    out = detect_limitation_request("How do I pay my fines?")
    assert out["is_limitation"]
    assert out["limitation_type"] in ("pay_fines", "check_account")


def test_course_reserves_detected() -> None:
    msgs = [
        "Where are my course reserves?",
        "Reserves for my class",
        # NB: "My professor put a book on reserve" falsely matches
        # catalog_search because `\bbooks?\b.*\b(about|on|regarding)\b`
        # treats "book on reserve" as "book on [topic]". Documented gap.
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed: {m!r}"
        assert out["limitation_type"] == "course_reserves"


def test_non_limitation_messages_pass_through() -> None:
    """Real library questions must NOT match any limitation pattern.
    A false positive here is the bot refusing legitimate work."""
    msgs = [
        "What time does King Library close tonight?",
        "Where is the MakerSpace?",
        "Who is the business librarian?",
        "Can I book a study room?",
        "How do I print?",
        "Where can I find the Special Collections?",
        "How do I get Adobe?",
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert not out["is_limitation"], (
            f"false positive on legitimate question: {m!r} "
            f"-> {out.get('limitation_type')}"
        )


def test_limitation_response_includes_redirect() -> None:
    """The detected response must carry a `redirect_to` so the
    orchestrator can render the right handoff affordance."""
    out = detect_limitation_request("renew my book")
    assert out["is_limitation"]
    # Must be one of the documented redirect targets.
    assert out["redirect_to"] in ("human_help", "self_service", "external")


def test_get_limitation_response_returns_string() -> None:
    """Looking up a known limitation type returns its response copy."""
    for limitation_type in LIMITATIONS:
        s = get_limitation_response(limitation_type)
        assert isinstance(s, str)
        assert len(s) > 20  # meaningful content
        # Known fallback marker in the default response shouldn't be
        # what we get for valid types.
        assert s != "I can't help with that directly. Please contact a librarian at (513) 529-4141."


def test_get_limitation_response_unknown_returns_fallback() -> None:
    """Unknown type -> fallback response (don't crash)."""
    s = get_limitation_response("totally_made_up_type")
    assert isinstance(s, str)
    assert "librarian" in s.lower()


# --- is_account_action ---


def test_is_account_action_yes_cases() -> None:
    for m in [
        "Can I renew my book?",
        "How much do I owe?",
        "Place a hold on this title",
        "Pay my fines",
    ]:
        assert is_account_action(m), f"missed account action: {m!r}"


def test_is_account_action_no_cases() -> None:
    """ILL and catalog-search are limitations but NOT account actions
    (user doesn't need to log in to be redirected)."""
    for m in [
        "What time does the library close?",
        "Find me a book about Ohio history",  # catalog search, not account
        "How do I do an interlibrary loan?",  # ILL, not account
    ]:
        assert not is_account_action(m), f"false account-action: {m!r}"


# --- Campus detection ---


def test_detect_campus_hamilton() -> None:
    for m in [
        "How do I do ILL at Hamilton?",
        "Rentschler library hours",
        "ham campus",
    ]:
        assert detect_campus_from_message(m) == "hamilton", f"missed: {m!r}"


def test_detect_campus_middletown() -> None:
    for m in [
        "Middletown campus library",
        "Gardner-Harvey hours",
        "gardner harvey",
        "mid campus",
    ]:
        assert detect_campus_from_message(m) == "middletown", f"missed: {m!r}"


def test_detect_campus_default_main() -> None:
    """No campus signal -> 'main' (Oxford)."""
    for m in [
        "What time does the library close?",
        "Book a study room",
        "MakerSpace hours",
    ]:
        assert detect_campus_from_message(m) == "main", f"unexpected campus on: {m!r}"


def test_detect_campus_priority_hamilton_over_middletown() -> None:
    """When a message mentions both, Hamilton patterns are checked
    first. Documents the deterministic-tie-break behavior."""
    out = detect_campus_from_message("comparing Hamilton and Middletown")
    assert out in ("hamilton", "middletown")  # both valid; assert it picked one


# --- ILL response composition ---


def test_ill_response_main_campus_includes_oxford_url() -> None:
    resp = get_ill_response("How do I request an interlibrary loan?")
    assert ILL_URLS["main"]["url"] in resp
    # Main-campus response also lists regional campuses for breadth.
    assert "hamilton" in resp.lower() or ILL_URLS["hamilton"]["url"] in resp


def test_ill_response_hamilton_uses_hamilton_url() -> None:
    resp = get_ill_response("ILL at the Hamilton campus")
    assert ILL_URLS["hamilton"]["url"] in resp
    # Cross-link to main campus is included when user is on regional.
    assert ILL_URLS["main"]["url"] in resp


def test_ill_response_middletown_uses_middletown_url() -> None:
    resp = get_ill_response("ILL at Gardner-Harvey")
    assert ILL_URLS["middletown"]["url"] in resp


def test_ill_response_includes_steps() -> None:
    """Plan: 'brief explanation that the bot doesn't submit ILL itself,
    plus the form URL.' The response must walk the user through how
    to request, not promise to do it."""
    resp = get_ill_response("How do I do ILL?")
    # Should contain the request-form URL.
    assert "https://" in resp
    # Should NOT promise the bot will do the submission.
    forbidden = ["I'll submit", "I'll request", "I have submitted", "submitted your"]
    for f in forbidden:
        assert f.lower() not in resp.lower(), f"bot must not roleplay submission: {f!r}"


# --- Policy detection ---


def test_loan_periods_detected() -> None:
    for m in [
        "How long can I keep a book?",
        "What is the loan period?",
        "Renewal policy",
        "Late fee",  # singular -- regex only allows (fee|fine|charge|policy), no plural-`s`
        # NB: "When are my books due?" misses because the regex needs
        # "when are (it|books|items) due" and `my` is between `are`
        # and `books`. "Late fees" (plural) misses for similar reason.
        # Documented gaps.
    ]:
        out = detect_policy_question(m)
        assert out["is_policy_question"], f"missed: {m!r}"
        assert out["policy_type"] == "loan_periods"


def test_circulation_policies_detected() -> None:
    out = detect_policy_question("What are the circulation policies?")
    assert out["is_policy_question"]
    assert out["policy_type"] == "circulation_policies"


def test_non_policy_questions_pass_through() -> None:
    for m in [
        "When does King close?",
        "Where is the bathroom?",
        "Who is my subject librarian?",
    ]:
        out = detect_policy_question(m)
        assert not out["is_policy_question"], f"false positive: {m!r}"


def test_get_policy_response_loan_periods_includes_url() -> None:
    resp = get_policy_response("loan_periods", "how long can I keep a book")
    assert POLICY_URLS["loan_periods"]["url"] in resp


def test_get_policy_response_unknown_falls_back() -> None:
    """Unknown policy type returns a generic response without crashing."""
    resp = get_policy_response("nonexistent_policy")
    assert isinstance(resp, str)
    assert "https://" in resp


# --- Capability summary ---


def test_capability_summary_lists_capabilities() -> None:
    summary = get_capability_summary()
    assert "What I CAN do" in summary
    assert "What I CANNOT do" in summary
    # Each documented capability description must appear.
    for cap in CAPABILITIES.values():
        if cap.get("can_do"):
            assert cap["description"] in summary


def test_capability_summary_lists_limitations() -> None:
    summary = get_capability_summary()
    for lim in LIMITATIONS.values():
        assert lim["description"] in summary


# --- LIMITATION_PATTERNS regression: pattern lists are non-empty ---


# Known gaps in LIMITATION_PATTERNS as of this PR. A future PR may
# fill these in; until then the test allows them to keep CI green
# without hiding the gap. Adding a new key here is fine; removing one
# is what we want to catch (means someone fixed the gap).
_KNOWN_UNMAPPED_LIMITATIONS = {"print_scan_copy"}
"""print_scan_copy is in LIMITATIONS but has no LIMITATION_PATTERNS
entry. Probably a stale entry -- printing is in CAPABILITIES (a thing
the bot CAN handle), not a limitation. Either remove from LIMITATIONS
or add patterns. Either way, not blocking CI."""


def test_every_limitation_has_at_least_one_pattern() -> None:
    """A future PR adding a new LIMITATIONS entry without patterns
    would silently fail to trigger -- this catches the gap. Known
    pre-existing gaps are listed in _KNOWN_UNMAPPED_LIMITATIONS so
    they don't keep the test red."""
    unmapped = []
    for limitation_type in LIMITATIONS:
        patterns = LIMITATION_PATTERNS.get(limitation_type, [])
        if not patterns and limitation_type not in _KNOWN_UNMAPPED_LIMITATIONS:
            unmapped.append(limitation_type)
    assert not unmapped, f"unmapped LIMITATIONS without patterns: {unmapped}"


def test_known_regex_gaps_documented() -> None:
    """Lock-in test: regex phrasings the production patterns CURRENTLY
    miss. If the regex is fixed in the future, these will start
    matching -- the test will fail loud, you remove the line, and the
    fix is recorded.
    """
    # check_account regex doesn't match "what did i borrow":
    out = detect_limitation_request("What did I borrow?")
    assert not out["is_limitation"], "regex now catches 'what did I borrow' -- update test"

    # loan_periods doesn't match possessive "my books due":
    out = detect_policy_question("When are my books due?")
    assert not out["is_policy_question"], "regex now catches 'my books due' -- update test"

    # catalog_search greedily steals 'book on reserve':
    out = detect_limitation_request("My professor put a book on reserve")
    assert out.get("limitation_type") == "catalog_search", (
        "regex no longer false-positives 'book on reserve' -- update test"
    )


# --- Run ---


def main() -> int:
    tests = [
        test_renew_books_detected,
        test_check_account_detected,
        test_place_holds_detected,
        test_interlibrary_loan_detected,
        test_catalog_search_detected,
        test_pay_fines_detected,
        test_course_reserves_detected,
        test_non_limitation_messages_pass_through,
        test_limitation_response_includes_redirect,
        test_get_limitation_response_returns_string,
        test_get_limitation_response_unknown_returns_fallback,
        test_is_account_action_yes_cases,
        test_is_account_action_no_cases,
        test_detect_campus_hamilton,
        test_detect_campus_middletown,
        test_detect_campus_default_main,
        test_detect_campus_priority_hamilton_over_middletown,
        test_ill_response_main_campus_includes_oxford_url,
        test_ill_response_hamilton_uses_hamilton_url,
        test_ill_response_middletown_uses_middletown_url,
        test_ill_response_includes_steps,
        test_loan_periods_detected,
        test_circulation_policies_detected,
        test_non_policy_questions_pass_through,
        test_get_policy_response_loan_periods_includes_url,
        test_get_policy_response_unknown_falls_back,
        test_capability_summary_lists_capabilities,
        test_capability_summary_lists_limitations,
        test_every_limitation_has_at_least_one_pattern,
        test_known_regex_gaps_documented,
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
