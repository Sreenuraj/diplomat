"""Unit tests for the voice dictation and Whisper STT module."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication
from diplomat import voice


def test_is_whisper_available():
    assert voice.is_whisper_available() is True


def test_get_whisper_status():
    available, msg = voice.get_whisper_status()
    assert available is True
    assert "Whisper" in msg


def test_transcribe_nonexistent_or_empty(tmp_path):
    assert voice.transcribe(tmp_path / "does_not_exist.wav") == ""
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    assert voice.transcribe(empty_file) == ""


def test_real_transcribe_silence(tmp_path):
    import wave

    wav = tmp_path / "silence.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 3200)  # 0.1s PCM silence
    res = voice.transcribe(wav, model_name="base")
    assert isinstance(res, str)


def test_transcribe_worker_success(tmp_path):
    dummy_wav = tmp_path / "dummy.wav"
    dummy_wav.write_bytes(b"RIFF dummy wav data")

    results = []
    statuses = []

    def fake_transcribe(audio_path, model_name="base"):
        return "  hello world from test  "

    worker = voice.TranscribeWorker(
        str(dummy_wav),
        model_name="base",
        transcribe_fn=fake_transcribe,
    )
    worker.finished.connect(results.append)
    worker.status_changed.connect(statuses.append)

    worker.run()

    assert results == ["hello world from test"]
    assert len(statuses) > 0
    # Temporary file should have been cleaned up
    assert not dummy_wav.exists()


def test_transcribe_worker_error(tmp_path):
    dummy_wav = tmp_path / "dummy_err.wav"
    dummy_wav.write_bytes(b"test error")

    errors = []

    def failing_transcribe(audio_path, model_name="base"):
        raise RuntimeError("simulated model error")

    worker = voice.TranscribeWorker(
        str(dummy_wav),
        model_name="base",
        transcribe_fn=failing_transcribe,
    )
    worker.failed.connect(errors.append)

    worker.run()

    assert errors == ["simulated model error"]
    assert not dummy_wav.exists()


def test_voice_recorder_init_and_cancel():
    import time

    app = QCoreApplication.instance() or QCoreApplication([])
    rec = voice.VoiceRecorder()
    assert not rec.is_recording()

    # Test start and cancel
    started = rec.start_recording()
    if started:
        assert rec.is_recording()
        temp_file = rec._temp_path
        assert temp_file is not None
        assert temp_file.exists()
        rec.cancel_recording()
        assert not rec.is_recording()
        assert not temp_file.exists()
        deadline = time.monotonic() + 1.0
        while rec._recorder.recorderState() != voice.QMediaRecorder.RecorderState.StoppedState and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        rec.teardown()
        app.processEvents()
    else:
        rec.teardown()
