"""
Synthesizer-alone quality eval (no Weaviate, no classifier needed).

Why this exists right now: the full `--with-real-llm` eval needs
Weaviate up (the classifier loads exemplar embeddings from it). With
the Weaviate server under construction, we can't run the 184-case
gold suite. But we CAN still measure the riskiest LLM component --
the synthesizer -- by giving it hand-curated evidence bundles
(simulating "good retrieval") and watching its real output.

What this proves: GIVEN good retrieval, does the synthesizer produce
grounded, cited, contract-respecting answers? If yes, then bugs in
the live system are likely retrieval bugs, not synth bugs. If no, the
synth contract has a hole and Weaviate fixes won't help.

What this does NOT prove: retrieval quality. That requires real
Weaviate + the full gold suite. Run `src.eval.run_eval --with-real-llm
--with-judge` once Weaviate is back.

Cost: ~$0.05/case (synth on mini + judge on nano, both cached). 6
cases = ~$0.30.

Cases (hand-picked for coverage + tractability):

  1. fs_makerspace_3d        -- featured service, evidence-grounded answer
  2. fs_nyt_subscription     -- featured service, "yes we have it" with URL
  3. fs_ill_oxford           -- point-to-url contract (don't roleplay)
  4. fs_adobe_unspecified    -- ambiguous audience, should clarify
  5. fs_special_collections  -- King-only, appointment-based
  6. tech_borrow_laptop      -- generic service answer

Run:
    .venv/bin/python -m scripts.eval_synth_alone
    .venv/bin/python -m scripts.eval_synth_alone --filter makerspace
    .venv/bin/python -m scripts.eval_synth_alone --out /tmp/synth_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _load_env() -> None:
    from dotenv import load_dotenv
    here = Path(__file__).resolve().parent
    load_dotenv(here.parent.parent / ".env")


# Late imports so --help works without OpenAI key set.
def _imports() -> dict[str, Any]:
    # Importing the prompt modules triggers their register_prefix()
    # side effects -- without these the builder doesn't know the prefix ids.
    import src.prompts.synthesizer_v1  # noqa: F401
    import src.prompts.judge_v1  # noqa: F401

    from src.synthesis.synthesizer import synthesize, SynthesisRequest, SynthesisResult
    from src.synthesis.corrections import EvidenceChunk
    from src.eval.judge import judge_answer, JudgeRequest
    from src.llm.client import structured_completion
    from src.config.models import resolve_model
    return locals()


# --- The 6 hand-curated cases --------------------------------------------


@dataclass
class SynthCase:
    id: str
    question: str
    scope_campus: str
    scope_library: Optional[str]
    expected_answer: str
    allowed_urls: list[str]
    evidence: list[dict]  # list of EvidenceChunk kwargs


CASES: list[SynthCase] = [
    SynthCase(
        id="fs_makerspace_3d",
        question="Does Miami University Libraries have a MakerSpace with 3D printing?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Yes -- the MakerSpace is in King Library on the Oxford campus and "
            "includes 3D printers among its equipment. Cite the MakerSpace LibGuide."
        ),
        allowed_urls=[
            "https://libguides.lib.miamioh.edu/create/makerspace/home",
            "https://www.lib.miamioh.edu/about/locations/king-library/",
        ],
        evidence=[
            {
                "chunk_id": "ms_home_1",
                "source_url": "https://libguides.lib.miamioh.edu/create/makerspace/home",
                "text": (
                    "The MakerSpace at King Library is a hands-on creative space "
                    "open to all Miami students, faculty, and staff. Equipment "
                    "available includes 3D printers (Prusa, Bambu), vinyl cutters, "
                    "sewing machines, button makers, and a laser cutter. Located "
                    "on the first floor of King Library, Oxford campus. Walk-ins "
                    "welcome during open hours; consultations available for "
                    "complex projects."
                ),
                "campus": "oxford",
                "library": "king",
                "topic": "spaces",
                "featured_service": "makerspace",
            },
        ],
    ),
    SynthCase(
        id="fs_nyt_subscription",
        question="Does the library have a New York Times subscription I can use?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Yes -- Miami University Libraries provides NYT access. The "
            "activation page is at the cited URL. Note: NYT activation must be "
            "done from on-campus / via Miami network."
        ),
        allowed_urls=[
            "https://libguides.lib.miamioh.edu/newspapers/nyt",
        ],
        evidence=[
            {
                "chunk_id": "nyt_1",
                "source_url": "https://libguides.lib.miamioh.edu/newspapers/nyt",
                "text": (
                    "Miami University Libraries provides New York Times (NYTimes.com) "
                    "academic access to current Miami students, faculty, and staff. "
                    "To activate: visit accessNYT.com from a Miami campus network OR "
                    "use the Miami VPN, then create / link your NYT account using "
                    "your @miamioh.edu email. The pass renews annually and grants "
                    "full website + apps access."
                ),
                "campus": "oxford",
                "library": "all",
                "topic": "research",
                "featured_service": "newspapers",
            },
        ],
    ),
    SynthCase(
        id="fs_ill_oxford",
        question="How do I request an interlibrary loan?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Briefly explain what ILL is and POINT TO the official request form "
            "URL. The bot must NOT roleplay submitting the request itself."
        ),
        allowed_urls=[
            "https://www.lib.miamioh.edu/use/borrow/ill/",
        ],
        evidence=[
            {
                "chunk_id": "ill_oxford_1",
                "source_url": "https://www.lib.miamioh.edu/use/borrow/ill/",
                "text": (
                    "Interlibrary Loan (ILL) lets you request books and articles "
                    "Miami University Libraries doesn't own from other libraries. "
                    "To request: log in to ILLiad with your Miami credentials and "
                    "submit a request form. Articles typically arrive in 1-3 days "
                    "as a PDF; books in 1-2 weeks. Oxford pickup is at the King "
                    "Library Circulation Desk."
                ),
                "campus": "oxford",
                "library": "king",
                "topic": "borrowing",
                "featured_service": "ill",
            },
        ],
    ),
    SynthCase(
        id="fs_adobe_unspecified",
        question="How do I get access to Adobe Creative Cloud?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Surface the page that explains Adobe access at Miami. Acceptable "
            "behavior: either give both student and faculty/staff paths, or "
            "ask which the user is. NOT acceptable: paraphrase license terms."
        ),
        allowed_urls=[
            "https://www.lib.miamioh.edu/use/technology/software/",
        ],
        evidence=[
            {
                "chunk_id": "adobe_1",
                "source_url": "https://www.lib.miamioh.edu/use/technology/software/",
                "text": (
                    "Adobe Creative Cloud access at Miami: STUDENTS get a free "
                    "named-user license via the Adobe student program -- sign in "
                    "at adobe.com with your @miamioh.edu email and follow Miami's "
                    "single-sign-on. FACULTY AND STAFF use a separate enterprise "
                    "license -- request access through IT Services. Both flows "
                    "are documented on the library software page."
                ),
                "campus": "oxford",
                "library": "all",
                "topic": "technology",
                "featured_service": "adobe_checkout",
            },
        ],
    ),
    SynthCase(
        id="fs_special_collections",
        question="How do I see something in Special Collections?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Explain that Special Collections is housed in King Library on the "
            "Oxford campus and access is appointment-based. Cite the Special "
            "Collections page."
        ),
        allowed_urls=[
            "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
        ],
        evidence=[
            {
                "chunk_id": "sc_1",
                "source_url": "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
                "text": (
                    "The Walter Havighurst Special Collections & University "
                    "Archives is located on the third floor of King Library, "
                    "Oxford campus. Access is by appointment to ensure staff "
                    "can retrieve materials and supervise their use. To request "
                    "access: contact the archives via the form on the page or "
                    "email scua@miamioh.edu at least 48 hours in advance."
                ),
                "campus": "oxford",
                "library": "special",
                "topic": "spaces",
                "featured_service": "special_collections",
            },
        ],
    ),
    SynthCase(
        id="tech_borrow_laptop",
        question="Can I borrow a laptop from the library?",
        scope_campus="oxford",
        scope_library=None,
        expected_answer=(
            "Confirm laptops are available for checkout (Oxford / King) and cite "
            "the technology lending page. Mention the loan period from the page."
        ),
        allowed_urls=[
            "https://www.lib.miamioh.edu/use/technology/checkout/",
        ],
        evidence=[
            {
                "chunk_id": "tech_1",
                "source_url": "https://www.lib.miamioh.edu/use/technology/checkout/",
                "text": (
                    "King Library lends laptops (both MacBook and Windows), "
                    "Chromebooks, chargers, calculators, and other tech items "
                    "to current Miami students. Standard checkout is 4 hours, "
                    "in-library use only. Overnight checkout (24 hours) is "
                    "available for some devices. Pick up at the Circulation Desk "
                    "with your Miami ID."
                ),
                "campus": "oxford",
                "library": "king",
                "topic": "technology",
                "featured_service": None,
            },
        ],
    ),
]


# --- Runner ---------------------------------------------------------------


def _real_llm_call(*, prefix_id: str, dynamic_suffix: str, model: str) -> tuple[dict, dict]:
    """Adapt structured_completion to the JudgeLLM/SynthesizerLLM Protocol."""
    from src.llm.client import structured_completion
    parsed, usage = structured_completion(
        prefix_id=prefix_id,
        dynamic_suffix=dynamic_suffix,
        response_schema=_JUDGE_SCHEMA,
        schema_name="judge_verdict",
        model=model,
    )
    return parsed, usage.as_dict()


_JUDGE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "reason", "citation_validity"],
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
}


def run_case(case: SynthCase) -> dict:
    """Run one case: synth -> judge -> return scoring dict."""
    mods = _imports()
    EvidenceChunk = mods["EvidenceChunk"]
    SynthesisRequest = mods["SynthesisRequest"]
    synthesize = mods["synthesize"]
    JudgeRequest = mods["JudgeRequest"]
    judge_answer = mods["judge_answer"]
    resolve_model = mods["resolve_model"]

    evidence = [EvidenceChunk(**kw) for kw in case.evidence]
    req = SynthesisRequest(
        question=case.question,
        evidence=evidence,
        scope_campus=case.scope_campus,
        scope_library=case.scope_library,
        corrections=[],
        url_allowlist=set(case.allowed_urls),
    )

    t0 = time.monotonic()
    try:
        result = synthesize(req, model=resolve_model("basic"))
    except Exception as e:  # noqa: BLE001
        return {
            "id": case.id,
            "phase": "synth",
            "error": f"{type(e).__name__}: {e}",
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        }
    synth_ms = int((time.monotonic() - t0) * 1000)
    pp = result.post_processor
    is_refusal = pp.is_refusal
    if is_refusal:
        bot_answer = pp.refusal.message if pp.refusal else "(empty refusal)"
        n_citations = 0
        confidence = "low"
    else:
        bot_answer = pp.answer.answer if pp.answer else "(empty answer)"
        n_citations = len(pp.answer.citations) if pp.answer else 0
        confidence = pp.answer.confidence if pp.answer else "?"

    # Judge.
    t0 = time.monotonic()
    try:
        judge_outcome = judge_answer(
            JudgeRequest(
                question=case.question,
                expected_answer=case.expected_answer,
                bot_answer=bot_answer,
                allowed_urls=case.allowed_urls,
            ),
            judge_llm=_real_llm_call,
            model=resolve_model("cheap"),
        )
    except Exception as e:  # noqa: BLE001
        return {
            "id": case.id,
            "phase": "judge",
            "error": f"{type(e).__name__}: {e}",
            "synth_ms": synth_ms,
            "bot_answer": bot_answer[:200],
        }
    judge_ms = int((time.monotonic() - t0) * 1000)

    v = judge_outcome.verdict
    return {
        "id": case.id,
        "verdict": v.verdict,
        "citation_validity": v.citation_validity,
        "reason": v.reason,
        "is_refusal": is_refusal,
        "n_citations": n_citations,
        "confidence": confidence,
        "input_tokens": result.input_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "output_tokens": result.output_tokens,
        "synth_ms": synth_ms,
        "judge_ms": judge_ms,
        "bot_answer": bot_answer[:300],
    }


# --- Main -----------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Synthesizer-alone quality eval.")
    parser.add_argument("--filter", default=None, help="Only run cases whose id contains this substring.")
    parser.add_argument("--out", default=None, help="Write per-case JSONL to this path.")
    args = parser.parse_args(argv)

    _load_env()
    if not os.getenv("OPENAI_API_KEY"):
        print("FATAL: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    cases = CASES
    if args.filter:
        cases = [c for c in cases if args.filter in c.id]
    if not cases:
        print(f"No cases matched filter {args.filter!r}", file=sys.stderr)
        return 1

    print(f"Running {len(cases)} synth-alone cases...")
    print()

    rows: list[dict] = []
    PASS_VERDICTS = {"correct", "partial", "refused_correctly"}
    n_pass = 0
    for c in cases:
        print(f"  {c.id} ...", end=" ", flush=True)
        row = run_case(c)
        if "error" in row:
            print(f"ERROR ({row['phase']}): {row['error']}")
            rows.append(row)
            continue
        passed = row["verdict"] in PASS_VERDICTS
        if passed:
            n_pass += 1
        mark = "PASS" if passed else "FAIL"
        print(f"{mark}  verdict={row['verdict']}  cites={row['n_citations']}  "
              f"cit_validity={row['citation_validity']}  "
              f"({row['synth_ms']+row['judge_ms']}ms)")
        print(f"      reason: {row['reason']}")
        print(f"      answer: {row['bot_answer'][:120]}...")
        rows.append(row)

    print()
    print(f"Summary: {n_pass}/{len(cases)} passed")
    print()

    # Verdict distribution
    from collections import Counter
    verdicts = Counter(r.get("verdict", "ERROR") for r in rows)
    for v, n in verdicts.most_common():
        print(f"  {v}: {n}")

    if args.out:
        with open(args.out, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"\nWrote per-case JSONL to {args.out}")

    return 0 if n_pass == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
