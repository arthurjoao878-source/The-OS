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


def test_m134_shortcut_identity_and_window_scope(host) -> None:
    window, provider, _ = host
    shortcut = window.transcript_focus_shortcut
    assert shortcut.objectName() == "lyra_transcript_focus_shortcut"
    assert shortcut.parent() is window
    assert shortcut.key() == QKeySequence("Ctrl+Shift+M")
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.isEnabled()
    assert window.chat.isReadOnly()
    assert provider.calls == 0


def test_m134_direct_focus_from_composer_keeps_draft(host) -> None:
    window, provider, _ = host
    window.input.setText("rascunho privado")
    focus(window, window.input)
    window._focus_transcript()
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert window.input.text() == "rascunho privado"
    assert provider.calls == 0


def test_m134_real_ctrl_shift_m_from_composer(host) -> None:
    window, provider, _ = host
    window.input.setText("não enviar")
    focus(window, window.input)
    QTest.keyClick(
        window.input, Qt.Key.Key_M,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert window.input.text() == "não enviar"
    assert provider.calls == 0


def test_m134_real_ctrl_shift_m_from_find_preserves_selection_and_modes(host) -> None:
    window, provider, _ = host
    window._lyra("Oak oak Oak")
    window.transcript_find.setText("Oak")
    window.transcript_find_case_sensitive.setChecked(True)
    window.transcript_find_whole_word.setChecked(True)
    window._find_next_in_transcript()
    window.input.setText("draft")
    snapshot = (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
    )
    focus(window, window.transcript_find)
    QTest.keyClick(
        window.transcript_find, Qt.Key.Key_M,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert snapshot == (
        window.transcript_find.text(), window.transcript_find_status.text(),
        window.transcript_match_count.text(), window.transcript_match_position.text(),
        window.chat.textCursor().selectedText(),
    )
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_whole_word.isChecked()
    assert window.input.text() == "draft"
    assert provider.calls == 0


def test_m134_explicit_signal_moves_focus_only(host) -> None:
    window, provider, _ = host
    focus(window, window.input)
    window.transcript_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m134_repeated_direct_focus_is_idempotent(host) -> None:
    window, provider, _ = host
    window._lyra("scroll position")
    focus(window, window.chat)
    before = window.chat.toPlainText()
    window._focus_transcript()
    window._focus_transcript()
    assert window.chat.hasFocus()
    assert window.chat.toPlainText() == before
    assert provider.calls == 0


def test_m134_busy_shortcut_and_direct_handler_fail_closed(host) -> None:
    window, provider, _ = host
    focus(window, window.input)
    window._set_busy(True)
    try:
        assert not window.transcript_focus_shortcut.isEnabled()
        window.chat.clearFocus()
        QApplication.processEvents()
        window._focus_transcript()
        assert not window.chat.hasFocus()
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_focus_shortcut.isEnabled()


def test_m134_shortcut_restored_after_busy_real_event(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    window._set_busy(False)
    focus(window, window.input)
    QTest.keyClick(
        window.input, Qt.Key.Key_M,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m134_ctrl_m_and_ctrl_f_remain_independent(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    QTest.keyClick(window.chat, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.input.hasFocus()
    QTest.keyClick(window.input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    QTest.keyClick(
        window.transcript_find, Qt.Key.Key_M,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m134_two_windows_have_independent_shortcuts(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.show()
        other.show()
        window.input.setText("first")
        other.input.setText("second")
        window.transcript_focus_shortcut.activated.emit()
        assert window.input.text() == "first"
        assert other.input.text() == "second"
        assert other.transcript_focus_shortcut is not window.transcript_focus_shortcut
        assert other.transcript_focus_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m134_reset_denied_keeps_shortcut_and_state(host, monkeypatch) -> None:
    window, provider, _ = host
    window.input.setText("draft")
    window.transcript_find.setText("query")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.input.text() == "draft"
    assert window.transcript_find.text() == "query"
    assert window.transcript_focus_shortcut.isEnabled()
    assert provider.calls == 0


def test_m134_accepted_reset_retains_shortcut(host, monkeypatch) -> None:
    window, provider, memory = host
    style = window._personality.snapshot()
    window.input.setText("draft")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert window.input.text() == ""
    assert window.transcript_focus_shortcut.isEnabled()
    assert window._personality.snapshot() == style
    assert window._memory is memory
    focus(window, window.input)
    window.transcript_focus_shortcut.activated.emit()
    QApplication.processEvents()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m134_does_not_change_context_perception_or_memory(host) -> None:
    window, provider, memory = host
    history = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    window.transcript_focus_shortcut.activated.emit()
    assert window._context.provider_snapshot() == history
    assert window._personality.snapshot() == personality
    assert window._perception is perception
    assert window._memory is memory
    assert provider.calls == 0


def test_m134_keeps_input_length_and_transcript_read_only(host) -> None:
    window, provider, _ = host
    window.input.setText("a" * 5000)
    assert len(window.input.text()) == 4096
    window.transcript_focus_shortcut.activated.emit()
    assert len(window.input.text()) == 4096
    assert window.chat.isReadOnly()
    assert provider.calls == 0
