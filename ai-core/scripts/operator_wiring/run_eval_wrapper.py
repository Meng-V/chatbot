"""Thin wrapper that imports and invokes run_eval() programmatically.

Bypasses the `python -m src.eval.run_eval` CLI path, which has a
runtime hang. Also adds `--ids id1,id2,...` so we can split sections
that would exceed the 32-case cumulative-state threshold.

Usage:
  python3 /tmp/run_eval_wrapper.py [--filter CAT] [--ids id1,id2,...] [--out PATH]
"""
import argparse, logging, os, sys
from pathlib import Path

ROOT = Path("/Users/qum/Documents/GitHub/chatbot/.claude/worktrees/nice-mcnulty-42183e")
AI_CORE = ROOT / "ai-core"
sys.path.insert(0, str(AI_CORE))
os.chdir(AI_CORE)
ENV = ROOT / ".env"
for line in ENV.read_text().splitlines():
    if not line or line.startswith("#") or "=" not in line: continue
    k, _, v = line.partition("="); k=k.strip(); v=v.strip().strip('"').strip("'")
    if k and k not in os.environ: os.environ[k] = v

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

p = argparse.ArgumentParser()
p.add_argument("--filter", default=None, help="Filter by category")
p.add_argument("--ids", default=None, help="Comma-separated list of question_ids; intersected with --filter if both given")
p.add_argument("--out", default="/tmp/eval_out.jsonl")
args = p.parse_args()

# Monkey-patch load_golden_set to support --ids on top of run_eval's --filter
if args.ids:
    wanted = set(s.strip() for s in args.ids.split(",") if s.strip())
    import src.eval.golden_set as gs
    _orig = gs.load_golden_set
    def _patched(*a, **kw):
        all_q = _orig(*a, **kw)
        return [q for q in all_q if q.id in wanted]
    gs.load_golden_set = _patched
    print(f">>> filtering to {len(wanted)} explicit IDs", flush=True)

import importlib
m = importlib.import_module("src.eval.run_eval")
if args.ids:
    m.load_golden_set = gs.load_golden_set  # propagate the patch into run_eval's namespace
report = m.run_eval(
    filter_category=args.filter,
    scope_only=False,
    with_judge=True,
    with_real_llm=True,
    results_out=Path(args.out),
)
m._print_report(report, verbose=False, scope_only=False)
