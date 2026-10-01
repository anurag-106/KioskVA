#!/bin/bash
# Start the kiosk: HTTPS backend + Chromium in kiosk mode, all over TLS.
#
# Usage: ./scripts/start-kiosk.sh [SERVER_IP] [KIOSK_ID] [--no-browser | --windowed]
#
#   SERVER_IP   VST server address (default 127.0.0.1). Must be in the
#               server cert's SAN (generate_certs --ip <SERVER_IP>).
#   KIOSK_ID    Must match a kiosk registered in the server admin UI
#               (default KIOSK-DEV).
#   --no-browser  Start only the backend (e.g. to open the page yourself).
#   --windowed    Open Chromium in a normal resizable window instead of fullscreen kiosk mode.
#
# Environment overrides:
#   SERVER_PORT  server port (default 443)
#   SERVER_CA    server.crt to trust (default: ../windowsServerVA/certs/server.crt,
#                then ./certs/server.crt)
#   LOCAL_PORT   kiosk page port on 127.0.0.1 (default 8080)
#   KIOSK_DB_PATH  kiosk debug log DB (default ./dev_kiosk.db)
#
# Links:  Chromium --HTTPS/WSS--> kiosk backend (127.0.0.1, certs/local.crt)
#         kiosk backend --WSS, cert verified--> server
# Ctrl+C stops both.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

POSITIONAL=()
OPEN_BROWSER=1
WINDOW_MODE=(--kiosk)
for arg in "$@"; do
    case "$arg" in
        --no-browser) OPEN_BROWSER=0 ;;
        --windowed) WINDOW_MODE=(--new-window --window-size=1280,800) ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
SERVER_IP="${POSITIONAL[0]:-127.0.0.1}"
KIOSK_ID="${POSITIONAL[1]:-KIOSK-DEV}"
SERVER_PORT="${SERVER_PORT:-443}"
LOCAL_PORT="${LOCAL_PORT:-8080}"

if [ -z "$SERVER_CA" ]; then
    for candidate in "$PROJECT_DIR/../windowsServerVA/certs/server.crt" "$PROJECT_DIR/certs/server.crt"; do
        if [ -f "$candidate" ]; then SERVER_CA="$(realpath "$candidate")"; break; fi
    done
fi
if [ ! -f "$SERVER_CA" ]; then
    echo "ERROR: server certificate not found."
    echo "Copy the server's certs/server.crt to $PROJECT_DIR/certs/server.crt or set SERVER_CA=/path/to/server.crt"
    exit 1
fi

# --- Python environment ---
if ! .venv/bin/python -c "import fastapi, uvicorn, websockets, pydantic" 2>/dev/null; then
    echo "Setting up .venv ..."
    [ -x .venv/bin/python ] || python3 -m venv .venv
    .venv/bin/pip install --quiet --no-index --find-links ./wheels -r requirements.txt 2>/dev/null \
        || .venv/bin/pip install --quiet -r requirements.txt
fi

# --- Local HTTPS cert for the kiosk page ---
"$SCRIPT_DIR/gen-local-cert.sh" "$PROJECT_DIR/certs" >/dev/null
LOCAL_CERT="$PROJECT_DIR/certs/local.crt"
LOCAL_KEY="$PROJECT_DIR/certs/local.key"
SPKI="$(openssl x509 -in "$LOCAL_CERT" -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64)"

export PYTHONPATH="$PROJECT_DIR/src"
export VST_CONF_PATH="${VST_CONF_PATH:-/nonexistent}"   # dev: ignore /etc/vst-kiosk.conf
export VST_SERVER_IP="$SERVER_IP"
export VST_SERVER_PORT="$SERVER_PORT"
export VST_KIOSK_ID="$KIOSK_ID"
export VST_LOCAL_PORT="$LOCAL_PORT"
# Own variable: VST_DB_PATH may be set for the server in the same shell
export VST_DB_PATH="${KIOSK_DB_PATH:-$PROJECT_DIR/dev_kiosk.db}"
export VST_SSL_VERIFY="true"
export VST_SSL_CA_BUNDLE="$SERVER_CA"
export VST_LOCAL_CERT="$LOCAL_CERT"
export VST_LOCAL_KEY="$LOCAL_KEY"
export VST_LOG_LEVEL="${VST_LOG_LEVEL:-INFO}"

URL="https://127.0.0.1:${LOCAL_PORT}/"
echo "=== VST Kiosk ==="
echo "Server:   wss://${SERVER_IP}:${SERVER_PORT}/ws/kiosk/${KIOSK_ID}  (trusting ${SERVER_CA})"
echo "Page:     ${URL}"
echo ""

# Fail fast with a clear message if the server cert won't verify
if ! curl -sf --max-time 5 --cacert "$SERVER_CA" "https://${SERVER_IP}:${SERVER_PORT}/api/health" >/dev/null; then
    echo "WARNING: https://${SERVER_IP}:${SERVER_PORT} is not reachable with this cert yet."
    echo "         Is the server running with TLS, and is ${SERVER_IP} in its cert SAN? Kiosk will keep retrying."
fi

.venv/bin/python -m vst_kiosk &
BACKEND_PID=$!
BROWSER_PID=""
cleanup() {
    [ -n "$BROWSER_PID" ] && kill "$BROWSER_PID" 2>/dev/null
    kill "$BACKEND_PID" 2>/dev/null
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
    curl -sf --cacert "$LOCAL_CERT" "${URL}health" >/dev/null 2>&1 && break
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then echo "ERROR: kiosk backend exited."; exit 1; fi
    sleep 1
done

if [ "$OPEN_BROWSER" = 1 ]; then
    BROWSER=""
    for b in /snap/bin/chromium chromium-browser chromium google-chrome; do
        if command -v "$b" >/dev/null 2>&1; then BROWSER="$(command -v "$b")"; break; fi
    done
    if [ -z "$BROWSER" ]; then
        echo "No Chromium/Chrome found — open ${URL} manually. Backend is running (Ctrl+C to stop)."
    else
        # Snap Chromium can only write inside ~/snap/chromium
        case "$BROWSER" in
            /snap/*) PROFILE="$HOME/snap/chromium/common/vst-kiosk-profile" ;;
            *)       PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/vst-kiosk/chrome-profile" ;;
        esac
        mkdir -p "$PROFILE"
        # SPKI pin trusts exactly certs/local.crt; it needs its own --user-data-dir
        "$BROWSER" \
            "${WINDOW_MODE[@]}" \
            --user-data-dir="$PROFILE" \
            --ignore-certificate-errors-spki-list="$SPKI" \
            --no-first-run \
            --disable-translate \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --disable-features=TranslateUI \
            --autoplay-policy=no-user-gesture-required \
            --noerrdialogs \
            --disable-pinch \
            --overscroll-history-navigation=0 \
            "$URL" >/dev/null 2>&1 &
        BROWSER_PID=$!
        echo "Chromium started (${WINDOW_MODE[0]#--}). Closing it or Ctrl+C here stops the kiosk."
    fi
fi

# Stop everything when either the backend or the browser exits
if [ -n "$BROWSER_PID" ]; then
    wait -n "$BACKEND_PID" "$BROWSER_PID"
else
    wait "$BACKEND_PID"
fi
