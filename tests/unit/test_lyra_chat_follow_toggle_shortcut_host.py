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
        widget, Qt.Key.Key_A,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m135_identity_parent_key_and_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.chat_follow_toggle_shortcut
    assert shortcut.objectName() == "lyra_chat_follow_toggle_shortcut"
    assert shortcut.parent() is window
    assert shortcut.key() == QKeySequence("Ctrl+Shift+A")
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.isEnabled()
    assert window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_direct_toggle_off_and_on(host) -> None:
    window, provider, _ = host
    assert window.chat_follow.isChecked()
    window._toggle_chat_follow_shortcut()
    assert not window.chat_follow.isChecked()
    window._toggle_chat_follow_shortcut()
    assert window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_signal_routes_to_existing_follow_control(host) -> None:
    window, provider, _ = host
    window.chat_follow_toggle_shortcut.activated.emit()
    assert not window.chat_follow.isChecked()
    window.chat_follow_toggle_shortcut.activated.emit()
    assert window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_real_qt_key_from_composer_preserves_draft(host) -> None:
    window, provider, _ = host
    window.input.setText("rascunho que não deve ser enviado")
    focus(window, window.input)
    press_toggle(window.input)
    assert not window.chat_follow.isChecked()
    assert window.input.text() == "rascunho que não deve ser enviado"
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m135_real_qt_key_from_find_preserves_query_rank_modes(host) -> None:
    window, provider, _ = host
    window._lyra("Oak oak Oak")
    window.transcript_find.setText("Oak")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window._find_next_in_transcript()
    window.input.setText("draft")
    previous = (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
    )
    focus(window, window.transcript_find)
    press_toggle(window.transcript_find)
    assert not window.chat_follow.isChecked()
    assert window.transcript_find.hasFocus()
    assert previous == (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
    )
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert window.input.text() == "draft"
    assert provider.calls == 0


def test_m135_real_qt_key_from_read_only_transcript(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    assert window.chat.isReadOnly()
    press_toggle(window.chat)
    assert not window.chat_follow.isChecked()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m135_shortcut_and_checkbox_share_one_authoritative_state(host) -> None:
    window, provider, _ = host
    window.chat_follow.setChecked(False)
    assert not window.chat_follow.isChecked()
    window.chat_follow_toggle_shortcut.activated.emit()
    assert window.chat_follow.isChecked()
    window.chat_follow.setChecked(False)
    assert not window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_follow_off_preserves_reading_position_on_append(host) -> None:
    window, provider, _ = host
    window.show()
    window.chat.setPlainText("\n".join(str(x) for x in range(250)))
    QApplication.processEvents()
    scrollbar = window.chat.verticalScrollBar()
    assert scrollbar.maximum() > 0
    window._toggle_chat_follow_shortcut()
    scrollbar.setValue(scrollbar.minimum())
    before = scrollbar.value()
    window._lyra("new arrival")
    assert scrollbar.value() == before
    assert not window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_follow_on_reuses_existing_bottom_scroll_semantics(host) -> None:
    window, provider, _ = host
    window.show()
    window.chat.setPlainText("\n".join(str(x) for x in range(250)))
    QApplication.processEvents()
    scrollbar = window.chat.verticalScrollBar()
    assert scrollbar.maximum() > 0
    window._toggle_chat_follow_shortcut()
    scrollbar.setValue(scrollbar.minimum())
    window._toggle_chat_follow_shortcut()
    assert window.chat_follow.isChecked()
    assert scrollbar.value() == scrollbar.maximum()
    window._lyra("new reply")
    assert scrollbar.value() == scrollbar.maximum()
    assert provider.calls == 0


def test_m135_busy_signal_direct_and_qt_fail_closed(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    window._set_busy(True)
    try:
        assert not window.chat_follow_toggle_shortcut.isEnabled()
        assert window.chat_follow.isChecked()
        window._toggle_chat_follow_shortcut()
        window.chat_follow_toggle_shortcut.activated.emit()
        press_toggle(window.chat)
        assert window.chat_follow.isChecked()
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.chat_follow_toggle_shortcut.isEnabled()


def test_m135_shortcut_restored_after_busy_with_qt_key(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    window._set_busy(False)
    focus(window, window.input)
    press_toggle(window.input)
    assert not window.chat_follow.isChecked()
    assert provider.calls == 0


def test_m135_two_windows_independent(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.chat_follow_toggle_shortcut.activated.emit()
        assert not window.chat_follow.isChecked()
        assert other.chat_follow.isChecked()
        assert other.chat_follow_toggle_shortcut is not window.chat_follow_toggle_shortcut
        assert other.chat_follow_toggle_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m135_reset_denied_keeps_follow_and_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.chat_follow.setChecked(False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert not window.chat_follow.isChecked()
    assert window.chat_follow_toggle_shortcut.isEnabled()
    assert provider.calls == 0


def test_m135_reset_accepted_restores_follow_and_retains_shortcut(host, monkeypatch) -> None:
    window, provider, memory = host
    style = window._personality.snapshot()
    window.chat_follow.setChecked(False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.chat_follow.isChecked()
    assert window.chat_follow_toggle_shortcut.isEnabled()
    window.chat_follow_toggle_shortcut.activated.emit()
    assert not window.chat_follow.isChecked()
    assert window._personality.snapshot() == style
    assert window._memory is memory
    assert provider.calls == 0


def test_m135_no_context_memory_personality_or_provider_side_effect(host) -> None:
    window, provider, memory = host
    history = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    transcript = window.chat.toPlainText()
    window.chat_follow_toggle_shortcut.activated.emit()
    assert window._context.provider_snapshot() == history
    assert window._personality.snapshot() == personality
    assert window._perception is perception
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
