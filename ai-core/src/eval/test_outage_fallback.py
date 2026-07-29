"""Subject lookups must survive a LibGuides outage.

The operator's own `LibrarianSubject` table exists precisely so a
Springshare outage does not take out subject questions. It could not do that
job: `_lookup_by_subject_via_libguides` raised ToolError on any API
exception, which aborted the lookup BEFORE the Postgres path ran. Proved
2026-07-29 by stubbing the tool to raise -- all seven regional subject
lookups failed with data sitting in Postgres.
"""

import pytest

import src.eval.real_backends as rb
from src.agent.tool_registry import ToolError


class _DeadAPI:
    """Stands in for Springshare being down."""

    name = "dead"
    calls = 0

    async def execute(self, **kw):
        _DeadAPI.calls += 1
        raise RuntimeError("simulated Springshare outage")


@pytest.fixture
def dead_api(monkeypatch):
    import src.tools.libguide_comprehensive_tools as lg
    _DeadAPI.calls = 0
    monkeypatch.setattr(lg, "LibGuideSubjectLookupTool", _DeadAPI)
    return _DeadAPI


def test_outage_falls_through_to_postgres(dead_api, monkeypatch):
    """An API exception must degrade, not abort."""
    rows_seen = {}

    def fake_db(fn):
        # Stand in for the LibrarianSubject query: one Middletown liaison.
        class _Lib:
            id = "l1"
            name = "Jennifer Hicks"
            alternateName = None
            email = "hicksjl2@miamioh.edu"
            title = "Outreach and Instruction Librarian"
            department = None
            phone = None
            campus = "Middletown"
            profileUrl = None
            isActive = True

        class _Link:
            librarian = _Lib()
            subjectId = "s1"

        class _Client:
            class librariansubject:
                @staticmethod
                async def find_many(**kw):
                    rows_seen["where"] = kw.get("where")
                    return [_Link()]

            class subjectlibguide:
                @staticmethod
                async def find_many(**kw):
                    return []

        import asyncio
        return asyncio.run(fn(_Client()))

    monkeypatch.setattr(rb, "_db", fake_db)
    out = rb._make_lookup_librarian()(
        {"subject": "Criminal Justice", "campus": "middletown"})

    assert dead_api.calls > 0, "the API should still have been attempted"
    assert [r["name"] for r in out] == ["Jennifer Hicks"]
    assert out[0]["source"] == rb.SOURCE_DB


def test_raw_wording_reaches_the_db_path(dead_api, monkeypatch):
    """The DB path must query the user's OWN term, not only the alias.

    `terms0 = resolved if resolved else [subject]` dropped the raw wording
    whenever an alias existed -- so "Criminal Justice" was rewritten to
    "Criminology" and the DB never looked for the subject the regional
    liaison is actually linked to.
    """
    from src.tools.subject_aliases import find_subject_by_alias

    # precondition: an alias for this term really does exist
    assert find_subject_by_alias("Criminal Justice") == "Criminology"

    seen = {}

    def fake_db(fn):
        class _Client:
            class librariansubject:
                @staticmethod
                async def find_many(**kw):
                    w = kw.get("where") or {}
                    names = (((w.get("subject") or {}).get("is") or {})
                             .get("name") or {})
                    seen.setdefault("terms", []).extend(names.get("in") or [])
                    return []
        import asyncio
        return asyncio.run(fn(_Client()))

    monkeypatch.setattr(rb, "_db", fake_db)
    with pytest.raises(ToolError):
        rb._make_lookup_librarian()(
            {"subject": "Criminal Justice", "campus": "middletown"})

    terms = seen.get("terms") or []
    assert "Criminal Justice" in terms, f"raw wording missing from {terms}"
    assert "Criminal Justice - MC" in terms, "campus variant missing"


def test_outage_with_no_local_data_hands_off(dead_api, monkeypatch):
    """API unreachable AND nothing in Postgres must NOT tell the patron that
    no librarian covers the subject -- we cannot know that right now."""

    def empty_db(fn):
        class _Client:
            class librariansubject:
                @staticmethod
                async def find_many(**kw):
                    return []
        import asyncio
        return asyncio.run(fn(_Client()))

    monkeypatch.setattr(rb, "_db", empty_db)
    with pytest.raises(ToolError) as ei:
        rb._make_lookup_librarian()({"subject": "Underwater Basket Weaving"})
    assert "unreachable" in str(ei.value)


def test_a_genuine_miss_is_still_an_empty_result(monkeypatch):
    """With the API HEALTHY and answering "nobody", the caller must get an
    empty list -- that is a fact we can state -- not an outage error."""
    import src.tools.libguide_comprehensive_tools as lg

    class _HealthyButEmpty:
        name = "ok"

        async def execute(self, **kw):
            return {"success": False}

    monkeypatch.setattr(lg, "LibGuideSubjectLookupTool", _HealthyButEmpty)

    def empty_db(fn):
        class _Client:
            class librariansubject:
                @staticmethod
                async def find_many(**kw):
                    return []
        import asyncio
        return asyncio.run(fn(_Client()))

    monkeypatch.setattr(rb, "_db", empty_db)
    assert rb._make_lookup_librarian()(
        {"subject": "Underwater Basket Weaving"}) == []
