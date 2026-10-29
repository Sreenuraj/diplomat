import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from diplomat import config, llm, prompt

DEFAULT_SLIDERS = config.DEFAULTS["sliders"]
SLACK = prompt.PRESETS["slack_office"]
LINKEDIN = prompt.PRESETS["linkedin"]


# ---- sliders

@pytest.mark.parametrize("value,band", [(0, 0), (19, 0), (20, 1), (50, 2), (79, 3), (80, 4), (100, 4), (150, 4), (-5, 0)])
def test_band_index(value, band):
    assert prompt.band_index(value) == band


def test_default_sliders_match_plan():
    # Plan defaults, on a 1-5 scale: 3,3,3,1(=0 of 5 in plan),1,2,3
    bands = {k: prompt.band_index(v) + 1 for k, v in DEFAULT_SLIDERS.items()}
    assert bands == {"formality": 3, "warmth": 3, "directness": 3, "humor": 1, "sarcasm": 1, "enthusiasm": 2, "brevity": 3}


def test_slider_lines_cover_all_sliders():
    lines = prompt.slider_lines(DEFAULT_SLIDERS)
    assert len(lines) == 7
    assert "No humor at all" in "\n".join(lines)


def test_sarcasm_top_band_stays_workplace_safe():
    assert "workplace-safe" in prompt.SLIDER_BANDS["sarcasm"][4]
    assert all(len(b) == 5 for b in prompt.SLIDER_BANDS.values())


# ---- prompt assembly

def test_system_prompt_blocks():
    sp = prompt.build_system_prompt(SLACK, DEFAULT_SLIDERS, slop_rules=True)
    assert "tone editor" in sp
    assert "Fidelity" in sp
    assert "Plain text only" in sp
    assert "Writing rules" in sp


def test_system_prompt_without_rules():
    sp = prompt.build_system_prompt(SLACK, DEFAULT_SLIDERS, slop_rules=False)
    assert "Writing rules" not in sp


def test_system_prompt_banned_and_length():
    sp = prompt.build_system_prompt(LINKEDIN, DEFAULT_SLIDERS, banned=["Here's the thing"], max_chars=2700)
    assert "Here's the thing" in sp
    assert "under 2700 characters" in sp


def test_user_message_with_and_without_context():
    plain = prompt.build_user_message("  hello  ")
    assert plain.startswith("<draft>hello</draft>")
    assert "<context>" not in plain
    withctx = prompt.build_user_message("hello", "Can you send it?")
    assert withctx.startswith("<context>Can you send it?</context>\n<draft>hello</draft>")
    assert withctx.endswith("No preface, no quotes, no explanation.")
    assert "English" in prompt.build_system_prompt(SLACK, DEFAULT_SLIDERS)
    assert "<context>" not in prompt.build_user_message("hello", "   ")


def test_target_chars():
    assert prompt.target_chars(3000) == 2700
    assert prompt.target_chars(None) is None


def test_unknown_preset():
    with pytest.raises(KeyError):
        prompt.get_preset("nope")


# ---- post-processing

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Here's the rewritten message:\n\nHi Sam, the report is late.", "Hi Sam, the report is late."),
        ("Sure! Here is the polished version:\n\nHi Sam.", "Hi Sam."),
        ('"Hi Sam, the report is late."', "Hi Sam, the report is late."),
        ("\u201cHi Sam.\u201d", "Hi Sam."),
        ("```\nHi Sam.\n```", "Hi Sam."),
        ("<think>hmm let me think</think>\nHi Sam.", "Hi Sam."),
        ("<think>never closed", ""),
        ("Rewritten message: Hi Sam.", "Hi Sam."),
        ("Please read **this** now.", "Please read this now."),
        ("Hi Sam.", "Hi Sam."),
        ('He said "no" and "yes"', 'He said "no" and "yes"'),
        ("\u201cHello,\u201d she said, \u201chow are you?\u201d", "\u201cHello,\u201d she said, \u201chow are you?\u201d"),
    ],
)
def test_clean_output(raw, expected):
    assert prompt.clean_output(raw) == expected


def test_strip_think_multiline():
    assert llm.strip_think("<think>a\nb</think>Hello") == "Hello"


# ---- slop detection

@pytest.mark.parametrize(
    "text",
    [
        "It's not a bug, it's a feature request.",
        "This is not just a delay but a blocker.",
        "Here's the thing: we are late.",
        "I hope this email finds you well.",
        "We need to leverage the new tool.",
        "At the end of the day, it ships Friday.",
        "Let me be clear about this.",
        "I wanted to reach out about the invoice.",
    ],
)
def test_find_slop_hits(text):
    assert prompt.find_slop(text)


@pytest.mark.parametrize(
    "text",
    [
        "Hi Priya, thanks for flagging this. I can have the fix ready by Friday.",
        "Could you send the Q3 numbers before 5pm today?",
        "The meeting moved to Oct 14 at 3:30pm PST in room 4B.",
    ],
)
def test_find_slop_clean(text):
    assert prompt.find_slop(text) == []


# ---- length logic

def test_over_limit():
    assert prompt.over_limit("x" * 3001, 3000)
    assert not prompt.over_limit("x" * 3000, 3000)
    assert not prompt.over_limit("x" * 99999, None)


class FakeChat:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_generate_clean_first_try():
    chat = FakeChat(["Hi Sam, the report is late."])
    r = prompt.generate(chat, "report late tell sam", SLACK, DEFAULT_SLIDERS)
    assert r.text == "Hi Sam, the report is late."
    assert r.retries == []
    assert len(chat.calls) == 1


def test_generate_slop_retry_once_then_shown_as_is():
    chat = FakeChat(["Here's the thing: it is late.", "Here's the thing: it is still late."])
    r = prompt.generate(chat, "late", SLACK, DEFAULT_SLIDERS)
    assert len(chat.calls) == 2
    assert r.retries == ["slop"]
    assert r.remaining_slop  # shown as-is, flagged
    assert "Here's the thing" in chat.calls[1][-1]["content"]


def test_generate_shortens_once_when_over_limit():
    chat = FakeChat(["x" * 3200, "y" * 2000])
    r = prompt.generate(chat, "long", LINKEDIN, DEFAULT_SLIDERS)
    assert r.text == "y" * 2000
    assert r.retries == ["length"]
    assert not r.over_limit
    assert "under 2700 characters" in chat.calls[1][-1]["content"]


def test_generate_never_truncates_if_still_over():
    chat = FakeChat(["x" * 3200, "y" * 3100])
    r = prompt.generate(chat, "long", LINKEDIN, DEFAULT_SLIDERS)
    assert len(r.text) == 3100
    assert r.over_limit
    assert len(chat.calls) == 2  # only one retry


def test_generate_no_limit_no_length_retry():
    chat = FakeChat(["x" * 5000])
    r = prompt.generate(chat, "long", SLACK, DEFAULT_SLIDERS)
    assert len(r.text) == 5000
    assert len(chat.calls) == 1


def test_generate_slop_rules_off_skips_check():
    chat = FakeChat(["Here's the thing: it is late."])
    r = prompt.generate(chat, "late", SLACK, DEFAULT_SLIDERS, slop_rules=False)
    assert len(chat.calls) == 1
    assert r.remaining_slop == []


# ---- samples file

def test_sample_inputs_has_15():
    samples = prompt.read_samples(Path(__file__).parent / "sample_inputs.txt")
    assert len(samples) == 15


# ---- config

def test_config_defaults_when_missing(tmp_path):
    cfg = config.load(tmp_path / "c.json")
    assert cfg == config.DEFAULTS


def test_config_roundtrip_and_merge(tmp_path):
    p = tmp_path / "sub" / "c.json"
    config.save({"model": "llama3", "sliders": {"humor": 70}}, p)
    cfg = config.load(p)
    assert cfg["model"] == "llama3"
    assert cfg["sliders"]["humor"] == 70
    assert cfg["sliders"]["formality"] == config.DEFAULTS["sliders"]["formality"]
    assert cfg["hotkey"] == "option+space"


def test_config_corrupt_is_backed_up(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    cfg = config.load(p)
    assert cfg == config.DEFAULTS
    assert not p.exists()
    assert list(tmp_path.glob("c.corrupt-*.json"))


def test_config_non_object_is_corrupt(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([1, 2]))
    assert config.load(p) == config.DEFAULTS


def test_is_local_url():
    assert config.is_local_url("http://localhost:11434/v1")
    assert config.is_local_url("http://127.0.0.1:1234/v1")
    assert not config.is_local_url("https://api.example.com/v1")

def test_em_dash_replaced_in_code():
    assert prompt.clean_output("Ship it \u2014 today.") == "Ship it, today."
    assert "\u2014" not in prompt.clean_output("a\u2014b")
    assert prompt.clean_output("Line one\n\n\u2014 Line two") == "Line one\n\n, Line two"


def test_default_model_is_not_machine_specific():
    assert config.DEFAULTS["model"] == ""


def test_config_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DIPLOMAT_CONFIG", str(tmp_path / "x.json"))
    assert config.config_path() == tmp_path / "x.json"


# ---- step 2: hotkey & popup UI

def test_hotkey_formatting_and_pynput_mapping():
    from diplomat import main as main_mod

    assert main_mod.to_pynput_hotkey("option+space") == "<alt>+<space>"
    assert main_mod.to_pynput_hotkey("cmd+shift+d") == "<cmd>+<shift>+d"
    assert main_mod.format_hotkey_label("option+space") == "⌥ Space"
    with pytest.raises(ValueError):
        main_mod.to_pynput_hotkey("   ")


def test_format_counter_states():
    from diplomat import ui

    assert ui.format_counter(0, None) == ("", "normal")
    assert ui.format_counter(120, None) == ("120 chars", "normal")
    assert ui.format_counter(500, 3000) == ("500 / 3000", "normal")
    assert ui.format_counter(2700, 3000) == ("2700 / 3000", "amber")
    assert ui.format_counter(3000, 3000) == ("3000 / 3000", "amber")
    assert ui.format_counter(3001, 3000) == ("3001 / 3000", "red")


def test_popup_ui_end_to_end(tmp_path):
    import time
    from PySide6.QtWidgets import QApplication
    from diplomat import ui

    app = QApplication.instance() or QApplication([])
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)
    cfg["model"] = "test-model"

    def fake_stream(base_url, model, messages, api_key=None):
        yield "Hi Priya, "
        yield "I can have the fix ready by Friday."

    popup = ui.PopupWindow(cfg=cfg, config_path=cfg_file, stream_fn=fake_stream)

    # Empty input: Generate is disabled
    assert not popup.generate_btn.isEnabled()
    assert not popup.copy_btn.isEnabled()

    # Tone panel toggle persists to config
    assert popup.tone_panel.isHidden()
    popup._toggle_tone_panel()
    assert not popup.tone_panel.isHidden()
    assert config.load(cfg_file)["tone_open"] is True

    # Slider change + reset
    popup.slider_widgets["humor"].setValue(80)
    assert config.load(cfg_file)["sliders"]["humor"] == 80
    popup.reset_sliders()
    assert config.load(cfg_file)["sliders"]["humor"] == 0

    # Type draft, generate, wait for worker, and copy
    popup.draft_edit.setPlainText("fix ready friday tell priya")
    assert popup.generate_btn.isEnabled()
    popup.trigger_generate()
    deadline = time.monotonic() + 3.0
    while popup.is_generating() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert popup.output_edit.toPlainText() == "Hi Priya, I can have the fix ready by Friday."
    assert popup.generate_btn.text() == "Regenerate"
    assert popup.copy_btn.isEnabled()
    assert popup.copy_output() is True
    assert app.clipboard().text() == "Hi Priya, I can have the fix ready by Friday."


def test_popup_error_and_retry_state(tmp_path):
    import time
    from PySide6.QtWidgets import QApplication
    from diplomat import ui

    app = QApplication.instance() or QApplication([])
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)
    cfg["model"] = "missing-model"

    def failing_stream(base_url, model, messages, api_key=None):
        raise llm.LLMError("model_missing", "Model 'missing-model' was not found on the server. Pick another one in Settings.")
        yield ""  # pragma: no cover

    popup = ui.PopupWindow(cfg=cfg, config_path=cfg_file, stream_fn=failing_stream)
    popup.draft_edit.setPlainText("hello")
    popup.trigger_generate()
    deadline = time.monotonic() + 3.0
    while popup.is_generating() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert not popup.error_label.isHidden()
    assert "Settings" in popup.error_label.text()
    assert not popup.open_settings_inline_btn.isHidden()
    assert popup.generate_btn.text() == "Retry"


# ---- step 3 & 4: settings dialog, hotkey recorder, launcher scripts

def test_keyevent_to_hotkey_spec():
    from PySide6.QtCore import Qt
    from diplomat import ui

    assert ui.keyevent_to_hotkey_spec(Qt.Key.Key_Space, Qt.KeyboardModifier.AltModifier) == "option+space"
    assert (
        ui.keyevent_to_hotkey_spec(
            Qt.Key.Key_D,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        == "shift+cmd+d"
    )
    assert ui.keyevent_to_hotkey_spec(Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier) is None
    assert ui.keyevent_to_hotkey_spec(Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier) is None


def test_settings_dialog_end_to_end(tmp_path):
    from PySide6.QtWidgets import QApplication
    from diplomat import ui

    _ = QApplication.instance() or QApplication([])
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    models_state = ["qwen2.5:7b-instruct", "llama3.1:8b"]

    def fake_list_models(base_url, api_key):
        return list(models_state)

    def fake_test_connection(base_url, model, api_key):
        return (f"Could you please send me the file? ({model})", 0.42)

    dlg = ui.SettingsDialog(
        cfg=cfg,
        config_path=cfg_file,
        list_models_fn=fake_list_models,
        test_connection_fn=fake_test_connection,
        hotkey_status_fn=lambda spec: (True, None),
    )

    # First open auto-picks the first installed model and shows Connected status
    assert "Connected" in dlg.server_status_label.text()
    assert dlg.model_combo.currentText() == "qwen2.5:7b-instruct"
    assert config.load(cfg_file)["model"] == "qwen2.5:7b-instruct"
    assert dlg.model_hint_box.isHidden()

    # Switching provider to LM Studio updates base_url immediately
    dlg.provider_combo.setCurrentIndex(1)  # lmstudio
    assert dlg.base_url_edit.text() == config.PROVIDERS["lmstudio"]
    assert config.load(cfg_file)["provider"] == "lmstudio"

    # Test connection displays reply and elapsed time
    assert dlg.run_test_connection() is True
    assert "0.42s" in dlg.test_result_label.text()

    # Empty model list shows copyable ollama pull hint
    models_state.clear()
    dlg.cfg["model"] = ""
    dlg.refresh_models()
    assert not dlg.model_hint_box.isHidden()
    assert "ollama pull" in dlg.model_hint_box.text()

    # Hotkey & writing rules apply immediately
    dlg._on_hotkey_changed("cmd+shift+space")
    dlg.slop_rules_check.setChecked(False)
    saved = config.load(cfg_file)
    assert saved["hotkey"] == "cmd+shift+space"
    assert saved["slop_rules"] is False


def test_launcher_scripts_exist_and_executable():
    import os

    root = Path(__file__).resolve().parents[1]
    for name in ("run.sh", "Diplomat.command"):
        path = root / name
        assert path.exists(), f"{name} is missing"
        assert os.access(path, os.X_OK), f"{name} is not executable"