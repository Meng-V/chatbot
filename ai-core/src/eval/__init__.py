"""
Eval harness for the smart-chatbot rebuild.

The eval harness is the safety net for everything else: it lets us tell
"the new system is at least as good as the old one" before flipping the
rollout flag. Without it, every change is a gamble.

Per plan timeline week 1: 100-question gold set covering each intent +
known failure cases (printing, MakerSpace location, librarian-by-subject,
hours edge cases, cross-campus disambiguation).

Scoring:
  - answer correctness via LLM-as-judge (uses prompts/judge_v1)
  - citation validity (URL exists in UrlSeen, n's match citations array)
  - refusal correctness ("did the bot correctly say I don't know?")

Entry point: `python -m src.eval.run_eval` from ai-core/.
"""

from src.eval.golden_set import GoldQuestion, load_golden_set
from src.eval.run_eval import EvalResult, run_eval

__all__ = ["GoldQuestion", "load_golden_set", "EvalResult", "run_eval"]
