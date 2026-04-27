#!/bin/bash
# Build the VST Kiosk .deb package.
#
# Usage: ./scripts/build-deb.sh
#
# Prerequisites:
#   - Run on a machine with internet to download wheels first:
#     pip download -r requirements.txt -d wheels/
#   - dpkg-deb must be installed

set -e

VERSION="1.0.0"
PKG_NAME="vst-kiosk"
BUILD_DIR="build/${PKG_NAME}_${VERSION}_all"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Building ${PKG_NAME} ${VERSION} ==="

# Clean previous build
rm -rf "$BUILD_DIR"

# Create directory structure
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/vst-kiosk/src"
mkdir -p "${BUILD_DIR}/opt/vst-kiosk/frontend"
mkdir -p "${BUILD_DIR}/opt/vst-kiosk/wheels"
mkdir -p "${BUILD_DIR}/opt/vst-kiosk/bin"
mkdir -p "${BUILD_DIR}/etc/systemd/system"
mkdir -p "${BUILD_DIR}/etc/xdg/autostart"
mkdir -p "${BUILD_DIR}/var/lib/vst-kiosk"
mkdir -p "${BUILD_DIR}/var/log/vst-kiosk"

# Copy DEBIAN control files
cp debian/control "${BUILD_DIR}/DEBIAN/"
cp debian/conffiles "${BUILD_DIR}/DEBIAN/"
cp debian/postinst "${BUILD_DIR}/DEBIAN/"
cp debian/prerm "${BUILD_DIR}/DEBIAN/"
cp debian/postrm "${BUILD_DIR}/DEBIAN/"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"

# Copy application source
cp -r src/vst_kiosk "${BUILD_DIR}/opt/vst-kiosk/src/"

# Copy frontend
cp -r frontend/* "${BUILD_DIR}/opt/vst-kiosk/frontend/"

# Copy wheels (if they exist)
if ls wheels/*.whl 1>/dev/null 2>&1; then
    cp wheels/*.whl "${BUILD_DIR}/opt/vst-kiosk/wheels/"
fi

# Copy config template
cp debian/vst-kiosk.conf.template "${BUILD_DIR}/etc/vst-kiosk.conf" 2>/dev/null || \
cat > "${BUILD_DIR}/etc/vst-kiosk.conf" << 'CONF'
[server]
ip = 10.1.50.100
port = 443

[kiosk]
id = KIOSK-CHANGE-ME
local_port = 8080

[database]
path = /var/lib/vst-kiosk/kiosk.db
purge_days = 30

[logging]
level = INFO

[ssl]
verify = true
CONF

# Copy systemd service
cp debian/vst-kiosk.service "${BUILD_DIR}/etc/systemd/system/"

# Copy Chromium launcher
cp debian/vst-kiosk-chromium.sh "${BUILD_DIR}/opt/vst-kiosk/bin/"
chmod 755 "${BUILD_DIR}/opt/vst-kiosk/bin/vst-kiosk-chromium.sh"

# Copy Chromium autostart
cp debian/vst-kiosk-chromium.desktop "${BUILD_DIR}/etc/xdg/autostart/"

# Build the .deb
dpkg-deb --build "$BUILD_DIR"

echo ""
echo "=== Package built: build/${PKG_NAME}_${VERSION}_all.deb ==="
echo ""
echo "Deploy steps:"
echo "  1. Copy .deb to NUC"
echo "  2. sudo dpkg -i ${PKG_NAME}_${VERSION}_all.deb"
echo "  3. sudo nano /etc/vst-kiosk.conf  # set SERVER_IP and KIOSK_ID"
echo "  4. sudo systemctl start vst-kiosk"
