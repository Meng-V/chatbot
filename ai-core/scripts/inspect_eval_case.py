"""
Gold-set audit tool: read each gold case against the live Miami site.

The gold set (`ai-core/src/eval/golden_set.jsonl`) is the answer key
the eval scores the bot against. It's hand-written, so it has bugs
(e.g. the makerspace / room-booking errors found 2026-05-14/15). This
tool surfaces one or more gold cases so a human can verify the
`expected_answer` + `allowed_urls` actually match what
lib.miamioh.edu / libguides.* / ham.* / mid.* say today.

Two modes:
  - default: prints the gold case only. No LLM, no Weaviate, ~$0,
    instant. Use this to eyeball expected-answer correctness.
  - `--live`: also runs REAL Weaviate retrieval for the question and
    prints the top-k chunks the bot would actually see. Requires the
    SSH tunnel + a populated index. Distinguishes a gold-set bug
    (wrong expected answer) from a corpus gap (right gold, the ETL
    just didn't crawl the page).

When the gold is wrong: capture the truth in
`ai-core/docs/canonical/` and file the correction.

Usage:
    python -m scripts.inspect_eval_case --id svc_print_color
    python -m scripts.inspect_eval_case --category cross_campus --limit 5
    python -m scripts.inspect_eval_case --intent makerspace_3d --live
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Optional

# Allow running as `python -m scripts.inspect_eval_case` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.golden_set import GoldQuestion, load_golden_set  # noqa: E402


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.fill(
        text, width=86,
        initial_indent=indent, subsequent_indent=indent,
    )


def _live_chunks(q: GoldQuestion, k: int) -> list[dict]:
    """Run REAL Weaviate retrieval for this gold question (requires the
    SSH tunnel + a populated index). Returns the top-k hit dicts so a
    human can eyeball whether the corpus actually has the content the
    gold expects. Empty list on any failure."""
    try:
        from src.retrieval.scope_filter import ScopeFilter
        from src.retrieval.search import RetrievalRequest, search_kb
        from src.scope.resolver import resolve_scope
        from src.weaviate_adapters.search_adapter import WeaviateSearchAdapter

        s = resolve_scope(
            q.question,
            session_origin_campus=q.needs_session_origin,  # type: ignore[arg-type]
        )
        scope = ScopeFilter(campus=s.campus, library=s.library)
        result = search_kb(
            RetrievalRequest(query=q.question, scope=scope, k=k),
            weaviate=WeaviateSearchAdapter(),
            collection=None,  # WEAVIATE_CHUNK_COLLECTION env var
        )
        return [
            {
                "source_url": c.source_url,
                "score": round(c.score, 3),
                "text": (c.text[:300] + "...") if len(c.text) > 300 else c.text,
            }
            for c in result.chunks
        ]
    except Exception as e:  # noqa: BLE001
        print(f"  (live retrieval unavailable: {type(e).__name__}: {e})")
        return []


def _show(q: GoldQuestion, *, live: bool, k: int) -> None:
    """Pretty-print one gold case for human audit against the live
    Miami website. With `live=True`, also shows what real Weaviate
    retrieval returns so you can spot corpus gaps vs gold-set bugs."""
    bar = "─" * 90
    print(f"\n{bar}")
    print(f"  ID:        {q.id}")
    print(f"  category:  {q.category}")
    print(f"  intent:    {q.intent}")
    print(f"  outcome:   {q.expected_outcome}")
    print(f"  scope:     campus={q.scope_campus}, library={q.scope_library}")
    # session_origin is the field that EXPLAINS a non-Oxford scope on
    # a generic question. Surface it next to scope so "why is this
    # Hamilton when King is the default?" is answered inline, not a
    # mystery. Default scope = Oxford/King; session_origin OVERRIDES
    # that default when the chat widget is embedded on a regional
    # campus site (ham.miamioh.edu / mid.miamioh.edu).
    if q.needs_session_origin:
        print(f"  session_origin: {q.needs_session_origin}  "
              f"<-- OVERRIDES the Oxford/King default; scope is "
              f"{q.scope_campus} because the chat is simulated as "
              f"originating from the {q.needs_session_origin} campus site")
    else:
        print("  session_origin: (none)  -- scope came from the "
              "question text or the Oxford/King default")
    if q.notes:
        print(f"  notes:     {q.notes}")
    print(bar)

    print("\n  QUESTION (what the user asked):")
    print(_wrap(q.question))

    print("\n  GOLD EXPECTED ANSWER (what a librarian wrote -- audit THIS "
          "against the live site):")
    print(_wrap(q.expected_answer or "(none)"))

    if q.allowed_urls:
        print("\n  ALLOWED URLS (gold says these are the only URLs the bot "
              "may cite -- verify they're live + canonical, not redirects):")
        for u in q.allowed_urls:
            print(f"    - {u}")

    if live:
        print(f"\n  LIVE RETRIEVAL (top-{k} real chunks the bot would "
              f"actually see):")
        chunks = _live_chunks(q, k)
        if not chunks:
            print("    (no chunks returned -- corpus gap OR scope filter "
                  "too strict OR tunnel down)")
        for i, c in enumerate(chunks, 1):
            print(f"    [{i}] score={c['score']}  {c['source_url']}")
            print(_wrap(c["text"], indent="        "))
    else:
        print("\n  (run with --live to see the real retrieved chunks; "
              "requires the SSH tunnel + populated Weaviate)")

    if q.expected_outcome == "refusal":
        print("\n  NOTE: gold expects a refusal here -- confirm the question "
              "is genuinely unanswerable (out-of-scope / no corpus content / "
              "service-not-at-this-building), NOT just thin retrieval.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument(
        "--id", nargs="*", default=None,
        help="One or more gold case ids to inspect (e.g. svc_print_color).",
    )
    p.add_argument(
        "--category", default=None,
        help="Filter to a single gold category (e.g. service, featured_service).",
    )
    p.add_argument(
        "--intent", default=None,
        help="Filter to gold cases with this expected intent (e.g. hours).",
    )
    p.add_argument(
        "--outcome", choices=["answer", "refusal", "clarify"], default=None,
        help="Filter to gold cases with this expected outcome.",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N cases (handy with --category for a quick scan).",
    )
    p.add_argument(
        "--live", action="store_true",
        help=(
            "Also run REAL Weaviate retrieval per case to show the "
            "actual chunks the bot would see. Requires the SSH tunnel "
            "+ a populated index. Without this flag, only the gold "
            "case is shown (always works, no deps)."
        ),
    )
    p.add_argument(
        "-k", type=int, default=5,
        help="With --live: how many retrieved chunks to show (default 5).",
    )
    args = p.parse_args()

    questions = load_golden_set()

    if args.id:
        wanted = set(args.id)
        questions = [q for q in questions if q.id in wanted]
        missing = wanted - {q.id for q in questions}
        if missing:
            print(f"warning: ids not found in gold set: {sorted(missing)}",
                  file=sys.stderr)
    if args.category:
        questions = [q for q in questions if q.category == args.category]
    if args.intent:
        questions = [q for q in questions if q.intent == args.intent]
    if args.outcome:
        questions = [q for q in questions if q.expected_outcome == args.outcome]

    if not questions:
        print("no gold cases matched the filters", file=sys.stderr)
        return 1

    if args.limit:
        questions = questions[: args.limit]

    print(f"Inspecting {len(questions)} gold case(s)"
          f"{' [LIVE retrieval]' if args.live else ''}:")
    for q in questions:
        _show(q, live=args.live, k=args.k)

    print(f"\n{'─' * 90}")
    print(f"  Inspected: {len(questions)} case(s).")
    print(
        "  This is a GOLD-SET AUDIT tool. Read each case's expected "
        "answer + allowed URLs\n  against the live Miami website "
        "(lib.miamioh.edu / libguides.* / ham.* / mid.*).\n"
        "  When the gold is wrong, capture the truth in "
        "ai-core/docs/canonical/ and file the\n  correction. With "
        "--live you also see the real retrieved chunks, which "
        "distinguishes\n  a gold-set bug (wrong expected answer) from "
        "a corpus gap (right gold, missing crawl)."
    )
    print(f"{'─' * 90}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
