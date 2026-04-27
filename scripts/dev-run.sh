#!/bin/bash
# Run the kiosk app locally for development.
#
# Usage: ./scripts/dev-run.sh [SERVER_IP] [KIOSK_ID]
#
# Example:
#   ./scripts/dev-run.sh 10.1.50.100 KIOSK-NS-3E

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

export PYTHONPATH="${PROJECT_DIR}/src"
export VST_SERVER_IP="${1:-127.0.0.1}"
export VST_KIOSK_ID="${2:-KIOSK-DEV}"
export VST_LOCAL_PORT="${3:-8080}"
export VST_DB_PATH="${PROJECT_DIR}/dev_kiosk.db"
export VST_LOG_LEVEL="DEBUG"
export VST_SSL_VERIFY="false"

echo "=== VST Kiosk Dev Mode ==="
echo "Server:   ${VST_SERVER_IP}"
echo "Kiosk ID: ${VST_KIOSK_ID}"
echo "Local:    http://127.0.0.1:${VST_LOCAL_PORT}"
echo "DB:       ${VST_DB_PATH}"
echo ""

python3 -m vst_kiosk
