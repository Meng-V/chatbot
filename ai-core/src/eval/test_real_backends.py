"""Unit tests for the eval's honest-baseline ToolBackends.

Run: `python -m src.eval.test_real_backends` from ai-core/.

These are OFFLINE tests -- no Postgres, no LibCal. The load-bearing
one is `test_point_to_url_urls_mirror_capability_scope`: it is the
anti-fabrication drift guard. The entire project exists to stop the
bot inventing URLs; this module must never be the thing that does.

Tests:
  1. point_to_url non-ILL URLs are all still literally present in a
     capability_scope.LIMITATIONS response (DRIFT GUARD).
  2. point_to_url ILL is campus-aware and sourced live from ILL_URLS
     (Oxford != Hamilton != Middletown).
  3. point_to_url for an unknown service returns NO url (never a guess).
  4. ONLY write/handoff tools + lookup_space stay unwired sentinels
     (get_hours / get_room_availability are now WIRED to legacy LibCal).
  5. every read-only backend is wired (none is the unwired sentinel).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.config.capability_scope import ILL_URLS, LIMITATIONS  # noqa: E402
from src.agent.tool_registry import ToolError  # noqa: E402
from src.eval.real_backends import (  # noqa: E402
    _mark_todays_row,
    _make_get_hours,
    _today_sentence,
    _library_today,
    _POINT_TO_URL,
    _canonical_service,
    _make_point_to_url,
    _resolve_subject_terms,
    build_eval_backends,
)

_URL_RE = re.compile(r"https://[^\s\"',)]+")


def _capability_scope_urls() -> set[str]:
    """Every https URL that appears in a LIMITATIONS response string."""
    urls: set[str] = set()
    for entry in LIMITATIONS.values():
        resp = entry.get("response") or ""
        urls.update(_URL_RE.findall(resp))
    return urls


# --- 1. DRIFT GUARD ---


def test_point_to_url_urls_mirror_capability_scope() -> None:
    """Every non-ILL URL the eval can emit MUST still be literally
    present in capability_scope. If someone edits capability_scope and
    this map drifts, this fails loudly -- which is the entire point."""
    source_urls = _capability_scope_urls()
    for service, (url, _desc) in _POINT_TO_URL.items():
        assert url in source_urls, (
            f"point_to_url[{service!r}] = {url!r} is NOT present in any "
            f"capability_scope.LIMITATIONS response. Either the URL was "
            f"invented (forbidden) or capability_scope changed and this "
            f"map must be updated to match the new source of truth."
        )


# --- 2. ILL campus-awareness, live-sourced ---


def test_point_to_url_ill_is_campus_aware_and_live_sourced() -> None:
    point = _make_point_to_url()

    oxford = point("ill", {"campus": "oxford"})
    hamilton = point("ill", {"campus": "hamilton"})
    middletown = point("interlibrary_loan", {"campus": "middletown"})
    default = point("ill", {})  # no campus -> Oxford default

    # Sourced LIVE from capability_scope.ILL_URLS (cannot drift).
    assert oxford["url"] == ILL_URLS["main"]["url"]
    assert hamilton["url"] == ILL_URLS["hamilton"]["url"]
    assert middletown["url"] == ILL_URLS["middletown"]["url"]
    assert default["url"] == ILL_URLS["main"]["url"]

    # The whole reason ILL is campus-aware: never cross campuses.
    assert hamilton["url"] != oxford["url"]
    assert middletown["url"] != oxford["url"]
    assert all(r["found"] for r in (oxford, hamilton, middletown, default))


# --- 3. unknown service: NO fabrication ---


def test_point_to_url_unknown_service_returns_no_url() -> None:
    point = _make_point_to_url()
    out = point("teleportation", {"campus": "oxford"})
    assert out["found"] is False
    assert out["url"] is None
    # It must NOT have guessed a plausible-looking link.
    assert "http" not in (str(out["url"]) or "")
    assert "teleportation" in out["description"]


def test_point_to_url_known_service_shape() -> None:
    point = _make_point_to_url()
    out = point("course_reserves", {})
    assert out["found"] is True
    assert out["url"].startswith("https://")
    assert out["service"] == "course_reserves"


# --- 4. ONLY write/handoff/space tools stay unwired ---


def test_only_ticket_and_handoff_tools_stay_unwired() -> None:
    """get_hours / get_room_availability / lookup_space are WIRED, and as
    of 2026-06-10 so is book_room (the v1 LibCal reservation tool revived
    behind a confirm gate -- see _make_book_room). Only create_ticket /
    handoff_human stay unwired; `_build_real_deps` still drops book_room
    from the EVAL surface so no eval run can ever fire a write.

    lookup_space was wired 2026-05-25 to fix the phone-number
    hallucination bug: the agent had no structured source for
    "what is the library phone number?" so search_kb returned the
    Dean's personal office number (529-3934) from a staff bio chunk
    instead of the main library line (529-4141)."""
    b = build_eval_backends()
    for name, call in (
        ("create_ticket", lambda: b.create_ticket({})),
        ("handoff_human", lambda: b.handoff_human({})),
    ):
        try:
            call()
        except ToolError as e:
            assert "not wired" in str(e).lower(), (name, str(e))
            continue
        raise AssertionError(f"{name} should raise the unwired ToolError")
    # book_room is real now -- it must NOT be the unwired sentinel.
    assert getattr(b.book_room, "__name__", "") != "_unwired", (
        "book_room regressed to the unwired sentinel"
    )


# --- 5. every read-only backend is actually wired (not a sentinel) ---


def test_all_readonly_backends_wired() -> None:
    b = build_eval_backends()
    # point_to_url is exercisable offline -> prove it's the real one.
    out = b.point_to_url("ill", {"campus": "hamilton"})
    assert out["url"] == ILL_URLS["hamilton"]["url"]
    # The rest hit Postgres / LibCal (network) -> don't call here.
    # Prove none is the tools_v2 unwired sentinel (whose closure
    # qualname contains "_make_unwired_sentinel" -> "unwired").
    for name in (
        "validate_url",
        "lookup_librarian",
        "lookup_space",
        "get_hours",
        "get_room_availability",
    ):
        backend = getattr(b, name)
        qualname = getattr(backend, "__qualname__", "")
        assert "unwired" not in qualname, (
            f"{name} is still the unwired sentinel ({qualname})"
        )
    # validate_url is the production UrlAllowlistValidator instance.
    assert type(b.validate_url).__name__ == "UrlAllowlistValidator"


# --- 6. point_to_url synonym widening (the failing circulation cases) ---


def test_point_to_url_synonyms_resolve_to_verified_urls() -> None:
    """The failing `circulation` cases (renew/reserves/holds phrasings)
    must now resolve -- WITHOUT introducing any new URL."""
    point = _make_point_to_url()
    cases = {
        "renew my books": _POINT_TO_URL["renewals"][0],
        "extend my loan": _POINT_TO_URL["renewals"][0],
        "reserves": _POINT_TO_URL["course_reserves"][0],
        "course reserve": _POINT_TO_URL["course_reserves"][0],
        "place a hold": _POINT_TO_URL["holds"][0],
        "pay my overdue fines": _POINT_TO_URL["fines"][0],
        "ohiolink account": _POINT_TO_URL["account"][0],
    }
    for phrasing, expected_url in cases.items():
        out = point(phrasing, {})
        assert out["found"] is True, (phrasing, out)
        assert out["url"] == expected_url, (phrasing, out["url"])


def test_canonical_service_maps_and_passthrough() -> None:
    assert _canonical_service("renew") == "renewals"
    assert _canonical_service("RESERVES") == "course_reserves"
    assert _canonical_service("how do I place a hold?") == "holds"
    assert _canonical_service("ill") == "ill"
    # genuinely unknown still passes through (-> no-url, no guess)
    assert _canonical_service("teleportation") == "teleportation"


def test_holds_url_is_still_drift_safe() -> None:
    """The new `holds` entry must use a URL already in a
    capability_scope LIMITATIONS response (no new fabrication)."""
    assert _POINT_TO_URL["holds"][0] in _capability_scope_urls()


# --- 7. lookup_librarian subject resolution (the reinvention fix) ---


def test_raw_subject_is_tried_before_aliases(monkeypatch) -> None:
    """An alias must never override a subject the API knows verbatim.

    "Engineering Technology" IS Krista McDonald's subject at Hamilton, but
    the alias map rewrote it to "Electrical and Computer Engineering", so
    the lookup answered with an Oxford librarian and the Hamilton one was
    unreachable (found 2026-07-28). Same for "Psychological Science" and
    "Criminal Justice" -- the REGIONAL programme names -- so the alias
    layer was defeating regional coverage exactly where it was scarcest.
    """
    import src.eval.real_backends as rb
    import src.tools.libguide_comprehensive_tools as lg

    # sanity: an alias for this term really does exist, so the ordering is
    # what decides the outcome
    assert "Engineering Technology" not in rb._resolve_subject_terms(
        "Engineering Technology", "")

    asked: list[str] = []

    class FakeTool:
        name = "fake"

        async def execute(self, query=None, subject_name=None, **kw):
            asked.append(subject_name)
            if subject_name == "Engineering Technology":
                return {"success": True, "librarians": [{
                    "first_name": "Krista", "last_name": "McDonald",
                    "email": "mcdonak@miamioh.edu", "campus": "Hamilton"}]}
            return {"success": False}

    monkeypatch.setattr(lg, "LibGuideSubjectLookupTool", FakeTool)
    monkeypatch.setattr(rb, "_db", lambda fn: (_ for _ in ()).throw(
        AssertionError("must not need the DB fallback here")))

    rows = rb._make_lookup_librarian()({"subject": "Engineering Technology"})

    assert asked[0] == "Engineering Technology", (
        f"raw wording must be queried FIRST, but order was {asked}")
    assert [r["name"] for r in rows] == ["Krista McDonald"]
    assert rows[0]["campus"] == "Hamilton"


def test_resolve_subject_terms_alias_and_course_code() -> None:
    """The resolution the hand-rolled lookup lacked: alias + course
    code -> canonical subject names, via the project's own maps."""
    assert "Biology" in _resolve_subject_terms("biology", "")
    assert "English" in _resolve_subject_terms("", "who helps with ENG 111")
    # librarian-name -> their subjects (Ginny Boehme is the bio liaison)
    # Name -> subject inference was REMOVED 2026-07-28: the roster is no
    # longer duplicated in code, and inferring subjects from a name
    # produced wrong-person answers twice in one day. A name now resolves
    # through the direct Postgres name lookup instead.
    assert _resolve_subject_terms("", "ginny boehme") == []
    # nothing resolvable -> empty (DB contains-match fallback handles it)
    assert _resolve_subject_terms("", "") == []


def test_resolve_subject_terms_dedupes_preserving_order() -> None:
    out = _resolve_subject_terms("biology", "biology")
    assert out == list(dict.fromkeys(out))  # no dupes


# --- 8. book_room backend protocol (v1 tool + confirm gate) ---------------


class _FakeBridge:
    """Stands in for real_backends._bridge, dispatching on WHICH coroutine.

    It used to dispatch on call ORDER -- #1 building validation, #2 the v1
    tool -- and `calls == 1` was the proxy for "no write happened". That broke
    the moment a legitimate third call appeared: moving the building-hours
    check ahead of the confirm gate (2026-07-30) made the pre-confirm path
    issue two more bridge calls, and the positional fake handed the second one
    the v1 tool's result. Dispatching by name says what each call IS, and
    `tool_invoked` states the thing the test actually cares about.
    """

    def __init__(self, validate_result, tool_result=None,
                 building_id="9999", hours_result=(True, None)):
        self.validate_result = validate_result
        self.tool_result = tool_result
        # Default is a building the hours gate does not cover (it applies only
        # to King "2047" and Art "4089"), so existing tests are unaffected
        # unless they opt in.
        self.building_id = building_id
        self.hours_result = hours_result
        self.calls = 0
        self.tool_invoked = False

    def __call__(self, coro, timeout=30.0):
        name = getattr(getattr(coro, "cr_code", None), "co_name", "") or ""
        coro.close()
        self.calls += 1
        if "validate_library_for_rooms" in name:
            return self.validate_result
        if "get_building_id" in name:
            return self.building_id
        if "check_building_hours" in name:
            return self.hours_result
        self.tool_invoked = True
        assert self.tool_result is not None, (
            "v1 tool was invoked when the protocol forbids it"
        )
        return self.tool_result


def _booking_args(**over):
    base = dict(building="King", date="tomorrow", start_time="2pm",
                end_time="3pm", first_name="Test", last_name="User",
                email="qum@miamioh.edu")
    base.update(over)
    return base


def _run_with_bridge(fake_bridge, args):
    import src.eval.real_backends as rb
    orig = rb._bridge
    rb._bridge = fake_bridge
    try:
        fn = rb._make_book_room()
        return fn(args)
    finally:
        rb._bridge = orig


def test_book_room_rejects_fake_building() -> None:
    """Operator requirement #1: 'book a room at OSU' must be told we
    don't book there, with the real options -- BEFORE anything else."""
    fake = _FakeBridge(validate_result=(
        False,
        "We don't reserve rooms at 'OSU'. Valid libraries: King, "
        "Art & Architecture, Rentschler (Hamilton), Gardner-Harvey "
        "(Middletown).",
        "",
    ))
    out = _run_with_bridge(fake, _booking_args(building="OSU"))
    assert out["success"] is False
    assert out["stage"] == "invalid_building"
    assert "King" in out["text"]
    assert not fake.tool_invoked  # v1 tool NEVER invoked


def test_book_room_missing_slots_delegates_for_friendly_list() -> None:
    """Missing slots -> v1 tool's 'I still need ...' text (it cannot
    book with missing params, so delegation is side-effect-free)."""
    fake = _FakeBridge(
        validate_result=(True, "king", "King Library"),
        tool_result={"success": False,
                     "text": "To complete your room reservation, I still "
                             "need: @miamioh.edu email address."},
    )
    out = _run_with_bridge(
        fake, _booking_args(email=None)
    )
    assert out["success"] is False
    assert out["stage"] == "tool_response"
    assert "still need" in out["text"]
    assert fake.tool_invoked  # delegation is safe: it cannot book


def test_book_room_complete_slots_without_confirm_summarizes_only() -> None:
    """THE confirm gate: all slots present but confirm absent -> a
    summary is returned and the v1 tool is NOT called (structurally no
    write can happen)."""
    fake = _FakeBridge(validate_result=(True, "king", "King Library"))
    out = _run_with_bridge(fake, _booking_args())
    assert out["success"] is False
    assert out["stage"] == "needs_confirmation"
    assert "confirm" in out["text"].lower()
    assert "Nothing is booked yet" in out["text"]
    assert not fake.tool_invoked  # structurally no write can happen


def test_book_room_confirm_true_books() -> None:
    fake = _FakeBridge(
        validate_result=(True, "king", "King Library"),
        tool_result={"success": True,
                     "text": "Room 110 ... Confirmation number: cs_ABC123."},
    )
    out = _run_with_bridge(fake, _booking_args(confirm=True))
    assert out["success"] is True
    assert out["stage"] == "booked"
    assert "Confirmation number" in out["text"]
    assert fake.tool_invoked


def main() -> int:
    tests = [
        test_point_to_url_urls_mirror_capability_scope,
        test_point_to_url_ill_is_campus_aware_and_live_sourced,
        test_point_to_url_unknown_service_returns_no_url,
        test_point_to_url_known_service_shape,
        test_only_ticket_and_handoff_tools_stay_unwired,
        test_all_readonly_backends_wired,
        test_point_to_url_synonyms_resolve_to_verified_urls,
        test_canonical_service_maps_and_passthrough,
        test_holds_url_is_still_drift_safe,
        test_resolve_subject_terms_alias_and_course_code,
        test_resolve_subject_terms_dedupes_preserving_order,
        test_book_room_rejects_fake_building,
        test_book_room_missing_slots_delegates_for_friendly_list,
        test_book_room_complete_slots_without_confirm_summarizes_only,
        test_book_room_confirm_true_books,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


def test_book_room_hours_gate_is_not_wired_pre_confirm() -> None:
    """Records a KNOWN rough edge, so nobody re-adds it the unsafe way.

    Checking building hours before the confirm gate is the right behaviour --
    a student should not be asked to commit to a time the building is closed.
    Wiring it at the pre-confirm call site was tried on 2026-07-30 and reverted
    the same day: those helpers reach LibCal through the singletons described in
    real_backends' module docstring, and driving them from the _bridge loop
    there bound an asyncio.Event to that loop, so the next request died with
    "is bound to a different event loop". An out-of-hours message became a
    server error for the whole turn.

    The fix belongs INSIDE the v1 tool, ahead of its own summary, where it
    already runs on the right loop.
    """
    fake = _FakeBridge(
        validate_result=(True, "king", "King Library"),
        building_id="2047",
        hours_result=(False, "King Library is open 7:30am to 5:00pm."),
    )
    out = _run_with_bridge(fake, _booking_args(start_time="5pm", end_time="6pm"))
    # Today it still reaches the summary; when the check moves into the v1
    # tool this assertion is what should change.
    assert out["stage"] == "needs_confirmation"
    assert not fake.tool_invoked


# --- hours evidence names the day WITHOUT polluting the hours text ----------
#
# On Monday 2026-08-03 the bot answered "King Library closes at 9:00pm today,
# Wednesday, August 5, 2026." -- 2 times in 3 when hours followed a booking
# turn, never when asked cold. LibCalWeekHoursTool returns seven dated rows and
# marks none as current, nothing injects the date into the prompt (builder.py
# keeps it out of the cached prefix on purpose), and the synthesizer rule's own
# example read "(Wed)". With no anchor, the model copied the example's weekday.
#
# The FIRST fix stamped the day into the `hours` string itself. That was wrong
# and shipped a worse bug: several callers print `hours` verbatim -- e.g.
# _special_collections_hours_answer builds its entire answer from it -- so
# "Today is Monday, August 3, 2026" and a "<-- TODAY" marker went straight to a
# patron, along with the whole week's schedule that prompt rule 12 forbids.
# Caught in the 2026-08-03 baseline eval (hr_special_collections_appt_only).
#
# So the day now travels as its own field. These tests pin BOTH halves.

_WEEK = """**King Library Hours (Week of 2026-08-03):**

• **Monday (2026-08-03)**: 7:30am to 9:00pm
• **Tuesday (2026-08-04)**: 7:30am to 9:00pm"""


def test_today_sentence_names_the_weekday_and_the_date():
    out = _today_sentence()
    today = _library_today()
    assert today.strftime("%A") in out
    assert today.isoformat() in out
    assert str(today.year) in out


def test_today_uses_eastern_not_the_box_clock():
    """The box runs UTC; Oxford is UTC-4 in summer. From 8pm ET the UTC date is
    already tomorrow, which would misname the day every evening."""
    import datetime as dt

    import pytz

    eastern = dt.datetime.now(pytz.timezone("America/New_York")).date()
    assert _library_today() == eastern
    assert eastern.strftime("%A") in _today_sentence()


def test_the_day_never_leaks_into_the_hours_string():
    """THE regression. `hours` has verbatim consumers, so anything meant only
    for the model must stay out of it."""
    backends = build_eval_backends()
    # _make_get_hours is exercised through the real backend dict; assert on the
    # contract every verbatim caller depends on.
    import inspect

    src = inspect.getsource(_make_get_hours)
    assert '"hours": res.get("text", "")' in src, (
        "the hours field must be passed through untouched -- stamping it leaked "
        "'Today is ...' and '<-- TODAY' into a patron answer"
    )
    assert '"today": _today_sentence()' in src, (
        "the day must still reach the model, just in its own field"
    )
    assert "_mark_todays_row(res.get" in src, (
        "the model still needs today's row marked -- with only a bare `today` "
        "sentence, 'is the library open right now?' came back as the whole "
        "week plus 'depends on the current day and time'"
    )
    assert '"hours": _mark' not in src and '"hours": _stamp' not in src, (
        "the marked-up week must never be assigned to `hours`"
    )


def test_no_today_marker_text_can_reach_an_answer():
    """Belt and braces: the marker strings must not appear in the pristine
    week text that callers print."""
    assert "<-- TODAY" not in _WEEK
    assert "Today is" not in _WEEK


def test_marked_week_tags_exactly_todays_row():
    week = ("**King Library Hours (Week of 2026-08-03):**\n\n"
            "• **Monday (2026-08-03)**: 7:30am to 9:00pm\n"
            "• **Tuesday (2026-08-04)**: 7:30am to 9:00pm")
    out = _mark_todays_row(week)
    assert out.startswith("Today is ")
    tagged = [ln for ln in out.splitlines() if "<-- TODAY" in ln]
    assert len(tagged) <= 1, tagged
    for ln in tagged:
        # never the "Week of 2026-08-03" header, which carries the same date
        assert ln.lstrip().startswith("•"), ln


def test_marked_week_is_idempotent():
    """get_hours can be called twice in one turn; don't stack headers."""
    week = "• **Monday (2026-08-03)**: 7:30am to 9:00pm"
    once = _mark_todays_row(week)
    assert _mark_todays_row(once).count("<-- TODAY") <= 1


def test_marked_week_passes_through_empty():
    assert _mark_todays_row("") == ""
