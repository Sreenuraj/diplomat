"""Platform-specific utilities for macOS (window management, paste, and selection capture)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication

logger = logging.getLogger("diplomat.platform")


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


def simulate_paste(target_pid: int | None = None) -> bool:
    """Simulate Cmd+V keystroke to paste into the active application."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz

        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)

        # Release lingering modifier keys (Option, Shift, Return)
        for key in (0x3A, 0x3D, 0x38, 0x3C, 0x24):
            rel = Quartz.CGEventCreateKeyboardEvent(src, key, False)
            Quartz.CGEventSetFlags(rel, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, rel)

        # kVK_ANSI_V = 0x09
        down = Quartz.CGEventCreateKeyboardEvent(src, 0x09, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

        time.sleep(0.015)

        up = Quartz.CGEventCreateKeyboardEvent(src, 0x09, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        return True
    except Exception as exc:
        logger.warning(f"simulate_paste failed: {exc}")
        return False


def simulate_copy(target_pid: int | None = None) -> bool:
    """Simulate Cmd+C keystroke to copy from the active application."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz

        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)

        # Explicitly release Option and Shift keys so the stroke is pure Cmd+C rather than ⌥⌘C
        for key in (0x3A, 0x3D, 0x38, 0x3C):
            rel = Quartz.CGEventCreateKeyboardEvent(src, key, False)
            Quartz.CGEventSetFlags(rel, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, rel)

        # kVK_ANSI_C = 0x08
        down = Quartz.CGEventCreateKeyboardEvent(src, 0x08, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

        time.sleep(0.015)

        up = Quartz.CGEventCreateKeyboardEvent(src, 0x08, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        return True
    except Exception as exc:
        logger.warning(f"simulate_copy failed: {exc}")
        return False


def capture_selected_text(target_pid: int | None = None, timeout_sec: float = 0.45) -> str | None:
    """Grabs selected text from the frontmost app via Cmd+C, preserving existing clipboard."""
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        pb = NSPasteboard.generalPasteboard()
        initial_change_count = pb.changeCount()
        old_text = pb.stringForType_(NSPasteboardTypeString)

        logger.info(f"capture_selected_text: initial changeCount={initial_change_count}")
        if not simulate_copy(target_pid=target_pid):
            logger.warning("capture_selected_text: simulate_copy returned False")
            return None

        # Give target app time to process Cmd+C and write to pasteboard
        start = time.monotonic()
        captured: str | None = None
        while time.monotonic() - start < timeout_sec:
            QCoreApplication.processEvents()
            current_count = pb.changeCount()
            if current_count != initial_change_count:
                captured = pb.stringForType_(NSPasteboardTypeString)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                logger.info(f"capture_selected_text: changeCount {initial_change_count} -> {current_count} in {elapsed_ms}ms")
                break
            time.sleep(0.015)

        if captured is not None:
            # Restore previous clipboard content so user's clipboard is preserved
            pb.clearContents()
            if old_text is not None:
                pb.setString_forType_(old_text, NSPasteboardTypeString)
            cleaned = captured.strip()
            logger.info(f"capture_selected_text: captured {len(cleaned)} chars: {repr(cleaned[:50])}")
            return cleaned if cleaned else None

        logger.info(f"capture_selected_text: timed out after {timeout_sec}s with no clipboard change")
        return None
    except Exception as exc:
        logger.warning(f"capture_selected_text error: {exc}")
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

        # For Chromium and Electron apps (Teams, Chrome, Slack, VS Code), activate AX tree
        AX.AXUIElementSetAttributeValue(app_elem, "AXManualAccessibility", True)

        elem = None
        err, focused = AX.AXUIElementCopyAttributeValue(app_elem, "AXFocusedUIElement", None)
        if err == 0 and focused:
            elem = focused
        else:
            # Fallback: check focused window's focused element
            err_w, win = AX.AXUIElementCopyAttributeValue(app_elem, "AXFocusedWindow", None)
            if err_w == 0 and win:
                err_f, f_elem = AX.AXUIElementCopyAttributeValue(win, "AXFocusedUIElement", None)
                if err_f == 0 and f_elem:
                    elem = f_elem

        if not elem:
            # Also try system wide focused element
            sys_elem = AX.AXUIElementCreateSystemWide()
            err_s, s_elem = AX.AXUIElementCopyAttributeValue(sys_elem, "AXFocusedUIElement", None)
            if err_s == 0 and s_elem:
                elem = s_elem

        if not elem:
            logger.info(f"is_front_element_editable: no focused element found for pid={pid}")
            return False

        # 1. Native AXIsEditable attribute (Chromium, WebKit, AppKit)
        err_ed, is_ed = AX.AXUIElementCopyAttributeValue(elem, "AXIsEditable", None)
        if err_ed == 0 and is_ed:
            logger.info(f"is_front_element_editable: AXIsEditable=True for pid={pid}")
            return True

        # 2. Check if selected text or value is settable (editable)
        err_sel, sel_set = AX.AXUIElementIsAttributeSettable(elem, "AXSelectedText", None)
        if err_sel == 0 and sel_set:
            logger.info(f"is_front_element_editable: AXSelectedText is settable for pid={pid}")
            return True

        err_val, val_set = AX.AXUIElementIsAttributeSettable(elem, "AXValue", None)
        if err_val == 0 and val_set:
            logger.info(f"is_front_element_editable: AXValue is settable for pid={pid}")
            return True

        # 3. Check text-input roles
        err_role, role = AX.AXUIElementCopyAttributeValue(elem, "AXRole", None)
        logger.info(f"is_front_element_editable: role={role} for pid={pid}")
        if err_role == 0 and role in ("AXTextArea", "AXTextField", "AXComboBox", "AXSearchField"):
            return True

        # 4. Check if element has an editable ancestor
        err_anc, anc = AX.AXUIElementCopyAttributeValue(elem, "AXEditableAncestor", None)
        if err_anc == 0 and anc:
            logger.info(f"is_front_element_editable: AXEditableAncestor present for pid={pid}")
            return True

        return False
    except Exception as exc:
        logger.warning(f"is_front_element_editable error: {exc}")
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

