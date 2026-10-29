"""Popup window and Settings dialog for Diplomat."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QPalette,
    QShortcut,
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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import config as config_mod
from . import llm, prompt

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
            min-height: 22px;
            font-size: 13px;
        }}
        QComboBox:hover {{
            background-color: {t["btn_hover"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
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
    """


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
    """Read-only output box where Return/Enter copies and closes the popup."""

    return_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.return_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PopupWindow(QWidget):
    """Floating translucent Diplomat popup window."""

    settings_requested = Signal()
    quit_requested = Signal()
    config_changed = Signal(dict)

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

        self._setup_window()
        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme()
        self._sync_from_config()

    # ---------------------------------------------------------------- setup

    def _setup_window(self) -> None:
        self.setWindowTitle("Diplomat")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(540)
        self.resize(560, 450)

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

        # 1. Header bar: Title | Preset dropdown | Settings button | Quit button
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel("Diplomat")
        self.title_label.setObjectName("titleLabel")
        header.addWidget(self.title_label)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(148)
        for key, preset in prompt.PRESETS.items():
            self.preset_combo.addItem(preset.label, userData=key)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        header.addWidget(self.preset_combo)

        header.addStretch(1)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("iconButton")
        self.settings_btn.setToolTip("Settings (⌘,)")
        self.settings_btn.clicked.connect(self._on_settings_clicked)
        header.addWidget(self.settings_btn)

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

        # 2. Draft text box
        self.draft_edit = _DraftEdit()
        self.draft_edit.setPlaceholderText("Type anything…  (⌘↩ to generate)")
        self.draft_edit.setFixedHeight(88)
        self.draft_edit.textChanged.connect(self._on_draft_changed)
        self.draft_edit.submit_requested.connect(self.trigger_generate)
        layout.addWidget(self.draft_edit)

        # 3. Collapsible "Replying to…" section
        self.reply_toggle_btn = QPushButton("▸ Replying to… (optional: paste the message you got)")
        self.reply_toggle_btn.setObjectName("sectionToggle")
        self.reply_toggle_btn.clicked.connect(self._toggle_reply_panel)
        layout.addWidget(self.reply_toggle_btn)

        self.context_edit = _DraftEdit()
        self.context_edit.setPlaceholderText("Paste the message you are replying to…")
        self.context_edit.setFixedHeight(64)
        self.context_edit.setVisible(False)
        self.context_edit.submit_requested.connect(self.trigger_generate)
        layout.addWidget(self.context_edit)

        # 4. Collapsible Tone panel + Reset button
        tone_header = QHBoxLayout()
        tone_header.setContentsMargins(0, 0, 0, 0)
        self.tone_toggle_btn = QPushButton("▸ Tone")
        self.tone_toggle_btn.setObjectName("sectionToggle")
        self.tone_toggle_btn.clicked.connect(self._toggle_tone_panel)
        tone_header.addWidget(self.tone_toggle_btn)
        tone_header.addStretch(1)

        self.reset_sliders_btn = QPushButton("Reset")
        self.reset_sliders_btn.setObjectName("linkButton")
        self.reset_sliders_btn.setToolTip("Reset tone sliders to defaults")
        self.reset_sliders_btn.clicked.connect(self.reset_sliders)
        tone_header.addWidget(self.reset_sliders_btn)
        layout.addLayout(tone_header)

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

        layout.addWidget(self.tone_panel)

        # 5. Divider
        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)

        # 6. Output box + error label
        self.output_edit = _OutputEdit()
        self.output_edit.setObjectName("outputEdit")
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("Your polished message will appear here…")
        self.output_edit.setMinimumHeight(96)
        self.output_edit.return_pressed.connect(self.copy_and_close)
        layout.addWidget(self.output_edit)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # 7. Footer: char counter | status | Regenerate / Generate | Copy
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.counter_label = QLabel("")
        self.counter_label.setObjectName("mutedLabel")
        footer.addWidget(self.counter_label)

        self.status_label = QLabel("")
        self.status_label.setObjectName("mutedLabel")
        footer.addWidget(self.status_label)

        footer.addStretch(1)

        self.open_settings_inline_btn = QPushButton("Open Settings")
        self.open_settings_inline_btn.clicked.connect(self._on_settings_clicked)
        self.open_settings_inline_btn.setVisible(False)
        footer.addWidget(self.open_settings_inline_btn)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setMinimumWidth(96)
        self.generate_btn.setToolTip("Generate (⌘↩) or Regenerate (⌘R)")
        self.generate_btn.clicked.connect(self._on_generate_button_clicked)
        footer.addWidget(self.generate_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("primaryButton")
        self.copy_btn.setMinimumWidth(82)
        self.copy_btn.setToolTip("Copy to clipboard (↩ in output copies & closes)")
        self.copy_btn.clicked.connect(self.copy_output)
        self.copy_btn.setEnabled(False)
        footer.addWidget(self.copy_btn)

        layout.addLayout(footer)

    def _bind_shortcuts(self) -> None:
        for seq in ("Ctrl+Return", "Ctrl+Enter", "Meta+Return", "Meta+Enter"):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(self.trigger_generate)

        regen_sc = QShortcut(QKeySequence("Ctrl+R"), self)
        regen_sc.activated.connect(self.trigger_generate)

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

    def reload_config(self, cfg: dict | None = None) -> None:
        self.cfg = cfg if cfg is not None else config_mod.load(self._config_path)
        self._sync_from_config()

    def _save_config(self) -> None:
        try:
            config_mod.save(self.cfg, self._config_path)
        except OSError:
            pass
        self.config_changed.emit(self.cfg)

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
        arrow = "▾" if open_now else "▸"
        self.tone_toggle_btn.setText(f"{arrow} Tone")
        self.cfg["tone_open"] = open_now
        if save:
            self._save_config()
        self.adjustSize()

    def _on_draft_changed(self) -> None:
        self._update_controls()

    def _on_settings_clicked(self) -> None:
        self.settings_requested.emit()

    # ---------------------------------------------------------------- generation

    def is_generating(self) -> bool:
        return self._worker is not None

    def _on_generate_button_clicked(self) -> None:
        if self.is_generating():
            self.cancel_generation()
        else:
            self.trigger_generate()

    def trigger_generate(self) -> None:
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
        if result.retries:
            self.status_label.setText("retried: " + ", ".join(result.retries))
        else:
            self.status_label.setText("")
        self._update_counter()
        self._update_controls()

    def _on_worker_failed(self, kind: str, message: str) -> None:
        if self.sender() is not self._worker:
            return
        self._worker = None
        self._last_error_kind = kind
        self.status_label.setText("")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.open_settings_inline_btn.setVisible(kind == "model_missing")
        self._update_controls()

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
        has_output = bool(self.output_edit.toPlainText().strip())

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
            self.generate_btn.setEnabled(has_draft)

        self.copy_btn.setEnabled(has_output and not self.is_generating())

    # ---------------------------------------------------------------- clipboard & visibility

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

    def handle_escape(self) -> None:
        if self.is_generating():
            self.cancel_generation()
        else:
            self.hide_popup()

    def apply_theme(self) -> None:
        self.setStyleSheet(build_stylesheet(is_dark_mode()))

    def center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + int(geo.height() * 0.22)
        self.move(x, max(geo.y() + 24, y))

    def show_popup(self) -> None:
        self.apply_theme()
        self.reload_config()
        if not self.isVisible():
            self.center_on_screen()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
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
        if not self.isVisible():
            return
        self.hide()

    def toggle_popup(self) -> None:
        if self.isVisible() and self.isActiveWindow():
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
        self._recording = True
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
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._config_path = config_path
        self.cfg = cfg if cfg is not None else config_mod.load(config_path)
        self._list_models_fn = list_models_fn or (lambda url, key: llm.list_models(url, key))
        self._test_connection_fn = test_connection_fn or llm.test_connection
        self._hotkey_status_fn = hotkey_status_fn

        self.setWindowTitle("Diplomat Settings")
        self.setMinimumWidth(540)
        self.setStyleSheet(build_stylesheet(is_dark_mode()))
        self._build_ui()
        self._load_from_cfg()
        self.refresh_models()

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

        # 4. Model dropdown + Refresh + empty-model copyable hint
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(8)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
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

    def refresh_models(self) -> list[str]:
        base_url = self.base_url_edit.text().strip() or config_mod.DEFAULTS["base_url"]
        api_key = self.api_key_edit.text().strip() or None
        current_model = self.cfg.get("model", "").strip()

        try:
            models = self._list_models_fn(base_url, api_key)
        except llm.LLMError as exc:
            self.server_status_label.setStyleSheet("color: #ff453a; font-size: 12px;")
            self.server_status_label.setText(f"● {exc}")
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
            self.model_hint_box.setVisible(False)
            chosen = current_model if current_model in models else models[0]
            self.model_combo.setCurrentText(chosen)
            self.model_combo.blockSignals(False)
            if chosen != current_model:
                self.cfg["model"] = chosen
                self._save_and_emit()
        else:
            if current_model:
                self.model_combo.addItem(current_model)
                self.model_combo.setCurrentText(current_model)
            self.model_combo.blockSignals(False)
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