#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
    
generate_week_report_and_context() {
    week="$1"
    outjson="docs/reports/weekly-report-w${week}.json"
    
    "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_report_run.py"  \
      --db data/footstat.sqlite3   \
      --competition E0   \
      --team Arsenal  \
      --seasons 2025-2026   \
      --through-week ${week} \
      --out-json ${outjson}
    
    
    "$PYTHON_BIN" "$ROOT_DIR/e0_weekly_context_export.py"    \
      --report-json ${outjson}  \
      --week ${week}  \
      --team Arsenal  \
      --season 2025-2026
}

cd "$ROOT_DIR"
for i in {1..28}
do
    generate_week_report_and_context $i
done
