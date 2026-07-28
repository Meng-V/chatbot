"""Regression tests for the librarian-name -> subjects map.

Run: `pytest src/tools/test_subject_aliases.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from src.tools.subject_aliases import (  # noqa: E402
    find_subject_by_alias,
    find_subjects_by_librarian_name,
)


def test_middle_initial_is_not_a_wildcard() -> None:
    """The partial match used to be a SUBSTRING test, and the map holds
    "roger a justus" -- so the initial "a" matched almost any name
    ("a" is in "krist-a") and the function returned Roger's subjects for
    everyone. Downstream that answered "How do I contact Krista
    McDonald?" with Roger Justus's details (live repro 2026-07-28);
    wrong-person contacts are the worst error this bot can make.
    """
    for name in ["Krista McDonald", "Jennifer Hicks", "John Burke",
                 "Samantha Young", "Leah Tabler", "Brea McQueen"]:
        assert find_subjects_by_librarian_name(name) == [], name


def test_librarian_name_map_is_gone() -> None:
    """The hand-maintained person->subjects map was DELETED 2026-07-28.
    It duplicated Postgres + the LibGuides API, went stale silently (a
    departed colleague stayed in it), and its substring matching handed
    out the wrong person's contact details twice in one day. The accessor
    is a soft-fail stub; names resolve via the direct Postgres lookup."""
    import src.tools.subject_aliases as sa
    assert not hasattr(sa, "LIBRARIAN_SUBJECTS")
    for name in ["Ginny Boehme", "Boehme", "Erica Freed", "Roger Justus",
                 "roger a justus", "Krista McDonald"]:
        assert find_subjects_by_librarian_name(name) == [], name


def test_empty_and_garbage_names() -> None:
    assert find_subjects_by_librarian_name("") == []
    assert find_subjects_by_librarian_name("   ") == []
    assert find_subjects_by_librarian_name("12345") == []


def test_subject_alias_lookup_unchanged() -> None:
    assert find_subject_by_alias("chemistry") == "Chemistry and Biochemistry"
    assert find_subject_by_alias("chem") == "Chemistry and Biochemistry"
