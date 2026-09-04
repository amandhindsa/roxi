#!/usr/bin/env bash
# Daily cron script for running all active verticals.
# Add to crontab: 0 7 * * 1-5 /path/to/roxi/scripts/run_daily.sh
# Runs Monday-Friday at 07:00 local time.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROXI_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROXI_DIR"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

VENV="$ROXI_DIR/.venv/bin/python3"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Starting Roxi daily run"

VERTICALS="${ROXI_VERTICALS:-hauler_ai}"

for vertical in $VERTICALS; do
  log "Running pipeline: $vertical"
  "$VENV" -m roxi run "$vertical" && log "Done: $vertical" || log "FAILED: $vertical"
done

log "All done"
