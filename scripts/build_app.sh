#!/usr/bin/env bash
# Build standalone Diplomat.app bundle using PyInstaller and ad-hoc code sign
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(which python3)"
fi

echo "==> Checking build dependencies..."
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller in virtual environment..."
    "$PYTHON" -m pip install pyinstaller
fi

echo "==> Building Diplomat.app with PyInstaller..."
"$PYTHON" -m PyInstaller \
    --name "Diplomat" \
    --windowed \
    --noconfirm \
    --clean \
    --add-data "diplomat/rules/no_ai_slop_compact.md:diplomat/rules" \
    --osx-bundle-identifier "com.sreenuraj.diplomat" \
    diplomat/main.py

APP_PATH="dist/Diplomat.app"

if [[ -d "$APP_PATH" ]]; then
    echo "==> Ad-hoc signing $APP_PATH..."
    codesign --force --deep --sign - "$APP_PATH"
    echo "✓ Successfully built: $APP_PATH"
    echo "You can move it to /Applications or double-click to launch."
else
    echo "Build failed: $APP_PATH was not found."
    exit 1
fi

