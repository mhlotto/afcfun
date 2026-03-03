#!/usr/bin/env bash
set -euo pipefail

# Batch wrapper for the API-driven weekly LLM steps.
#
# Default scope:
# - Arsenal
# - 2025-2026
# - ideation JSON regeneration
# - blog markdown regeneration (if an editorial-selection artifact exists)
# - site rebuild at the end
#
# Usage:
#   ./run_weekly_llm_api_batch.sh 27 28
#   ./run_weekly_llm_api_batch.sh 1 2 3 4
#
# Environment overrides:
#   TEAM=Arsenal
#   SEASON=2025-2026
#   IDEATE_MAX_OUTPUT_TOKENS=12000
#   BLOG_MAX_OUTPUT_TOKENS=5000
#   SKIP_SITE_BUILD=1
#
# Required environment:
#   OPENAI_API_KEY=...
# Optional:
#   OPENAI_MODEL=gpt-5

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TEAM="${TEAM:-Arsenal}"
SEASON="${SEASON:-2025-2026}"
IDEATE_MAX_OUTPUT_TOKENS="${IDEATE_MAX_OUTPUT_TOKENS:-12000}"
BLOG_MAX_OUTPUT_TOKENS="${BLOG_MAX_OUTPUT_TOKENS:-5000}"
SKIP_SITE_BUILD="${SKIP_SITE_BUILD:-0}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <week> [<week> ...]" >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is not set" >&2
  exit 1
fi

cd "$ROOT_DIR"
shopt -s nullglob

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

TEAM_SLUG="$(slugify "$TEAM")"
SEASON_KEY="${SEASON//-/}"

for week in "$@"; do
  if [[ ! "$week" =~ ^[0-9]+$ ]]; then
    echo "invalid week: $week" >&2
    exit 1
  fi

  context_matches=(docs/reports/weekly-context-"$TEAM_SLUG"-"$SEASON_KEY"-w"$week"-*.json)
  if [[ ${#context_matches[@]} -ne 1 ]]; then
    echo "expected exactly one context JSON for week $week, found ${#context_matches[@]}" >&2
    printf '  %s\n' "${context_matches[@]}" >&2
    exit 1
  fi
  context_path="${context_matches[0]}"

  echo "Generating ideation for week $week"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_ideate_generate.py" \
    --context-json "$context_path" \
    --overwrite \
    --max-output-tokens "$IDEATE_MAX_OUTPUT_TOKENS"

  selection_matches=(docs/reports/editorial-selection-"$TEAM_SLUG"-"$SEASON_KEY"-w"$week"-*.json)
  if [[ ${#selection_matches[@]} -eq 1 ]]; then
    selection_path="${selection_matches[0]}"
    echo "Generating blog draft for week $week"
    "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_blog_generate.py" \
      --selection-json "$selection_path" \
      --overwrite \
      --max-output-tokens "$BLOG_MAX_OUTPUT_TOKENS"
  elif [[ ${#selection_matches[@]} -eq 0 ]]; then
    echo "Skipping blog draft for week $week (no editorial-selection artifact found)"
  else
    echo "expected at most one editorial-selection JSON for week $week, found ${#selection_matches[@]}" >&2
    printf '  %s\n' "${selection_matches[@]}" >&2
    exit 1
  fi
done

if [[ "$SKIP_SITE_BUILD" != "1" ]]; then
  echo "Rebuilding site"
  "$PYTHON_BIN" "$ROOT_DIR/e0_site_build.py" \
    --team "$TEAM" \
    --season "$SEASON"
fi

echo "Done."
