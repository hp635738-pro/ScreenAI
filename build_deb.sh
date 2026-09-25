#!/usr/bin/env bash
# Build a .deb package for ScreenAI (Architecture: all).
#
# Usage:
#   ./build_deb.sh            # builds dist/screenai_<version>_all.deb
#
# Install:
#   sudo apt install ./dist/screenai_<version>_all.deb
#   sudo apt remove --purge screenai   # clean uninstall
#
# The package installs the app under /usr/lib/screenai with a launcher at
# /usr/bin/screenai. Runtime dependencies (python3-pyside6) are declared
# in the control file; PySide6 via pip inside a venv also works if you
# launch from source instead.

set -euo pipefail

APP_NAME="screenai"
MAINTAINER="ScreenAI <screenai@localhost>"
ARCH="all"
HOMEPAGE="https://github.com/hp635738-pro/ScreenAI"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

APP_VERSION="$(python3 - <<'PY'
import pathlib
import re

text = pathlib.Path("core/version.py").read_text(encoding="utf-8")
match = re.search(r'^\s*VERSION = "(.+?)"', text, re.MULTILINE)
assert match, "VERSION not found in core/version.py"
print(match.group(1))
PY
)"

STAGE="build/deb/${APP_NAME}"
APP_DIR="${STAGE}/usr/lib/${APP_NAME}"
DIST_DIR="dist"
DEB_FILE="${DIST_DIR}/${APP_NAME}_${APP_VERSION}_${ARCH}.deb"

echo "==> Staging ${APP_NAME} ${APP_VERSION}"
rm -rf "${STAGE}"
mkdir -p \
    "${STAGE}/DEBIAN" \
    "${APP_DIR}" \
    "${STAGE}/usr/bin" \
    "${STAGE}/usr/share/applications" \
    "${STAGE}/usr/share/icons/hicolor/scalable/apps"

# Application code (no caches, no local databases).
for item in main.py requirements.txt ui core database assets; do
    cp -a "${item}" "${APP_DIR}/"
done
find "${APP_DIR}" -name '__pycache__' -type d -exec rm -rf {} +

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: ${APP_NAME}
Version: ${APP_VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.12), python3-pyside6.qtwidgets, python3-pyside6.qtsvg, python3-pyautogui, python3-pil, python3-mss, python3-pynput
Recommends: xdotool
Maintainer: ${MAINTAINER}
Homepage: ${HOMEPAGE}
Description: AI-powered screen assistant and desktop control engine
 ScreenAI is a personal desktop assistant for Kubuntu/KDE. It parses
 natural commands locally and executes them: launching applications,
 running terminal commands and driving mouse/keyboard automation with
 a floating always-on-top execution popup and an emergency stop.
 Includes an OpenAI/Ollama tool-using agent, voice input, learn-mode
 workflows, system tray control and a confirmation safety model.
EOF

cat > "${STAGE}/usr/bin/${APP_NAME}" <<EOF
#!/bin/sh
exec python3 /usr/lib/${APP_NAME}/main.py "\$@"
EOF

cat > "${STAGE}/usr/share/applications/${APP_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ScreenAI
GenericName=Screen Assistant
Comment=AI-powered screen assistant with floating execution popup
Exec=/usr/bin/${APP_NAME}
Icon=${APP_NAME}
Terminal=false
Categories=Utility;Qt;
StartupWMClass=screenai
EOF

cp assets/icons/screenai.svg "${STAGE}/usr/share/icons/hicolor/scalable/apps/${APP_NAME}.svg"

# Permissions: dirs 755, files 644, launcher 755.
find "${STAGE}" -type d -exec chmod 755 {} +
find "${STAGE}" -type f -exec chmod 644 {} +
chmod 755 "${STAGE}/usr/bin/${APP_NAME}"

echo "==> Building ${DEB_FILE}"
mkdir -p "${DIST_DIR}"
dpkg-deb --root-owner-group --build "${STAGE}" "${DEB_FILE}"

echo "==> Package info"
dpkg-deb --info "${DEB_FILE}"
echo
echo "Install with:  sudo apt install ./${DEB_FILE}"
