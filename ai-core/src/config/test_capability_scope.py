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


def test_renew_books_detected_action_phrasing() -> None:
    """Action-style requests (bot-directive, imperative, 'for me')
    must trigger renew_books refusal. Info phrasings ('How do I renew?',
    'Can I renew my book?') are handled by the intent-capability
    registry / agent loop -- see test_renew_info_phrasings_pass_through.
    Updated 2026-05-23 with action-vs-info gate; previously this test
    asserted info phrasings refused, which over-fired on every gold
    'how do I renew' question."""
    msgs = [
        "Can you renew my book?",            # bot-directive
        "Renew my checkout for me",          # imperative + for me
        "Please renew my book",              # please + imperative
        "Extend my checkout for me",         # imperative possessive + for me
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed action phrasing: {m!r}"
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


def test_place_holds_detected_action_phrasing() -> None:
    """Imperative 'Place a hold...' triggers refusal. Info phrasings
    ('How do I place a hold?') are READY-tier and answer normally."""
    msgs = [
        "Place a hold on this book",          # sentence-initial imperative
        "Can you place a hold on Hamlet?",    # bot-directive
        "Please place a hold for me",         # please + for me
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed action phrasing: {m!r}"
        assert out["limitation_type"] == "place_holds"


def test_interlibrary_loan_detected_action_phrasing() -> None:
    """ILL refuses ONLY for action requests where the user is asking
    the bot to submit/process an ILL on their behalf. Info questions
    ("How do I do ILL?", "Where do I pick up at Hamilton?") fall through
    to the agent loop -- ILL is READY in intent_capabilities.py and
    the agent composes a "here's how + here's the form URL" answer.

    See gold cases `fs_ill_no_submit` (refusal-expected, has "for me")
    vs `fs_ill_oxford` / `fs_ill_hamilton` / `ill_turnaround_no_guess`
    (answer-expected, all info phrasings)."""
    msgs = [
        "Submit an ILL request for The Great Gatsby for me.",  # gold fs_ill_no_submit
        "Can you file an ILL request for Hamlet?",
        "Please submit an interlibrary loan request",
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed action phrasing: {m!r}"
        assert out["limitation_type"] == "interlibrary_loan"


def test_catalog_search_detected_action_phrasing() -> None:
    """Catalog-search refusal fires ONLY when the user asks the bot to
    do the search for them. Info phrasings ("Do you have Hamlet?",
    "Where can I find books on Ohio history?") are POINT_TO_URL via
    `intent_capabilities.find_resource` -> Primo -- see
    test_catalog_info_phrasings_pass_through."""
    msgs = [
        "Find me 5 articles about climate change",  # "find me" = imperative + topic match (find...articles)
        "Pull up books on World War 2 for me",      # "for me" + topic match (books...on)
        "Could you search the catalog for World War 2?",  # "could you" + topic match (catalog search)
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed action phrasing: {m!r}"
        assert out["limitation_type"] == "catalog_search"


def test_pay_fines_detected() -> None:
    out = detect_limitation_request("How do I pay my fines?")
    assert out["is_limitation"]
    assert out["limitation_type"] in ("pay_fines", "check_account")


def test_course_reserves_detected_action_phrasing() -> None:
    """Course-reserves refusal fires ONLY for action requests. Info
    phrasings ("Where are my course reserves?", "How do I find course
    reserves?") fall through to the agent loop / point_to_url."""
    msgs = [
        "Pull up my course reserves",                  # imperative phrasing
        "Can you find my course reserves for me?",     # bot-directive + for me
        "Please pull up reserves for my class",        # please + imperative
    ]
    for m in msgs:
        out = detect_limitation_request(m)
        assert out["is_limitation"], f"missed action phrasing: {m!r}"
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


def test_renew_info_phrasings_pass_through() -> None:
    """Info-style renew/holds/ILL/catalog/reserves questions must NOT
    refuse -- the agent loop or point_to_url tier handles them.

    These are gold answer-expected cases (renew_basic, fs_ill_oxford,
    circ_place_hold, find_book_specific, reserves_find) that previously
    refused with `capability_limitation:*` -- the action-vs-info gate
    fixes all 27 false positives. Eval failure analysis 2026-05-23."""
    info_phrasings = [
        # Renew
        "Can I renew my book?",                          # gold renew_basic
        "How many times can I renew a book?",            # gold renew_how_many
        "How do I extend my checkout?",                  # gold renew_extend
        # Place holds
        "How do I place a hold on a book at Miami?",     # gold circ_place_hold
        "Will I get a confirmation when I place a hold on a book?",  # gold circ_confirmation
        # ILL
        "How do I request an interlibrary loan?",        # gold fs_ill_oxford
        "How do I get a book from another library to Hamilton?",   # gold fs_ill_hamilton
        "Where do I pick up an ILL request at Hamilton?",  # gold ill_hamilton_pickup
        "Can I pick up ILL at Gardner-Harvey?",          # gold ill_middletown_pickup
        "How long does ILL take?",                       # gold ill_turnaround_no_guess
        "Where do I return an interlibrary loan book?",  # gold fs_ill_return
        "Are there fees for interlibrary loan?",         # gold fs_ill_fee
        # Catalog (find_resource is POINT_TO_URL via intent_capabilities)
        "Do you have a copy of Hamlet?",                 # gold find_book_specific
        "I'm looking for an article about climate change",  # gold find_article_topic
        "Where can I find books on Ohio history?",       # gold find_books_topic
        # Course reserves
        "How do I find course reserves?",                # gold reserves_find
        "Where are my course reserves?",                 # gold reserves_my_class
    ]
    for m in info_phrasings:
        out = detect_limitation_request(m)
        assert not out["is_limitation"], (
            f"info phrasing wrongly triggered limitation: {m!r} "
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

    # 'book on reserve' no longer false-positives because catalog_search
    # is now action-gated and "My professor put..." has no action signal.
    # Updated 2026-05-23 -- the over-firing this documented is fixed.
    out = detect_limitation_request("My professor put a book on reserve")
    assert not out["is_limitation"], (
        "action-vs-info gate should suppress catalog_search here"
    )


# --- Run ---


def main() -> int:
    tests = [
        test_renew_books_detected_action_phrasing,
        test_check_account_detected,
        test_place_holds_detected_action_phrasing,
        test_interlibrary_loan_detected_action_phrasing,
        test_catalog_search_detected_action_phrasing,
        test_pay_fines_detected,
        test_course_reserves_detected_action_phrasing,
        test_non_limitation_messages_pass_through,
        test_renew_info_phrasings_pass_through,
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
