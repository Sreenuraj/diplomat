"""App entrypoint, menu bar tray icon, global hotkey listener and wiring."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import signal
import sys
from typing import Callable

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as config_mod
from .ui import PopupWindow, SettingsDialog, configure_macos_accessory_app

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

# macOS Carbon modifier flags (HIToolbox Events.h)
_CARBON_MODS = {
    "cmd": 1 << 8,       # cmdKey (0x0100)
    "command": 1 << 8,
    "super": 1 << 8,
    "meta": 1 << 8,
    "shift": 1 << 9,     # shiftKey (0x0200)
    "option": 1 << 11,   # optionKey (0x0800)
    "opt": 1 << 11,
    "alt": 1 << 11,
    "ctrl": 1 << 12,     # controlKey (0x1000)
    "control": 1 << 12,
}

# macOS virtual keycodes (HIToolbox Events.h kVK_*)
_MAC_VK_MAP = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "=": 0x18,
    "9": 0x19,
    "7": 0x1A,
    "-": 0x1B,
    "8": 0x1C,
    "0": 0x1D,
    "]": 0x1E,
    "o": 0x1F,
    "u": 0x20,
    "[": 0x21,
    "i": 0x22,
    "p": 0x23,
    "return": 0x24,
    "enter": 0x24,
    "l": 0x25,
    "j": 0x26,
    "'": 0x27,
    "k": 0x28,
    ";": 0x29,
    "\\": 0x2A,
    ",": 0x2B,
    "/": 0x2C,
    "n": 0x2D,
    "m": 0x2E,
    ".": 0x2F,
    "tab": 0x30,
    "space": 0x31,
    "`": 0x32,
    "backspace": 0x33,
    "delete": 0x33,
    "esc": 0x35,
    "escape": 0x35,
    "f1": 0x7A,
    "f2": 0x78,
    "f3": 0x63,
    "f4": 0x76,
    "f5": 0x60,
    "f6": 0x61,
    "f7": 0x62,
    "f8": 0x64,
    "f9": 0x65,
    "f10": 0x6D,
    "f11": 0x67,
    "f12": 0x6F,
    "left": 0x7B,
    "right": 0x7C,
    "down": 0x7D,
    "up": 0x7E,
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


def to_carbon_hotkey(spec: str) -> tuple[int, int]:
    """Convert a config hotkey like 'option+space' into (keycode, carbon_modifiers)."""
    parts = [p.strip().lower() for p in (spec or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey specification")
    modifiers = 0
    keycode: int | None = None
    for part in parts:
        clean = part[1:-1] if (part.startswith("<") and part.endswith(">")) else part
        if clean in _CARBON_MODS:
            modifiers |= _CARBON_MODS[clean]
        elif clean in _MAC_VK_MAP:
            if keycode is not None:
                raise ValueError(f"Multiple non-modifier keys in '{spec}'")
            keycode = _MAC_VK_MAP[clean]
        else:
            raise ValueError(f"Unsupported key '{part}' in '{spec}'")
    if modifiers == 0 or keycode is None:
        raise ValueError(f"Hotkey '{spec}' must include at least one modifier and one key")
    return keycode, modifiers


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
    """Qt signal bridge so hotkey callbacks always execute on the Qt main thread."""

    triggered = Signal()


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_EventHandlerProcPtr = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class _CarbonHotkeyBackend:
    """Main-thread macOS Carbon RegisterEventHotKey backend.

    Avoids calling TISCopyCurrentKeyboardInputSource from a background thread
    (which crashes with EXC_BREAKPOINT / SIGTRAP on modern macOS).
    """

    kEventClassKeyboard = 0x6B657962  # 'keyb'
    kEventHotKeyPressed = 6
    SIGNATURE = 0x44504C4D  # 'DPLM'

    def __init__(self, on_trigger: Callable[[], None]):
        lib_path = ctypes.util.find_library("Carbon")
        if not lib_path:
            raise RuntimeError("Carbon framework not available")
        self._carbon = ctypes.cdll.LoadLibrary(lib_path)
        self._on_trigger = on_trigger
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_counter = 0

        self._carbon.GetApplicationEventTarget.argtypes = []
        self._carbon.GetApplicationEventTarget.restype = ctypes.c_void_p

        self._carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            _EventHandlerProcPtr,
            ctypes.c_uint32,
            ctypes.POINTER(_EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.InstallEventHandler.restype = ctypes.c_int32

        self._carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.RegisterEventHotKey.restype = ctypes.c_int32

        self._carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        self._carbon.UnregisterEventHotKey.restype = ctypes.c_int32

        def _handler(_next_handler, _event, _user_data) -> int:
            try:
                self._on_trigger()
            except Exception:
                pass
            return 0

        # Keep a strong reference to the ctypes callback for the lifetime of the backend
        self._c_handler = _EventHandlerProcPtr(_handler)
        spec = _EventTypeSpec(self.kEventClassKeyboard, self.kEventHotKeyPressed)
        target = self._carbon.GetApplicationEventTarget()
        status = self._carbon.InstallEventHandler(
            target,
            self._c_handler,
            1,
            ctypes.byref(spec),
            None,
            ctypes.byref(self._handler_ref),
        )
        if status != 0:
            raise RuntimeError(f"InstallEventHandler failed with OSStatus {status}")

    def register(self, spec: str) -> None:
        self.unregister()
        keycode, modifiers = to_carbon_hotkey(spec)
        self._hotkey_counter += 1
        hk_id = _EventHotKeyID(self.SIGNATURE, self._hotkey_counter)
        target = self._carbon.GetApplicationEventTarget()
        ref = ctypes.c_void_p()
        status = self._carbon.RegisterEventHotKey(
            keycode,
            modifiers,
            hk_id,
            target,
            0,
            ctypes.byref(ref),
        )
        if status != 0 or not ref.value:
            raise RuntimeError(f"RegisterEventHotKey returned OSStatus {status}")
        self._hotkey_ref = ref

    def unregister(self) -> None:
        if self._hotkey_ref and self._hotkey_ref.value:
            try:
                self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            except Exception:
                pass
            self._hotkey_ref = ctypes.c_void_p()


class HotkeyManager:
    """Manage the global hotkey listener lifecycle."""

    def __init__(self, callback: Callable[[], None]):
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(callback)
        self._listener = None
        self._carbon_backend: _CarbonHotkeyBackend | None = None
        self.current_spec: str = ""
        self.last_error: str | None = None

    def pause(self) -> None:
        """Temporarily unregister the hotkey (e.g. while recording a new shortcut)."""
        if self._carbon_backend is not None:
            self._carbon_backend.unregister()
        elif self._listener is not None:
            self.stop()

    def resume(self) -> None:
        """Re-register the current hotkey after recording finishes or cancels."""
        if self.current_spec:
            self.start(self.current_spec)

    def start(self, spec: str) -> bool:
        self.stop()
        self.current_spec = spec
        if sys.platform == "darwin":
            try:
                if self._carbon_backend is None:
                    self._carbon_backend = _CarbonHotkeyBackend(self.bridge.triggered.emit)
                self._carbon_backend.register(spec)
                self.last_error = None
                return True
            except Exception as exc:
                self.last_error = f"Could not register hotkey '{spec}' ({exc}). Try another shortcut."
                return False

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
        if self._carbon_backend is not None:
            self._carbon_backend.unregister()
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
        configure_macos_accessory_app()
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
        """Open the one-screen Settings dialog above the always-on-top popup."""
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.present()
            return self.settings_dialog

        dlg = SettingsDialog(
            cfg=self.cfg,
            config_path=self.config_path,
            hotkey_status_fn=self._rebind_hotkey,
            hotkey_pause_fn=self.hotkey.pause,
            hotkey_resume_fn=self.hotkey.resume,
            parent=self.popup,
        )
        dlg.config_changed.connect(self._on_config_changed)
        dlg.quit_requested.connect(self.shutdown)
        self.settings_dialog = dlg
        dlg.present()
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