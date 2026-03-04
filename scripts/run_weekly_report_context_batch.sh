#!/usr/bin/env bash
set -euo pipefail

# Rebuild weekly report JSON + weekly context JSON for one or more weeks.
#
# Default scope:
# - Arsenal
# - 2025-2026
# - competition E0
#
# Usage:
#   ./scripts/run_weekly_report_context_batch.sh 1 2 3
#   ./scripts/run_weekly_report_context_batch.sh all
#
# Environment overrides:
#   PYTHON_BIN=python3
#   DB_PATH=data/footstat.sqlite3
#   COMPETITION=E0
#   TEAM=Arsenal
#   SEASON=2025-2026
#   REPORT_DATE=2026-03-03

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DB_PATH="${DB_PATH:-data/footstat.sqlite3}"
COMPETITION="${COMPETITION:-E0}"
TEAM="${TEAM:-Arsenal}"
SEASON="${SEASON:-2025-2026}"
REPORT_DATE="${REPORT_DATE:-$(date +%F)}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <week> [<week> ...] | all" >&2
  exit 1
fi

cd "$ROOT_DIR"
mkdir -p docs/reports

weeks=()
if [[ "$#" -eq 1 && "$1" == "all" ]]; then
  max_week="$("$PYTHON_BIN" - <<PY
from e0_inspect import load_normalized_team_rows

rows = load_normalized_team_rows(
    source="db",
    team=${TEAM@Q},
    side="both",
    db_path=${DB_PATH@Q},
    competition_code=${COMPETITION@Q},
    seasons=[${SEASON@Q}],
)
print(len(rows))
PY
)"
  if [[ ! "$max_week" =~ ^[0-9]+$ ]] || [[ "$max_week" -le 0 ]]; then
    echo "failed to determine max week count for $TEAM $SEASON" >&2
    exit 1
  fi
  for week in $(seq 1 "$max_week"); do
    weeks+=("$week")
  done
else
  for week in "$@"; do
    if [[ ! "$week" =~ ^[0-9]+$ ]]; then
      echo "invalid week: $week" >&2
      exit 1
    fi
    weeks+=("$week")
  done
fi

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

TEAM_SLUG="$(slugify "$TEAM")"
SEASON_KEY="${SEASON//-/}"

for week in "${weeks[@]}"; do
  report_json="docs/reports/weekly-report-${TEAM_SLUG}-${SEASON_KEY}-through-w${week}-${REPORT_DATE}.json"
  echo "Generating weekly report for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_report_run.py" \
    --db "$DB_PATH" \
    --competition "$COMPETITION" \
    --team "$TEAM" \
    --seasons "$SEASON" \
    --through-week "$week" \
    --out-json "$report_json"

  echo "Generating weekly context for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_context_export.py" \
    --report-json "$report_json" \
    --team "$TEAM" \
    --season "$SEASON" \
    --week "$week"
done

echo "Done."
