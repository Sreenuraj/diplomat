"""Popup window (Step 2) and Settings hook for Diplomat."""

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
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
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


def build_stylesheet(dark: bool) -> str:
    if dark:
        card_bg = "rgba(32, 32, 36, 242)"
        card_border = "rgba(255, 255, 255, 36)"
        text_fg = "#f2f2f7"
        muted_fg = "#98989f"
        field_bg = "rgba(255, 255, 255, 16)"
        field_border = "rgba(255, 255, 255, 28)"
        field_focus = "rgba(10, 132, 255, 180)"
        btn_bg = "rgba(255, 255, 255, 22)"
        btn_hover = "rgba(255, 255, 255, 36)"
        primary_bg = "#0a84ff"
        primary_hover = "#409cff"
        primary_fg = "#ffffff"
        divider = "rgba(255, 255, 255, 26)"
        slider_groove = "rgba(255, 255, 255, 38)"
    else:
        card_bg = "rgba(250, 250, 252, 245)"
        card_border = "rgba(0, 0, 0, 28)"
        text_fg = "#1c1c1e"
        muted_fg = "#6c6c70"
        field_bg = "rgba(0, 0, 0, 11)"
        field_border = "rgba(0, 0, 0, 22)"
        field_focus = "rgba(0, 122, 255, 170)"
        btn_bg = "rgba(0, 0, 0, 14)"
        btn_hover = "rgba(0, 0, 0, 24)"
        primary_bg = "#007aff"
        primary_hover = "#0062cc"
        primary_fg = "#ffffff"
        divider = "rgba(0, 0, 0, 20)"
        slider_groove = "rgba(0, 0, 0, 32)"

    return f"""
        QFrame#card {{
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: 22px;
        }}
        QLabel {{
            color: {text_fg};
            background: transparent;
        }}
        QLabel#titleLabel {{
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#mutedLabel, QLabel#sliderLabel {{
            color: {muted_fg};
            font-size: 12px;
        }}
        QLabel#errorLabel {{
            color: #ff453a;
            font-size: 12px;
        }}
        QLabel#warnLabel {{
            color: #d97706;
            font-size: 11px;
        }}
        QPlainTextEdit {{
            background-color: {field_bg};
            color: {text_fg};
            border: 1px solid {field_border};
            border-radius: 10px;
            padding: 8px;
            font-size: 13px;
            selection-background-color: {primary_bg};
            selection-color: {primary_fg};
        }}
        QPlainTextEdit:focus {{
            border: 1px solid {field_focus};
        }}
        QPlainTextEdit#outputEdit {{
            background-color: transparent;
            border: 1px solid {field_border};
        }}
        QComboBox {{
            background-color: {btn_bg};
            color: {text_fg};
            border: 1px solid {field_border};
            border-radius: 8px;
            padding: 4px 10px;
            font-size: 12px;
        }}
        QComboBox:hover {{
            background-color: {btn_hover};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}
        QPushButton {{
            background-color: {btn_bg};
            color: {text_fg};
            border: 1px solid {field_border};
            border-radius: 8px;
            padding: 5px 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {btn_hover};
        }}
        QPushButton:disabled {{
            color: {muted_fg};
            background-color: transparent;
            border-color: {divider};
        }}
        QPushButton#primaryButton {{
            background-color: {primary_bg};
            color: {primary_fg};
            border: none;
            font-weight: 600;
        }}
        QPushButton#primaryButton:hover {{
            background-color: {primary_hover};
        }}
        QPushButton#primaryButton:disabled {{
            background-color: {btn_bg};
            color: {muted_fg};
        }}
        QPushButton#sectionToggle, QPushButton#linkButton, QPushButton#iconButton {{
            background: transparent;
            border: none;
            color: {muted_fg};
            padding: 2px 6px;
            font-size: 12px;
            text-align: left;
        }}
        QPushButton#sectionToggle:hover, QPushButton#linkButton:hover, QPushButton#iconButton:hover {{
            color: {text_fg};
        }}
        QPushButton#iconButton {{
            font-size: 15px;
            padding: 2px 8px;
        }}
        QFrame#divider {{
            background-color: {divider};
            max-height: 1px;
            min-height: 1px;
            border: none;
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {slider_groove};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {primary_bg};
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
        self.setMinimumWidth(520)
        self.resize(540, 440)

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

        # 1. Header bar: Title | Preset dropdown | Settings button
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_label = QLabel("Diplomat")
        self.title_label.setObjectName("titleLabel")
        header.addWidget(self.title_label)

        self.preset_combo = QComboBox()
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
        tone_grid.setHorizontalSpacing(14)
        tone_grid.setVerticalSpacing(6)

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
        self.generate_btn.setToolTip("Generate (⌘↩) or Regenerate (⌘R)")
        self.generate_btn.clicked.connect(self._on_generate_button_clicked)
        footer.addWidget(self.generate_btn)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("primaryButton")
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