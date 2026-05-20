#!/usr/bin/env bash
#
# Run every offline-clean test module in ai-core/ and exit non-zero if
# any fail. Intended for pre-PR and pre-deploy checks: it's the closest
# thing this repo has to `make test`.
#
# What "offline-clean" means here: passes without network, without a DB
# connection, without OpenAI / Google CSE / Weaviate credentials. The
# integration tests (those that genuinely need live infra) are listed
# at the bottom of this file and printed for awareness but not run.
#
# Usage:
#   cd ai-core
#   bash scripts/run_offline_tests.sh
#
# Exit codes:
#   0  all offline tests passed
#   1  one or more offline tests failed (real signal -- look at the FAIL lines)
#
# Adding a new test:
#   * If it's offline-clean (no network/DB/keys), append it to OFFLINE.
#   * If it needs live infra, append it to INTEGRATION with a one-word reason.
#   * Either way: keep the lists sorted so PR diffs stay small.

set -u  # NOT set -e -- we want to keep going through failures.

cd "$(dirname "$0")/.." || {
  echo "FATAL: could not cd to ai-core/" >&2
  exit 2
}

# --- Offline-clean modules (the runnable set) ---------------------------
# Sorted. Add to alphabetical position when extending.

OFFLINE=(
  scripts.etl.test_chunker
  scripts.etl.test_classify
  scripts.etl.test_diff_report
  scripts.etl.test_discover
  scripts.etl.test_extract
  scripts.etl.test_gate
  scripts.etl.test_upsert
  scripts.test_cost_rollup
  scripts.test_digest_email
  scripts.test_google_agent_direct
  src.agent.test_agent
  src.agent.test_tool_registry
  src.api.admin.test_review
  src.api.admin.test_validators
  src.api.test_rate_limit
  src.config.test_capability_scope
  src.config.test_models
  src.database.test_urlseen_adapter
  src.eval.test_calibrate_clarify
  src.eval.test_inspect_turn
  src.eval.test_judge
  src.eval.test_smoke_e2e
  src.graph.test_new_orchestrator
  src.graph.test_v2_serving
  src.llm.test_client
  src.observability.test_cache_health
  src.observability.test_logging
  src.observability.test_metrics
  src.observability.test_metrics_endpoint
  src.observability.test_request_id_middleware
  src.observability.test_sentry
  src.observability.test_smoketest
  src.prompts.test_builder
  src.retrieval.test_scope_filter
  src.retrieval.test_search
  src.router.test_intent_capabilities
  src.router.test_intent_knn
  src.scope.test_date_window
  src.scope.test_service_availability
  src.synthesis.test_corrections
  src.synthesis.test_post_processor
  src.synthesis.test_refusal_templates
  src.synthesis.test_synthesizer
  src.tools.test_search_kb_tool
  src.weaviate_adapters.test_etl_adapter
  src.weaviate_adapters.test_search_adapter
)

# --- Integration tests (NOT run -- listed for awareness) ----------------
# Format: "<module>  <one-word reason>"
# Run these manually when the corresponding env is set up.

INTEGRATION=(
  "scripts.test_library_spaces           prisma"
  "scripts.test_routing_smoke            prisma"
  "src.eval.test_real_backends           prisma+weaviate"
  "scripts.test_policy_routing           openai+weaviate"
  "scripts.test_google_cse_cost_controls google-cse"
)

# --- Runner -------------------------------------------------------------

PYTHON="${PYTHON:-python3}"
START_TS=$(date +%s)

passed=0
failed=0
failed_modules=()

printf "Running %d offline test modules with %s\n" "${#OFFLINE[@]}" "$PYTHON"
printf "Working dir: %s\n\n" "$(pwd)"

for mod in "${OFFLINE[@]}"; do
  out=$("$PYTHON" -m "$mod" 2>&1)
  rc=$?
  # Last non-empty line is usually the harness summary ("N/M passed").
  last=$(printf '%s\n' "$out" | awk 'NF{line=$0} END{print line}' | tr -d '\r' | cut -c1-90)
  if [ "$rc" -eq 0 ]; then
    printf "PASS  %-55s  %s\n" "$mod" "$last"
    passed=$((passed + 1))
  else
    printf "FAIL  %-55s  %s  (exit %d)\n" "$mod" "$last" "$rc"
    failed=$((failed + 1))
    failed_modules+=("$mod")
  fi
done

elapsed=$(( $(date +%s) - START_TS ))

printf "\n%s\n" "================================================================"
printf "Offline:     %d/%d passed in %ds\n" "$passed" "${#OFFLINE[@]}" "$elapsed"
if [ "$failed" -gt 0 ]; then
  printf "FAILED:      %s\n" "${failed_modules[*]}"
fi
printf "\nIntegration (NOT run -- need live env):\n"
for entry in "${INTEGRATION[@]}"; do
  printf "  - %s\n" "$entry"
done
printf "%s\n" "================================================================"

if [ "$failed" -gt 0 ]; then
  exit 1
fi
exit 0
