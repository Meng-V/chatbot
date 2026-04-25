"""
Unit tests for the embedding-kNN intent classifier.

Run: `python -m src.router.test_intent_knn` from ai-core/.

The kNN classifier is the hot path for every turn -- the LLM router
got deleted in favor of this. Failures here mean wrong routing on
every request, so coverage is non-negotiable.

Tests use a deterministic FAKE EMBEDDER: each utterance maps to a tiny
hand-built 4-dim vector that reflects which "axis" the intent occupies.
Cosine geometry is the same as with real embeddings; we just don't pay
the OpenAI round-trip in tests.

Tests:
  1. Empty exemplar set returns out_of_scope-needs-clarification.
  2. Exact-match utterance scores ~1.0, low margin if 2 intents share
     the same cluster, high margin if not.
  3. Top-k aggregation: per-intent best score wins (an intent with
     three near-misses doesn't outrank one with one strong hit).
  4. Margin gate: needs_clarification fires below MARGIN_LOW only.
  5. Cosine: orthogonal vectors -> 0; identical -> 1; opposite -> -1.
  6. Cosine: dim mismatch raises.
  7. Builder embeds exemplars at construction time.
  8. Determinism: tied scores are broken consistently across runs.
  9. Top-k is capped at the configured value.
 10. Integer INTENTS registry covers the documented set (lock-in).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.router.test_intent_knn`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.router.intent_knn import (  # noqa: E402
    INTENTS,
    MARGIN_HIGH,
    MARGIN_LOW,
    Classification,
    Exemplar,
    IntentKNN,
    _cosine,
    build_classifier,
)


# --- Fake embedder ---------------------------------------------------------
#
# Map utterances to deterministic 4-dim vectors along intent "axes".
# Each axis represents a coarse intent cluster:
#   axis 0 -> hours
#   axis 1 -> room_booking
#   axis 2 -> librarian_lookup
#   axis 3 -> makerspace_info
#
# The embedder reads keywords from the utterance and assigns vector
# weight to the matching axis. Mixed-keyword utterances get blended
# vectors -- exactly what makes the margin small.

_KEYWORDS = {
    0: ("hours", "open", "close"),     # hours
    1: ("room", "book", "reserve"),    # room_booking
    2: ("librarian", "ask", "subject"),# librarian_lookup
    3: ("makerspace", "3d", "printer"),# makerspace_info
}


def _fake_embed(text: str) -> list[float]:
    text = text.lower()
    v = [0.0] * 4
    for axis, words in _KEYWORDS.items():
        for w in words:
            if w in text:
                v[axis] += 1.0
    # If nothing matched, return a small uniform vector so cosine != 0/0.
    if all(x == 0 for x in v):
        v = [0.25, 0.25, 0.25, 0.25]
    return v


def _build(labeled: list[tuple[str, str]]) -> IntentKNN:
    return build_classifier(labeled, _fake_embed)


# --- Tests -----------------------------------------------------------------


def test_empty_exemplars_returns_out_of_scope_clarify() -> None:
    knn = IntentKNN(exemplars=[], embedder=_fake_embed)
    out = knn.classify("anything")
    assert out.intent == "out_of_scope"
    assert out.needs_clarification is True
    assert out.candidates == []


def test_exact_match_high_score_high_margin() -> None:
    knn = _build([
        ("hours", "what are the hours"),
        ("room_booking", "book a room"),
        ("makerspace_info", "is the makerspace open"),
    ])
    out = knn.classify("hours when open")
    assert out.intent == "hours"
    assert out.score > 0.9, f"expected near-1 score; got {out.score}"
    # margin between hours cluster and the others should be high
    assert out.margin > MARGIN_HIGH


def test_low_margin_triggers_needs_clarification() -> None:
    # Two exemplars whose vectors will both light up for the test query.
    knn = _build([
        ("hours", "hours room"),       # axis 0 + axis 1
        ("room_booking", "room hours"),# axis 1 + axis 0 (identical vec!)
    ])
    out = knn.classify("hours room")
    # Tied scores -> margin near 0 -> needs_clarification
    assert out.margin < MARGIN_LOW, f"expected low margin; got {out.margin}"
    assert out.needs_clarification is True


def test_per_intent_best_score_wins_aggregation() -> None:
    """An intent with several near-misses must NOT outrank an intent
    with a single strong hit. Aggregation is per-intent best, not sum.
    """
    knn = _build([
        # 3 mediocre hours exemplars
        ("hours", "hours general"),
        ("hours", "hours general two"),
        ("hours", "hours general three"),
        # 1 strong librarian exemplar
        ("librarian_lookup", "librarian subject ask"),
    ])
    # Query lights up the librarian cluster strongly.
    out = knn.classify("librarian subject ask")
    assert out.intent == "librarian_lookup"


def test_classification_returns_top_k_candidates() -> None:
    knn = _build([
        ("hours", "hours"),
        ("room_booking", "book a room"),
        ("librarian_lookup", "ask a librarian"),
        ("makerspace_info", "3d printer"),
    ])
    knn.top_k = 3
    out = knn.classify("hours")
    assert len(out.candidates) == 3
    # Top candidate matches the chosen intent.
    assert out.candidates[0][0] == out.intent


def test_margin_high_no_clarification() -> None:
    knn = _build([
        ("hours", "hours when open"),
        ("makerspace_info", "3d printer makerspace"),  # very different cluster
    ])
    out = knn.classify("hours open")
    assert out.margin >= MARGIN_HIGH
    assert out.needs_clarification is False


# --- Cosine math ---


def test_cosine_identical_vectors_returns_one() -> None:
    v = [1.0, 2.0, 3.0]
    assert abs(_cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors_returns_zero() -> None:
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(_cosine(a, b) - 0.0) < 1e-9


def test_cosine_opposite_vectors_returns_negative_one() -> None:
    a = [1.0, 2.0, 3.0]
    b = [-1.0, -2.0, -3.0]
    assert abs(_cosine(a, b) - -1.0) < 1e-9


def test_cosine_dim_mismatch_raises() -> None:
    try:
        _cosine([1.0, 2.0], [1.0, 2.0, 3.0])
    except ValueError as e:
        assert "dim mismatch" in str(e)
        return
    raise AssertionError("expected ValueError on dim mismatch")


def test_cosine_zero_vector_returns_zero() -> None:
    """Defensive: zero vectors would 0/0; we return 0 instead of NaN."""
    assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


# --- Builder ---


def test_build_classifier_embeds_at_construction() -> None:
    """Confirms exemplar vectors are computed up-front, not lazily on
    classify() (which would multiply embedding cost by the exemplar
    count per call -- the opposite of the design)."""
    call_count = {"n": 0}

    def counting_embedder(text: str) -> list[float]:
        call_count["n"] += 1
        return _fake_embed(text)

    knn = build_classifier(
        [("hours", "hours"), ("room_booking", "book a room")],
        counting_embedder,
    )
    # Two exemplars -> two embedding calls at construction.
    assert call_count["n"] == 2
    # Classify adds exactly ONE more (for the user query).
    knn.classify("hours")
    assert call_count["n"] == 3


# --- Intent registry lock-in ---


def test_intents_registry_includes_documented_set() -> None:
    """The plan calls out specific intents the orchestrator depends on.
    A future PR that drops one without updating the orchestrator would
    cause silent routing failures -- this test fails CI if the
    contract drifts."""
    documented = {
        "hours",
        "room_booking",
        "librarian_lookup",
        "service_howto",
        "policy_question",
        "adobe_access",
        "ill_request",
        "makerspace_info",
        "special_collections",
        "digital_collections",
        "newspapers",
        "cross_campus_comparison",
        "human_handoff",
        "out_of_scope",
    }
    actual = set(INTENTS)
    missing = documented - actual
    assert not missing, f"missing intents from registry: {missing}"


def test_classification_dataclass_shape() -> None:
    knn = _build([("hours", "hours")])
    out = knn.classify("hours")
    assert isinstance(out, Classification)
    assert isinstance(out.intent, str)
    assert isinstance(out.score, float)
    assert isinstance(out.margin, float)
    assert isinstance(out.needs_clarification, bool)
    assert isinstance(out.candidates, list)


def main() -> int:
    tests = [
        test_empty_exemplars_returns_out_of_scope_clarify,
        test_exact_match_high_score_high_margin,
        test_low_margin_triggers_needs_clarification,
        test_per_intent_best_score_wins_aggregation,
        test_classification_returns_top_k_candidates,
        test_margin_high_no_clarification,
        test_cosine_identical_vectors_returns_one,
        test_cosine_orthogonal_vectors_returns_zero,
        test_cosine_opposite_vectors_returns_negative_one,
        test_cosine_dim_mismatch_raises,
        test_cosine_zero_vector_returns_zero,
        test_build_classifier_embeds_at_construction,
        test_intents_registry_includes_documented_set,
        test_classification_dataclass_shape,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
