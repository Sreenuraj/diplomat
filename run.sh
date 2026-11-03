#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment in .venv…"
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    echo "Installing dependencies from requirements.txt…"
    .venv/bin/pip install -r requirements.txt
fi

LOG_FILE="$HOME/Library/Logs/Diplomat.log"

case "${1:-}" in
    --bg|start)
        shift || true
        if pgrep -f "diplomat.main" >/dev/null 2>&1; then
            echo "Diplomat is already running (PID $(pgrep -f "diplomat.main" | head -n1))."
            exit 0
        fi
        mkdir -p "$HOME/Library/Logs"
        nohup .venv/bin/python -m diplomat.main "$@" > "$LOG_FILE" 2>&1 &
        pid=$!
        echo "✓ Diplomat started in background (PID ${pid})."
        echo "  Hotkey : ⌥ Space"
        echo "  Reply  : ⌥ ⇧ Space"
        echo "  Logs   : ${LOG_FILE}"
        echo "Stop with: ./run.sh stop, ⌘Q, or the tray icon."
        ;;
    stop)
        if pgrep -f "diplomat.main" >/dev/null 2>&1; then
            pkill -f "diplomat.main" 2>/dev/null || true
            echo "✓ Diplomat stopped."
        else
            echo "Diplomat is not running."
        fi
        ;;
    status)
        if pgrep -f "diplomat.main" >/dev/null 2>&1; then
            echo "Diplomat is running (PID $(pgrep -f "diplomat.main" | tr '\n' ' '))."
        else
            echo "Diplomat is stopped."
        fi
        ;;
    *)
        exec .venv/bin/python -m diplomat.main "$@"
        ;;
esac