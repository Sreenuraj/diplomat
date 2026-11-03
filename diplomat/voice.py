"""Voice dictation module for Diplomat using local Whisper STT."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioInput,
    QMediaCaptureSession,
    QMediaFormat,
    QMediaRecorder,
)

WHISPER_MODELS = ("tiny", "base", "small", "medium", "turbo")
_LOADED_MODELS: dict[str, Any] = {}


def is_whisper_available() -> bool:
    """Return True if OpenAI Whisper is importable or available as a CLI tool."""
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        pass
    return shutil.which("whisper") is not None


def get_whisper_status() -> tuple[bool, str]:
    """Return (available, description_message)."""
    try:
        import whisper  # noqa: F401
        return True, "Whisper available (Python module)"
    except ImportError:
        pass
    cli = shutil.which("whisper")
    if cli:
        return True, f"Whisper available (CLI: {cli})"
    return False, "Whisper not found (run: pip install openai-whisper)"


def transcribe(audio_path: str | Path, model_name: str = "base") -> str:
    """Transcribe an audio file using local Whisper.

    Tries the in-process Python module first (reusing loaded model in memory),
    then falls back to the CLI executable if the module is not installed in the
    current Python environment.
    """
    path = Path(audio_path)
    if not path.exists() or path.stat().st_size == 0:
        return ""

    # 1. In-process Python API
    try:
        import whisper

        global _LOADED_MODELS
        if model_name not in _LOADED_MODELS:
            _LOADED_MODELS[model_name] = whisper.load_model(model_name)
        model = _LOADED_MODELS[model_name]
        result = model.transcribe(str(path), fp16=False)
        return (result.get("text") or "").strip()
    except ImportError:
        pass

    # 2. CLI fallback
    cli = shutil.which("whisper")
    if cli:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cmd = [
                cli,
                str(path),
                "--model",
                model_name,
                "--output_dir",
                tmp_dir,
                "--output_format",
                "txt",
                "--fp16",
                "False",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                raise RuntimeError(f"Whisper CLI failed: {res.stderr or res.stdout}")
            txt_file = Path(tmp_dir) / f"{path.stem}.txt"
            if txt_file.exists():
                return txt_file.read_text(encoding="utf-8").strip()
            return ""

    raise RuntimeError(
        "Whisper is not installed. Run 'pip install openai-whisper' or install whisper via pyenv/Homebrew."
    )


class VoiceRecorder(QObject):
    """Records audio from the default microphone into a temporary WAV file."""

    recording_started = Signal()
    recording_stopped = Signal(str)  # emitted with absolute path to .wav file
    recording_failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._session = QMediaCaptureSession(self)
        self._audio_input = QAudioInput(self)
        self._session.setAudioInput(self._audio_input)

        self._recorder = QMediaRecorder(self)
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        self._recorder.setMediaFormat(media_format)
        self._session.setRecorder(self._recorder)

        self._temp_path: Path | None = None
        self._cancelled = False

        self._recorder.recorderStateChanged.connect(self._on_state_changed)
        self._recorder.errorOccurred.connect(self._on_error)

    def is_recording(self) -> bool:
        return (not self._cancelled) and (
            self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState
        )

    def start_recording(self) -> bool:
        """Start microphone recording to a temporary WAV file."""
        if self.is_recording():
            return False
        self._cancelled = False
        fd, tmp = tempfile.mkstemp(prefix="diplomat_rec_", suffix=".wav")
        os.close(fd)
        self._temp_path = Path(tmp)
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self._temp_path)))
        self._recorder.record()
        self.recording_started.emit()
        return True

    def stop_recording(self) -> None:
        """Stop recording and emit recording_stopped with the audio file path."""
        if self.is_recording():
            self._recorder.stop()

    def cancel_recording(self) -> None:
        """Stop recording and discard the temporary audio file."""
        self._cancelled = True
        if self.is_recording():
            self._recorder.stop()
        self._cleanup_temp_file()

    def teardown(self) -> None:
        """Release multimedia capture session and recorder cleanly."""
        self.cancel_recording()
        if hasattr(self, "_session") and self._session is not None:
            self._session.setAudioInput(None)
            self._session.setRecorder(None)

    def _cleanup_temp_file(self) -> None:
        if self._temp_path and self._temp_path.exists():
            try:
                self._temp_path.unlink()
            except OSError:
                pass
        self._temp_path = None

    def _on_state_changed(self, state: QMediaRecorder.RecorderState) -> None:
        if state == QMediaRecorder.RecorderState.StoppedState:
            if self._cancelled:
                self._cleanup_temp_file()
                return
            if self._temp_path:
                path_str = str(self._temp_path)
                self.recording_stopped.emit(path_str)

    def _on_error(self, error: QMediaRecorder.Error, error_string: str) -> None:
        self._cleanup_temp_file()
        self.recording_failed.emit(error_string or str(error))


class TranscribeWorker(QObject):
    """Background worker for transcribing recorded audio without blocking Qt UI."""

    finished = Signal(str)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(
        self,
        audio_path: str,
        model_name: str = "base",
        transcribe_fn: Callable[[str | Path, str], str] | None = None,
    ):
        super().__init__()
        self.audio_path = audio_path
        self.model_name = model_name
        self.transcribe_fn = transcribe_fn or transcribe

    def run(self) -> None:
        try:
            self.status_changed.emit(f"Transcribing audio with Whisper ({self.model_name})…")
            text = self.transcribe_fn(self.audio_path, self.model_name)
            self.finished.emit((text or "").strip())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            path = Path(self.audio_path)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
