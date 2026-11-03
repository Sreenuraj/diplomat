"""Popup window and Settings dialog for Diplomat."""

from __future__ import annotations

import sys
import threading
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import config as config_mod
from . import llm, platform as platform_mod, prompt, voice

AMBER_RATIO = 0.9


def is_dark_mode() -> bool:
    """Detect whether the current macOS / Qt appearance is dark."""
    app = QGuiApplication.instance()
    if app is not None:
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        except AttributeError:
            pass
        pal = app.palette()
        return pal.color(QPalette.ColorRole.Window).lightness() < 128
    return False


def _theme_tokens(dark: bool) -> dict[str, str]:
    if dark:
        return {
            "win_bg": "#1e1e22",
            "card_bg": "rgba(32, 32, 36, 244)",
            "card_border": "rgba(255, 255, 255, 38)",
            "text_fg": "#f2f2f7",
            "muted_fg": "#98989f",
            "field_bg": "rgba(255, 255, 255, 16)",
            "field_border": "rgba(255, 255, 255, 32)",
            "field_focus": "#0a84ff",
            "btn_bg": "rgba(255, 255, 255, 22)",
            "btn_hover": "rgba(255, 255, 255, 38)",
            "primary_bg": "#0a84ff",
            "primary_hover": "#409cff",
            "primary_fg": "#ffffff",
            "danger_fg": "#ff453a",
            "danger_bg": "rgba(255, 69, 58, 28)",
            "danger_hover": "rgba(255, 69, 58, 52)",
            "divider": "rgba(255, 255, 255, 26)",
            "slider_groove": "rgba(255, 255, 255, 42)",
        }
    return {
        "win_bg": "#f5f5f7",
        "card_bg": "rgba(250, 250, 252, 246)",
        "card_border": "rgba(0, 0, 0, 28)",
        "text_fg": "#1c1c1e",
        "muted_fg": "#6c6c70",
        "field_bg": "rgba(0, 0, 0, 9)",
        "field_border": "rgba(0, 0, 0, 24)",
        "field_focus": "#007aff",
        "btn_bg": "rgba(0, 0, 0, 13)",
        "btn_hover": "rgba(0, 0, 0, 24)",
        "primary_bg": "#007aff",
        "primary_hover": "#0062cc",
        "primary_fg": "#ffffff",
        "danger_fg": "#d70015",
        "danger_bg": "rgba(215, 0, 21, 18)",
        "danger_hover": "rgba(215, 0, 21, 34)",
        "divider": "rgba(0, 0, 0, 20)",
        "slider_groove": "rgba(0, 0, 0, 32)",
    }


def build_stylesheet(dark: bool) -> str:
    t = _theme_tokens(dark)
    return f"""
        QDialog {{
            background-color: {t["win_bg"]};
            color: {t["text_fg"]};
        }}
        QFrame#card {{
            background-color: {t["card_bg"]};
            border: 1px solid {t["card_border"]};
            border-radius: 22px;
        }}
        QLabel {{
            color: {t["text_fg"]};
            background: transparent;
            font-size: 13px;
        }}
        QLabel#titleLabel {{
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#formLabel {{
            color: {t["muted_fg"]};
            font-size: 13px;
            font-weight: 500;
        }}
        QLabel#mutedLabel, QLabel#sliderLabel {{
            color: {t["muted_fg"]};
            font-size: 12px;
        }}
        QLabel#errorLabel {{
            color: {t["danger_fg"]};
            font-size: 12px;
        }}
        QLabel#warnLabel {{
            color: #d97706;
            font-size: 11px;
        }}
        QPlainTextEdit {{
            background-color: {t["field_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 10px;
            padding: 8px;
            font-size: 13px;
            selection-background-color: {t["primary_bg"]};
            selection-color: {t["primary_fg"]};
        }}
        QPlainTextEdit:focus {{
            border: 1px solid {t["field_focus"]};
        }}
        QPlainTextEdit#outputEdit {{
            background-color: transparent;
            border: 1px solid {t["field_border"]};
        }}
        QLineEdit {{
            background-color: {t["field_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 8px;
            padding: 5px 10px;
            min-height: 22px;
            font-size: 13px;
            selection-background-color: {t["primary_bg"]};
            selection-color: {t["primary_fg"]};
        }}
        QLineEdit:focus {{
            border: 1px solid {t["field_focus"]};
        }}
        QComboBox {{
            background-color: {t["btn_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 8px;
            padding: 5px 10px;
            min-height: 24px;
            font-size: 13px;
        }}
        QComboBox:hover {{
            background-color: {t["btn_hover"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {t["win_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            selection-background-color: {t["primary_bg"]};
            selection-color: {t["primary_fg"]};
            padding: 4px;
            outline: none;
        }}
        QPushButton {{
            background-color: {t["btn_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 8px;
            padding: 5px 14px;
            min-height: 22px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {t["btn_hover"]};
        }}
        QPushButton:disabled {{
            color: {t["muted_fg"]};
            background-color: transparent;
            border-color: {t["divider"]};
        }}
        QPushButton#primaryButton {{
            background-color: {t["primary_bg"]};
            color: {t["primary_fg"]};
            border: none;
            font-weight: 600;
        }}
        QPushButton#primaryButton:hover {{
            background-color: {t["primary_hover"]};
        }}
        QPushButton#primaryButton:disabled {{
            background-color: {t["btn_bg"]};
            color: {t["muted_fg"]};
        }}
        QPushButton#dangerButton {{
            background-color: {t["danger_bg"]};
            color: {t["danger_fg"]};
            border: 1px solid {t["danger_fg"]};
            font-weight: 500;
        }}
        QPushButton#dangerButton:hover {{
            background-color: {t["danger_hover"]};
        }}
        QPushButton#sectionToggle, QPushButton#linkButton, QPushButton#iconButton {{
            background: transparent;
            border: none;
            color: {t["muted_fg"]};
            padding: 2px 6px;
            min-height: 20px;
            font-size: 12px;
            text-align: left;
        }}
        QPushButton#sectionToggle:hover, QPushButton#linkButton:hover, QPushButton#iconButton:hover {{
            color: {t["text_fg"]};
        }}
        QPushButton#iconButton {{
            font-size: 15px;
            padding: 2px 8px;
            text-align: center;
        }}
        QCheckBox {{
            color: {t["text_fg"]};
            font-size: 13px;
            spacing: 8px;
        }}
        QFrame#divider {{
            background-color: {t["divider"]};
            max-height: 1px;
            min-height: 1px;
            border: none;
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {t["slider_groove"]};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {t["primary_bg"]};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: #ffffff;
            border: 1px solid rgba(0, 0, 0, 60);
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QFrame#inputContainer {{
            background-color: {t["field_bg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 16px;
        }}
        QFrame#inputContainer:focus-within {{
            border: 1px solid {t["field_focus"]};
        }}
        QPlainTextEdit#chatDraftEdit {{
            background-color: transparent;
            border: none;
            padding: 4px 6px;
            font-size: 13.5px;
            color: {t["text_fg"]};
        }}
        QComboBox#pillCombo {{
            background-color: {t["btn_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 11px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 500;
            min-height: 22px;
            max-height: 24px;
        }}
        QComboBox#pillCombo:hover {{
            background-color: {t["btn_hover"]};
        }}
        QPushButton#pillButton {{
            background-color: {t["btn_bg"]};
            color: {t["text_fg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 11px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 500;
            min-height: 22px;
            max-height: 24px;
        }}
        QPushButton#pillButton:hover {{
            background-color: {t["btn_hover"]};
        }}
        QPushButton#circleIconButton {{
            border: none;
            border-radius: 16px;
            min-width: 32px;
            max-width: 32px;
            min-height: 32px;
            max-height: 32px;
            background: transparent;
        }}
        QPushButton#circleIconButton:hover {{
            opacity: 0.88;
        }}
        QFrame#outputContainer {{
            background-color: {t["field_bg"]};
            border: 1px solid {t["field_border"]};
            border-radius: 14px;
        }}
        QLabel#statusBadge {{
            color: #34c759;
            font-size: 11.5px;
            font-weight: 600;
        }}
    """


def configure_macos_accessory_app() -> None:
    """Make the macOS application an accessory agent (like Spotlight / Raycast)
    so its floating NSPanel can appear over any active or full-screen app on the
    current Space without forcing macOS to switch back to a desktop Space.
    """
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        ns_app = AppKit.NSApplication.sharedApplication()
        if ns_app is not None:
            policy = int(getattr(AppKit, "NSApplicationActivationPolicyAccessory", 1))
            ns_app.setActivationPolicy_(policy)
    except Exception:
        pass


def apply_macos_vibrancy(widget: QWidget) -> bool:
    """Attach an NSVisualEffectView to the macOS window for native frosted glass blur."""
    if sys.platform != "darwin":
        return False
    try:
        import objc
        import AppKit

        wid = int(widget.winId())
        if not wid:
            return False
        ns_view = objc.objc_object(c_void_p=wid)
        ns_win = ns_view.window() if hasattr(ns_view, "window") else None
        if ns_win is None:
            return False

        content_view = ns_win.contentView()
        if content_view is None:
            return False

        for sub in content_view.subviews():
            if "NSVisualEffectView" in str(type(sub)):
                return True

        bounds = content_view.bounds()
        effect_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(bounds)
        effect_view.setAutoresizingMask_(18)  # NSViewWidthSizable (2) | NSViewHeightSizable (16)
        effect_view.setBlendingMode_(getattr(AppKit, "NSVisualEffectBlendingModeBehindWindow", 0))
        effect_view.setState_(getattr(AppKit, "NSVisualEffectStateActive", 1))
        effect_view.setMaterial_(getattr(AppKit, "NSVisualEffectMaterialHUDWindow", 20))
        if hasattr(effect_view, "setWantsLayer_"):
            effect_view.setWantsLayer_(True)
            layer = effect_view.layer()
            if layer is not None and hasattr(layer, "setCornerRadius_"):
                layer.setCornerRadius_(22.0)
                layer.setMasksToBounds_(True)

        content_view.addSubview_positioned_relativeTo_(effect_view, -1, None)
        return True
    except Exception:
        return False


def _configure_macos_window(
    widget: QWidget,
    level_offset: int = 0,
    non_activating_panel: bool = True,
) -> None:
    """Configure macOS NSPanel / NSWindow so it floats above all apps on every
    Space and full-screen Space (Spotlight-style), never hides when another app
    is clicked, and follows the user across Spaces.
    """
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        import objc

        apply_macos_vibrancy(widget)

        wid = int(widget.winId())
        if not wid:
            return
        ns_view = objc.objc_object(c_void_p=wid)
        ns_win = ns_view.window()
        if ns_win is None:
            return

        # NSNonactivatingPanelMask (1 << 7 = 128) lets QNSPanel receive key events
        # and appear over full-screen apps without switching Spaces.
        if non_activating_panel and hasattr(ns_win, "styleMask") and hasattr(ns_win, "setStyleMask_"):
            non_activating_mask = 1 << 7
            ns_win.setStyleMask_(int(ns_win.styleMask()) | non_activating_mask)

        if hasattr(ns_win, "setHidesOnDeactivate_"):
            ns_win.setHidesOnDeactivate_(False)
        if hasattr(ns_win, "setFloatingPanel_"):
            ns_win.setFloatingPanel_(True)
        if hasattr(ns_win, "setWorksWhenModal_"):
            ns_win.setWorksWhenModal_(True)

        # NSStatusWindowLevel (25) sits above normal, floating, and full-screen app windows
        base_level = int(getattr(AppKit, "NSStatusWindowLevel", 25))
        ns_win.setLevel_(base_level + level_offset)

        can_join_all_spaces = int(getattr(AppKit, "NSWindowCollectionBehaviorCanJoinAllSpaces", 1 << 0))
        stationary = int(getattr(AppKit, "NSWindowCollectionBehaviorStationary", 1 << 4))
        ignores_cycle = int(getattr(AppKit, "NSWindowCollectionBehaviorIgnoresCycle", 1 << 6))
        fullscreen_aux = int(getattr(AppKit, "NSWindowCollectionBehaviorFullScreenAuxiliary", 1 << 8))
        ns_win.setCollectionBehavior_(
            can_join_all_spaces | stationary | ignores_cycle | fullscreen_aux
        )
        if hasattr(ns_win, "orderFrontRegardless"):
            ns_win.orderFrontRegardless()
    except Exception:
        pass


def open_macos_emoji_picker() -> bool:
    """Open the native macOS Character Viewer / Emoji & Symbols palette."""
    if sys.platform != "darwin":
        return False
    try:
        import AppKit

        app = AppKit.NSApplication.sharedApplication()
        if app is not None and hasattr(app, "orderFrontCharacterPalette_"):
            app.orderFrontCharacterPalette_(None)
            return True
    except Exception:
        pass
    return False


def format_counter(length: int, limit: int | None) -> tuple[str, str]:
    """Return (counter_text, state) where state is 'normal' | 'amber' | 'red'."""
    if limit:
        text = f"{length} / {limit}"
        if length > limit:
            return text, "red"
        if length >= int(limit * AMBER_RATIO):
            return text, "amber"
        return text, "normal"
    return (f"{length} chars" if length > 0 else ""), "normal"


class _CancelledError(Exception):
    """Raised internally when the user cancels an in-flight generation."""


class _GenerateWorker(QObject):
    """Background worker that streams LLM tokens and runs prompt.generate retries."""

    status_changed = Signal(str)
    partial_ready = Signal(str)
    finished_result = Signal(object)  # prompt.Result
    failed = Signal(str, str)  # (kind, message)
    cancelled = Signal()
    resolved_model = Signal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        draft: str,
        context: str | None,
        preset: prompt.Preset,
        sliders: dict[str, float],
        slop_rules: bool,
        stream_fn: Callable | None = None,
        extra_instruction: str | None = None,
    ):
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.draft = draft
        self.context = context
        self.preset = preset
        self.sliders = dict(sliders)
        self.slop_rules = slop_rules
        self.stream_fn = stream_fn or llm.stream_chat
        self.extra_instruction = extra_instruction
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            model = self.model.strip()
            if not model:
                self.status_changed.emit("Detecting installed models…")
                installed = llm.list_models(self.base_url, self.api_key)
                if not installed:
                    raise llm.LLMError(
                        "model_missing",
                        f"No models found at {self.base_url}. Pull one (e.g. ollama pull qwen2.5:7b-instruct) or choose one in Settings.",
                    )
                model = installed[0]
                self.resolved_model.emit(model)

            call_index = 0

            def chat_fn(messages: list[dict]) -> str:
                nonlocal call_index
                call_index += 1
                if self._cancel.is_set():
                    raise _CancelledError()
                if call_index == 1:
                    self.status_changed.emit("Loading model…")
                else:
                    self.status_changed.emit("Refining output…")
                chunks: list[str] = []
                got_first = False
                for piece in self.stream_fn(
                    self.base_url,
                    model,
                    messages,
                    api_key=self.api_key,
                ):
                    if self._cancel.is_set():
                        raise _CancelledError()
                    if not got_first:
                        got_first = True
                        self.status_changed.emit("Generating…")
                    chunks.append(piece)
                    preview = prompt.clean_output("".join(chunks))
                    if preview:
                        self.partial_ready.emit(preview)
                return "".join(chunks)

            result = prompt.generate(
                chat_fn,
                self.draft,
                self.preset,
                self.sliders,
                context=self.context,
                slop_rules=self.slop_rules,
                extra_instruction=self.extra_instruction,
            )
            if self._cancel.is_set():
                raise _CancelledError()
            self.finished_result.emit(result)
        except _CancelledError:
            self.cancelled.emit()
        except llm.LLMError as exc:
            self.failed.emit(exc.kind, str(exc))
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.failed.emit("http", f"Unexpected error: {exc}")


class _DraftEdit(QPlainTextEdit):
    """Draft box where Cmd+Return / Ctrl+Return triggers generation."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        ):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _OutputEdit(QPlainTextEdit):
    """Read-only output box where Return copies & closes, and Shift+Return pastes & closes."""

    return_pressed = Signal()
    shift_return_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                self.return_pressed.emit()
                event.accept()
                return
            elif event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                self.shift_return_pressed.emit()
                event.accept()
                return
        super().keyPressEvent(event)


def render_whatsapp_mic_icon(recording: bool = False, size: int = 32) -> QIcon:
    """Render a WhatsApp-style circular microphone icon in crisp high DPI."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = (size * 2) / 64.0
    p.scale(scale, scale)

    if recording:
        # Active recording: WhatsApp/macOS red circle with white stop square
        p.setBrush(QColor("#ff3b30"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(3, 3, 58, 58))

        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(22, 22, 20, 20), 4, 4)
    else:
        # Idle: WhatsApp green circle with white microphone
        p.setBrush(QColor("#25d366"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(3, 3, 58, 58))

        p.setBrush(QColor("#ffffff"))
        # Mic capsule body
        p.drawRoundedRect(QRectF(26, 16, 12, 21), 6, 6)

        # Arc cradle around mic
        pen = QPen(QColor("#ffffff"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.arcMoveTo(QRectF(20, 22, 24, 20), 0)
        path.arcTo(QRectF(20, 22, 24, 20), 0, -180)
        p.drawPath(path)

        # Stem and base line
        p.drawLine(32, 42, 32, 48)
        p.drawLine(25, 48, 39, 48)

    p.end()
    return QIcon(pixmap)


def render_transcribing_icon(size: int = 32) -> QIcon:
    """Render a circular transcribing / loading indicator."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = (size * 2) / 64.0
    p.scale(scale, scale)

    p.setBrush(QColor("#0a84ff"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(3, 3, 58, 58))

    p.setPen(QPen(QColor("#ffffff"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.arcMoveTo(QRectF(18, 18, 28, 28), 30)
    path.arcTo(QRectF(18, 18, 28, 28), 30, 280)
    p.drawPath(path)

    p.end()
    return QIcon(pixmap)


class PopupWindow(QWidget):
    """Floating translucent Diplomat popup window."""

    settings_requested = Signal()
    quit_requested = Signal()
    config_changed = Signal(dict)
    _server_probed = Signal(bool, list, str)

    def __init__(
        self,
        cfg: dict | None = None,
        config_path=None,
        stream_fn: Callable | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._config_path = config_path
        self.cfg = cfg if cfg is not None else config_mod.load(config_path)
        self._stream_fn = stream_fn
        self._worker: _GenerateWorker | None = None
        self._thread: threading.Thread | None = None
        self._drag_offset: QPoint | None = None
        self._last_result: prompt.Result | None = None
        self._last_error_kind: str | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._voice_recorder = voice.VoiceRecorder(self)
        self._voice_recorder.recording_started.connect(self._on_voice_recording_started)
        self._voice_recorder.recording_stopped.connect(self._on_voice_recording_stopped)
        self._voice_recorder.recording_failed.connect(self._on_voice_recording_failed)
        self._transcribe_worker: voice.TranscribeWorker | None = None
        self._transcribe_thread: threading.Thread | None = None
        self._previous_app: Any | None = None
        self._variants: list[str] = []
        self._current_variant_idx: int = -1
        self._history: list[dict] = []
        self._server_probed.connect(self._on_models_queried)

        self._setup_window()
        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme()
        self._sync_from_config()

    # ---------------------------------------------------------------- setup

    def _setup_window(self) -> None:
        self.setWindowTitle("Diplomat")
        # Qt.WindowType.Tool creates an NSPanel on macOS, which is required by WindowServer
        # (along with NSNonactivatingPanelMask + FullScreenAuxiliary) to appear on top of
        # full-screen apps and follow across all desktop Spaces without switching Spaces.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(560)
        self.resize(580, 480)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        self.card = QFrame(self)
        self.card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)

        # 1. Header bar: Title | Stretch | Clear | Quit
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel("Diplomat")
        self.title_label.setObjectName("titleLabel")
        header.addWidget(self.title_label)

        header.addStretch(1)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("linkButton")
        self.clear_btn.setToolTip("Clear draft, reply context and output (⌘K)")
        self.clear_btn.clicked.connect(self.clear_all)
        self.clear_btn.setEnabled(False)
        header.addWidget(self.clear_btn)

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("linkButton")
        self.quit_btn.setToolTip("Quit Diplomat completely (⌘Q)")
        self.quit_btn.clicked.connect(self.quit_requested.emit)
        header.addWidget(self.quit_btn)
        layout.addLayout(header)

        # Non-local URL warning banner (only shown when base_url is remote)
        self.remote_warn_label = QLabel("")
        self.remote_warn_label.setObjectName("warnLabel")
        self.remote_warn_label.setWordWrap(True)
        self.remote_warn_label.setVisible(False)
        layout.addWidget(self.remote_warn_label)

        # 2. Modern Unified Input Box
        self.input_container = QFrame()
        self.input_container.setObjectName("inputContainer")
        input_layout = QVBoxLayout(self.input_container)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(6)

        # 2a. Seamless typing area
        self.draft_edit = _DraftEdit()
        self.draft_edit.setObjectName("chatDraftEdit")
        self.draft_edit.setPlaceholderText("Type or speak (⌘D)…  (⌘↩ to generate)")
        self.draft_edit.setFixedHeight(78)
        self.draft_edit.textChanged.connect(self._on_draft_changed)
        self.draft_edit.submit_requested.connect(self.trigger_generate)
        input_layout.addWidget(self.draft_edit)

        # 2b. Collapsible "Replying to…" section inside container
        self.reply_toggle_btn = QPushButton("▸ Replying to… (optional)")
        self.reply_toggle_btn.setObjectName("sectionToggle")
        self.reply_toggle_btn.clicked.connect(self._toggle_reply_panel)
        input_layout.addWidget(self.reply_toggle_btn)

        self.context_edit = _DraftEdit()
        self.context_edit.setPlaceholderText("Paste the message you are replying to…")
        self.context_edit.setFixedHeight(56)
        self.context_edit.setVisible(False)
        self.context_edit.submit_requested.connect(self.trigger_generate)
        input_layout.addWidget(self.context_edit)

        # 2c. Toolbar directly below typing area
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 4, 0, 2)
        toolbar.setSpacing(6)

        # Traffic light status indicator
        self.traffic_light = QLabel()
        self.traffic_light.setObjectName("trafficLight")
        self.traffic_light.setFixedSize(8, 8)
        self.traffic_light.setStyleSheet(
            "background-color: #f59e0b; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px;"
        )
        self.traffic_light.setToolTip("Checking model server…")
        toolbar.addWidget(self.traffic_light)

        # Model selector dropdown
        self.model_combo = QComboBox()
        self.model_combo.setObjectName("pillCombo")
        self.model_combo.setToolTip("Active model (switch anytime)")
        self.model_combo.currentTextChanged.connect(self._on_model_changed_in_combo)
        toolbar.addWidget(self.model_combo)

        # Preset dropdown
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("pillCombo")
        self.preset_combo.setToolTip("Preset style & limits")
        for key, preset in prompt.PRESETS.items():
            self.preset_combo.addItem(preset.label, userData=key)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        toolbar.addWidget(self.preset_combo)

        # Tone sliders button
        self.tone_toggle_btn = QPushButton("🎚 Tone ▾")
        self.tone_toggle_btn.setObjectName("pillButton")
        self.tone_toggle_btn.setToolTip("Adjust tone sliders")
        self.tone_toggle_btn.clicked.connect(self._toggle_tone_panel)
        toolbar.addWidget(self.tone_toggle_btn)

        # Emoji button
        self.emoji_btn = QPushButton("😊")
        self.emoji_btn.setObjectName("iconButton")
        self.emoji_btn.setToolTip("Insert Emoji / Smiley (⌃⌘Space)")
        self.emoji_btn.clicked.connect(self._on_emoji_clicked)
        toolbar.addWidget(self.emoji_btn)

        # History button
        self.history_btn = QPushButton("🕒")
        self.history_btn.setObjectName("iconButton")
        self.history_btn.setToolTip("Recent history (⌘H)")
        self.history_btn.clicked.connect(self.show_history_menu)
        toolbar.addWidget(self.history_btn)

        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("iconButton")
        self.settings_btn.setToolTip("Settings (⌘,)")
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        toolbar.addWidget(self.settings_btn)

        toolbar.addStretch(1)

        # WhatsApp-style circular mic button
        self.mic_btn = QPushButton()
        self.mic_btn.setObjectName("circleIconButton")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setIcon(render_whatsapp_mic_icon(recording=False, size=32))
        self.mic_btn.setIconSize(QSize(28, 28))
        self.mic_btn.setToolTip("Speak instead of typing (⌘D)")
        self.mic_btn.clicked.connect(self.toggle_voice_recording)
        toolbar.addWidget(self.mic_btn)

        # Generate button
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setMinimumWidth(88)
        self.generate_btn.setToolTip("Generate (⌘↩) or Regenerate (⌘R)")
        self.generate_btn.clicked.connect(self._on_generate_button_clicked)
        toolbar.addWidget(self.generate_btn)

        input_layout.addLayout(toolbar)
        layout.addWidget(self.input_container)

        # 3. Collapsible Tone panel + Reset button
        self.tone_panel = QWidget()
        tone_grid = QGridLayout(self.tone_panel)
        tone_grid.setContentsMargins(4, 2, 4, 4)
        tone_grid.setHorizontalSpacing(16)
        tone_grid.setVerticalSpacing(8)
        for col in range(3):
            tone_grid.setColumnStretch(col, 1)

        self.slider_widgets: dict[str, QSlider] = {}
        self.slider_labels: dict[str, QLabel] = {}
        for idx, name in enumerate(prompt.SLIDER_ORDER):
            row = idx // 3
            col = idx % 3
            cell = QVBoxLayout()
            cell.setSpacing(2)
            lbl = QLabel(name.capitalize())
            lbl.setObjectName("sliderLabel")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setSingleStep(5)
            slider.setPageStep(20)
            slider.valueChanged.connect(lambda val, n=name: self._on_slider_changed(n, val))
            cell.addWidget(lbl)
            cell.addWidget(slider)
            tone_grid.addLayout(cell, row, col)
            self.slider_widgets[name] = slider
            self.slider_labels[name] = lbl

        reset_row = QHBoxLayout()
        reset_row.setContentsMargins(0, 2, 0, 0)
        reset_row.addStretch(1)
        self.reset_sliders_btn = QPushButton("Reset Tone")
        self.reset_sliders_btn.setObjectName("linkButton")
        self.reset_sliders_btn.setToolTip("Reset tone sliders to defaults")
        self.reset_sliders_btn.clicked.connect(self.reset_sliders)
        reset_row.addWidget(self.reset_sliders_btn)
        tone_grid.addLayout(reset_row, 3, 0, 1, 3)

        layout.addWidget(self.tone_panel)

        # 4. Error banner (if any)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.open_settings_inline_btn = QPushButton("Open Settings")
        self.open_settings_inline_btn.clicked.connect(self._on_settings_clicked)
        self.open_settings_inline_btn.setVisible(False)
        layout.addWidget(self.open_settings_inline_btn)

        # 5. Output Box + Footer
        self.output_card = QFrame()
        self.output_card.setObjectName("outputContainer")
        output_layout = QVBoxLayout(self.output_card)
        output_layout.setContentsMargins(10, 8, 10, 8)
        output_layout.setSpacing(6)

        self.output_edit = _OutputEdit()
        self.output_edit.setObjectName("outputEdit")
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("Polished message will appear here and copy automatically…")
        self.output_edit.setMinimumHeight(84)
        self.output_edit.return_pressed.connect(self.copy_and_close)
        output_layout.addWidget(self.output_edit)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusBadge")
        footer.addWidget(self.status_label)

        self.counter_label = QLabel("")
        self.counter_label.setObjectName("mutedLabel")
        footer.addWidget(self.counter_label)

        footer.addStretch(1)

        # Variant switcher: [ ◀ 1/2 ▶ ]
        self.variant_container = QWidget()
        v_box = QHBoxLayout(self.variant_container)
        v_box.setContentsMargins(0, 0, 0, 0)
        v_box.setSpacing(4)
        self.prev_variant_btn = QPushButton("◀")
        self.prev_variant_btn.setObjectName("linkButton")
        self.prev_variant_btn.setFixedWidth(20)
        self.prev_variant_btn.setToolTip("Previous variant (⌥[)")
        self.prev_variant_btn.clicked.connect(self.prev_variant)
        v_box.addWidget(self.prev_variant_btn)

        self.variant_label = QLabel("1/1")
        self.variant_label.setObjectName("mutedLabel")
        v_box.addWidget(self.variant_label)

        self.next_variant_btn = QPushButton("▶")
        self.next_variant_btn.setObjectName("linkButton")
        self.next_variant_btn.setFixedWidth(20)
        self.next_variant_btn.setToolTip("Next variant (⌥])")
        self.next_variant_btn.clicked.connect(self.next_variant)
        v_box.addWidget(self.next_variant_btn)
        self.variant_container.setVisible(False)
        footer.addWidget(self.variant_container)

        self.shorter_btn = QPushButton("Shorter")
        self.shorter_btn.setObjectName("linkButton")
        self.shorter_btn.setToolTip("Condense output to be shorter and punchier (⌘S)")
        self.shorter_btn.clicked.connect(self.trigger_shorter)
        self.shorter_btn.setEnabled(False)
        footer.addWidget(self.shorter_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("linkButton")
        self.copy_btn.setToolTip("Copy to clipboard (already copied automatically)")
        self.copy_btn.clicked.connect(self.copy_output)
        self.copy_btn.setEnabled(False)
        footer.addWidget(self.copy_btn)

        self.paste_btn = QPushButton("Paste (⇧↩)")
        self.paste_btn.setObjectName("linkButton")
        self.paste_btn.setToolTip("Paste directly into previous app and close (⇧↩)")
        self.paste_btn.clicked.connect(self.paste_and_close)
        self.paste_btn.setEnabled(False)
        footer.addWidget(self.paste_btn)

        output_layout.addLayout(footer)
        layout.addWidget(self.output_card)

    def _bind_shortcuts(self) -> None:
        for seq in ("Ctrl+Return", "Ctrl+Enter", "Meta+Return", "Meta+Enter"):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(self.trigger_generate)

        regen_sc = QShortcut(QKeySequence("Ctrl+R"), self)
        regen_sc.activated.connect(self.trigger_generate)

        clear_sc = QShortcut(QKeySequence("Ctrl+K"), self)
        clear_sc.activated.connect(self.clear_all)

        for seq in ("Ctrl+D", "Meta+D"):
            dictate_sc = QShortcut(QKeySequence(seq), self)
            dictate_sc.activated.connect(self.toggle_voice_recording)

        self.output_edit.return_pressed.connect(self.copy_and_close)
        self.output_edit.shift_return_pressed.connect(self.paste_and_close)

        for seq in ("Shift+Return", "Shift+Enter"):
            paste_sc = QShortcut(QKeySequence(seq), self)
            paste_sc.activated.connect(self.paste_and_close)

        for seq in ("Ctrl+S", "Meta+S"):
            shorter_sc = QShortcut(QKeySequence(seq), self)
            shorter_sc.activated.connect(self.trigger_shorter)

        prev_v_sc = QShortcut(QKeySequence("Alt+["), self)
        prev_v_sc.activated.connect(self.prev_variant)

        next_v_sc = QShortcut(QKeySequence("Alt+]"), self)
        next_v_sc.activated.connect(self.next_variant)

        for seq in ("Ctrl+H", "Meta+H"):
            hist_sc = QShortcut(QKeySequence(seq), self)
            hist_sc.activated.connect(self.show_history_menu)

        settings_sc = QShortcut(QKeySequence("Ctrl+,"), self)
        settings_sc.activated.connect(self._on_settings_clicked)

        quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_sc.activated.connect(self.quit_requested.emit)

        esc_sc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_sc.activated.connect(self.handle_escape)

    # ---------------------------------------------------------------- state & config

    def _sync_from_config(self) -> None:
        preset_key = self.cfg.get("default_preset", "slack_office")
        idx = self.preset_combo.findData(preset_key)
        if idx >= 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(idx)
            self.preset_combo.blockSignals(False)

        sliders = self.cfg.get("sliders", config_mod.DEFAULTS["sliders"])
        for name, slider in self.slider_widgets.items():
            val = int(sliders.get(name, config_mod.DEFAULTS["sliders"][name]))
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
            self._update_slider_label(name, val)

        tone_open = bool(self.cfg.get("tone_open", False))
        self._set_tone_panel_open(tone_open, save=False)

        base_url = self.cfg.get("base_url", "")
        if base_url and not config_mod.is_local_url(base_url):
            self.remote_warn_label.setText(f"Note: sending text to non-local server ({base_url}).")
            self.remote_warn_label.setVisible(True)
        else:
            self.remote_warn_label.setVisible(False)

        self._update_controls()
        self._update_counter()
        if self._stream_fn is None:
            self.refresh_server_and_models()

    def reload_config(self, cfg: dict | None = None) -> None:
        self.cfg = cfg if cfg is not None else config_mod.load(self._config_path)
        self._sync_from_config()

    def _save_config(self) -> None:
        try:
            config_mod.save(self.cfg, self._config_path)
        except OSError:
            pass
        self.config_changed.emit(self.cfg)

    def refresh_server_and_models(self) -> None:
        base_url = (
            self.cfg.get("base_url")
            or config_mod.PROVIDERS.get(self.cfg.get("provider", "ollama"))
            or config_mod.DEFAULTS["base_url"]
        )
        api_key = self.cfg.get("api_key")
        self.traffic_light.setStyleSheet(
            "background-color: #f59e0b; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px;"
        )
        self.traffic_light.setToolTip("Checking model server…")

        def _worker():
            try:
                models = llm.list_models(base_url, api_key, timeout=3.0)
                self._server_probed.emit(True, models, base_url)
            except Exception as exc:
                self._server_probed.emit(False, [], str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_models_queried(self, ok: bool, models: list[str], info: str) -> None:
        if ok and models:
            self.traffic_light.setStyleSheet(
                "background-color: #34c759; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px;"
            )
            self.traffic_light.setToolTip(f"Online: {info} ({len(models)} model(s) available)")
            current = self.cfg.get("model", "")
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for m in models:
                self.model_combo.addItem(m)
            if current and current in models:
                self.model_combo.setCurrentText(current)
            elif models:
                self.model_combo.setCurrentIndex(0)
                self.cfg["model"] = models[0]
                self._save_config()
            self.model_combo.blockSignals(False)
        else:
            self.traffic_light.setStyleSheet(
                "background-color: #ff3b30; border-radius: 4px; min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px;"
            )
            self.traffic_light.setToolTip(f"Model server unreachable: {info}")
            current = self.cfg.get("model", "")
            if current and self.model_combo.count() == 0:
                self.model_combo.blockSignals(True)
                self.model_combo.addItem(current)
                self.model_combo.setCurrentText(current)
                self.model_combo.blockSignals(False)

    def _on_model_changed_in_combo(self, text: str) -> None:
        model = text.strip()
        if model and model != self.cfg.get("model"):
            self.cfg["model"] = model
            self._save_config()

    def current_preset(self) -> prompt.Preset:
        key = self.preset_combo.currentData() or "slack_office"
        return prompt.get_preset(key)

    def current_sliders(self) -> dict[str, int]:
        return {name: slider.value() for name, slider in self.slider_widgets.items()}

    # ---------------------------------------------------------------- UI handlers

    def _on_preset_changed(self) -> None:
        key = self.preset_combo.currentData()
        if key:
            self.cfg["default_preset"] = key
            self._save_config()
            self._update_counter()
            self.adjustSize()

    def _update_slider_label(self, name: str, value: int) -> None:
        band = prompt.band_index(value)
        desc = prompt.SLIDER_BANDS[name][band]
        lbl = self.slider_labels[name]
        lbl.setText(f"{name.capitalize()} ({band + 1}/5)")
        lbl.setToolTip(desc)
        self.slider_widgets[name].setToolTip(desc)

    def _on_slider_changed(self, name: str, value: int) -> None:
        self._update_slider_label(name, value)
        self.cfg.setdefault("sliders", {})[name] = int(value)
        self._save_config()

    def reset_sliders(self) -> None:
        defaults = config_mod.DEFAULTS["sliders"]
        self.cfg["sliders"] = dict(defaults)
        for name, slider in self.slider_widgets.items():
            val = int(defaults[name])
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
            self._update_slider_label(name, val)
        self._save_config()

    def _toggle_reply_panel(self) -> None:
        open_now = not self.context_edit.isVisible()
        self.context_edit.setVisible(open_now)
        arrow = "▾" if open_now else "▸"
        self.reply_toggle_btn.setText(f"{arrow} Replying to… (optional: paste the message you got)")
        if open_now:
            self.context_edit.setFocus()
        self.adjustSize()

    def _toggle_tone_panel(self) -> None:
        self._set_tone_panel_open(not self.tone_panel.isVisible(), save=True)

    def _set_tone_panel_open(self, open_now: bool, save: bool = True) -> None:
        self.tone_panel.setVisible(open_now)
        self.reset_sliders_btn.setVisible(open_now)
        arrow = "▴" if open_now else "▾"
        self.tone_toggle_btn.setText(f"🎚 Tone {arrow}")
        self.cfg["tone_open"] = open_now
        if save:
            self._save_config()
        self.adjustSize()

    def _on_draft_changed(self) -> None:
        self._update_controls()

    def _on_emoji_clicked(self) -> None:
        if not self.context_edit.hasFocus():
            self.draft_edit.setFocus()
        open_macos_emoji_picker()

    def clear_all(self) -> None:
        """Clear draft, reply context, output, and error state."""
        if self.is_recording():
            self.cancel_voice_recording()
        if self.is_generating():
            self.cancel_generation()
        self._last_result = None
        self.clear_error()
        self.draft_edit.clear()
        self.context_edit.clear()
        self.output_edit.clear()
        self._variants.clear()
        self._current_variant_idx = -1
        self._update_variant_ui()
        self.status_label.setText("")
        self._update_counter()
        self._update_controls()
        self.draft_edit.setFocus()

    def clear_error(self) -> None:
        self._last_error_kind = None
        self.error_label.setText("")
        self.error_label.setVisible(False)
        self.open_settings_inline_btn.setVisible(False)

    def show_error(self, kind: str, message: str) -> None:
        self._last_error_kind = kind
        self.status_label.setText("")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.open_settings_inline_btn.setVisible(kind == "model_missing")
        self._update_controls()

    def _on_settings_clicked(self) -> None:
        self.settings_requested.emit()

    # ---------------------------------------------------------------- voice dictation

    def is_recording(self) -> bool:
        return self._voice_recorder.is_recording()

    def toggle_voice_recording(self) -> None:
        if self._transcribe_worker is not None:
            return
        if self.is_recording():
            self._voice_recorder.stop_recording()
        else:
            self._start_voice_recording()

    def _start_voice_recording(self) -> None:
        self.clear_error()
        self.status_label.setText("Listening… speak now (⌘D to stop)")
        self.mic_btn.setIcon(render_whatsapp_mic_icon(recording=True, size=32))
        self.mic_btn.setToolTip("Stop recording and transcribe with Whisper (⌘D)")
        if not self.draft_edit.toPlainText().strip():
            self.draft_edit.setPlaceholderText("Listening… speak now (press ⌘D or click to stop)")
        ok = self._voice_recorder.start_recording()
        if not ok:
            self._reset_mic_button()
        self._update_controls()

    def _on_voice_recording_started(self) -> None:
        self.status_label.setText("Listening… speak now (⌘D to stop)")
        self._update_controls()

    def _on_voice_recording_stopped(self, audio_path: str) -> None:
        self._reset_mic_button(transcribing=True)
        self.status_label.setText("Transcribing audio with Whisper…")

        whisper_model = self.cfg.get("whisper_model", "base")
        worker = voice.TranscribeWorker(audio_path, model_name=whisper_model)
        worker.status_changed.connect(self.status_label.setText)
        worker.finished.connect(self._on_voice_transcribe_finished)
        worker.failed.connect(self._on_voice_transcribe_failed)
        self._transcribe_worker = worker

        thread = threading.Thread(target=worker.run, daemon=True)
        self._transcribe_thread = thread
        thread.start()

    def _on_voice_recording_failed(self, error_str: str) -> None:
        self._reset_mic_button()
        self.show_error(
            "mic_error",
            f"Microphone error: {error_str}. Check microphone permissions in macOS System Settings.",
        )
        self._update_controls()

    def _on_voice_transcribe_finished(self, text: str) -> None:
        self._transcribe_worker = None
        self._transcribe_thread = None
        self._reset_mic_button()
        clean = text.strip()
        if clean:
            existing = self.draft_edit.toPlainText().strip()
            if existing:
                self.draft_edit.setPlainText(f"{existing} {clean}")
            else:
                self.draft_edit.setPlainText(clean)
            self.draft_edit.setFocus()
            cursor = self.draft_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.draft_edit.setTextCursor(cursor)
            word_count = len(clean.split())
            self.status_label.setText(
                f"Transcribed {word_count} word{'s' if word_count != 1 else ''}"
            )
        else:
            self.status_label.setText("No speech detected")
        self._update_controls()

    def _on_voice_transcribe_failed(self, error_str: str) -> None:
        self._transcribe_worker = None
        self._transcribe_thread = None
        self._reset_mic_button()
        self.show_error("whisper_error", f"Whisper transcription failed: {error_str}")
        self._update_controls()

    def cancel_voice_recording(self) -> None:
        if self.is_recording():
            self._voice_recorder.cancel_recording()
        self._reset_mic_button()
        self.status_label.setText("")
        self._update_controls()

    def _reset_mic_button(self, transcribing: bool = False) -> None:
        if transcribing:
            self.mic_btn.setIcon(render_transcribing_icon(size=32))
            self.mic_btn.setEnabled(False)
            self.mic_btn.setToolTip("Transcribing audio with Whisper…")
        else:
            self.mic_btn.setIcon(render_whatsapp_mic_icon(recording=False, size=32))
            self.mic_btn.setEnabled(True)
            self.mic_btn.setToolTip("Speak to dictate (⌘D)")
            self.draft_edit.setPlaceholderText("Type or speak (⌘D)…  (⌘↩ to generate)")

    # ---------------------------------------------------------------- generation

    def is_generating(self) -> bool:
        return self._worker is not None

    def _on_generate_button_clicked(self) -> None:
        if self.is_generating():
            self.cancel_generation()
        else:
            self.trigger_generate()

    def trigger_generate(self, extra_instruction: str | None = None) -> None:
        draft = self.draft_edit.toPlainText().strip()
        if not draft:
            self._update_controls()
            return
        if self.is_generating():
            self.cancel_generation()

        self._last_result = None
        self._last_error_kind = None
        self.error_label.setVisible(False)
        self.open_settings_inline_btn.setVisible(False)
        self.output_edit.setPlainText("")
        self.status_label.setText("Loading model…")

        context = self.context_edit.toPlainText().strip() if self.context_edit.isVisible() else None
        preset = self.current_preset()
        sliders = self.current_sliders()
        slop_rules = bool(self.cfg.get("slop_rules", True))

        worker = _GenerateWorker(
            base_url=self.cfg.get("base_url", config_mod.DEFAULTS["base_url"]),
            model=self.cfg.get("model", ""),
            api_key=self.cfg.get("api_key"),
            draft=draft,
            context=context,
            preset=preset,
            sliders=sliders,
            slop_rules=slop_rules,
            stream_fn=self._stream_fn,
            extra_instruction=extra_instruction,
        )
        worker.status_changed.connect(self._on_worker_status)
        worker.partial_ready.connect(self._on_worker_partial)
        worker.finished_result.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.resolved_model.connect(self._on_worker_resolved_model)

        self._worker = worker
        self._update_controls()

        thread = threading.Thread(target=worker.run, daemon=True)
        self._thread = thread
        thread.start()

    def trigger_shorter(self) -> None:
        """Condense the current output message into a shorter, punchier version."""
        if not self.output_edit.toPlainText().strip() or self.is_generating():
            return
        if "brevity" in self.slider_widgets:
            self.slider_widgets["brevity"].setValue(100)
        self.trigger_generate(extra_instruction="Make this significantly shorter and more concise while preserving core facts.")

    def prev_variant(self) -> None:
        if self._current_variant_idx > 0:
            self._current_variant_idx -= 1
            self._apply_current_variant()

    def next_variant(self) -> None:
        if self._current_variant_idx < len(self._variants) - 1:
            self._current_variant_idx += 1
            self._apply_current_variant()

    def _apply_current_variant(self) -> None:
        if 0 <= self._current_variant_idx < len(self._variants):
            text = self._variants[self._current_variant_idx]
            self.output_edit.setPlainText(text)
            self.copy_output()
            self._update_variant_ui()
            self._update_controls()
            self._update_counter()

    def _update_variant_ui(self) -> None:
        total = len(self._variants)
        has_multi = total > 1
        self.variant_container.setVisible(has_multi)
        if has_multi:
            curr = self._current_variant_idx + 1
            self.variant_label.setText(f"{curr}/{total}")
            self.prev_variant_btn.setEnabled(self._current_variant_idx > 0)
            self.next_variant_btn.setEnabled(self._current_variant_idx < total - 1)

    def show_history_menu(self) -> None:
        menu = QMenu(self)
        if not self._history:
            empty_action = menu.addAction("No recent history")
            empty_action.setEnabled(False)
        else:
            for item in reversed(self._history):
                snippet = item["output"].replace("\n", " ")
                if len(snippet) > 42:
                    snippet = snippet[:40] + "…"
                label = f"[{item['time']}] {snippet}"
                action = menu.addAction(label)
                action.triggered.connect(lambda checked=False, it=item: self._restore_history_item(it))
        pos = self.history_btn.mapToGlobal(QPoint(0, self.history_btn.height() + 4))
        menu.exec(pos)

    def _restore_history_item(self, item: dict) -> None:
        self.output_edit.setPlainText(item["output"])
        if not self.draft_edit.toPlainText().strip() and item.get("draft"):
            self.draft_edit.setPlainText(item["draft"])
        self.copy_output()
        self._update_controls()
        self._update_counter()

    def cancel_generation(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
            self.status_label.setText("Cancelled")
            self._update_controls()

    def _on_worker_resolved_model(self, model: str) -> None:
        if not self.cfg.get("model"):
            self.cfg["model"] = model
            self._save_config()

    def _on_worker_status(self, status: str) -> None:
        if self.sender() is not self._worker:
            return
        self.status_label.setText(status)

    def _on_worker_partial(self, text: str) -> None:
        if self.sender() is not self._worker:
            return
        self.output_edit.setPlainText(text)
        self._update_counter()

    def _on_worker_finished(self, result: prompt.Result) -> None:
        if self.sender() is not self._worker:
            return
        self._worker = None
        self._last_result = result
        self._last_error_kind = None
        self.output_edit.setPlainText(result.text)

        # Automatically copy to clipboard as requested
        if result.text.strip():
            if not self._variants or self._variants[-1] != result.text.strip():
                self._variants.append(result.text.strip())
            self._current_variant_idx = len(self._variants) - 1
            self._update_variant_ui()
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(result.text.strip())
            self.status_label.setText("✓ Copied to clipboard")
            self.copy_btn.setText("Copied ✓")
            QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy"))

            import datetime
            now_str = datetime.datetime.now().strftime("%H:%M")
            self._history.append({
                "draft": self.draft_edit.toPlainText().strip(),
                "output": result.text.strip(),
                "preset": self.current_preset().label,
                "time": now_str,
            })
            if len(self._history) > 20:
                self._history.pop(0)
        elif result.retries:
            self.status_label.setText("retried: " + ", ".join(result.retries))
        else:
            self.status_label.setText("")

        self._update_counter()
        self._update_controls()

    def _on_worker_failed(self, kind: str, message: str) -> None:
        if self.sender() is not self._worker:
            return
        self._worker = None
        self.show_error(kind, message)

    def _on_worker_cancelled(self) -> None:
        if self.sender() is not self._worker:
            return
        self._worker = None
        self.status_label.setText("Cancelled")
        self._update_controls()

    # ---------------------------------------------------------------- counter & buttons

    def _update_counter(self) -> None:
        text = self.output_edit.toPlainText()
        limit = self.current_preset().limit
        label_text, state = format_counter(len(text), limit)
        self.counter_label.setText(label_text)
        if state == "red":
            self.counter_label.setStyleSheet("color: #ff453a; font-weight: 600; font-size: 12px;")
        elif state == "amber":
            self.counter_label.setStyleSheet("color: #f59e0b; font-weight: 600; font-size: 12px;")
        else:
            self.counter_label.setStyleSheet("")

    def _update_controls(self) -> None:
        has_draft = bool(self.draft_edit.toPlainText().strip())
        has_context = bool(self.context_edit.toPlainText().strip())
        has_output = bool(self.output_edit.toPlainText().strip())
        has_any = has_draft or has_context or has_output or (self._last_error_kind is not None) or self.is_recording()

        if self.is_generating():
            self.generate_btn.setText("Cancel")
            self.generate_btn.setEnabled(True)
        else:
            if self._last_error_kind is not None:
                self.generate_btn.setText("Retry")
            elif has_output or self._last_result is not None:
                self.generate_btn.setText("Regenerate")
            else:
                self.generate_btn.setText("Generate")
            self.generate_btn.setEnabled(has_draft and not self.is_recording())

        self.clear_btn.setEnabled(has_any or self.is_generating() or self.is_recording())
        self.shorter_btn.setEnabled(has_output and not self.is_generating())
        self.copy_btn.setEnabled(has_output and not self.is_generating())
        self.paste_btn.setEnabled(has_output and not self.is_generating())

    # ---------------------------------------------------------------- clipboard & visibility

    def set_previous_app(self, app: Any | None) -> None:
        if app is not None:
            self._previous_app = app

    def set_captured_draft(self, text: str) -> None:
        if text:
            self.draft_edit.setPlainText(text)
            cursor = self.draft_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.draft_edit.setTextCursor(cursor)
            self._update_controls()
            self._update_counter()

    def copy_output(self) -> bool:
        text = self.output_edit.toPlainText().strip()
        if not text:
            return False
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copy"))
        return True

    def copy_and_close(self) -> None:
        if self.copy_output():
            self.hide_popup()

    def paste_and_close(self) -> None:
        if not self.copy_output():
            return

        if not platform_mod.is_accessibility_trusted(prompt=False):
            platform_mod.is_accessibility_trusted(prompt=True)
            self.status_label.setText("Copied ✓ (Grant Accessibility in Settings to auto-paste)")
            QTimer.singleShot(1500, self.hide_popup)
            return

        self.hide_popup()
        QTimer.singleShot(100, self._execute_paste)

    def _execute_paste(self) -> None:
        if self._previous_app is not None:
            platform_mod.activate_app(self._previous_app)
        QTimer.singleShot(60, platform_mod.simulate_paste)

    def handle_escape(self) -> None:
        if self.is_recording():
            self.cancel_voice_recording()
        elif self.is_generating():
            self.cancel_generation()
        else:
            self.hide_popup()

    def closeEvent(self, event) -> None:
        self._voice_recorder.teardown()
        super().closeEvent(event)

    def apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(is_dark_mode()))

    def center_on_screen(self) -> None:
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + int(geo.height() * 0.22)
        self.move(x, max(geo.y() + 24, y))

    def show_popup(self) -> None:
        if not self.isVisible() and self._previous_app is None:
            self._previous_app = platform_mod.get_frontmost_app()
        self.apply_theme()
        self.reload_config()
        if not self.isVisible():
            self.center_on_screen()
        if self._fade_anim is not None:
            self._fade_anim.stop()
        self.setWindowOpacity(0.0)
        self.show()
        _configure_macos_window(self, level_offset=0, non_activating_panel=True)
        if sys.platform == "darwin":
            try:
                import AppKit

                AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass
        self.raise_()
        self.activateWindow()
        # Re-apply after Qt's show/raise/activateWindow so Qt doesn't reset NSPanel flags
        _configure_macos_window(self, level_offset=0, non_activating_panel=True)
        self.draft_edit.setFocus()
        self.draft_edit.selectAll()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(130)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._fade_anim = anim

    def hide_popup(self) -> None:
        if self.is_recording():
            self.cancel_voice_recording()
        if self._fade_anim is not None:
            self._fade_anim.stop()
        if not self.isVisible():
            return
        self.hide()

    def toggle_popup(self) -> None:
        """Spotlight-style toggle: if visible (always on top), hide it; if hidden, show it."""
        if self.isVisible():
            self.hide_popup()
        else:
            self.show_popup()

    # ---------------------------------------------------------------- window dragging & theme events

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 54:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.apply_theme()
        super().changeEvent(event)


# ---------------------------------------------------------------- Hotkey recorder & Settings dialog

_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R,
}

_SPECIAL_KEYS = {
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Return: "return",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab",
}


def keyevent_to_hotkey_spec(key: int, modifiers: Qt.KeyboardModifier) -> str | None:
    """Convert a Qt key + modifiers into a config hotkey string like 'option+space'.

    Note: on macOS Qt swaps Control and Meta by default:
    Qt.ControlModifier is ⌘ (Command), Qt.MetaModifier is ⌃ (Control), Qt.AltModifier is ⌥ (Option).
    """
    if key in _MODIFIER_KEYS or key == Qt.Key.Key_unknown:
        return None

    mods: list[str] = []
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        mods.append("ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        mods.append("option")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        mods.append("shift")
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        mods.append("cmd")

    if not mods:
        return None

    if key in _SPECIAL_KEYS:
        key_name = _SPECIAL_KEYS[key]
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        key_name = chr(key).lower()
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        key_name = chr(key)
    else:
        seq = QKeySequence(key).toString().lower().strip()
        if not seq or len(seq) > 6:
            return None
        key_name = seq

    return "+".join([*mods, key_name])


class HotkeyRecorder(QPushButton):
    """Clickable button that records a modifier+key shortcut."""

    hotkey_changed = Signal(str)
    recording_started = Signal()
    recording_cancelled = Signal()

    def __init__(self, initial: str = "option+space", parent: QWidget | None = None):
        super().__init__(parent)
        self._hotkey = initial or "option+space"
        self._recording = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clicked.connect(self._start_recording)
        self._refresh_text()

    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, spec: str) -> None:
        self._hotkey = spec or "option+space"
        self._recording = False
        self._refresh_text()

    def _start_recording(self) -> None:
        if not self._recording:
            self._recording = True
            self.recording_started.emit()
        self.setText("Press shortcut… (Esc to cancel)")
        self.setFocus()

    def _refresh_text(self) -> None:
        self.setText(self._hotkey)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._recording = False
            self._refresh_text()
            self.recording_cancelled.emit()
            event.accept()
            return
        spec = keyevent_to_hotkey_spec(event.key(), event.modifiers())
        if spec:
            self._hotkey = spec
            self._recording = False
            self._refresh_text()
            self.hotkey_changed.emit(spec)
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._recording:
            self._recording = False
            self._refresh_text()
            self.recording_cancelled.emit()
        super().focusOutEvent(event)


PROVIDER_LABELS = [
    ("ollama", "Ollama (localhost:11434)"),
    ("lmstudio", "LM Studio (localhost:1234)"),
    ("other", "Other (OpenAI-compatible)"),
]


def _make_row_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("formLabel")
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setMinimumWidth(112)
    return lbl


def _make_status_label() -> QLabel:
    lbl = QLabel("")
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    lbl.setContentsMargins(2, 2, 2, 4)
    return lbl


class SettingsDialog(QDialog):
    """One-screen Settings dialog: provider, model list, test, hotkey, and writing rules."""

    config_changed = Signal(dict)
    quit_requested = Signal()

    def __init__(
        self,
        cfg: dict | None = None,
        config_path=None,
        list_models_fn: Callable[[str, str | None], list[str]] | None = None,
        test_connection_fn: Callable[[str, str, str | None], tuple[str, float]] | None = None,
        hotkey_status_fn: Callable[[str], tuple[bool, str | None]] | None = None,
        hotkey_pause_fn: Callable[[], None] | None = None,
        hotkey_resume_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._config_path = config_path
        self.cfg = cfg if cfg is not None else config_mod.load(config_path)
        self._list_models_fn = list_models_fn or (lambda url, key: llm.list_models(url, key))
        self._test_connection_fn = test_connection_fn or llm.test_connection
        self._hotkey_status_fn = hotkey_status_fn
        self._hotkey_pause_fn = hotkey_pause_fn
        self._hotkey_resume_fn = hotkey_resume_fn

        self.setWindowTitle("Diplomat Settings")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumWidth(540)
        self.setStyleSheet(build_stylesheet(is_dark_mode()))
        self._build_ui()
        self._load_from_cfg()
        self.refresh_models()

    def present(self) -> None:
        """Show Settings above the always-on-top PopupWindow and focus it."""
        self.setStyleSheet(build_stylesheet(is_dark_mode()))
        self.refresh_models()
        self.show()
        _configure_macos_window(self, level_offset=2, non_activating_panel=False)
        if sys.platform == "darwin":
            try:
                import AppKit

                AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass
        self.raise_()
        self.activateWindow()
        _configure_macos_window(self, level_offset=2, non_activating_panel=False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        row = 0

        # 1. Provider dropdown
        self.provider_combo = QComboBox()
        self.provider_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for key, label in PROVIDER_LABELS:
            self.provider_combo.addItem(label, userData=key)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        grid.addWidget(_make_row_label("Provider:"), row, 0)
        grid.addWidget(self.provider_combo, row, 1)
        row += 1

        # 2. Server URL + reachability status in dedicated non-clipped rows
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://localhost:11434/v1")
        self.base_url_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.base_url_edit.editingFinished.connect(self._on_base_url_edited)
        grid.addWidget(_make_row_label("Server URL:"), row, 0)
        grid.addWidget(self.base_url_edit, row, 1)
        row += 1

        self.server_status_label = _make_status_label()
        grid.addWidget(self.server_status_label, row, 1)
        row += 1

        self.remote_url_warn = _make_status_label()
        self.remote_url_warn.setStyleSheet("color: #f59e0b; font-size: 12px;")
        self.remote_url_warn.setVisible(False)
        grid.addWidget(self.remote_url_warn, row, 1)
        row += 1

        # 3. Optional API key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Optional (only needed for authenticated servers)")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.api_key_edit.editingFinished.connect(self._on_api_key_edited)
        grid.addWidget(_make_row_label("API Key:"), row, 0)
        grid.addWidget(self.api_key_edit, row, 1)
        row += 1

        # 4. Model dropdown + Refresh + available models summary + empty-model copyable hint
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_row.addWidget(self.model_combo, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumWidth(88)
        self.refresh_btn.clicked.connect(self.refresh_models)
        model_row.addWidget(self.refresh_btn)
        grid.addWidget(_make_row_label("Model:"), row, 0)
        grid.addLayout(model_row, row, 1)
        row += 1

        self.available_models_label = _make_status_label()
        self.available_models_label.setObjectName("mutedLabel")
        self.available_models_label.setVisible(False)
        grid.addWidget(self.available_models_label, row, 1)
        row += 1

        self.model_hint_box = QLineEdit("ollama pull qwen2.5:7b-instruct")
        self.model_hint_box.setReadOnly(True)
        self.model_hint_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.model_hint_box.setToolTip("No models found — copy and run this command in Terminal")
        self.model_hint_box.setVisible(False)
        grid.addWidget(self.model_hint_box, row, 1)
        row += 1

        # 5. Test connection button + result
        test_row = QHBoxLayout()
        test_row.setContentsMargins(0, 0, 0, 0)
        self.test_btn = QPushButton("Test Model")
        self.test_btn.setMinimumWidth(120)
        self.test_btn.clicked.connect(self.run_test_connection)
        test_row.addWidget(self.test_btn)
        test_row.addStretch(1)
        grid.addWidget(_make_row_label("Test:"), row, 0)
        grid.addLayout(test_row, row, 1)
        row += 1

        self.test_result_label = _make_status_label()
        self.test_result_label.setVisible(False)
        grid.addWidget(self.test_result_label, row, 1)
        row += 1

        # 6. Hotkey recorder + Default button
        hotkey_row = QHBoxLayout()
        hotkey_row.setContentsMargins(0, 0, 0, 0)
        hotkey_row.setSpacing(8)
        self.hotkey_recorder = HotkeyRecorder()
        if self._hotkey_pause_fn is not None:
            self.hotkey_recorder.recording_started.connect(self._hotkey_pause_fn)
        if self._hotkey_resume_fn is not None:
            self.hotkey_recorder.recording_cancelled.connect(self._hotkey_resume_fn)
        self.hotkey_recorder.hotkey_changed.connect(self._on_hotkey_changed)
        hotkey_row.addWidget(self.hotkey_recorder, 1)

        self.reset_hotkey_btn = QPushButton("Default (⌥ Space)")
        self.reset_hotkey_btn.setMinimumWidth(140)
        self.reset_hotkey_btn.clicked.connect(lambda: self._on_hotkey_changed("option+space"))
        hotkey_row.addWidget(self.reset_hotkey_btn)
        grid.addWidget(_make_row_label("Global Hotkey:"), row, 0)
        grid.addLayout(hotkey_row, row, 1)
        row += 1

        self.hotkey_status_label = _make_status_label()
        self.hotkey_status_label.setVisible(False)
        grid.addWidget(self.hotkey_status_label, row, 1)
        row += 1

        # 7. Writing rules toggle
        self.slop_rules_check = QCheckBox("Use compact no-ai-slop writing rules")
        self.slop_rules_check.toggled.connect(self._on_slop_rules_toggled)
        grid.addWidget(_make_row_label("Writing Rules:"), row, 0)
        grid.addWidget(self.slop_rules_check, row, 1)
        row += 1

        # 8. Selection capture toggle
        self.capture_selection_check = QCheckBox("Grab selected text on hotkey")
        self.capture_selection_check.toggled.connect(self._on_capture_selection_toggled)
        grid.addWidget(_make_row_label("Selection:"), row, 0)
        grid.addWidget(self.capture_selection_check, row, 1)
        row += 1

        # 9. Voice dictation (Whisper STT)
        whisper_row = QHBoxLayout()
        whisper_row.setContentsMargins(0, 0, 0, 0)
        whisper_row.setSpacing(8)
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for m in voice.WHISPER_MODELS:
            self.whisper_model_combo.addItem(f"{m} (local)", userData=m)
        self.whisper_model_combo.currentIndexChanged.connect(self._on_whisper_model_changed)
        whisper_row.addWidget(self.whisper_model_combo, 1)

        grid.addWidget(_make_row_label("Voice Input:"), row, 0)
        grid.addLayout(whisper_row, row, 1)
        row += 1

        self.whisper_status_label = _make_status_label()
        avail, status_msg = voice.get_whisper_status()
        self.whisper_status_label.setText(f"✓ {status_msg}" if avail else f"⚠ {status_msg}")
        self.whisper_status_label.setStyleSheet(
            "color: #34c759; font-size: 12px;" if avail else "color: #ff9500; font-size: 12px;"
        )
        grid.addWidget(self.whisper_status_label, row, 1)
        row += 1

        # 10. Startup (Launch at login)
        self.autostart_check = QCheckBox("Launch Diplomat automatically at login")
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        grid.addWidget(_make_row_label("Startup:"), row, 0)
        grid.addWidget(self.autostart_check, row, 1)
        row += 1

        root.addLayout(grid)

        divider = QFrame()
        divider.setObjectName("divider")
        root.addWidget(divider)

        # Footer: Quit Diplomat (left) | Done (right)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        self.quit_app_btn = QPushButton("Quit Diplomat")
        self.quit_app_btn.setObjectName("dangerButton")
        self.quit_app_btn.setToolTip("Stop the Diplomat background process and exit (⌘Q)")
        self.quit_app_btn.clicked.connect(self._on_quit_clicked)
        footer.addWidget(self.quit_app_btn)

        footer.addStretch(1)

        self.close_btn = QPushButton("Done")
        self.close_btn.setObjectName("primaryButton")
        self.close_btn.setMinimumWidth(96)
        self.close_btn.setDefault(True)
        self.close_btn.clicked.connect(self.accept)
        footer.addWidget(self.close_btn)
        root.addLayout(footer)

        quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_sc.activated.connect(self._on_quit_clicked)

    def _on_quit_clicked(self) -> None:
        self.quit_requested.emit()
        self.close()

    def _load_from_cfg(self) -> None:
        provider = self.cfg.get("provider", "ollama")
        idx = self.provider_combo.findData(provider)
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(max(0, idx))
        self.provider_combo.blockSignals(False)

        base_url = self.cfg.get("base_url") or config_mod.PROVIDERS.get(provider) or config_mod.DEFAULTS["base_url"]
        self.base_url_edit.setText(base_url)
        self._update_remote_warning(base_url)

        self.api_key_edit.setText(self.cfg.get("api_key") or "")

        model = self.cfg.get("model", "")
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if model:
            self.model_combo.addItem(model)
            self.model_combo.setCurrentText(model)
        self.model_combo.blockSignals(False)

        self.hotkey_recorder.set_hotkey(self.cfg.get("hotkey", "option+space"))
        self.slop_rules_check.blockSignals(True)
        self.slop_rules_check.setChecked(bool(self.cfg.get("slop_rules", True)))
        self.slop_rules_check.blockSignals(False)

        self.capture_selection_check.blockSignals(True)
        self.capture_selection_check.setChecked(bool(self.cfg.get("capture_selection", True)))
        self.capture_selection_check.blockSignals(False)

        wm = self.cfg.get("whisper_model", "base")
        w_idx = self.whisper_model_combo.findData(wm)
        self.whisper_model_combo.blockSignals(True)
        self.whisper_model_combo.setCurrentIndex(max(0, w_idx))
        self.whisper_model_combo.blockSignals(False)

        self.autostart_check.blockSignals(True)
        self.autostart_check.setChecked(platform_mod.is_autostart_enabled())
        self.autostart_check.blockSignals(False)

    def _on_autostart_toggled(self, checked: bool) -> None:
        platform_mod.set_autostart_enabled(bool(checked))

    def _on_whisper_model_changed(self) -> None:
        wm = self.whisper_model_combo.currentData() or "base"
        self.cfg["whisper_model"] = wm
        self._save_and_emit()

    def _save_and_emit(self) -> None:
        try:
            config_mod.save(self.cfg, self._config_path)
        except OSError:
            pass
        self.config_changed.emit(self.cfg)

    def _update_remote_warning(self, url: str) -> None:
        if url and not config_mod.is_local_url(url):
            self.remote_url_warn.setText("Warning: this URL is not localhost. Your text will be sent to this server.")
            self.remote_url_warn.setVisible(True)
        else:
            self.remote_url_warn.setVisible(False)
        self.adjustSize()

    def _on_provider_changed(self) -> None:
        provider = self.provider_combo.currentData() or "ollama"
        self.cfg["provider"] = provider
        preset_url = config_mod.PROVIDERS.get(provider)
        if preset_url:
            self.base_url_edit.setText(preset_url)
            self.cfg["base_url"] = preset_url
        self._update_remote_warning(self.base_url_edit.text().strip())
        self._save_and_emit()
        self.refresh_models()

    def _on_base_url_edited(self) -> None:
        url = self.base_url_edit.text().strip()
        if not url:
            return
        self.cfg["base_url"] = url
        self._update_remote_warning(url)
        self._save_and_emit()
        self.refresh_models()

    def _on_api_key_edited(self) -> None:
        key = self.api_key_edit.text().strip() or None
        self.cfg["api_key"] = key
        self._save_and_emit()

    def _on_model_changed(self, text: str) -> None:
        model = text.strip()
        self.cfg["model"] = model
        self._save_and_emit()

    def _on_hotkey_changed(self, spec: str) -> None:
        self.hotkey_recorder.set_hotkey(spec)
        self.cfg["hotkey"] = spec
        self._save_and_emit()
        if self._hotkey_status_fn is not None:
            ok, err = self._hotkey_status_fn(spec)
            if ok:
                self.hotkey_status_label.setStyleSheet("color: #30d158; font-size: 12px;")
                self.hotkey_status_label.setText(f"● Hotkey '{spec}' active")
            else:
                self.hotkey_status_label.setStyleSheet("color: #ff453a; font-size: 12px;")
                self.hotkey_status_label.setText(err or f"● Could not register '{spec}'")
            self.hotkey_status_label.setVisible(True)
            self.adjustSize()

    def _on_slop_rules_toggled(self, checked: bool) -> None:
        self.cfg["slop_rules"] = bool(checked)
        self._save_and_emit()

    def _on_capture_selection_toggled(self, checked: bool) -> None:
        self.cfg["capture_selection"] = bool(checked)
        self._save_and_emit()

    def refresh_models(self) -> list[str]:
        base_url = self.base_url_edit.text().strip() or config_mod.DEFAULTS["base_url"]
        api_key = self.api_key_edit.text().strip() or None
        current_model = self.cfg.get("model", "").strip()

        try:
            models = self._list_models_fn(base_url, api_key)
        except llm.LLMError as exc:
            self.server_status_label.setStyleSheet("color: #ff453a; font-size: 12px;")
            self.server_status_label.setText(f"● {exc}")
            self.available_models_label.setVisible(False)
            self.model_hint_box.setVisible(False)
            self.adjustSize()
            return []

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)

        if models:
            self.server_status_label.setStyleSheet("color: #30d158; font-size: 12px;")
            self.server_status_label.setText(f"● Connected ({len(models)} model{'s' if len(models) != 1 else ''} available)")
            self.available_models_label.setText("Available: " + ", ".join(models))
            self.available_models_label.setVisible(True)
            self.model_hint_box.setVisible(False)
            chosen = current_model if current_model in models else models[0]
            idx = self.model_combo.findText(chosen)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            self.model_combo.blockSignals(False)
            if chosen != current_model:
                self.cfg["model"] = chosen
                self._save_and_emit()
        else:
            if current_model:
                self.model_combo.addItem(current_model)
                self.model_combo.setCurrentIndex(0)
            self.model_combo.blockSignals(False)
            self.available_models_label.setVisible(False)
            self.server_status_label.setStyleSheet("color: #f59e0b; font-size: 12px;")
            self.server_status_label.setText("● Server reachable, but no models are installed. Pull one in Terminal:")
            self.model_hint_box.setVisible(True)
        self.adjustSize()
        return models

    def run_test_connection(self) -> bool:
        base_url = self.base_url_edit.text().strip() or config_mod.DEFAULTS["base_url"]
        model = self.model_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip() or None

        self.test_result_label.setVisible(True)
        if not model:
            self.test_result_label.setStyleSheet("color: #ff453a; font-size: 12px;")
            self.test_result_label.setText("Choose or pull a model first.")
            self.adjustSize()
            return False

        try:
            reply, elapsed = self._test_connection_fn(base_url, model, api_key)
        except llm.LLMError as exc:
            self.test_result_label.setStyleSheet("color: #ff453a; font-size: 12px;")
            self.test_result_label.setText(f"Test failed: {exc}")
            self.adjustSize()
            return False

        self.test_result_label.setStyleSheet("color: #30d158; font-size: 12px;")
        self.test_result_label.setText(f"✓ ({elapsed:.2f}s) {reply}")
        self.adjustSize()
        return True