"""
Verify OpenAI prompt caching is actually firing for our stable prefixes.

The plan's threshold-3 cost-cache gate (Verification §7) requires
cached_input_tokens / input_tokens >= 0.6 across the eval. That number
only happens if the stable prefix in `src/prompts/*_v1.py` is BIG ENOUGH
(>=1024 tokens) AND BYTE-IDENTICAL call-to-call. PR #74 was designed
around that contract; this script proves it works.

Procedure:
  1. Pick a stable prefix (default: synthesizer_v1).
  2. Make N calls (default: 3) via the Responses API with:
       - identical prefix
       - varying small suffix
       - same model
     Wait briefly between calls so the cache can warm.
  3. Read `usage.input_tokens_details.cached_tokens` per response.
  4. Report per-call + the cache_hit_rate for calls 2..N.

The first call ALWAYS misses (cache is cold). The second and later
should be `>= 1024` cached_tokens if the prefix is correctly stable.

Cost: tiny. ~3,200 input tokens per call * (mini @ $0.75/1M) ~ $0.0024
per call uncached, ~$0.00026 per call when cached. 3 calls ≈ $0.005.

Usage:
    .venv/bin/python -m scripts.verify_prompt_cache
    .venv/bin/python -m scripts.verify_prompt_cache --prefix agent_v1
    .venv/bin/python -m scripts.verify_prompt_cache --calls 5 --model gpt-5.4-nano
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Optional

from openai import OpenAI


# Load .env from the repo root the same way main.py does
def _load_env() -> None:
    from pathlib import Path
    from dotenv import load_dotenv
    here = Path(__file__).resolve().parent
    # ai-core/scripts/ -> repo root is two parents up
    root_env = here.parent.parent / ".env"
    load_dotenv(root_env)


def _resolve_prefix(prefix_id: str) -> str:
    """Load a stable prefix by id (synthesizer_v1, agent_v1, etc.)."""
    if prefix_id == "synthesizer_v1":
        from src.prompts.synthesizer_v1 import SYNTHESIZER_V1_PREFIX
        return SYNTHESIZER_V1_PREFIX
    if prefix_id == "agent_v1":
        from src.prompts.agent_v1 import AGENT_V1_PREFIX
        return AGENT_V1_PREFIX
    if prefix_id == "clarifier_v1":
        from src.prompts.clarifier_v1 import CLARIFIER_V1_PREFIX
        return CLARIFIER_V1_PREFIX
    if prefix_id == "judge_v1":
        from src.prompts.judge_v1 import JUDGE_V1_PREFIX
        return JUDGE_V1_PREFIX
    raise ValueError(f"unknown prefix id: {prefix_id}")


def _extract_cached_tokens(usage: Any) -> int:
    """The Responses API usage object exposes cached_tokens under
    `input_tokens_details.cached_tokens` on current SDK versions. Older
    surfaces had it as a top-level `cached_tokens` or under a slightly
    different name. Be defensive."""
    if usage is None:
        return 0
    # Newer SDK: usage.input_tokens_details.cached_tokens
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        v = getattr(details, "cached_tokens", None)
        if v is not None:
            return int(v)
    # Some SDK versions: usage.prompt_tokens_details.cached_tokens
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        v = getattr(details, "cached_tokens", None)
        if v is not None:
            return int(v)
    # Legacy / direct
    v = getattr(usage, "cached_tokens", None)
    if v is not None:
        return int(v)
    return 0


def run(prefix_id: str, calls: int, model: str, sleep_ms: int) -> int:
    _load_env()
    prefix = _resolve_prefix(prefix_id)
    print(f"Prefix: {prefix_id}  chars={len(prefix)}  approx_tokens~{len(prefix)//4}")
    print(f"Model:  {model}")
    print(f"Calls:  {calls}")
    print()

    client = OpenAI()
    results: list[tuple[int, int, int]] = []  # (input, cached, output)
    for i in range(1, calls + 1):
        # Tiny per-call variant so OpenAI doesn't dedupe at request layer.
        suffix = f"\n\nVariant {i}. Respond with the single word OK."
        t0 = time.monotonic()
        resp = client.responses.create(
            model=model,
            input=prefix + suffix,
            max_output_tokens=20,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        u = getattr(resp, "usage", None)
        inp = int(getattr(u, "input_tokens", 0)) if u else 0
        out = int(getattr(u, "output_tokens", 0)) if u else 0
        cached = _extract_cached_tokens(u)
        results.append((inp, cached, out))
        pct = (cached / inp * 100) if inp else 0
        print(f"  call {i}: input={inp:5d}  cached={cached:5d} ({pct:5.1f}%)  output={out:3d}  {elapsed}ms")
        if i < calls and sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

    print()
    if len(results) >= 2:
        cached_2plus = sum(c for _, c, _ in results[1:])
        input_2plus = sum(i for i, _, _ in results[1:])
        rate = (cached_2plus / input_2plus) if input_2plus else 0
        print(f"Cache hit rate (calls 2..N): {cached_2plus}/{input_2plus} = {rate:.1%}")
        # The plan's release gate is 0.6. The first call always misses;
        # we measure the steady-state rate over calls 2..N.
        ok = rate >= 0.6
        print(f"Plan threshold (>= 60%):     {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify OpenAI prompt caching on a stable prefix.")
    parser.add_argument(
        "--prefix",
        default="synthesizer_v1",
        choices=["synthesizer_v1", "agent_v1", "clarifier_v1", "judge_v1"],
        help="Which prompt prefix to test.",
    )
    parser.add_argument(
        "--calls",
        type=int,
        default=3,
        help="How many calls to make (default 3; first always misses).",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4-nano",
        help="Model to use. Default nano (cheapest verification).",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=500,
        help="Sleep between calls to let cache propagate (ms; default 500).",
    )
    args = parser.parse_args(argv)
    return run(args.prefix, args.calls, args.model, args.sleep_ms)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run"]
