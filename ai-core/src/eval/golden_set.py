"""
Loader and schema for the gold-question set.

The set lives as JSONL (one question per line) so it's easy to diff in
git, easy to add new cases without touching code, and easy to filter
(`grep '"intent": "makerspace"' golden_set.jsonl`).

See plan: Verification §6 (cross-campus correctness gate -- 15+ such cases)
and timeline week 1 (100-question seed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# Default location -- adjust if you move the file.
GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"


@dataclass(frozen=True)
class GoldQuestion:
    """One row of the gold set.

    Fields:
        id: stable identifier; use a slug (e.g. "makerspace_hamilton_refusal")
            so test failures are self-explanatory.
        question: the user message verbatim.
        intent: the expected intent the kNN classifier should pick.
        scope_campus: the expected resolved scope.campus.
        scope_library: the expected resolved scope.library (or None).
        expected_answer: free-text gold answer; the judge compares against this.
            For refusal-expected cases, set to the literal "REFUSAL".
        expected_outcome: "answer" | "refusal" | "clarify".
        allowed_urls: URLs the bot is permitted to cite. Anything else is wrong.
        category: free-text bucket for filtering reports
            (e.g. "cross_campus", "featured_service", "out_of_scope").
        notes: optional reviewer note for context.
        needs_session_origin: optional campus ID ("hamilton" | "middletown" |
            "oxford") that the scope-only check should pass as
            session_origin_campus. Use when the question is written as if
            from that campus's chat widget ("Can I book a room?" on the
            Hamilton site should resolve to campus=hamilton).
    """

    id: str
    question: str
    intent: str
    scope_campus: str
    scope_library: Optional[str]
    expected_answer: str
    expected_outcome: str
    allowed_urls: list[str]
    category: str
    notes: Optional[str] = None
    needs_session_origin: Optional[str] = None


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[GoldQuestion]:
    """Read the JSONL file and return the parsed gold questions.

    Skips blank lines and lines starting with `//` (comment convention,
    not strictly JSONL but useful for in-file reviewer notes).
    """
    questions: list[GoldQuestion] = []
    with open(path, encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue
            try:
                obj: dict[str, Any] = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no} not valid JSON: {e}") from e
            questions.append(
                GoldQuestion(
                    id=obj["id"],
                    question=obj["question"],
                    intent=obj["intent"],
                    scope_campus=obj["scope_campus"],
                    scope_library=obj.get("scope_library"),
                    expected_answer=obj["expected_answer"],
                    expected_outcome=obj["expected_outcome"],
                    allowed_urls=obj.get("allowed_urls", []),
                    category=obj.get("category", "uncategorized"),
                    notes=obj.get("notes"),
                    needs_session_origin=obj.get("needs_session_origin"),
                )
            )
    return questions
