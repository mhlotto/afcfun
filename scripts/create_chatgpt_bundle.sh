#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# create_chatgpt_bundle.sh
#
# Purpose
#   Build a ZIP bundle intended for external review (for example uploading to
#   ChatGPT) with source code + useful docs/config, while excluding local
#   environment noise (venv binaries, generated assets, large data dumps, etc).
#
# Safety notes (important)
#   1) This script NEVER deletes anything in your repo.
#   2) It only copies selected files into a temporary staging directory.
#   3) It only deletes that temporary staging directory on exit.
#   4) The only write outside temp is the output ZIP path you choose.
#
# Usage
#   ./scripts/create_chatgpt_bundle.sh
#   ./scripts/create_chatgpt_bundle.sh /tmp/my-bundle.zip
#
# What gets included
#   - Python source (*.py)
#   - key root files (README, requirements, plan, etc.)
#   - markdown docs, including nested prompt docs in docs/prompts/
#   - selected workflow artifacts in docs/reports/
#   - generated site HTML in docs/site/
#   - helper markdown packets in exports/
#   - tests + golden JSON fixtures
#   - football-data notes file (column definitions)
#
# What gets excluded
#   - virtualenv artifacts (bin/lib/include/etc unless explicitly matched)
#   - generated HTML/SVG outputs
#   - large CSV datasets
#   - anything not explicitly allowlisted by rsync include rules
# ---------------------------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +"%Y%m%d-%H%M%S")"
OUT_ZIP="${1:-$ROOT_DIR/exports/footstat-chatgpt-$STAMP.zip}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "error: rsync is required but not found." >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "error: zip is required but not found." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  # Safety: only remove the temp dir created by mktemp above.
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

STAGE_DIR="$TMP_DIR/footstat"
mkdir -p "$STAGE_DIR"
mkdir -p "$(dirname "$OUT_ZIP")"

# Keep bundle focused on source/config/docs/tests.
# This is allowlist-based: if a file pattern is not included below, it is NOT copied.
RSYNC_ARGS=(
  -a
  --prune-empty-dirs
  --include="*/"
  --include="README.md"
  --include="AGENTS.md"
  --include="PLAN0001.md"
  --include="Makefile"
  --include="requirements.txt"
  --include="pytest.ini"
  --include="*.py"
  --include="scripts/*.sh"
  --include="scripts/*.bash"
  --include="docs/*.md"
  --include="docs/prompts/*.md"
  --include="assets/graphics/*.md"
  --include="assets/graphics/*.png"
  --include="docs/site/*.html"
  --include="docs/site/*/*.html"
  --include="docs/site/*/*/*.html"
  --include="docs/*example*.json"
  --include="docs/reports/editorial-selection-*.json"
  --include="docs/reports/weekly-context-*.json"
  --include="docs/reports/weekly-chatgpt-ideate-*.json"
  --include="docs/reports/weekly-post-*.md"
  --include="exports/*.md"
  --include="tests/*.py"
  --include="tests/golden/*.json"
  --include="data/football-data.co.uk/notes.txt"
  --exclude="*"
)

rsync "${RSYNC_ARGS[@]}" "$ROOT_DIR/" "$STAGE_DIR/"

# Add a manifest so the bundle is easy to inspect in ChatGPT.
(
  cd "$STAGE_DIR"
  find . -type f | LC_ALL=C sort > BUNDLE_CONTENTS.txt
)

(
  cd "$TMP_DIR"
  zip -qr "$OUT_ZIP" footstat
)

echo "Wrote bundle: $OUT_ZIP"
