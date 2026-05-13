"""
Measure intent-kNN classifier accuracy on the gold set.

This is the answer to "did the v38 librarian-labeled exemplars improve
routing accuracy?" -- it runs every gold question through the actual
classifier (real text-embedding-3-large embeddings, real cosine kNN)
and reports per-intent + per-category accuracy.

The eval-harness skeleton in `src/eval/run_eval.py` only covers scope
resolution today; the bot-orchestrator + judge wiring is still a TODO.
This script is the focused classifier-only measurement that doesn't
need any of that.

Cost / runtime:
  ~5,258 exemplars + ~213 gold questions = ~5,471 embedding calls.
  Batched at 100/call (OpenAI text-embedding-3-large supports up to
  2048 per batch but 100 keeps payloads small). With cache: subsequent
  runs are free.
  ~$0.05 first run; ~$0.001 for re-eval after cache hit.

Cache layout:
  data/eval/classifier_embeddings.json
    {"<sha256 of text>": [3072 floats]}
  Cache key is content-hash so utterance-text edits invalidate cleanly
  and reused texts (gold question that matches an exemplar verbatim)
  share one embedding.

Usage:
    python -m scripts.eval_classifier_v38                 # full gold set
    python -m scripts.eval_classifier_v38 --no-cache       # bypass cache
    python -m scripts.eval_classifier_v38 --top-misses 30 # report 30 worst
    python -m scripts.eval_classifier_v38 --filter cross_campus

See plan: Layer 3 -> Intent kNN classifier; Verification §2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Allow running as `python -m scripts.eval_classifier_v38` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

# Load .env so OPENAI_API_KEY is available before src.llm.client tries
# to construct the client. Done with a tiny parser to avoid adding a
# python-dotenv dep just for this script.
_ENV_PATH = _AI_CORE.parent / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402
from src.router.intent_knn import (  # noqa: E402
    Classification,
    Exemplar,
    INTENTS,
    IntentKNN,
)

logger = logging.getLogger("eval_classifier_v38")


# --- Embedding cache (content-hashed) ------------------------------------

_CACHE_PATH = _AI_CORE / "data" / "eval" / "classifier_embeddings.json"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("could not read cache (%s); starting fresh", e)
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    tmp.replace(_CACHE_PATH)


# --- Batched embedder ----------------------------------------------------


def _batched_embed(
    texts: list[str],
    cache: dict[str, list[float]],
    *,
    batch_size: int = 100,
    use_cache: bool = True,
) -> dict[str, list[float]]:
    """Embed each text, hitting the cache first; fresh calls are batched.

    Returns a `{text -> vector}` map. The cache is mutated in place and
    saved by the caller (so partial runs still persist progress).
    """
    from src.llm.client import _get_client

    out: dict[str, list[float]] = {}
    todo: list[str] = []
    for t in texts:
        h = _hash_text(t)
        if use_cache and h in cache:
            out[t] = cache[h]
        else:
            todo.append(t)

    if not todo:
        logger.info("all %d texts cached; no API calls needed", len(texts))
        return out

    logger.info(
        "embedding %d new texts in batches of %d (cache hit %d/%d)",
        len(todo), batch_size, len(texts) - len(todo), len(texts),
    )
    client = _get_client()
    t0 = time.time()
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        resp = client.embeddings.create(
            model="text-embedding-3-large",
            input=batch,
        )
        for text, item in zip(batch, resp.data):
            vec = list(item.embedding)
            out[text] = vec
            cache[_hash_text(text)] = vec
        if (i // batch_size) % 5 == 0:
            done = min(i + batch_size, len(todo))
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            logger.info("  embedded %d/%d (%.1f/s)", done, len(todo), rate)
    logger.info("embedding done in %.1fs", time.time() - t0)
    return out


# --- Exemplar loading ----------------------------------------------------


def _load_exemplars(path: Path) -> list[tuple[str, str]]:
    """Return (intent, utterance) pairs from exemplars.jsonl."""
    pairs: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            pairs.append((obj["intent"], obj["utterance"]))
    return pairs


# --- Eval runner ---------------------------------------------------------


def _build_classifier_with_cache(
    pairs: list[tuple[str, str]],
    embed_map: dict[str, list[float]],
) -> IntentKNN:
    """Build an IntentKNN whose vectors come from a precomputed map.

    `build_classifier` calls the embedder once per exemplar -- we already
    have all vectors batched, so build Exemplars directly and skip the
    re-call.
    """
    exemplars = [
        Exemplar(intent=intent, text=text, vector=embed_map[text])
        for intent, text in pairs
    ]
    # The embedder closure here is only used for the runtime classify()
    # call's query vector. We pass a lambda that hits the same map.
    def embedder(t: str) -> list[float]:
        return embed_map[t]
    return IntentKNN(exemplars=exemplars, embedder=embedder)


def run(
    *,
    use_cache: bool,
    filter_category: Optional[str],
    top_misses: int,
) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # 1. Load data
    exemplar_path = _AI_CORE / "src" / "router" / "exemplars" / "exemplars.jsonl"
    pairs = _load_exemplars(exemplar_path)
    logger.info("loaded %d exemplars from %s", len(pairs), exemplar_path)

    questions = load_golden_set()
    if filter_category:
        questions = [q for q in questions if q.category == filter_category]
    logger.info("loaded %d gold questions", len(questions))

    # 2. Embed everything (cache-aware, batched)
    cache = _load_cache() if use_cache else {}
    all_texts = list({t for _, t in pairs} | {q.question for q in questions})
    logger.info("unique texts to embed: %d", len(all_texts))
    embed_map = _batched_embed(all_texts, cache, use_cache=use_cache)
    if use_cache:
        _save_cache(cache)
        logger.info("cache saved to %s (%d entries)", _CACHE_PATH, len(cache))

    # 3. Build classifier
    knn = _build_classifier_with_cache(pairs, embed_map)
    logger.info("classifier built with %d exemplars", len(pairs))

    # 4. Classify each gold question
    correct = 0
    by_category_total: Counter = Counter()
    by_category_correct: Counter = Counter()
    by_intent_total: Counter = Counter()
    by_intent_correct: Counter = Counter()
    misses: list[tuple[GoldQuestion, Classification]] = []

    for q in questions:
        c = knn.classify(q.question)
        by_category_total[q.category] += 1
        by_intent_total[q.intent] += 1
        if c.intent == q.intent:
            correct += 1
            by_category_correct[q.category] += 1
            by_intent_correct[q.intent] += 1
        else:
            misses.append((q, c))

    # 5. Report
    total = len(questions)
    acc = correct / max(total, 1)
    print()
    print("=" * 70)
    print(f"Classifier accuracy: {correct}/{total} = {100 * acc:.1f}%")
    print(f"Exemplars: {len(pairs)} from {exemplar_path.name}")
    print("=" * 70)
    print()

    print("Per-category accuracy:")
    for cat in sorted(by_category_total):
        n = by_category_total[cat]
        k = by_category_correct[cat]
        rate = 100 * k / n
        print(f"  {cat:30s} {k:3d}/{n:3d} ({rate:5.1f}%)")

    print()
    print("Per-expected-intent accuracy (only intents in gold set):")
    for intent in sorted(by_intent_total):
        n = by_intent_total[intent]
        k = by_intent_correct[intent]
        rate = 100 * k / n
        marker = "" if rate == 100 else (" *" if rate < 50 else "")
        print(f"  {intent:30s} {k:3d}/{n:3d} ({rate:5.1f}%){marker}")

    if misses:
        print()
        print(f"Top {min(top_misses, len(misses))} misclassifications "
              f"(of {len(misses)} total):")
        # Sort by lowest margin first (most ambiguous failures are most
        # interesting; high-margin wrong answers are bigger bugs).
        sorted_misses = sorted(misses, key=lambda m: m[1].margin)
        for q, c in sorted_misses[:top_misses]:
            top3 = ", ".join(
                f"{i}({s:.2f})" for i, s in c.candidates[:3]
            )
            print(f"  [{q.id}] expected={q.intent!r}  got={c.intent!r}  "
                  f"margin={c.margin:.2f}")
            print(f"    Q: {q.question}")
            print(f"    top-3: {top3}")

    # 6. Confusion summary -- which expected intent is most often
    # confused with what wrong intent?
    confusion: dict[str, Counter] = defaultdict(Counter)
    for q, c in misses:
        confusion[q.intent][c.intent] += 1
    if confusion:
        print()
        print("Confusion summary (expected -> most-frequent wrong intent):")
        for expected, wrong_counter in sorted(confusion.items()):
            wrong, n = wrong_counter.most_common(1)[0]
            print(f"  {expected:30s} -> {wrong:30s} ({n}x)")

    # Gate: classifier accuracy >= 0.85 is a reasonable v0 floor.
    return 0 if acc >= 0.85 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Force fresh embedding calls (don't read or write cache).",
    )
    parser.add_argument(
        "--filter", help="Only run gold questions in this category.",
    )
    parser.add_argument(
        "--top-misses", type=int, default=20,
        help="How many misclassifications to print in detail (default 20).",
    )
    args = parser.parse_args()
    return run(
        use_cache=not args.no_cache,
        filter_category=args.filter,
        top_misses=args.top_misses,
    )


if __name__ == "__main__":
    sys.exit(main())
