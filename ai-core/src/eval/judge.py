"""
LLM-as-judge for the eval harness.

Given (question, expected_answer, bot_answer, allowed_urls), call the
judge LLM with `prompts/judge_v1.py`'s stable prefix and parse the
returned verdict JSON.

Design notes:
  - The judge LLM is INJECTABLE (Callable Protocol). Tests pass a stub
    that returns canned verdicts; prod injects the real OpenAI call
    via src/llm/client.py.
  - The judge prompt's stable prefix is registered at import time via
    src.prompts.judge_v1. We compose [stable prefix] + [dynamic
    suffix] using prompts.builder so cache hits are preserved.
  - `Verdict` is the parsed JSON the judge returns. Six labels (per
    plan §week 1):
        correct | partial | wrong | refused_correctly |
        refused_incorrectly | answered_should_have_refused
  - Citation validity is a SEPARATE check the judge reports
    (`citation_validity: all_valid | some_invalid | no_citations | n_a`).
    This lets the eval suite assert "answer was correct AND every
    citation URL was valid" as one composite gate.

See plan:
  - timeline week 1 -> "automated scoring: answer correctness
    (LLM-as-judge), citation validity (URL check), refusal
    correctness".
  - prompts/judge_v1.py for the stable rubric prefix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol


# --- Types ---------------------------------------------------------------


@dataclass(frozen=True)
class JudgeRequest:
    """One judgment call's input."""

    question: str
    expected_answer: str
    bot_answer: str
    allowed_urls: list[str] = field(default_factory=list)
    """URLs the bot is permitted to cite. Anything else is wrong."""

    notes: Optional[str] = None
    """The gold case's `notes` field: operator review history and
    intent for this case. Shown to the judge (judge_v2+) as
    authoritative context for interpreting expected_answer -- the
    2026-07-16 triage found ~60/76 flagged verdicts were judge
    harshness the notes would have resolved."""


@dataclass(frozen=True)
class Verdict:
    """The parsed verdict from the judge LLM.

    `verdict` and `citation_validity` are kept as strings (not enums)
    so a future judge variant adding labels can land without breaking
    parsing -- the gate code in run_eval branches on string equality.
    """

    verdict: str
    """One of: correct | partial | wrong | refused_correctly |
    refused_incorrectly | answered_should_have_refused."""

    reason: str
    """One short sentence explaining the call. Logged per-question."""

    citation_validity: str
    """One of: all_valid | some_invalid | no_citations | n_a."""


@dataclass(frozen=True)
class JudgeOutcome:
    """Returned to the eval-harness caller. Includes the parsed
    verdict plus the raw judge JSON for forensic logging."""

    verdict: Verdict
    raw_response: dict


class JudgeLLM(Protocol):
    """Minimal interface the judge needs from an LLM client.

    `(parsed_response_dict, usage_dict)` shape mirrors the synthesizer
    LLM Protocol so src/llm/client.py can implement both with one
    method. Returns the JSON the judge model emitted.
    """

    def __call__(
        self,
        *,
        prefix_id: str,
        dynamic_suffix: str,
        model: str,
    ) -> tuple[dict, dict]:
        ...


# --- Pure prompt-suffix builder -----------------------------------------


def build_judge_dynamic_suffix(request: JudgeRequest) -> str:
    """Build the non-cached portion of the judge prompt.

    Order: question, expected, bot answer, allowed URLs. The judge
    reads top-down -- expected answer immediately after the question
    so the rubric is anchored before the bot's answer is shown.
    """
    allowed = (
        "\n".join(f"  - {u}" for u in request.allowed_urls)
        if request.allowed_urls
        else "  (none)"
    )
    suffix = (
        f"QUESTION: {request.question}\n\n"
        f"EXPECTED: {request.expected_answer}\n\n"
        f"BOT ANSWER: {request.bot_answer}\n\n"
        f"ALLOWED URLS:\n{allowed}\n"
    )
    if request.notes:
        suffix += f"\nOPERATOR NOTES: {request.notes}\n"
    return suffix


# --- Verdict parsing -----------------------------------------------------


_VALID_VERDICTS = frozenset({
    "correct",
    "partial",
    "wrong",
    "refused_correctly",
    "refused_incorrectly",
    "answered_should_have_refused",
})

_VALID_CITATION_VALIDITIES = frozenset({
    "all_valid",
    "some_invalid",
    "no_citations",
    "n_a",
})


class JudgeParseError(ValueError):
    """The judge returned a JSON shape we can't act on. Fail loud --
    silently coercing to "wrong" would hide real model regressions."""


def parse_verdict(raw: dict | str) -> Verdict:
    """Convert the judge's raw response into a typed Verdict.

    Accepts either a dict (already-parsed structured output) or a
    string (plain-text JSON). Raises JudgeParseError on missing or
    invalid fields.
    """
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise JudgeParseError(f"judge returned non-JSON string: {e}") from e
    elif isinstance(raw, dict):
        obj = raw
    else:
        raise JudgeParseError(f"judge returned {type(raw).__name__}, expected dict or str")

    verdict = obj.get("verdict")
    if verdict not in _VALID_VERDICTS:
        raise JudgeParseError(
            f"unknown verdict label {verdict!r} (valid: {sorted(_VALID_VERDICTS)})"
        )

    citation_validity = obj.get("citation_validity")
    if citation_validity not in _VALID_CITATION_VALIDITIES:
        raise JudgeParseError(
            f"unknown citation_validity {citation_validity!r} "
            f"(valid: {sorted(_VALID_CITATION_VALIDITIES)})"
        )

    reason = obj.get("reason") or ""
    return Verdict(
        verdict=str(verdict),
        reason=str(reason),
        citation_validity=str(citation_validity),
    )


# --- Entry point ---------------------------------------------------------


def judge_answer(
    request: JudgeRequest,
    *,
    judge_llm: JudgeLLM,
    prefix_id: str = "judge_v1",
    model: str = "",
    samples: int = 5,
) -> JudgeOutcome:
    """Score one bot answer.

    Args:
        request: question + expected + bot_answer + allowed_urls.
        judge_llm: injectable LLM caller (Protocol).
        prefix_id: which prompt prefix to use. Default is the v1
            registered in src/prompts/judge_v1.py. Bump only if the
            rubric changes substantively (and update the eval gold
            set's expected verdicts in the same PR).
        model: which model to use. Default "" -> resolve_model("cheap")
            (env LLM_MODEL_CHEAP, default gpt-5.4-nano). The judge is
            high-volume mechanical rubric scoring once per question per
            regression run -- nano is ~3.7x cheaper than mini and the
            single biggest eval-cost line; consistency matters more
            than reasoning depth here. Pass an explicit id to override.
        samples: how many independent judge calls to take a majority
            vote across. Default 5 (was 3). Single-sample judging was
            empirically noisy on the 2026-05-22 wired-baseline run
            (22 of 79 failing cases flipped on a single re-judge, 11
            flipped worse) -- a 3-shot majority moved the measured
            score from 50.3% to 59.1% on the SAME bot answers. The
            2026-07-16 back-to-back runs showed 3-shot majorities on
            nano still flip 18% of verdicts on IDENTICAL answers, so
            the default went to 5. Pass 1 to revert to single-sample
            (e.g., for unit tests that stub the judge).

    Returns:
        JudgeOutcome with parsed Verdict + raw response (for logs).
        When samples>1, raw_response is the FIRST sample's raw text;
        verdict is the majority-vote verdict across all parseable
        samples.

    Raises:
        JudgeParseError: ALL judge samples returned malformed JSON.
            A subset of parse errors is tolerated -- majority is
            computed over the parseable samples.
    """
    from collections import Counter

    suffix = build_judge_dynamic_suffix(request)
    if not model:
        from src.config.models import resolve_model
        model = resolve_model("cheap")  # nano: cheapest tier for the judge

    raws: list[str] = []
    verdicts: list[Verdict] = []
    last_parse_error: Optional[Exception] = None
    for _ in range(max(1, int(samples))):
        try:
            raw, _usage = judge_llm(
                prefix_id=prefix_id,
                dynamic_suffix=suffix,
                model=model,
            )
            raws.append(raw)
            verdicts.append(parse_verdict(raw))
        except JudgeParseError as e:
            last_parse_error = e
            continue
    if not verdicts:
        # All samples failed to parse — propagate the last error so
        # the caller's existing JudgeParseError handling fires.
        assert last_parse_error is not None
        raise last_parse_error

    # Majority verdict label. Tie-break: keep the first sample's
    # verdict that matches the majority (deterministic ordering).
    label_counts = Counter(v.verdict for v in verdicts)
    top_label, _ = label_counts.most_common(1)[0]
    chosen = next(v for v in verdicts if v.verdict == top_label)

    return JudgeOutcome(verdict=chosen, raw_response=raws[0])


# --- Aggregation helper --------------------------------------------------


@dataclass(frozen=True)
class JudgeAggregate:
    """Roll up of all judge verdicts in one eval run."""

    total: int
    by_verdict: dict[str, int]
    """e.g. {"correct": 73, "partial": 12, "wrong": 9, ...}"""

    correct_rate: float
    """Fraction with verdict="correct" + "refused_correctly"."""

    citation_valid_rate: float
    """Fraction of NON-refusal answers where citation_validity=='all_valid'.
    Refusals are excluded (citation_validity='n_a' there)."""


def aggregate_verdicts(verdicts: list[Verdict]) -> JudgeAggregate:
    """Compute the run-level aggregates from per-question verdicts."""
    if not verdicts:
        return JudgeAggregate(total=0, by_verdict={}, correct_rate=0.0,
                              citation_valid_rate=0.0)

    by_verdict: dict[str, int] = {}
    for v in verdicts:
        by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1

    correct_count = (
        by_verdict.get("correct", 0)
        + by_verdict.get("refused_correctly", 0)
    )

    # Citation validity is meaningful only for non-refusal answers.
    cv_eligible = [v for v in verdicts if v.citation_validity != "n_a"]
    cv_valid = [v for v in cv_eligible if v.citation_validity == "all_valid"]

    return JudgeAggregate(
        total=len(verdicts),
        by_verdict=by_verdict,
        correct_rate=correct_count / len(verdicts),
        citation_valid_rate=(len(cv_valid) / len(cv_eligible)) if cv_eligible else 0.0,
    )


__all__ = [
    "JudgeAggregate",
    "JudgeLLM",
    "JudgeOutcome",
    "JudgeParseError",
    "JudgeRequest",
    "Verdict",
    "aggregate_verdicts",
    "build_judge_dynamic_suffix",
    "judge_answer",
    "parse_verdict",
]
