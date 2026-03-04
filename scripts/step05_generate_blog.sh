#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

require_openai_key
cd "$ROOT_DIR"
WEEKS=($(expand_weeks "$@"))

run_week_blog() {
  local week="$1"
  selection_path="$(find_one_match "docs/reports/editorial-selection-${TEAM_SLUG}-${SEASON_KEY}-w${week}-*.json")"
  echo "[step05] generating blog for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_blog_generate.py" \
    --selection-json "$selection_path" \
    --overwrite \
    --max-output-tokens "$BLOG_MAX_OUTPUT_TOKENS"
}

if [[ "$BLOG_PARALLELISM" -le 1 ]]; then
  for week in "${WEEKS[@]}"; do
    run_week_blog "$week"
  done
  exit 0
fi

echo "[step05] parallelism=$BLOG_PARALLELISM"
pids=()
for week in "${WEEKS[@]}"; do
  run_week_blog "$week" &
  pids+=("$!")
  while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$BLOG_PARALLELISM" ]]; do
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
  echo "[step05] one or more blog jobs failed" >&2
  exit 1
fi
