#!/usr/bin/env bash
set -euo pipefail

# One-off batch helper for generating ChatGPT blog-draft packets from the
# existing editorial-selection artifacts.
#
# Default behavior:
# - scans docs/reports for Arsenal 2025-2026 editorial selections
# - writes one packet per week into exports/
#
# Optional argument:
#   ./run_weekly_blog_packets.sh "docs/reports/editorial-selection-*.json"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PATTERN="${1:-docs/reports/editorial-selection-arsenal-20252026-w*.json}"

cd "$ROOT_DIR"
shopt -s nullglob

matches=($PATTERN)
if [[ ${#matches[@]} -eq 0 ]]; then
  echo "no editorial-selection files matched: $PATTERN" >&2
  exit 1
fi

for selection_path in "${matches[@]}"; do
  echo "Generating blog packet for ${selection_path}"
  "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_blog_packet.py" \
    --selection-json "$selection_path" \
    --write-default
done

echo "Done."
