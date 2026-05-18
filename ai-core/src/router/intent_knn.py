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

MARGIN_LOW = 0.03
"""Below this margin, classifier is uncertain -- ask the user.

Lowered 0.05 -> 0.03 from the 2026-05-17 full eval. 34/184 turns
(18.5%) hit the clarification chip; in 18 of those the classifier had
ALREADY picked the gold-correct intent (`actual_intent == gold_intent`)
and bounced only because the #1/#2 *intent* margin was <0.05. Those
pairs were semantically ADJACENT library topics (ILL~circulation,
tech_checkout~adobe, databases~digital_collections, loan_policy~
account) -- a thin margin there is topic adjacency the single
tool-calling agent handles fine, not genuine user ambiguity. The plan
requires clarification to be RARE and scope/building-bound, so 18.5%
is a defect. 0.03 is a conservative, monotonic step (strictly fewer
needless chips, no exemplar overfitting). The precise final value /
a high-confidence-score bypass is to be calibrated from the new
`clf_score`/`clf_margin`/`clf_candidates` eval telemetry on the next
run -- this constant stays the single tuning knob, never buried."""

SCORE_FLOOR = 0.50
"""Absolute top-1 cosine-similarity floor. Below this, NO exemplar is
genuinely close to the user message -- the message isn't about the
library at all. Override the kNN's "best of 38" to out_of_scope.

Calibrated against the gold-set eval (see findings/2026-05-13_v38_
classifier.md): real library questions, even ones routed to the wrong
intent, score >=0.50 against some exemplar. Off-topic questions
("Do my homework", "What's the score of the Bengals game") score
0.40-0.45 because no exemplar is genuinely about that topic.

Without this floor the classifier picks a best-of-38 even when
nothing matches -- a textbook closed-set classifier failure on
open-world inputs. With the floor, the bot refuses cleanly instead
of confidently mis-routing."""


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

        # Absolute-score floor: if NO exemplar is genuinely close, the
        # message isn't a library question. Override the closed-set
        # best-of-38 to out_of_scope. We do this AFTER computing margin
        # so telemetry still records the (suppressed) intent guess and
        # margin -- helps tune SCORE_FLOOR against real traffic.
        if top_score < SCORE_FLOOR:
            return Classification(
                intent="out_of_scope",
                score=top_score,
                margin=margin,
                # `needs_clarification=False` -- we're CONFIDENT this is
                # off-topic, not unsure between two intents. The
                # refusal flow handles this; clarification chips would
                # only confuse the user ("did you mean: hours / room /
                # databases?" for a sports question).
                needs_clarification=False,
                candidates=ranked,
            )

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


_EXEMPLARS_DIR = (
    __import__("pathlib").Path(__file__).parent / "exemplars"
)
_EXEMPLARS_PATH = _EXEMPLARS_DIR / "exemplars.jsonl"
"""Where the labeled exemplar JSONL lives. Built by
scripts/pack_labeled_v38.py from the librarian-labeled CSV.

The loader globs `exemplars*.jsonl` in this directory, so synthetic
supplements (e.g. `exemplars_synthetic_v38.jsonl` filling thin-tail
intents) merge in automatically without code changes. Returns an
empty list if no files exist yet (graceful early-launch behavior;
the classifier returns out_of_scope-needs-clarify on every call
until exemplars are populated)."""


def load_exemplars_from_disk(
    path: "Optional[__import__('pathlib').Path]" = None,
) -> list[tuple[str, str]]:
    """Read labeled exemplars from the JSONL files in the exemplars dir.

    Files matching `exemplars*.jsonl` (lexicographic order so loads
    are deterministic) are concatenated. Comments (lines starting
    with `//`) and blank lines are skipped.

    Args:
        path: Optional override -- if a single file, reads just that
            file; if a directory, globs `exemplars*.jsonl` inside.
            Default: the exemplars/ subdir adjacent to this module.

    Returns:
        A list of (intent, utterance) tuples ready to pass to
        `build_classifier()`. Empty list if no files exist -- callers
        fall through to the empty-classifier degradation path.
    """
    import json
    from pathlib import Path

    out: list[tuple[str, str]] = []

    if path is not None:
        # Caller-specified path: single file or single directory.
        p = Path(path)
        if p.is_dir():
            files = sorted(p.glob("exemplars*.jsonl"))
        elif p.exists():
            files = [p]
        else:
            return []
    else:
        # Default: glob the canonical directory.
        if not _EXEMPLARS_DIR.exists():
            return []
        files = sorted(_EXEMPLARS_DIR.glob("exemplars*.jsonl"))

    for f_path in files:
        with open(f_path, encoding="utf-8") as f:
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
#
# Grounded in the real service taxonomy at lib.miamioh.edu/use/ and
# /research/. Replaces the previous 14-intent set whose `ill_request`
# bucket was over-broad (catching circulation questions like "will I
# get a confirmation when I place a hold").
#
# Granularity choice: 38 intents. Each maps to a distinct service or
# answer-shape on the website. Refined from the earlier 31-intent set
# after librarian review of 6,236 real LibChat transcripts surfaced
# 7 services that didn't fit any existing bucket:
#
#   - remote_access         (352 real cases -- the largest gap by far;
#                            users hit proxy / EZproxy errors)
#   - website_feedback      (46 cases -- broken links / wrong content)
#   - scholarly_publishing  (41 cases -- Scholarly Commons, IR deposit)
#   - library_employment    (38 cases -- jobs at the library)
#   - copyright_permissions (14 cases -- distinct from citation_help)
#   - av_production         (14 cases -- distinct from tech_checkout)
#   - accessibility_services (9 cases -- ADA accommodations)
#
# See ai-core/src/router/exemplars/INTENT_GUIDE.md for the full
# definition table + priority rules + tie-breaks.

INTENTS: tuple[str, ...] = (
    # --- Lookup (info-shaped answers) ---
    "hours",
    "location_directions",
    "staff_lookup",
    "subject_librarian",

    # --- Borrow / circulation ---
    # Distinct from interlibrary_loan: this covers Miami-OWNED items
    # (placing a hold, "did the request go through", checkout
    # confirmations). Real ILL is when Miami doesn't have the item.
    "circulation_basic",
    "renewal",
    "loan_policy",
    "account",
    "interlibrary_loan",  # OhioLINK / ILLiad / WorldCat ONLY
    "course_reserves",
    "find_resource",      # "do you have X" -> catalog search

    # --- Spaces ---
    "room_booking",
    "space_info",         # silent floor / group study / where is the cafe
    "makerspace_3d",      # MakerSpace + 3D printing (high-value featured)

    # --- Technology ---
    "printing_wifi",
    "tech_checkout",      # laptops / chargers / calculators / cameras
    "software_access",    # software available on lib computers / checkout
    "adobe_access",       # Adobe-specific (high-volume, distinct flow)
    "av_production",      # podcast/video studios, recording, media-creation
                          # workflow (distinct from tech_checkout: equipment
                          # borrowing vs end-to-end production support)

    # --- Research ---
    "databases",          # JSTOR/EBSCO/PubMed -- which db to use, A-Z list
    "citation_help",      # APA / MLA / Chicago / Zotero
    "research_consultation",  # research appointment, topic narrowing,
                              # source strategy, meet a librarian
    "data_services",      # GIS / R / Python / data viz / research data
    "digital_collections",
    "special_collections",
    "newspapers",
    "remote_access",      # EZproxy / off-campus database access /
                          # 401-403 errors / VPN-shaped questions.
                          # CRITICAL: distinct from `databases` --
                          # "Do you have JSTOR?" = databases;
                          # "How do I get into JSTOR from home?" = remote_access.
    "copyright_permissions",  # fair use, permission to reuse, public
                              # domain, TEACH Act. Distinct from
                              # citation_help -- "How do I cite?" vs
                              # "Am I allowed to use this?"
    "scholarly_publishing",   # Scholarly Commons, IR deposit, author
                              # rights, open access, thesis/diss deposit

    # --- Other ---
    "events_news",        # upcoming events, exhibits, library news
    "instruction_request",  # faculty asking for a library session for their class
    "accessibility_services",  # ADA, accommodations, alt formats
    "library_employment",      # student/staff/faculty jobs at the libraries
    "website_feedback",        # broken links, form errors, incorrect content,
                               # chatbot feedback. Bot can't fix; route to
                               # webmaster.
    "service_howto",      # generic "how do I X" catch-all when no more
                          # specific intent fits. Fallback only.
    "cross_campus_comparison",
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
    "SCORE_FLOOR",
    "build_classifier",
]
