#!/usr/bin/env bash
set -euo pipefail

# Batch wrapper for e0_weekly_editorial_select.py using a simple CSV of:
#   week,story_candidate
#
# Expected default input:
#   weekly-selection.csv
#
# Expected file layout:
#   docs/reports/weekly-chatgpt-ideate-w<week>.json
#   docs/reports/weekly-context-arsenal-20252026-w<week>-*.json
#
# This script is intentionally narrow and pragmatic:
# - it is meant for the current Arsenal 2025-2026 weekly workflow
# - it does not try to be a general-purpose import tool
# - it fails fast if an ideation file or context file is missing
# - it also fails if more than one context file matches a week, because that
#   usually means the run is ambiguous and should be fixed rather than guessed

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CSV_PATH="${1:-$ROOT_DIR/weekly-selection.csv}"

if [[ ! -f "$CSV_PATH" ]]; then
  echo "selection CSV not found: $CSV_PATH" >&2
  exit 1
fi

cd "$ROOT_DIR"
shopt -s nullglob

while IFS=, read -r raw_week raw_story _rest; do
  week="${raw_week//$'\r'/}"
  story="${raw_story//$'\r'/}"

  # Skip blank lines and the header row. The current file uses a commented
  # header ('#week,story_candidate'), so handle both '#week' and 'week'.
  if [[ -z "${week// }" ]]; then
    continue
  fi
  if [[ "$week" == \#week || "$week" == week ]]; then
    continue
  fi

  if [[ -z "${story// }" ]]; then
    echo "missing story_candidate for week $week in $CSV_PATH" >&2
    exit 1
  fi

  ideation_path="docs/reports/weekly-chatgpt-ideate-w${week}.json"
  if [[ ! -f "$ideation_path" ]]; then
    echo "missing ideation JSON for week $week: $ideation_path" >&2
    exit 1
  fi

  context_matches=(docs/reports/weekly-context-arsenal-20252026-w"${week}"-*.json)
  if [[ ${#context_matches[@]} -eq 0 ]]; then
    echo "missing context JSON for week $week: docs/reports/weekly-context-arsenal-20252026-w${week}-*.json" >&2
    exit 1
  fi
  if [[ ${#context_matches[@]} -gt 1 ]]; then
    echo "multiple context JSON files found for week $week:" >&2
    printf '  %s\n' "${context_matches[@]}" >&2
    exit 1
  fi
  context_path="${context_matches[0]}"

  echo "Selecting ${story} for week ${week}"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_editorial_select.py" \
    --ideation-json "$ideation_path" \
    --context-json "$context_path" \
    --story-id "$story" \
    --selection-mode "batch-csv" \
    --reason "Batch-selected ${story} from $(basename "$CSV_PATH")."
done < "$CSV_PATH"

echo "Done."
