#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

require_openai_key
cd "$ROOT_DIR"
WEEKS=($(expand_weeks "$@"))

run_week_ideation() {
  local week="$1"
  context_path="$(find_one_match "docs/reports/weekly-context-${TEAM_SLUG}-${SEASON_KEY}-w${week}-*.json")"
  echo "[step02] ideation for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_ideate_generate.py" \
    --context-json "$context_path" \
    --overwrite \
    --max-output-tokens "$IDEATE_MAX_OUTPUT_TOKENS"
}

if [[ "$IDEATE_PARALLELISM" -le 1 ]]; then
  for week in "${WEEKS[@]}"; do
    run_week_ideation "$week"
  done
  exit 0
fi

echo "[step02] parallelism=$IDEATE_PARALLELISM"
pids=()
for week in "${WEEKS[@]}"; do
  run_week_ideation "$week" &
  pids+=("$!")
  while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$IDEATE_PARALLELISM" ]]; do
    sleep 0.2
  done
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=1
  fi
done

if [[ "$failed" -ne 0 ]]; then
  echo "[step02] one or more ideation jobs failed" >&2
  exit 1
fi
