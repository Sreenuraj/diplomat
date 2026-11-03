#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
./run.sh --bg "$@"

# Automatically close the launcher Terminal window on macOS
osascript -e 'tell application "Terminal" to close (every window whose name contains "Diplomat.command")' 2>/dev/null || true
exit 0