#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DB_PATH="${DB_PATH:-data/footstat.sqlite3}"
COMPETITION="${COMPETITION:-E0}"
TEAM="${TEAM:-Arsenal}"
SEASON="${SEASON:-2025-2026}"
REPORT_DATE="${REPORT_DATE:-$(date +%F)}"
IDEATE_MAX_OUTPUT_TOKENS="${IDEATE_MAX_OUTPUT_TOKENS:-12000}"
BLOG_MAX_OUTPUT_TOKENS="${BLOG_MAX_OUTPUT_TOKENS:-5000}"
PARALLELISM="${PARALLELISM:-2}"
IDEATE_PARALLELISM="${IDEATE_PARALLELISM:-$PARALLELISM}"
BLOG_PARALLELISM="${BLOG_PARALLELISM:-$PARALLELISM}"

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

TEAM_SLUG="$(slugify "$TEAM")"
SEASON_KEY="${SEASON//-/}"

require_weeks_or_all() {
  if [[ $# -lt 1 ]]; then
    echo "usage: $0 <week> [<week> ...] | all" >&2
    exit 1
  fi
}

expand_weeks() {
  require_weeks_or_all "$@"
  if [[ "$#" -eq 1 && "$1" == "all" ]]; then
    TEAM="$TEAM" SEASON="$SEASON" DB_PATH="$DB_PATH" COMPETITION="$COMPETITION" "$PYTHON_BIN" - <<'PY'
import os
from e0_inspect import load_normalized_team_rows

rows = load_normalized_team_rows(
    source="db",
    team=os.environ["TEAM"],
    side="both",
    db_path=os.environ["DB_PATH"],
    competition_code=os.environ["COMPETITION"],
    seasons=[os.environ["SEASON"]],
)
for i in range(1, len(rows) + 1):
    print(i)
PY
    return
  fi
  for week in "$@"; do
    if [[ ! "$week" =~ ^[0-9]+$ ]]; then
      echo "invalid week: $week" >&2
      exit 1
    fi
    echo "$week"
  done
}

require_openai_key() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_API_KEY is not set" >&2
    exit 1
  fi
}

find_one_match() {
  local pattern="$1"
  shopt -s nullglob
  local matches=($pattern)
  if [[ ${#matches[@]} -eq 0 ]]; then
    echo "expected at least one match for pattern: $pattern" >&2
    exit 1
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    local last_index=$((${#matches[@]} - 1))
    echo "multiple matches for pattern: $pattern" >&2
    printf '  %s\n' "${matches[@]}" >&2
    echo "using latest: ${matches[$last_index]}" >&2
    printf '%s\n' "${matches[$last_index]}"
    return
  fi
  printf '%s\n' "${matches[0]}"
}
