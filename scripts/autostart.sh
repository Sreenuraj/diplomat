#!/usr/bin/env bash
# Manage Diplomat autostart on macOS login via launchd
set -euo pipefail

LABEL="com.diplomat.app"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(which python3)"
fi

action="${1:-status}"

case "$action" in
    enable|install)
        mkdir -p "$HOME/Library/LaunchAgents"
        cat <<EOF > "$PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>-m</string>
        <string>diplomat.main</string>
        <string>--no-popup</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${ROOT_DIR}</string>
</dict>
</plist>
EOF
        launchctl unload -w "$PLIST" 2>/dev/null || true
        launchctl load -w "$PLIST"
        echo "✓ Diplomat autostart enabled at login ($PLIST)"
        ;;
    disable|uninstall|remove)
        if [[ -f "$PLIST" ]]; then
            launchctl unload -w "$PLIST" 2>/dev/null || true
            rm -f "$PLIST"
            echo "✓ Diplomat autostart disabled"
        else
            echo "Diplomat autostart is not installed"
        fi
        ;;
    status)
        if [[ -f "$PLIST" ]]; then
            echo "Diplomat autostart is enabled ($PLIST)"
        else
            echo "Diplomat autostart is disabled"
        fi
        ;;
    *)
        echo "Usage: $0 [enable|disable|status]"
        exit 1
        ;;
esac
