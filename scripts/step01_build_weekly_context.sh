#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_step_common.sh"

cd "$ROOT_DIR"
WEEKS=($(expand_weeks "$@"))
echo "[step01] building weekly report/context for: ${WEEKS[*]}"
"$ROOT_DIR/scripts/run_weekly_report_context_batch.sh" "${WEEKS[@]}"
