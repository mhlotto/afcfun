#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

cd "$ROOT_DIR"
echo "[step06] rebuilding site"
"$PYTHON_BIN" "$ROOT_DIR/e0_site_build.py" \
  --team "$TEAM" \
  --season "$SEASON"
