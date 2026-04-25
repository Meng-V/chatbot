"""
Embedding-nearest-neighbor intent classifier.

Replaces the 4-stage router (heuristics -> Weaviate -> margin -> LLM
triage) with a single cheap call: embed the user message, cosine-
nearest-neighbor against ~50 labeled exemplar utterances, return the
top intent and a confidence margin.

Why this shape:
  - One embedding call per turn (~$0.00001 with text-embedding-3-large)
    instead of one LLM triage per turn (~$0.005). Two orders of
    magnitude cheaper.
  - Deterministic. The exemplar set is data, not code; adding a
    misclassified utterance to the exemplar set fixes future
    misclassifications without retraining.
  - Easy to debug. When a query routes wrong, the top-k nearest
    exemplars are an immediately-actionable explanation.

Confidence handling:
  - margin = top-1 score - top-2 score
  - margin >= MARGIN_HIGH        -> route directly
  - MARGIN_LOW <= margin < HIGH -> route, but flag low-margin in
                                    telemetry (don't ask the user)
  - margin < MARGIN_LOW          -> ask the user a clarification with
                                    the top-2 candidates as buttons

The two thresholds are intentional: most "did you mean" UIs are
infuriating because they fire on every borderline case. We only
bother the user when the classifier is genuinely confused.

See plan:
  - Layer 3 -> "Intent kNN classifier"
  - Layer 3 -> "Confidence gates"

Status: SCAFFOLD. The classifier itself is fully implemented (cosine
math is trivial), but it's gated on:
  1. An exemplar set per intent (lives in src/router/exemplars/).
     Empty initially; week 3 work to populate from LibChat transcripts.
  2. An embedder. Wired through as a Protocol so tests inject a fake
     and the real OpenAI embedder lands when src/llm/client.py does
     (gated by the model freshness rule).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol


# --- Public types ---------------------------------------------------------


@dataclass(frozen=True)
class Exemplar:
    """One labeled utterance + its precomputed embedding.

    Embeddings are computed ONCE at startup (or via an offline cache
    file) and held in memory. The exemplar set is small (~350 items at
    50 per intent across 7 intents) so this is well under 10MB even
    with text-embedding-3-large at 3072 dims.
    """

    intent: str
    text: str
    vector: list[float]


@dataclass(frozen=True)
class Classification:
    """The result of one classify() call.

    `margin` is top-1 minus top-2 cosine score. Used by the orchestrator
    to decide between (a) routing directly, (b) routing-with-warning,
    or (c) asking the user to disambiguate via clarification chips.
    """

    intent: str
    score: float
    margin: float
    needs_clarification: bool
    candidates: list[tuple[str, float]]
    """Top-k (intent, score) pairs for telemetry / debug. Includes the
    chosen intent at index 0."""


# --- Thresholds -----------------------------------------------------------
#
# Tuned values from the plan ("Margin > 0.10 -> route directly. Margin
# < 0.10 -> return clarification chips"). Kept as module-level constants
# so they're trivially adjustable per the eval-suite results -- DO NOT
# bury these in code paths.

MARGIN_HIGH = 0.10
"""Above this margin, classifier is confident -- route without warning."""

MARGIN_LOW = 0.05
"""Below this margin, classifier is uncertain -- ask the user."""


# --- Embedder seam --------------------------------------------------------


class Embedder(Protocol):
    """Minimal interface the classifier needs from an embedding provider.

    The real implementation lives in src/llm/client.py and wraps OpenAI
    text-embedding-3-large. Tests pass a fake that returns canned
    vectors. Kept Protocol so neither side imports the other.
    """

    def __call__(self, text: str) -> list[float]:
        """Return the embedding vector for `text`."""
        ...


# --- Math (pure) ----------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. No numpy dep -- the vectors are small enough
    (a few thousand dims, run once per turn) that the pure-python loop
    is fast enough and avoids dragging numpy into a hot path that
    doesn't need it. If we ever batch-classify, switch to numpy.
    """
    if len(a) != len(b):
        raise ValueError(f"vector dim mismatch: {len(a)} vs {len(b)}")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# --- Classifier -----------------------------------------------------------


@dataclass
class IntentKNN:
    """Holds the exemplar set and classifies user messages against it.

    Construct once at app startup (`build_classifier(...)` below).
    `classify(user_message)` runs one embedding call + a linear scan of
    exemplars. Memory: O(n_exemplars * dim). CPU: O(n_exemplars * dim)
    per call. For the planned ~350 exemplars * 3072 dims, that's a
    one-millisecond inner loop -- no need for an ANN index.
    """

    exemplars: list[Exemplar]
    embedder: Embedder
    top_k: int = 5

    def classify(self, user_message: str) -> Classification:
        """Classify a single user message.

        Returns the nearest-neighbor intent plus margin, plus the top-k
        for telemetry / debugging. Empty exemplar set returns a
        synthetic out_of_scope-needs-clarification result so the
        upstream orchestrator can degrade gracefully during initial
        rollout when exemplars are still being collected.
        """
        if not self.exemplars:
            return Classification(
                intent="out_of_scope",
                score=0.0,
                margin=0.0,
                needs_clarification=True,
                candidates=[],
            )

        query_vec = self.embedder(user_message)
        scored = [
            (ex.intent, _cosine(query_vec, ex.vector), ex.text)
            for ex in self.exemplars
        ]
        # Sort by score descending; tiebreak by exemplar index for
        # determinism (otherwise tied-score reorderings flap).
        scored.sort(key=lambda t: (-t[1],))

        # Aggregate to per-intent best score (kNN with k=1 per intent).
        # An intent with three near-misses shouldn't outrank an intent
        # with one strong hit.
        per_intent_best: dict[str, float] = {}
        for intent, score, _ in scored:
            if intent not in per_intent_best or score > per_intent_best[intent]:
                per_intent_best[intent] = score

        ranked = sorted(
            per_intent_best.items(), key=lambda kv: -kv[1]
        )[: self.top_k]

        top_intent, top_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - runner_up_score

        return Classification(
            intent=top_intent,
            score=top_score,
            margin=margin,
            needs_clarification=margin < MARGIN_LOW,
            candidates=ranked,
        )


# --- Builder --------------------------------------------------------------


def build_classifier(
    labeled_utterances: list[tuple[str, str]],
    embedder: Embedder,
) -> IntentKNN:
    """Build a classifier by embedding every exemplar utterance up front.

    Args:
        labeled_utterances: list of (intent_label, utterance_text).
        embedder: callable matching the Embedder protocol.

    Returns:
        A ready-to-classify IntentKNN.

    Performance: one embedding call per exemplar, batched at the call
    site if the embedder supports it. For ~350 exemplars this is a
    few seconds of startup cost paid once -- not worth caching unless
    cold starts become a problem.
    """
    exemplars = [
        Exemplar(intent=intent, text=text, vector=embedder(text))
        for intent, text in labeled_utterances
    ]
    return IntentKNN(exemplars=exemplars, embedder=embedder)


# --- Disk-backed exemplar loader ------------------------------------------


_EXEMPLARS_PATH = (
    __import__("pathlib").Path(__file__).parent / "exemplars" / "exemplars.jsonl"
)
"""Where the labeled exemplar JSONL lives. Built by
scripts/build_exemplars_jsonl.py from the librarian-labeled CSV.
Returns an empty list if the file doesn't exist yet (graceful early-
launch behavior; the classifier returns out_of_scope-needs-clarify
on every call until exemplars are populated)."""


def load_exemplars_from_disk(
    path: "Optional[__import__('pathlib').Path]" = None,
) -> list[tuple[str, str]]:
    """Read labeled exemplars from the JSONL file produced by
    scripts/build_exemplars_jsonl.py.

    Returns a list of (intent, utterance) tuples ready to pass to
    `build_classifier()`. Returns an empty list if the file doesn't
    exist -- callers fall through to the empty-classifier degradation
    path.
    """
    import json
    from pathlib import Path

    p = path if path is not None else _EXEMPLARS_PATH
    if not p.exists():
        return []
    out: list[tuple[str, str]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            obj = json.loads(line)
            intent = obj.get("intent", "")
            utterance = obj.get("utterance", "")
            if not intent or not utterance:
                continue
            out.append((intent, utterance))
    return out


# --- Intent registry ------------------------------------------------------
#
# The canonical list of intent labels the classifier may return.
# Keeping it here (not in a YAML file) means typos in
# orchestrator code are caught at import time.

INTENTS: tuple[str, ...] = (
    # Lookup intents (data-shaped answers, structured responses)
    "hours",
    "room_booking",
    "librarian_lookup",
    "service_howto",
    "policy_question",
    # Featured services -- separate intents so retrieval can boost
    # featured_service-tagged chunks without an extra classifier pass
    "adobe_access",
    "ill_request",
    "makerspace_info",
    "special_collections",
    "digital_collections",
    "newspapers",
    # Cross-campus -- explicit intent so the orchestrator knows to
    # run retrieval per-campus and merge
    "cross_campus_comparison",
    # Routing intents
    "human_handoff",
    "out_of_scope",
)


__all__ = [
    "Classification",
    "Embedder",
    "Exemplar",
    "INTENTS",
    "IntentKNN",
    "MARGIN_HIGH",
    "MARGIN_LOW",
    "build_classifier",
]
