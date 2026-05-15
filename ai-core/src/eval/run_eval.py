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
from typing import Any, Optional

# Allow running as a script.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

# Load .env so OPENAI_API_KEY is available when --with-judge fires.
# Tiny inline parser avoids adding python-dotenv as a dependency.
_ENV_PATH = _AI_CORE.parent / ".env"
if _ENV_PATH.exists():
    import os as _os
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _k not in _os.environ:
            _os.environ[_k] = _v

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402
from src.eval.judge import (  # noqa: E402
    JudgeAggregate,
    JudgeParseError,
    JudgeRequest,
    Verdict,
    aggregate_verdicts,
    judge_answer,
)
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
from src.retrieval.scope_filter import ScopeFilter  # noqa: E402
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
    # Refusal stats (plan §verification 2: "refusal rate"):
    refusals_total: int = 0
    refusals_correct: int = 0
    """Refusals that match `gold.expected_outcome == 'refusal'`."""
    refusals_false_positive: int = 0
    """Refused when the gold expected an answer."""
    refusals_missed: int = 0
    """Didn't refuse when the gold expected a refusal."""
    by_refusal_trigger: Counter = field(default_factory=Counter)
    # Citation stats (plan §verification 2: "citation validity rate"):
    citations_total: int = 0
    """Number of citations emitted across all answers."""
    answers_with_citations: int = 0
    """Number of non-refusal answers that included at least one citation."""
    # LLM-as-judge aggregates (populated only when --with-judge is set
    # AND the response was non-stub i.e. capability-tier short-circuit).
    judge_aggregate: Optional[JudgeAggregate] = None
    judge_called: int = 0
    judge_skipped_stub: int = 0
    """Cases where the response was stubbed agent_then_answer/refusal,
    not worth judging because the answer is canned regardless of
    question. Tracked separately so the user knows the judge's
    coverage is partial in the wiring phase."""
    judge_errors: int = 0
    """JudgeParseError count -- the judge returned malformed JSON.
    Logged but doesn't stop the run."""
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


# --- LLM-as-judge wrapper -------------------------------------------------
#
# Implements the `JudgeLLM` Protocol against `src.llm.client.structured_
# completion`. The judge prompt prefix is `judge_v1` (registered in
# src/prompts/judge_v1.py). Strict JSON schema so the parsed output
# matches `Verdict`'s fields exactly.


_JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [
                "correct", "partial", "wrong",
                "refused_correctly", "refused_incorrectly",
                "answered_should_have_refused",
            ],
        },
        "reason": {"type": "string"},
        "citation_validity": {
            "type": "string",
            "enum": ["all_valid", "some_invalid", "no_citations", "n_a"],
        },
    },
    "required": ["verdict", "reason", "citation_validity"],
}


def _real_judge_llm(*, prefix_id: str, dynamic_suffix: str, model: str):
    """Real JudgeLLM impl that calls src.llm.client.structured_completion.

    Imported lazily so test runs don't pull in the OpenAI SDK. Returns
    `(parsed_dict, usage_dict)` per the JudgeLLM Protocol.
    """
    from src.llm.client import structured_completion
    parsed, usage = structured_completion(
        prefix_id=prefix_id,
        dynamic_suffix=dynamic_suffix,
        response_schema=_JUDGE_SCHEMA,
        schema_name="judge_verdict",
        model=model,
    )
    return parsed, {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "output_tokens": usage.output_tokens,
    }


# Stub-output detection: the synth stub always returns this exact
# answer text. When the bot's answer matches, the response is a
# canned stub and not worth running through a paid judge.
_STUB_ANSWER_MARKER = "King opens at 7am [1]."


def _is_stub_answer(answer: Optional[str]) -> bool:
    return bool(answer) and _STUB_ANSWER_MARKER in answer


# --- Real-LLM deps: real OpenAI + real Weaviate retrieval ---------------
#
# When --with-real-llm is set, the eval uses the production agent +
# synthesizer LLM defaults AND `WeaviateSearchAdapter` against the
# real indexed corpus. There is NO canned/synthetic evidence anymore
# (the old `_REALISTIC_EVIDENCE` map was deleted once real retrieval
# was wired -- it caused more confusion than it was worth: the synth
# was grounding on hand-written approximations instead of the actual
# crawled Miami content).
#
# Requires the server's Weaviate reachable. From a laptop, run with
# the SSH tunnel up (see ai-core/docs/canonical/ for the workflow).
#
# Cost when --with-real-llm:
#   ~$0.005 agent + ~$0.005 synth per turn = ~$1.80 for 184 cases
#   plus ~$0.02 per judge call if --with-judge = ~$3.70 total
# Filter to a category for cheaper iteration.


def _build_real_deps(
    classifier: IntentKNN,
    *,
    scope: "ScopeFilter",
    intent: str,
):
    """Build OrchestratorDeps that use REAL OpenAI LLMs AND real
    Weaviate retrieval (no stubs, no canned evidence).

    `search_kb` is wired to `WeaviateSearchAdapter` -> the same
    `Chunk_v*` collection the production bot reads (selected via the
    WEAVIATE_CHUNK_COLLECTION env var, defaulting to Chunk_current).
    Requires the server's Weaviate to be reachable -- run the eval
    with the SSH tunnel up if you're on a laptop.

    `scope` and `intent` are pre-resolved by the caller (same pattern
    the eval already uses for scope-match checking). The orchestrator
    re-resolves both internally and arrives at the same values
    (deterministic); we pass them here only so the search tool's
    scope filter + featured-service boost match the resolved turn.

    `load_url_allowlist` returns an empty set deliberately: the
    post-processor's URL validator accepts any URL that appears in
    the retrieval bundle's source_urls (see
    test_url_cited_not_in_allowlist_is_ok). Real retrieved chunks
    carry their real source_url, so citing them passes validation
    without needing UrlSeen populated on the eval host. Only
    *fabricated* URLs (not in any retrieved chunk) get rejected --
    exactly the behavior we want to measure.
    """
    from src.tools.search_kb_tool import make_search_kb_tool
    from src.weaviate_adapters.search_adapter import WeaviateSearchAdapter

    weav = WeaviateSearchAdapter()  # real v4 client via get_weaviate_client()
    registry = ToolRegistry()
    registry.register(make_search_kb_tool(
        weaviate=weav,
        scope=scope,
        intent=intent,
        collection=None,  # resolves WEAVIATE_CHUNK_COLLECTION at request time
    ))

    return OrchestratorDeps(
        classifier=classifier,
        tool_registry=registry,
        agent_llm=None,         # use _default_llm_call -> real OpenAI
        synthesizer_llm=None,   # ditto
        load_corrections=lambda: [],
        load_url_allowlist=lambda: set(),
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
        # Surface the full exception (incl. OpenAI 400 body) in the
        # message itself -- extra={} is dropped by the default formatter,
        # which is why "turn crashed" was previously opaque.
        body = ""
        for attr in ("response", "body"):
            obj = getattr(e, attr, None)
            if obj is not None:
                try:
                    body = f" | {attr}={obj.text if hasattr(obj, 'text') else obj}"
                except Exception:  # noqa: BLE001
                    body = f" | {attr}=<unreadable>"
                break
        logger.warning(
            "turn crashed id=%s %s: %s%s",
            q.id,
            type(e).__name__,
            str(e),
            body,
            exc_info=True,
        )
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
    with_judge: bool = False,
    with_real_llm: bool = False,
    judge_llm: Optional[Any] = None,
) -> EvalReport:
    """Run the eval suite.

    Args:
        filter_category: If set, only run gold cases in this category.
        scope_only: True -> only exercise src/scope/resolver.py (legacy mode).
        with_judge: True -> after each turn, run the LLM-as-judge against
            the bot's response. Skips cases where the response is
            stubbed (agent_then_answer / agent_then_refusal with the
            canned answer) -- judging stub output wastes money. With
            stubs only ~14 cases per full run get judged (capability-
            tier short-circuits). With --with-real-llm, every turn
            gets a real answer + a real judge verdict.
        with_real_llm: True -> use real OpenAI agent + synthesizer
            LLMs (no stubs) plus a realistic intent-keyed fake
            search_kb tool. Cost ~$0.01 per turn -> ~$1.80 for the
            full 184-case set, or scale by `--filter`. Required if
            you want LLM-as-judge to score real LLM behavior.
        judge_llm: Callable matching JudgeLLM Protocol. If None and
            with_judge=True, uses `_real_judge_llm` (calls OpenAI).
            Tests pass a stub.
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

    # Register the agent + synthesizer prompt prefixes if we're going
    # to call real LLMs. Modules register via `register_prefix()` at
    # import time. Without these imports, `src.llm.client` raises
    # PromptBuildError on first call.
    if with_real_llm:
        import src.prompts.agent_v1  # noqa: F401 -- registers prefix
        import src.prompts.synthesizer_v1  # noqa: F401

    # Resolve the judge LLM if needed. Import prompts/judge_v1 so the
    # prefix registers before any call. Late-import keeps non-judge
    # runs from paying for the openai/prompt-builder imports.
    judge_verdicts: list[Verdict] = []
    if with_judge:
        import src.prompts.judge_v1  # noqa: F401 -- registers prefix
        if judge_llm is None:
            judge_llm = _real_judge_llm

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
            if with_real_llm:
                # Pre-resolve scope + intent so the real search_kb
                # tool filters/boosts to the right campus/library/
                # featured-service for this turn. The orchestrator
                # re-resolves both internally (deterministic) and
                # arrives at the same values -- the pre-resolution
                # here only configures the tool, which is built once
                # per turn in deps. One redundant classify + scope
                # resolve; negligible vs the LLM cost.
                pre_classification = classifier.classify(q.question)
                _s = resolve_scope(
                    q.question,
                    session_origin_campus=q.needs_session_origin,  # type: ignore[arg-type]
                )
                _scope = ScopeFilter(campus=_s.campus, library=_s.library)
                deps = _build_real_deps(
                    classifier,
                    scope=_scope,
                    intent=pre_classification.intent,
                )
            else:
                deps = _build_stub_deps(classifier)
            bot_out = _run_bot(q, deps)
            for k, v in bot_out.items():
                setattr(result, k, v)
            if result.intent_match:
                report.intent_matches += 1
            if result.path_match:
                report.path_matches += 1
            report.bot_called += 1

            # Refusal accounting -- plan §verification 2.
            if result.bot_was_refusal:
                report.refusals_total += 1
                if result.bot_refusal_trigger:
                    report.by_refusal_trigger[result.bot_refusal_trigger] += 1
                if q.expected_outcome == "refusal":
                    report.refusals_correct += 1
                elif q.expected_outcome == "answer":
                    report.refusals_false_positive += 1
            elif q.expected_outcome == "refusal":
                report.refusals_missed += 1

            # Citation accounting -- plan §verification 2.
            if result.bot_citations_count:
                report.citations_total += result.bot_citations_count
                if not result.bot_was_refusal:
                    report.answers_with_citations += 1

            # LLM-as-judge -- plan §verification 2 ("automated scoring:
            # answer correctness LLM-as-judge"). Skipped for stub
            # output: judging "King opens at 7am [1]." against every
            # gold question would produce mostly-wrong verdicts that
            # tell us nothing about the bot's real behavior. Only run
            # against capability-tier templated responses where the
            # output reflects real bot logic.
            if with_judge and judge_llm is not None and result.bot_answer:
                if _is_stub_answer(result.bot_answer):
                    report.judge_skipped_stub += 1
                else:
                    judge_req = JudgeRequest(
                        question=q.question,
                        expected_answer=q.expected_answer,
                        bot_answer=result.bot_answer,
                        allowed_urls=q.allowed_urls,
                    )
                    try:
                        outcome = judge_answer(judge_req, judge_llm=judge_llm)
                        result.judge_verdict = outcome.verdict.verdict
                        judge_verdicts.append(outcome.verdict)
                        report.judge_called += 1
                    except JudgeParseError as e:
                        report.judge_errors += 1
                        logger.warning(
                            "judge parse failed for %s: %s", q.id, e,
                        )

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
    if with_judge:
        report.judge_aggregate = aggregate_verdicts(judge_verdicts)
    return report


# --- Stats helpers --------------------------------------------------------


def _percentile(values: list[int], pct: float) -> float:
    """Linear-interpolated percentile. Returns 0 for an empty list.
    Used for p50/p95 reporting of latency + token counts."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


# --- LLM-as-judge (TODO: wires up when real bot LLMs do) ------------------
#
# Plan §verification 2 calls for "answer correctness (LLM-as-judge)"
# alongside the other 4 metrics this report now produces. The judge
# would receive (gold question, gold expected_answer, bot answer) and
# return a verdict in {"correct", "partial", "wrong"}, plus
# "refusal_appropriate" / "refusal_wrong" for refusal cases.
#
# Two prerequisites that aren't met yet, both tracked elsewhere:
#
#   1. Real synthesizer LLM + real agent LLM, not stubs. Without them
#      the bot's answer is always "King opens at 7am [1]." regardless
#      of question, so a judge would correctly rate ~all non-refusal
#      cases as "wrong" -- producing a meaningless 0% accuracy score.
#      The synth/agent LLM protocols exist (src/llm/client.py +
#      completion_with_tools / structured_completion); wiring them
#      into the eval = a follow-up PR.
#   2. A populated Weaviate index. Real agent depends on real
#      retrieval. Today the ETL apply phase hasn't run.
#
# When both are in place, the judge wire-up is:
#
#     from src.llm.client import structured_completion
#     verdict, _ = structured_completion(
#         prefix_id="judge_v1",
#         dynamic_suffix=json.dumps({
#             "question": q.question,
#             "expected": q.expected_answer,
#             "actual": result.bot_answer,
#         }),
#         response_schema={
#             "type": "object",
#             "properties": {"verdict": {"enum": [
#                 "correct", "partial", "wrong",
#                 "refusal_appropriate", "refusal_wrong",
#             ]}},
#             "required": ["verdict"],
#         },
#     )
#     result.judge_verdict = verdict["verdict"]
#
# Cost: ~$0.01 per gold question with gpt-5.4-mini, single regression
# run = ~$2 for 184 cases.


# --- Reporting ------------------------------------------------------------


def _print_judge_block(report: EvalReport) -> None:
    """Render the judge-verdict section. Caller already gated on
    `report.judge_aggregate is not None`."""
    agg = report.judge_aggregate
    if agg is None:
        return
    print()
    print(f"LLM-as-judge verdicts ({report.judge_called} judged, "
          f"{report.judge_skipped_stub} skipped as stub output, "
          f"{report.judge_errors} parse errors):")
    if agg.total == 0:
        print("  (no eligible cases this run)")
        return
    print(f"  correct_rate (correct + refused_correctly): "
          f"{100 * agg.correct_rate:.1f}%")
    print(f"  citation_valid_rate (non-refusal answers):  "
          f"{100 * agg.citation_valid_rate:.1f}%")
    print("  by verdict:")
    for v, n in sorted(agg.by_verdict.items(), key=lambda kv: -kv[1]):
        print(f"    {v:35s} {n}")


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

        # Refusal stats. plan §verification 2 wants the rate visible
        # broken into "correct refusal" (gold expected one) vs "false
        # positive" (refused when gold wanted an answer) -- they're
        # very different failure modes operationally.
        print()
        print(f"Refusals: {report.refusals_total}/{report.bot_called} turns "
              f"({100 * report.refusals_total / report.bot_called:.1f}%)")
        print(f"  correct refusals:        {report.refusals_correct}")
        print(f"  false positives:         {report.refusals_false_positive}   "
              f"(refused when gold expected an answer)")
        print(f"  missed refusals:         {report.refusals_missed}   "
              f"(answered when gold expected a refusal)")
        if report.by_refusal_trigger:
            print("  by trigger:")
            for trigger, n in report.by_refusal_trigger.most_common():
                print(f"    {trigger:35s} {n}")

        # Citation stats.
        non_refusal_turns = report.bot_called - report.refusals_total
        if non_refusal_turns:
            cite_rate = 100 * report.answers_with_citations / non_refusal_turns
            print()
            print(f"Citations: {report.answers_with_citations}/{non_refusal_turns} "
                  f"non-refusal answers cited at least one source ({cite_rate:.1f}%)")
            print(f"  Total citations emitted: {report.citations_total}")

        # Cost + latency. Two histograms-of-one (p50/p95) per the plan's
        # eval-suite report shape. All-or-nothing skip if telemetry
        # wasn't recorded (e.g., the orchestrator crashed for a turn).
        latencies = [r.latency_ms for r in report.results if r.latency_ms is not None]
        inputs = [r.input_tokens or 0 for r in report.results if r.input_tokens is not None]
        cached = [r.cached_input_tokens or 0 for r in report.results if r.cached_input_tokens is not None]
        outputs = [r.output_tokens or 0 for r in report.results if r.output_tokens is not None]
        if latencies:
            print()
            print(f"Latency (ms): "
                  f"p50={_percentile(latencies, 50):.0f} "
                  f"p95={_percentile(latencies, 95):.0f} "
                  f"max={max(latencies)}")
        if inputs:
            cache_hit_pct = (100 * sum(cached) / sum(inputs)) if sum(inputs) else 0
            print(f"Tokens:  "
                  f"input p50={_percentile(inputs, 50):.0f} p95={_percentile(inputs, 95):.0f} "
                  f"sum={sum(inputs):,}")
            print(f"  cached input sum={sum(cached):,} "
                  f"(cache hit {cache_hit_pct:.1f}% -- plan §week-4 gate >=60%)")
            print(f"  output p50={_percentile(outputs, 50):.0f} p95={_percentile(outputs, 95):.0f} "
                  f"sum={sum(outputs):,}")

        # Judge block (only when --with-judge produced anything).
        if report.judge_aggregate is not None:
            _print_judge_block(report)

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
    parser.add_argument(
        "--with-judge", action="store_true",
        help=(
            "After each turn, run the LLM-as-judge against the bot's "
            "response (using `judge_v1` prompt + gpt-5.4-mini). Skips "
            "stubbed answers automatically. ~$0.02 per judged case."
        ),
    )
    parser.add_argument(
        "--with-real-llm", action="store_true",
        help=(
            "Use real OpenAI agent + synthesizer LLMs (no stubs). "
            "search_kb returns intent-keyed realistic-fake evidence. "
            "Cost ~$0.01 per turn. Required if you want --with-judge "
            "to score real LLM behavior instead of stub output."
        ),
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
        with_judge=args.with_judge,
        with_real_llm=args.with_real_llm,
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
