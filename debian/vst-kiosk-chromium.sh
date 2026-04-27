#!/bin/bash
# VST Kiosk — Chromium launcher
# Waits for the backend to be ready, then launches Chromium in kiosk mode.

BACKEND_URL="http://127.0.0.1:8080"

# Wait for backend to be ready (up to 30 seconds)
for i in $(seq 1 30); do
    if curl -sf "${BACKEND_URL}/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

exec /snap/bin/chromium \
    --kiosk \
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
