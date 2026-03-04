#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

cd "$ROOT_DIR"
WEEKS=($(expand_weeks "$@"))

for week in "${WEEKS[@]}"; do
  context_path="$(find_one_match "docs/reports/weekly-context-${TEAM_SLUG}-${SEASON_KEY}-w${week}-*.json")"
  ideation_path="docs/reports/weekly-chatgpt-ideate-w${week}.json"
  echo "[step03] selecting S1 for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_editorial_select.py" \
    --ideation-json "$ideation_path" \
    --context-json "$context_path" \
    --story-id S1 \
    --selection-mode auto-s1 \
    --reason "Auto-selected S1."
done
