#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

cd "$ROOT_DIR"
WEEKS=($(expand_weeks "$@"))

for week in "${WEEKS[@]}"; do
  selection_path="$(find_one_match "docs/reports/editorial-selection-${TEAM_SLUG}-${SEASON_KEY}-w${week}-*.json")"
  echo "[step04] selecting visual for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_visual_select.py" \
    --selection-json "$selection_path"
  echo "[step04] resolving chart plan for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_chart_plan_resolve.py" \
    --selection-json "$selection_path"
done
