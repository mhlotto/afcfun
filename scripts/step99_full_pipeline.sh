#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/step00_ingest_db.sh"
"$SCRIPT_DIR/step01_build_weekly_context.sh" "$@"
"$SCRIPT_DIR/step02_run_ideation.sh" "$@"
"$SCRIPT_DIR/step03_select_story.sh" "$@"
"$SCRIPT_DIR/step04_select_visual.sh" "$@"
"$SCRIPT_DIR/step05_generate_blog.sh" "$@"
"$SCRIPT_DIR/step06_build_site.sh"
