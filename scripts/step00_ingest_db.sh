#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

cd "$ROOT_DIR"
echo "[step00] ingesting CSV data into $DB_PATH"
"$PYTHON_BIN" "$ROOT_DIR/e0_ingest_db.py" \
  --db "$DB_PATH" \
  --data-dir data/football-data.co.uk \
  --glob 'E0*.csv' \
  --current-label "$SEASON"

# One-off schedule normalization is folded into step00 so the rest of the pipeline
# can consume a consistent normalized schedule artifact without extra manual steps.
SCHEDULE_DIR="$ROOT_DIR/data/arsenal-epl"
if [[ -d "$SCHEDULE_DIR" ]]; then
  shopt -s nullglob
  schedule_files=("$SCHEDULE_DIR"/arsenal-schedule-*.json)
  for schedule_file in "${schedule_files[@]}"; do
    if [[ "$schedule_file" == *.normalized.json ]]; then
      continue
    fi
    out_file="${schedule_file%.json}.normalized.json"
    echo "[step00] normalizing schedule $(basename "$schedule_file")"
    "$PYTHON_BIN" "$ROOT_DIR/e0_schedule_normalize.py" \
      --db "$DB_PATH" \
      --in "$schedule_file" \
      --out "$out_file" \
      --write-aliases \
      --alias-source-scope "schedule"
  done
fi
