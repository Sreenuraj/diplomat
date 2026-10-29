"""App entrypoint, menu bar tray icon, global hotkey listener and wiring."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from typing import Callable

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as config_mod
from .ui import PopupWindow, SettingsDialog

_KEY_MAP = {
    "option": "<alt>",
    "opt": "<alt>",
    "alt": "<alt>",
    "cmd": "<cmd>",
    "command": "<cmd>",
    "super": "<cmd>",
    "meta": "<cmd>",
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "shift": "<shift>",
    "space": "<space>",
    "enter": "<enter>",
    "return": "<enter>",
    "tab": "<tab>",
    "esc": "<esc>",
    "escape": "<esc>",
}


def to_pynput_hotkey(spec: str) -> str:
    """Convert a config hotkey like 'option+space' into pynput's '<alt>+<space>'."""
    parts = [p.strip().lower() for p in (spec or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey specification")
    mapped: list[str] = []
    for part in parts:
        if part in _KEY_MAP:
            mapped.append(_KEY_MAP[part])
        elif part.startswith("<") and part.endswith(">"):
            mapped.append(part)
        elif len(part) == 1:
            mapped.append(part)
        else:
            mapped.append(f"<{part}>")
    return "+".join(mapped)


def format_hotkey_label(spec: str) -> str:
    """Format 'option+space' into macOS-friendly '⌥ Space' for menus."""
    symbols = {
        "option": "⌥",
        "opt": "⌥",
        "alt": "⌥",
        "cmd": "⌘",
        "command": "⌘",
        "ctrl": "⌃",
        "control": "⌃",
        "shift": "⇧",
        "space": "Space",
    }
    parts = [p.strip().lower() for p in (spec or "").split("+") if p.strip()]
    return " ".join(symbols.get(p, p.upper()) for p in parts) or spec


class HotkeyBridge(QObject):
    """Qt signal bridge so pynput's thread never touches Qt widgets directly."""

    triggered = Signal()


class HotkeyManager:
    """Manage the global hotkey listener lifecycle."""

    def __init__(self, callback: Callable[[], None]):
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(callback)
        self._listener = None
        self.current_spec: str = ""
        self.last_error: str | None = None

    def start(self, spec: str) -> bool:
        self.stop()
        self.current_spec = spec
        try:
            pynput_spec = to_pynput_hotkey(spec)
            from pynput import keyboard

            listener = keyboard.GlobalHotKeys({pynput_spec: self.bridge.triggered.emit})
            listener.daemon = True
            listener.start()
            self._listener = listener
            self.last_error = None
            return True
        except Exception as exc:
            self._listener = None
            self.last_error = (
                f"Could not register hotkey '{spec}' ({exc}). "
                "Check System Settings → Privacy & Security → Input Monitoring."
            )
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None


def build_tray_icon() -> QIcon:
    """Render a crisp monogram icon in code (no external asset files required)."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(28, 28, 30, 235))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(6, 6, 52, 52), 14, 14)

    painter.setPen(QColor("#ffffff"))
    font = QFont(".AppleSystemUIFont", 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRectF(6, 6, 52, 52), Qt.AlignmentFlag.AlignCenter, "D")
    painter.end()
    return QIcon(pixmap)


class DiplomatApp(QObject):
    """Coordinates the popup window, menu bar tray icon and global hotkey."""

    def __init__(
        self,
        app: QApplication,
        cfg: dict | None = None,
        config_path=None,
        enable_hotkey: bool = True,
    ):
        super().__init__()
        self.app = app
        self.config_path = config_path
        resolved_path = config_path or config_mod.config_path()
        self.is_first_run = not resolved_path.exists()
        self.cfg = cfg if cfg is not None else config_mod.load(config_path)
        self.settings_dialog: SettingsDialog | None = None
        self._stopped = False

        self.popup = PopupWindow(cfg=self.cfg, config_path=config_path)
        self.popup.settings_requested.connect(self.open_settings)
        self.popup.quit_requested.connect(self.shutdown)
        self.popup.config_changed.connect(self._on_config_changed)

        self.hotkey = HotkeyManager(self.popup.toggle_popup)
        if enable_hotkey:
            self.hotkey.start(self.cfg.get("hotkey", config_mod.DEFAULTS["hotkey"]))

        self.tray: QSystemTrayIcon | None = None
        self.toggle_action: QAction | None = None
        self._setup_tray()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(build_tray_icon(), self.app)
        tray.setToolTip("Diplomat")

        menu = QMenu()
        hotkey_label = format_hotkey_label(self.cfg.get("hotkey", config_mod.DEFAULTS["hotkey"]))
        self.toggle_action = menu.addAction(f"Show / Hide Diplomat ({hotkey_label})")
        self.toggle_action.triggered.connect(self.popup.toggle_popup)

        settings_action = menu.addAction("Settings…")
        settings_action.triggered.connect(self.open_settings)

        menu.addSeparator()
        quit_action = menu.addAction("Quit Diplomat (⌘Q)")
        quit_action.triggered.connect(self.shutdown)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray = tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.popup.toggle_popup()

    def _on_config_changed(self, cfg: dict) -> None:
        new_hotkey = cfg.get("hotkey", config_mod.DEFAULTS["hotkey"])
        if new_hotkey != self.hotkey.current_spec and self.hotkey.current_spec:
            self.hotkey.start(new_hotkey)
        if self.toggle_action is not None:
            self.toggle_action.setText(f"Show / Hide Diplomat ({format_hotkey_label(new_hotkey)})")
        self.cfg = cfg
        self.popup.reload_config(cfg)

    def _rebind_hotkey(self, spec: str) -> tuple[bool, str | None]:
        ok = self.hotkey.start(spec)
        if self.toggle_action is not None:
            self.toggle_action.setText(f"Show / Hide Diplomat ({format_hotkey_label(spec)})")
        return ok, self.hotkey.last_error

    def open_settings(self) -> SettingsDialog:
        """Open the one-screen Settings dialog; changes apply immediately."""
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return self.settings_dialog

        dlg = SettingsDialog(
            cfg=self.cfg,
            config_path=self.config_path,
            hotkey_status_fn=self._rebind_hotkey,
            parent=self.popup if self.popup.isVisible() else None,
        )
        dlg.config_changed.connect(self._on_config_changed)
        dlg.quit_requested.connect(self.shutdown)
        self.settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def print_startup_banner(self) -> None:
        resolved_path = self.config_path or config_mod.config_path()
        hotkey_spec = self.cfg.get("hotkey", config_mod.DEFAULTS["hotkey"])
        hotkey_label = format_hotkey_label(hotkey_spec)
        model = self.cfg.get("model") or "(auto-detect on first request)"
        print(
            f"Diplomat running (PID {os.getpid()})\n"
            f"  Provider : {self.cfg.get('provider')} ({self.cfg.get('base_url')})\n"
            f"  Model    : {model}\n"
            f"  Hotkey   : {hotkey_label} ({hotkey_spec})\n"
            f"  Config   : {resolved_path}\n"
            f"Stop with Ctrl+C in this terminal, ⌘Q, or the 'Quit' button in the UI.",
            flush=True,
        )

    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.hotkey.stop()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        if self.tray is not None:
            self.tray.hide()
        self.popup.close()
        print(f"\nDiplomat stopped (PID {os.getpid()}).", flush=True)
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m diplomat.main", description="Start the Diplomat popup and tray app.")
    ap.add_argument("--no-popup", action="store_true", help="start in the menu bar without opening the popup immediately")
    ap.add_argument("--no-hotkey", action="store_true", help="do not register the global hotkey")
    args = ap.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Diplomat")
    app.setQuitOnLastWindowClosed(False)

    controller = DiplomatApp(app, enable_hotkey=not args.no_hotkey)
    app.aboutToQuit.connect(controller.hotkey.stop)

    # Periodic heartbeat so Python runs signal handlers (Ctrl+C / SIGINT) while inside Qt's C++ loop
    sig_timer = QTimer(app)
    sig_timer.setInterval(150)
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start()

    def _handle_sig(_signum, _frame) -> None:
        controller.shutdown()

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    controller.print_startup_banner()

    if not args.no_popup:
        controller.popup.show_popup()
    if controller.is_first_run or not controller.cfg.get("model"):
        controller.open_settings()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())