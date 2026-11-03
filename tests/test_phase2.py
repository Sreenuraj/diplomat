"""Unit tests for Phase 2 extras:

- Paste into previous app (⇧↩)
- Selection capture
- 'Shorter' button and quick variants
- Email preset
- Native macOS vibrancy blur
- Launch at login autostart
- In-memory history
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from diplomat import config, platform as platform_mod, prompt, ui


def _get_app():
    return QApplication.instance() or QApplication(sys.argv)


def test_email_preset():
    assert "email" in prompt.PRESETS
    email = prompt.PRESETS["email"]
    assert email.limit is None
    assert "Subject:" in email.notes
    assert "Best regards" in email.notes


def test_shorter_and_variants_navigation(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)
    assert not win.shorter_btn.isEnabled()
    assert win.variant_container.isHidden()

    # Worker generates initial variant
    res1 = prompt.Result("Initial draft rewrite.", None)
    win._on_worker_finished(res1)
    assert win.output_edit.toPlainText() == "Initial draft rewrite."
    assert win.shorter_btn.isEnabled()
    assert len(win._variants) == 1
    assert win.variant_container.isHidden()

    # Second variant (e.g. from shorter or regenerate)
    res2 = prompt.Result("Shorter rewrite.", None)
    win._on_worker_finished(res2)
    assert win.output_edit.toPlainText() == "Shorter rewrite."
    assert len(win._variants) == 2
    assert not win.variant_container.isHidden()
    assert win.variant_label.text() == "2/2"

    # Flip between variants
    win.prev_variant()
    assert win.output_edit.toPlainText() == "Initial draft rewrite."
    assert win.variant_label.text() == "1/2"

    win.next_variant()
    assert win.output_edit.toPlainText() == "Shorter rewrite."
    assert win.variant_label.text() == "2/2"


def test_history_recording_and_restore(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)
    assert len(win._history) == 0

    win.draft_edit.setPlainText("Rough bullet points")
    win._on_worker_finished(prompt.Result("Clean bullet points message.", None))

    assert len(win._history) == 1
    item = win._history[0]
    assert item["draft"] == "Rough bullet points"
    assert item["output"] == "Clean bullet points message."
    assert "time" in item

    # Clear and restore from history
    win.clear_all()
    assert win.output_edit.toPlainText() == ""
    assert win.draft_edit.toPlainText() == ""

    win._restore_history_item(item)
    assert win.output_edit.toPlainText() == "Clean bullet points message."
    assert win.draft_edit.toPlainText() == "Rough bullet points"
    assert QGuiApplication.clipboard().text() == "Clean bullet points message."


def test_paste_and_selection_capture(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)
    assert not win.paste_btn.isEnabled()

    # Selection capture injection
    win.set_captured_draft("Highlighted text from Slack")
    assert win.draft_edit.toPlainText() == "Highlighted text from Slack"
    assert win.generate_btn.isEnabled()

    # Output set -> paste button active
    win.output_edit.setPlainText("Polished response ready to paste")
    win._update_controls()
    assert win.paste_btn.isEnabled()

    win.paste_and_close()
    assert QGuiApplication.clipboard().text() == "Polished response ready to paste"


def test_reply_to_selection_and_move_draft(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)
    assert win.context_edit.isHidden()

    # 1. Selection capture directly into "Replying to:" (⌥⇧ Space)
    win.set_captured_context("Can you finish the report by 3pm?")
    assert win.context_edit.toPlainText() == "Can you finish the report by 3pm?"
    assert not win.context_edit.isHidden()
    assert win.draft_edit.toPlainText() == ""

    # 2. Moving draft into reply context via ⌥C
    win.draft_edit.setPlainText("Accidentally typed message here")
    win._update_controls()
    assert not win.move_to_reply_btn.isHidden()
    win.move_draft_to_reply()
    assert win.context_edit.toPlainText() == "Accidentally typed message here"
    assert not win.context_edit.isHidden()
    assert win.draft_edit.toPlainText() == ""
    assert win.move_to_reply_btn.isHidden()


def test_reply_hotkey_parsing():
    from diplomat import main as main_mod

    assert config.DEFAULTS["reply_hotkey"] == "option+shift+space"
    pynput_spec = main_mod.to_pynput_hotkey("option+shift+space")
    assert pynput_spec == "<alt>+<shift>+<space>"
    if sys.platform == "darwin":
        vk, mods = main_mod.to_carbon_hotkey("option+shift+space")
        assert vk == 0x31  # Space
        assert mods == (1 << 11) | (1 << 9)  # optionKey | shiftKey
        assert main_mod.format_hotkey_label("option+shift+space") == "⌥ ⇧ Space"


def test_shortcuts_dialog(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)
    assert win.shortcuts_btn is not None
    assert win._shortcuts_dialog is None

    # Click / trigger shortcuts dialog
    win.show_shortcuts_dialog()
    dlg = win._shortcuts_dialog
    assert dlg is not None
    assert dlg.global_hotkey_lbl.text() == "⌥ Space"
    assert dlg.global_reply_lbl.text() == "⌥ ⇧ Space"

    # Reload config with custom hotkeys
    new_cfg = dict(cfg)
    new_cfg["hotkey"] = "ctrl+space"
    new_cfg["reply_hotkey"] = "ctrl+shift+space"
    win.reload_config(new_cfg)
    assert dlg.global_hotkey_lbl.text() == "⌃ Space"
    assert dlg.global_reply_lbl.text() == "⌃ ⇧ Space"

    dlg.close()


def test_streamlined_shortcuts_and_buttons(tmp_path):
    app = _get_app()
    cfg_file = tmp_path / "config.json"
    cfg = config.load(cfg_file)

    win = ui.PopupWindow(cfg=cfg, config_path=cfg_file)

    # Check button hotkey labels
    assert "⌘K" in win.clear_btn.text()
    assert "⌘Q" in win.quit_btn.text()
    assert "⌘↩" in win.generate_btn.text()
    assert "⌘S" in win.shorter_btn.text()
    assert "↩" in win.copy_btn.text()
    assert "⇧↩" in win.paste_btn.text()
    assert "⌥C" in win.move_to_reply_btn.text()

    # Test is_front_element_editable smoke test
    platform_mod.is_front_element_editable()

    # Test auto-paste flag on primary shortcut
    win.draft_edit.setPlainText("Test message")
    assert win.generate_btn.isEnabled()
    win.trigger_generate_and_paste()
    assert win._auto_paste_on_finish is True
    win.cancel_generation()
    assert win._auto_paste_on_finish is False


def test_autostart_logic(tmp_path, monkeypatch):
    test_plist = tmp_path / "test_autostart.plist"
    monkeypatch.setattr(platform_mod, "get_launch_agent_path", lambda: test_plist)

    # Initially disabled
    assert platform_mod.is_autostart_enabled() is False

    # Enabled
    ok = platform_mod.set_autostart_enabled(True)
    if sys.platform == "darwin":
        assert ok is True
        assert test_plist.exists()
        content = test_plist.read_text()
        assert "com.diplomat.app" in content
        assert "RunAtLoad" in content

        # Disable
        ok2 = platform_mod.set_autostart_enabled(False)
        assert ok2 is True
        assert not test_plist.exists()


def test_macos_vibrancy_smoke():
    app = _get_app()
    from PySide6.QtWidgets import QWidget

    w = QWidget()
    # Smoke test: does not raise error
    platform_mod.get_frontmost_app()
    ui.apply_macos_vibrancy(w)


def test_selection_capture_logic(monkeypatch):
    """Test selection capture changeCount detection and clipboard restoration."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    original_text = pb.stringForType_(NSPasteboardTypeString) or ""

    # Test 1: simulate_copy returns False -> capture_selected_text returns None
    monkeypatch.setattr(platform_mod, "simulate_copy", lambda **kwargs: False)
    assert platform_mod.capture_selected_text() is None

    # Test 2: simulate_copy succeeds and updates clipboard -> returns captured text & restores clipboard
    def fake_copy(**kwargs):
        pb.clearContents()
        pb.setString_forType_("Simulated Selected Text", NSPasteboardTypeString)
        return True

    monkeypatch.setattr(platform_mod, "simulate_copy", fake_copy)
    result = platform_mod.capture_selected_text(timeout_sec=0.1)
    assert result == "Simulated Selected Text"

    # Verify original clipboard was restored
    restored = pb.stringForType_(NSPasteboardTypeString) or ""
    assert restored == original_text

    # Test 3: editable detection doesn't crash on None or dummy
    assert platform_mod.is_front_element_editable(None) is False

