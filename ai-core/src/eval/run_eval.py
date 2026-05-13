"""
Eval-harness orchestrator: run every gold question through the bot,
score the result, and report.

This wires the v2 orchestrator end-to-end against the gold set with:
  - Real `IntentKNN` classifier using `text-embedding-3-large` and the
    full labeled+synthetic exemplar set on disk.
  - Real scope resolver.
  - Real capability registry, real refusal templates.
  - STUB agent + synthesizer LLMs (canned outputs per the smoke_e2e
    pattern). Wiring the orchestrator's path-routing this way costs
    zero LLM tokens; embeddings are cached after the first run.

What this measures TODAY (without real LLM):
  1. Scope resolution accuracy (alias table + session-origin fallback)
  2. Intent classification accuracy
  3. Orchestrator PATH accuracy: did the turn take the expected route
     (clarify / point_to_url / refuse / agent_then_answer /
     agent_then_refusal)?

What this does NOT measure yet (requires real LLM):
  4. Answer correctness (LLM-as-judge against gold.expected_answer)
  5. Citation validity rate (model emits URLs not in the bundle?)
  6. Refusal correctness for low-confidence / no-evidence cases

(4)-(6) require real `text=responses` calls plus a separate judge
model. That's a follow-up PR -- the wiring point is `_run_with_judge`
below, currently `None`.

Usage:
    python -m src.eval.run_eval                          # full set
    python -m src.eval.run_eval --filter cross_campus    # one category
    python -m src.eval.run_eval --scope-only             # scope-only
    python -m src.eval.run_eval --verbose                # show mismatches

See plan: timeline week 1 + Verification §2/§4/§6.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Allow running as a script.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402
from src.eval.smoke_e2e import (  # noqa: E402
    CannedAgentLLM,
    CannedSynthesizerLLM,
    classify_response_path,
)
from src.agent.tool_registry import Tool, ToolRegistry  # noqa: E402
from src.graph.new_orchestrator import (  # noqa: E402
    OrchestratorDeps,
    TurnRequest,
    run_turn,
)
from src.router.intent_knn import (  # noqa: E402
    Exemplar,
    IntentKNN,
    load_exemplars_from_disk,
)
from src.scope.resolver import resolve_scope  # noqa: E402

logger = logging.getLogger("eval")


# --- Expected-path mapping ------------------------------------------------

# Map gold's `expected_outcome` to the set of orchestrator paths that
# satisfy it. An "answer" gold case is satisfied by either a POINT_TO_URL
# short-circuit (databases, find_resource) or a full agent_then_answer
# run. A "refusal" gold case is satisfied by either a capability-tier
# REFUSE (account, events_news) or an agent_then_refusal (synth picked
# up no_results / low_confidence / etc.). Clarify is its own bucket.
_OK_PATHS_BY_OUTCOME: dict[str, set[str]] = {
    "answer": {"point_to_url", "agent_then_answer"},
    "refusal": {"refuse", "agent_then_refusal"},
    "clarify": {"clarify"},
}


# --- Result schema ---------------------------------------------------------


@dataclass
class EvalResult:
    """One question's eval outcome.

    All fields except scope_* and intent_* are populated when the bot
    wiring is active (i.e., scope_only=False). The judge_verdict slot
    is a future hook for LLM-as-judge.
    """

    question_id: str
    category: str
    # Scope check
    scope_match: bool
    actual_scope_campus: str
    actual_scope_library: Optional[str]
    # Intent check (added once the orchestrator runs)
    intent_match: Optional[bool] = None
    actual_intent: Optional[str] = None
    # Path check
    expected_path_set: Optional[frozenset] = None
    actual_path: Optional[str] = None
    path_match: Optional[bool] = None
    # Bot output (populated when wired)
    bot_answer: Optional[str] = None
    bot_was_refusal: Optional[bool] = None
    bot_refusal_trigger: Optional[str] = None
    bot_citations_count: Optional[int] = None
    # Judge verdict (None until LLM-as-judge wires up)
    judge_verdict: Optional[str] = None
    # Telemetry
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class EvalReport:
    """Aggregate of one eval run."""

    total: int = 0
    scope_matches: int = 0
    intent_matches: int = 0
    path_matches: int = 0
    bot_called: int = 0
    by_category: dict[str, dict] = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)


# --- Deps wiring (real classifier + stub LLMs) -----------------------------


def _build_classifier(embed_cache_path: Optional[Path] = None) -> IntentKNN:
    """Construct the real kNN classifier with disk-loaded exemplars.

    If `embed_cache_path` is given (the script's cache from
    scripts/eval_classifier_v38.py), preloaded vectors are used for
    every exemplar text -- zero OpenAI calls. Otherwise embeddings
    are computed on the fly via `src.llm.client.embed()` (one API
    call per unique text).
    """
    pairs = load_exemplars_from_disk()
    logger.info("loaded %d exemplars", len(pairs))

    if embed_cache_path is None:
        embed_cache_path = (
            _AI_CORE / "data" / "eval" / "classifier_embeddings.json"
        )

    cached: dict[str, list[float]] = {}
    if embed_cache_path.exists():
        import hashlib
        import json
        cached = json.loads(embed_cache_path.read_text(encoding="utf-8"))
        logger.info(
            "loaded %d cached embeddings from %s",
            len(cached), embed_cache_path,
        )

        def _hash(text: str) -> str:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        # Build exemplars from cache where possible; fall back to live
        # embed for misses. Track the miss count for cost visibility.
        from src.llm.client import embed
        misses = 0
        exemplars: list[Exemplar] = []
        for intent, text in pairs:
            h = _hash(text)
            if h in cached:
                vec = cached[h]
            else:
                vec = embed(text)
                cached[h] = vec
                misses += 1
            exemplars.append(Exemplar(intent=intent, text=text, vector=vec))
        if misses:
            logger.info("had to embed %d uncached exemplars live", misses)

        def embedder(t: str) -> list[float]:
            h = _hash(t)
            if h in cached:
                return cached[h]
            vec = embed(t)
            cached[h] = vec
            return vec

        return IntentKNN(exemplars=exemplars, embedder=embedder)

    # No cache: cold path. Slow + costs money but correct.
    from src.llm.client import embed
    exemplars = [
        Exemplar(intent=i, text=t, vector=embed(t)) for i, t in pairs
    ]
    return IntentKNN(exemplars=exemplars, embedder=embed)


def _build_stub_deps(classifier: IntentKNN) -> OrchestratorDeps:
    """Build OrchestratorDeps with the real classifier and stub
    agent/synth LLMs. Mirrors `src.eval.smoke_e2e._build_deps` but
    is shared across all gold questions (each question gets the same
    canned LLM behavior; only the classifier output varies)."""
    # Stub evidence must align with the synthesizer stub's hardcoded
    # citation URL (CannedSynthesizerLLM emits
    # `https://lib.miamioh.edu/king/cite-{n}/`) so the post-processor
    # can join citation -> evidence by URL and inherit
    # `campus: "all"`. Without this alignment, every citation lacks
    # campus metadata and the post-processor flags cross_campus_
    # mismatch on every non-Oxford gold case.
    #
    # `campus: "all"` is the contract for "this chunk is valid under
    # any scope" -- the stub is for wiring checks, not data quality.
    canned_evidence = {
        "n": 1,
        "chunk_id": "eval-stub-chunk",
        "source_url": "https://lib.miamioh.edu/king/cite-1/",
        "snippet": "Stubbed evidence for eval-time wiring check.",
        "campus": "all",
        "library": "all",
        "topic": "service",
        "featured_service": None,
        "score": 0.9,
    }

    registry = ToolRegistry()
    registry.register(Tool(
        name="search_kb",
        description="(stub) search the library knowledge base",
        parameters={"type": "object"},
        handler=lambda args: {"evidence": [canned_evidence]},
    ))

    return OrchestratorDeps(
        classifier=classifier,
        tool_registry=registry,
        agent_llm=CannedAgentLLM(),
        synthesizer_llm=CannedSynthesizerLLM(),
        load_corrections=lambda: [],
        load_url_allowlist=lambda: {canned_evidence["source_url"]},
        # No service-availability refusals in the wiring eval. Those
        # depend on real LibrarySpace seed data; cross_campus gold
        # cases exercise the path-classification regardless.
        lookup_service_availability=lambda intent, campus: None,
    )


# --- Per-question runners -------------------------------------------------


def _check_scope(q: GoldQuestion) -> tuple[bool, str, Optional[str]]:
    """Run the scope resolver and report whether it matches the gold scope."""
    s = resolve_scope(
        q.question,
        session_origin_campus=q.needs_session_origin,  # type: ignore[arg-type]
    )
    matches = (
        s.campus == q.scope_campus
        and s.library == q.scope_library
    )
    return matches, s.campus, s.library


def _run_bot(q: GoldQuestion, deps: OrchestratorDeps) -> dict:
    """Run one gold question through the orchestrator. Returns a dict
    of fields to merge into EvalResult."""
    # Simulate session-origin URL if the gold case requires it.
    origin = None
    if q.needs_session_origin == "hamilton":
        origin = "https://www.ham.miamioh.edu/library/"
    elif q.needs_session_origin == "middletown":
        origin = "https://www.mid.miamioh.edu/library/"

    request = TurnRequest(
        user_message=q.question,
        conversation_id=f"eval-{q.id}",
        session_origin_url=origin,
    )
    try:
        resp = run_turn(request, deps)
    except Exception as e:  # noqa: BLE001
        logger.warning("turn crashed", extra={"id": q.id, "error": str(e)})
        return {
            "actual_intent": None,
            "intent_match": False,
            "actual_path": f"crash:{type(e).__name__}",
            "path_match": False,
            "bot_answer": None,
            "bot_was_refusal": None,
            "bot_refusal_trigger": None,
            "bot_citations_count": None,
            "latency_ms": None,
        }

    path = classify_response_path(resp)
    expected_paths = _OK_PATHS_BY_OUTCOME.get(q.expected_outcome, set())
    return {
        "actual_intent": resp.intent,
        "intent_match": resp.intent == q.intent,
        "actual_path": path,
        "path_match": path in expected_paths,
        "bot_answer": resp.answer,
        "bot_was_refusal": resp.is_refusal,
        "bot_refusal_trigger": resp.refusal_trigger,
        "bot_citations_count": len(resp.citations),
        "latency_ms": resp.latency_ms,
        "input_tokens": resp.tokens.get("input"),
        "cached_input_tokens": resp.tokens.get("cached_input"),
        "output_tokens": resp.tokens.get("output"),
    }


# --- The main eval loop ---------------------------------------------------


def run_eval(
    filter_category: Optional[str] = None,
    scope_only: bool = False,
) -> EvalReport:
    """Run the eval suite.

    With scope_only=True: only exercises src/scope/resolver.py (the
    legacy behavior).

    With scope_only=False (default): builds the full orchestrator wiring
    (real classifier + stub LLMs) and runs every gold question through
    `run_turn`, recording scope+intent+path accuracy per question.
    """
    questions = load_golden_set()
    if filter_category:
        questions = [q for q in questions if q.category == filter_category]

    report = EvalReport(total=len(questions))
    # Scope-match accuracy is measured EXCLUDING clarify-outcome cases:
    # those are ambiguous by design.
    scope_eligible = [q for q in questions if q.expected_outcome != "clarify"]

    classifier: Optional[IntentKNN] = None
    if not scope_only:
        classifier = _build_classifier()

    for q in questions:
        scope_match, ac_campus, ac_lib = _check_scope(q)
        eligible = q.expected_outcome != "clarify"
        if scope_match and eligible:
            report.scope_matches += 1

        result = EvalResult(
            question_id=q.id,
            category=q.category,
            scope_match=scope_match,
            actual_scope_campus=ac_campus,
            actual_scope_library=ac_lib,
            expected_path_set=frozenset(
                _OK_PATHS_BY_OUTCOME.get(q.expected_outcome, set())
            ),
        )

        if not scope_only and classifier is not None:
            # Build a FRESH deps bundle for every gold question. The
            # `CannedAgentLLM` stub is stateful (only requests
            # search_kb on its first call); reusing the same instance
            # across gold cases starves every subsequent turn of
            # evidence and produces spurious no_results refusals.
            # Per-turn construction is cheap (no I/O, no embeddings)
            # so this is the right shape.
            deps = _build_stub_deps(classifier)
            bot_out = _run_bot(q, deps)
            for k, v in bot_out.items():
                setattr(result, k, v)
            if result.intent_match:
                report.intent_matches += 1
            if result.path_match:
                report.path_matches += 1
            report.bot_called += 1

        report.results.append(result)
        cat = report.by_category.setdefault(
            q.category,
            {
                "total": 0,
                "scope_matches": 0,
                "intent_matches": 0,
                "path_matches": 0,
                "eligible": 0,
            },
        )
        cat["total"] += 1
        if eligible:
            cat["eligible"] += 1
            if scope_match:
                cat["scope_matches"] += 1
        # Intent/path counts include clarify-outcome cases (they have
        # their own expected_path of {"clarify"}).
        if result.intent_match:
            cat["intent_matches"] += 1
        if result.path_match:
            cat["path_matches"] += 1

    # Top-level scope total is eligible-only; bot total is everything.
    report.total = len(scope_eligible)
    return report


# --- Reporting ------------------------------------------------------------


def _print_report(report: EvalReport, verbose: bool, scope_only: bool) -> None:
    all_n = len(report.results)
    eligible_n = report.total
    print()
    print(
        f"Eval results: {all_n} total questions "
        f"({eligible_n} scope-eligible; {all_n - eligible_n} clarify-case, "
        f"excluded from scope gate)"
    )
    scope_pct = 100 * report.scope_matches / max(eligible_n, 1)
    print(f"  Scope-resolver matches: {report.scope_matches}/{eligible_n} ({scope_pct:.1f}%)")
    if not scope_only and report.bot_called:
        intent_pct = 100 * report.intent_matches / report.bot_called
        path_pct = 100 * report.path_matches / report.bot_called
        print(
            f"  Intent classification:  {report.intent_matches}/{report.bot_called} "
            f"({intent_pct:.1f}%)"
        )
        print(
            f"  Orchestrator path:      {report.path_matches}/{report.bot_called} "
            f"({path_pct:.1f}%)   "
            f"[expected_outcome -> {{point_to_url|agent_then_answer|...}}]"
        )

    print()
    if scope_only:
        print("Per-category scope match rate (eligible only):")
        for cat, data in sorted(report.by_category.items()):
            eligible = data.get("eligible", data["total"])
            if eligible == 0:
                print(f"  {cat:25s}  (all clarify-case, skipped)")
                continue
            rate = 100 * data["scope_matches"] / eligible
            print(f"  {cat:25s}  {data['scope_matches']:3d}/{eligible:3d}  ({rate:5.1f}%)")
    else:
        print("Per-category breakdown:")
        print(f"  {'category':25s}  {'scope':>10s} {'intent':>10s} {'path':>10s}")
        for cat, data in sorted(report.by_category.items()):
            n = data["total"]
            eligible = data.get("eligible", n)
            s = data["scope_matches"]
            i = data["intent_matches"]
            p = data["path_matches"]
            scope_str = f"{s:>3d}/{eligible:<3d}" if eligible else "(clar.)"
            print(
                f"  {cat:25s}  {scope_str:>10s} {i:>3d}/{n:<3d}    {p:>3d}/{n:<3d}"
            )

    if verbose:
        print()
        print("Mismatches:")
        for r in report.results:
            issues = []
            if not r.scope_match and r.expected_path_set != frozenset({"clarify"}):
                issues.append(f"scope={r.actual_scope_campus}/{r.actual_scope_library}")
            if r.intent_match is False:
                issues.append(f"intent={r.actual_intent}")
            if r.path_match is False:
                issues.append(f"path={r.actual_path}")
            if issues:
                print(f"  [{r.question_id}] {', '.join(issues)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the smart-chatbot eval suite.")
    parser.add_argument("--filter", help="Only run questions in this category.")
    parser.add_argument(
        "--scope-only", action="store_true",
        help="Only check src/scope/resolver.py; don't build the bot.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report = run_eval(
        filter_category=args.filter,
        scope_only=args.scope_only,
    )
    _print_report(report, verbose=args.verbose, scope_only=args.scope_only)

    # Gates:
    #   - scope_match_rate >= 0.90 (existing).
    #   - path_match_rate >= 0.65 in the wiring eval. The plan's 0.75
    #     target assumes LLM-as-judge against real bot output; with
    #     stub agent/synth, ~14 out_of_scope cases score against us
    #     unfairly (stub agent always answers; real LLM would refuse)
    #     and intent-classification misses propagate to path misses.
    #     65% is the regression tripwire for this phase; raise once
    #     the judge wires up (TODO at top of this file).
    scope_rate = report.scope_matches / max(report.total, 1)
    if args.scope_only:
        return 0 if scope_rate >= 0.90 else 1
    if report.bot_called == 0:
        return 0
    path_rate = report.path_matches / report.bot_called
    if scope_rate < 0.90:
        logger.error("scope match rate %.1f%% below 90%% gate", scope_rate * 100)
        return 1
    if path_rate < 0.65:
        logger.error(
            "path match rate %.1f%% below 65%% wiring-gate "
            "(real-LLM target is 75%%, blocked on judge wiring)",
            path_rate * 100,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
