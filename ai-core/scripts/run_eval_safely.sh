#!/bin/bash
# Run the full eval WITHOUT risking the production service.
#
# Why this wrapper exists: on 2026-07-29 an eval run alongside the live
# service exhausted this box (t4g.medium, 4 GB) and the OOM killer fired
# twice. uvicorn had the highest oom_score on the machine at the time, so
# the next kill would very likely have taken the bot down -- and
# OOMPolicy=stop meant systemd would have left it down.
#
# The unit is now hardened (OOMScoreAdjust=-500, OOMPolicy=continue,
# Restart=always), but the right fix is not to compete for memory in the
# first place. This caps the EVAL instead of the service.
#
#   Usage:  bash scripts/run_eval_safely.sh [extra run_eval args...]
#
# Defaults match the 2026-07-18 baseline (92.7%) so the number is
# comparable: real LLMs, judge on gpt-5.4-mini.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="docs/eval/eval_results_$(date +%Y%m%d_%H%M)_minijudge.jsonl"
# 1.5 GB leaves room for uvicorn (~1 GB) + Weaviate (~400 MB) + Postgres.
# The eval gets OOM-killed before the machine does, which is the point.
LIMIT="${EVAL_MEMORY_MAX:-1500M}"

echo "results -> $OUT"
echo "memory cap -> $LIMIT (the eval dies before the box does)"
echo

# NOTE: OOMScoreAdjust is a *service* property -- `systemd-run --scope`
# rejects it ("Unknown assignment"). Set it on the process itself instead,
# which works everywhere and needs no privilege to RAISE the score.
exec systemd-run --scope --quiet \
  -p "MemoryMax=$LIMIT" \
  bash -c "echo 500 > /proc/self/oom_score_adj 2>/dev/null; \
    set -a; . /opt/chatbot/.env; set +a; \
    exec .venv/bin/python -m src.eval.run_eval \
      --with-real-llm --with-judge --judge-model gpt-5.4-mini \
      --results-out '$OUT' $*"
