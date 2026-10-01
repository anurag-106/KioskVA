#!/bin/bash
# Generate the kiosk's local HTTPS certificate (Chromium -> kiosk backend on 127.0.0.1).
#
# Usage: ./scripts/gen-local-cert.sh [OUT_DIR] [--force]
#   OUT_DIR defaults to ./certs (dev). The .deb uses /etc/vst-kiosk.
#
# Chromium is launched with this cert's SPKI hash pinned
# (--ignore-certificate-errors-spki-list), so only this exact cert is trusted
# for the local page — no system CA changes, no blanket cert-error bypass.

set -e

OUT_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)/certs}"
FORCE="${2:-}"
KEY="${OUT_DIR}/local.key"
CRT="${OUT_DIR}/local.crt"

if [ -f "$KEY" ] && [ -f "$CRT" ] && [ "$FORCE" != "--force" ]; then
    echo "Local cert already exists: $CRT (use --force to regenerate)"
    exit 0
fi

mkdir -p "$OUT_DIR"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout "$KEY" -out "$CRT" -days 3650 \
    -subj "/CN=VST Kiosk Local/O=VirtuSense Technologies" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
    -addext "basicConstraints=critical,CA:false" \
    -addext "extendedKeyUsage=serverAuth" 2>/dev/null
chmod 600 "$KEY"

echo "Local cert generated:"
echo "  $CRT"
echo "  $KEY"
echo "  SPKI: $(openssl x509 -in "$CRT" -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64)"
