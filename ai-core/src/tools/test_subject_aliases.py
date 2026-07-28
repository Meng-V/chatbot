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


def test_real_liaison_names_still_resolve() -> None:
    """The fix must not break the feature: "the Boehme librarian" and
    full names still map to their subject lists."""
    assert "Biology" in find_subjects_by_librarian_name("Ginny Boehme")
    assert "Biology" in find_subjects_by_librarian_name("Boehme")
    assert "Business" in find_subjects_by_librarian_name("Erica Freed")
    # the middle-initial entry itself must keep working
    for variant in ("Roger Justus", "roger a justus", "Justus"):
        assert "Mathematics" in find_subjects_by_librarian_name(variant), variant


def test_empty_and_garbage_names() -> None:
    assert find_subjects_by_librarian_name("") == []
    assert find_subjects_by_librarian_name("   ") == []
    assert find_subjects_by_librarian_name("12345") == []


def test_subject_alias_lookup_unchanged() -> None:
    assert find_subject_by_alias("chemistry") == "Chemistry and Biochemistry"
    assert find_subject_by_alias("chem") == "Chemistry and Biochemistry"
