from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, text, *, history=(), tools=()):
        _ = text, history, tools
        self.calls += 1
        return AIReply(text="ok", provider_id="fake")

    def continue_after_tools(self, turn, results):
        raise AssertionError("unexpected continuation")

    def reply(self, text, *, history=()):
        raise AssertionError("unexpected direct provider reply")


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    memory = object()
    window = MainWindow(
        ActionRegistry(), memory,  # type: ignore[arg-type]
        provider, build_default_tool_catalog(),
    )
    try:
        yield window, provider, memory
    finally:
        window.close()


def focus(window, widget) -> None:
    window.show()
    widget.setFocus()
    QApplication.processEvents()
    assert widget.hasFocus()


def press_toggle(widget) -> None:
    QTest.keyClick(
        widget, Qt.Key.Key_T,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m136_shortcut_identity_and_finite_options(host) -> None:
    window, provider, _ = host
    shortcut = window.chat_text_size_cycle_shortcut
    assert shortcut.objectName() == "lyra_chat_text_size_cycle_shortcut"
    assert shortcut.parent() is window
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.key() == QKeySequence("Ctrl+Shift+T")
    assert shortcut.isEnabled()
    assert window.chat_text_size.currentIndex() == 0
    assert tuple(window.chat_text_size.itemData(i) for i in range(4)) == (None, 10, 12, 16)
    assert provider.calls == 0


def test_m136_direct_cycle_all_four_and_wrap(host) -> None:
    window, provider, _ = host
    for expected_index in (1, 2, 3, 0):
        window._cycle_chat_text_size_shortcut()
        assert window.chat_text_size.currentIndex() == expected_index
    assert provider.calls == 0


def test_m136_font_values_reuse_combo_handler(host) -> None:
    window, provider, _ = host
    for expected_size in (10, 12, 16):
        window._cycle_chat_text_size_shortcut()
        assert window.chat.font().pointSize() == expected_size
    window._cycle_chat_text_size_shortcut()
    assert window.chat_text_size.currentData() is None
    assert window.chat.font() == window._chat_base_font
    assert provider.calls == 0


def test_m136_activation_signal_roundtrip(host) -> None:
    window, provider, _ = host
    for expected in (1, 2, 3, 0):
        window.chat_text_size_cycle_shortcut.activated.emit()
        assert window.chat_text_size.currentIndex() == expected
    assert provider.calls == 0


def test_m136_qt_real_key_composer_keeps_draft_and_focus(host) -> None:
    window, provider, _ = host
    window.input.setText("mensagem não enviada")
    focus(window, window.input)
    press_toggle(window.input)
    assert window.chat_text_size.currentIndex() == 1
    assert window.input.text() == "mensagem não enviada"
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m136_qt_real_key_find_preserves_state(host) -> None:
    window, provider, _ = host
    window._lyra("Oak oak Oak")
    window.transcript_find.setText("Oak")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window._find_next_in_transcript()
    window.input.setText("rascunho")
    before = (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
        window.transcript_find_case_sensitive.isChecked(),
        window.transcript_find_whole_word.isChecked(), window.input.text(),
    )
    focus(window, window.transcript_find)
    press_toggle(window.transcript_find)
    after = (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
        window.transcript_find_case_sensitive.isChecked(),
        window.transcript_find_whole_word.isChecked(), window.input.text(),
    )
    assert before == after
    assert window.transcript_find.hasFocus()
    assert window.chat_text_size.currentIndex() == 1
    assert provider.calls == 0


def test_m136_qt_real_key_from_read_only_chat(host) -> None:
    window, provider, _ = host
    window._lyra("read only")
    focus(window, window.chat)
    press_toggle(window.chat)
    assert window.chat.isReadOnly()
    assert "read only" in window.chat.toPlainText()
    assert window.chat_text_size.currentIndex() == 1
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m136_combo_selection_and_shortcut_share_state(host) -> None:
    window, provider, _ = host
    window.chat_text_size.setCurrentIndex(2)
    window.chat_text_size_cycle_shortcut.activated.emit()
    assert window.chat_text_size.currentIndex() == 3
    assert window.chat.font().pointSize() == 16
    window.chat_text_size.setCurrentIndex(0)
    assert window.chat.font() == window._chat_base_font
    assert provider.calls == 0


def test_m136_unchanged_follow_and_search_with_shortcut(host) -> None:
    window, provider, _ = host
    window.chat_follow.setChecked(False)
    window.transcript_find.setText("needle")
    window.input.setText("draft")
    window.chat_text_size_cycle_shortcut.activated.emit()
    assert not window.chat_follow.isChecked()
    assert window.transcript_find.text() == "needle"
    assert window.input.text() == "draft"
    assert provider.calls == 0


def test_m136_busy_direct_signal_and_real_key_fail_closed(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    window._set_busy(True)
    try:
        assert not window.chat_text_size_cycle_shortcut.isEnabled()
        window._cycle_chat_text_size_shortcut()
        window.chat_text_size_cycle_shortcut.activated.emit()
        press_toggle(window.chat)
        assert window.chat_text_size.currentIndex() == 0
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.chat_text_size_cycle_shortcut.isEnabled()


def test_m136_busy_reenable_key_event(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    window._set_busy(False)
    focus(window, window.input)
    press_toggle(window.input)
    assert window.chat_text_size.currentIndex() == 1
    assert provider.calls == 0


def test_m136_invalid_combo_model_fails_closed(host) -> None:
    window, provider, _ = host
    window.chat_text_size.addItem("extra", 20)
    window._cycle_chat_text_size_shortcut()
    assert window.chat_text_size.currentIndex() == 0
    assert provider.calls == 0


def test_m136_two_window_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.chat_text_size_cycle_shortcut.activated.emit()
        assert window.chat_text_size.currentIndex() == 1
        assert other.chat_text_size.currentIndex() == 0
        assert window.chat_text_size_cycle_shortcut is not other.chat_text_size_cycle_shortcut
        assert other.chat_text_size_cycle_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m136_denied_reset_keeps_selection_and_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.chat_text_size.setCurrentIndex(3)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.chat_text_size.currentIndex() == 3
    assert window.chat_text_size_cycle_shortcut.isEnabled()
    assert provider.calls == 0


def test_m136_accepted_reset_defaults_and_shortcut_remains(host, monkeypatch) -> None:
    window, provider, memory = host
    personality = window._personality.snapshot()
    window.chat_text_size.setCurrentIndex(3)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.chat_text_size.currentIndex() == 0
    assert window.chat_text_size_cycle_shortcut.isEnabled()
    window.chat_text_size_cycle_shortcut.activated.emit()
    assert window.chat_text_size.currentIndex() == 1
    assert window._memory is memory
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m136_provider_context_memory_personality_no_side_effect(host) -> None:
    window, provider, memory = host
    before_history = window._context.provider_snapshot()
    before_style = window._personality.snapshot()
    perception = window._perception
    transcript = window.chat.toPlainText()
    window.chat_text_size_cycle_shortcut.activated.emit()
    assert window._context.provider_snapshot() == before_history
    assert window._personality.snapshot() == before_style
    assert window._perception is perception
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
