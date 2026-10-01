#!/bin/bash
# VST Kiosk — Chromium launcher
# Waits for the HTTPS backend to be ready, then launches Chromium in kiosk mode.

LOCAL_CERT="/etc/vst-kiosk/local.crt"
BACKEND_URL="https://127.0.0.1:8080"

# Wait for backend to be ready (up to 30 seconds)
for i in $(seq 1 30); do
    if curl -sf --cacert "$LOCAL_CERT" "${BACKEND_URL}/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Pin the local page's self-signed cert by SPKI hash: trusts exactly this cert,
# no system CA change, no blanket cert-error bypass. Requires its own profile.
SPKI="$(openssl x509 -in "$LOCAL_CERT" -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64)"
PROFILE="$HOME/snap/chromium/common/vst-kiosk-profile"
mkdir -p "$PROFILE"

exec /snap/bin/chromium \
    --kiosk \
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
    "${BACKEND_URL}/"
