"""Platform-specific utilities for macOS (window management, paste, and selection capture)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication


def get_frontmost_app() -> Any | None:
    """Return the currently active frontmost NSRunningApplication on macOS."""
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        # Avoid treating Diplomat itself as the previous app
        if app is not None and app.processIdentifier() == os.getpid():
            return None
        return app
    except Exception:
        return None


def activate_app(app: Any | None) -> bool:
    """Activate / focus a previously active application."""
    if sys.platform != "darwin" or app is None:
        return False
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps

        return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception:
        return False


def is_accessibility_trusted(prompt: bool = False) -> bool:
    """Check if the process has macOS Accessibility permissions."""
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions

        return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": prompt}))
    except Exception:
        return False


def simulate_paste() -> bool:
    """Simulate Cmd+V keystroke to paste into the active application."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz

        # kVK_ANSI_V = 0x09
        down = Quartz.CGEventCreateKeyboardEvent(None, 0x09, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

        up = Quartz.CGEventCreateKeyboardEvent(None, 0x09, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        return True
    except Exception:
        return False


def simulate_copy() -> bool:
    """Simulate Cmd+C keystroke to copy from the active application."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz

        # kVK_ANSI_C = 0x08
        down = Quartz.CGEventCreateKeyboardEvent(None, 0x08, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

        up = Quartz.CGEventCreateKeyboardEvent(None, 0x08, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        return True
    except Exception:
        return False


def capture_selected_text(timeout_sec: float = 0.12) -> str | None:
    """Grabs selected text from the frontmost app via Cmd+C, then restores clipboard."""
    if sys.platform != "darwin":
        return None
    try:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return None
        old_text = clipboard.text()

        # Unique token unlikely to collide with actual clipboard text
        sentinel = f"__diplomat_capture_{time.time_ns()}__"
        clipboard.setText(sentinel)

        if not simulate_copy():
            clipboard.setText(old_text)
            return None

        # Give target app time to process Cmd+C
        start = time.monotonic()
        captured: str | None = None
        while time.monotonic() - start < timeout_sec:
            QCoreApplication.processEvents()
            current = clipboard.text()
            if current and current != sentinel:
                captured = current
                break
            time.sleep(0.015)

        # Restore previous clipboard content so user's clipboard is preserved
        clipboard.setText(old_text)

        cleaned = captured.strip() if captured else ""
        return cleaned if cleaned and cleaned != sentinel else None
    except Exception:
        return None


def is_front_element_editable(front_app: Any | None = None) -> bool:
    """Return True if the focused UI element in the frontmost app is an editable text field/area."""
    if sys.platform != "darwin":
        return False
    try:
        import ApplicationServices as AX

        if front_app is None:
            front_app = get_frontmost_app()
        if front_app is None:
            return False

        pid = front_app.processIdentifier()
        app_elem = AX.AXUIElementCreateApplication(pid)
        if not app_elem:
            return False

        err, elem = AX.AXUIElementCopyAttributeValue(app_elem, "AXFocusedUIElement", None)
        if err != 0 or not elem:
            return False

        # Check if selected text or value is settable (editable)
        err_sel, sel_set = AX.AXUIElementIsAttributeSettable(elem, "AXSelectedText", None)
        if err_sel == 0 and sel_set:
            return True

        err_val, val_set = AX.AXUIElementIsAttributeSettable(elem, "AXValue", None)
        if err_val == 0 and val_set:
            return True

        err_role, role = AX.AXUIElementCopyAttributeValue(elem, "AXRole", None)
        if err_role == 0 and role in ("AXTextArea", "AXTextField"):
            return True

        return False
    except Exception:
        return False


LAUNCH_AGENT_LABEL = "com.diplomat.app"


def get_launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def is_autostart_enabled() -> bool:
    """Return True if macOS launchd agent is installed."""
    if sys.platform != "darwin":
        return False
    return get_launch_agent_path().exists()


def set_autostart_enabled(enabled: bool) -> bool:
    """Enable or disable LaunchAgent to run Diplomat at user login."""
    if sys.platform != "darwin":
        return False

    plist_path = get_launch_agent_path()
    try:
        if enabled:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            python_bin = sys.executable
            repo_root = Path(__file__).resolve().parent.parent
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>-m</string>
        <string>diplomat.main</string>
        <string>--no-popup</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{repo_root}</string>
</dict>
</plist>
"""
            plist_path.write_text(plist_content, encoding="utf-8")
            subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True)
            return True
        else:
            if plist_path.exists():
                subprocess.run(["launchctl", "unload", "-w", str(plist_path)], capture_output=True)
                plist_path.unlink(missing_ok=True)
            return True
    except Exception:
        return False

