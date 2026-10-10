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
        widget, Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QApplication.processEvents()


def test_m138_shortcut_identity_and_default(host) -> None:
    window, provider, _ = host
    shortcut = window.transcript_find_case_sensitive_toggle_shortcut
    assert shortcut.objectName() == "lyra_transcript_find_case_sensitive_toggle_shortcut"
    assert shortcut.parent() is window
    assert shortcut.context() == Qt.ShortcutContext.WindowShortcut
    assert shortcut.key() == QKeySequence("Ctrl+Shift+C")
    assert shortcut.isEnabled()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert provider.calls == 0


def test_m138_direct_handler_roundtrip(host) -> None:
    window, provider, _ = host
    window._toggle_transcript_find_case_sensitive_shortcut()
    assert window.transcript_find_case_sensitive.isChecked()
    window._toggle_transcript_find_case_sensitive_shortcut()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert provider.calls == 0


def test_m138_activation_signal_roundtrip(host) -> None:
    window, provider, _ = host
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window.transcript_find_case_sensitive.isChecked()
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert provider.calls == 0


def test_m138_real_qt_composer_preserves_draft_and_focus(host) -> None:
    window, provider, _ = host
    window.input.setText("mensagem que não deve ser enviada")
    focus(window, window.input)
    press_toggle(window.input)
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.input.text() == "mensagem que não deve ser enviada"
    assert window.input.hasFocus()
    assert provider.calls == 0


def test_m138_real_qt_find_keeps_query_and_focus(host) -> None:
    window, provider, _ = host
    window.transcript_find.setText("casa")
    window.input.setText("rascunho")
    focus(window, window.transcript_find)
    press_toggle(window.transcript_find)
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find.text() == "casa"
    assert window.input.text() == "rascunho"
    assert window.transcript_find.hasFocus()
    assert provider.calls == 0


def test_m138_reuses_mode_invalidation_without_rescan(host) -> None:
    window, provider, _ = host
    window._lyra("cat concatenate cat")
    window.transcript_find.setText("cat")
    window._find_next_in_transcript()
    selected = window.chat.textCursor().selectedText()
    assert selected.lower() == "cat"
    assert window.transcript_match_count.text() != "Ocorrências: —"
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window.transcript_match_count.text() == "Ocorrências: —"
    assert window.transcript_match_position.text() == "Posição: —"
    assert window.transcript_find_status.text() == "Busca: pronta"
    assert window.chat.textCursor().selectedText() == selected
    assert window.transcript_find.text() == "cat"
    assert window._last_find_query is None
    assert provider.calls == 0


def test_m138_bounded_literal_case_sensitive_result(host) -> None:
    window, provider, _ = host
    window._lyra("cat Cat CAT cat")
    window.transcript_find.setText("cat")
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    window._find_next_in_transcript()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.chat.textCursor().selectedText() == "cat"
    assert provider.calls == 0


def test_m138_whole_word_flag_independent(host) -> None:
    window, provider, _ = host
    window.transcript_find_whole_word.setChecked(True)
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window.transcript_find_whole_word.isChecked()
    assert window.transcript_find_case_sensitive.isChecked()
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window.transcript_find_whole_word.isChecked()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert provider.calls == 0


def test_m138_real_qt_from_read_only_transcript(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    press_toggle(window.chat)
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.chat.isReadOnly()
    assert window.chat.hasFocus()
    assert provider.calls == 0


def test_m138_compatibility_with_existing_search_shortcuts(host) -> None:
    window, provider, _ = host
    window._lyra("alpha alpha")
    window.transcript_find.setText("alpha")
    focus(window, window.input)
    QTest.keyClick(window.input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert window.transcript_find.hasFocus()
    press_toggle(window.transcript_find)
    assert window.transcript_find_case_sensitive.isChecked()
    QTest.keyClick(window.transcript_find, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert window.transcript_match_count.text() == "Ocorrências: 2"
    assert window.input.text() == ""
    assert provider.calls == 0


def test_m138_busy_signal_direct_and_qt_fail_closed(host) -> None:
    window, provider, _ = host
    focus(window, window.chat)
    window._set_busy(True)
    try:
        assert not window.transcript_find_case_sensitive_toggle_shortcut.isEnabled()
        assert not window.transcript_find_case_sensitive.isEnabled()
        window._toggle_transcript_find_case_sensitive_shortcut()
        window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
        press_toggle(window.chat)
        assert not window.transcript_find_case_sensitive.isChecked()
        assert provider.calls == 0
    finally:
        window._set_busy(False)
    assert window.transcript_find_case_sensitive_toggle_shortcut.isEnabled()


def test_m138_qt_reenabled_after_busy(host) -> None:
    window, provider, _ = host
    window._set_busy(True)
    window._set_busy(False)
    focus(window, window.input)
    press_toggle(window.input)
    assert window.transcript_find_case_sensitive.isChecked()
    assert provider.calls == 0


def test_m138_two_window_isolation(host) -> None:
    window, provider, _ = host
    other_provider = CaptureProvider()
    other = MainWindow(
        ActionRegistry(), None,  # type: ignore[arg-type]
        other_provider, build_default_tool_catalog(),
    )
    try:
        window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
        assert window.transcript_find_case_sensitive.isChecked()
        assert not other.transcript_find_case_sensitive.isChecked()
        assert other.transcript_find_case_sensitive_toggle_shortcut is not window.transcript_find_case_sensitive_toggle_shortcut
        assert other.transcript_find_case_sensitive_toggle_shortcut.parent() is other
        assert provider.calls == 0 and other_provider.calls == 0
    finally:
        other.close()


def test_m138_denied_reset_keeps_mode_and_shortcut(host, monkeypatch) -> None:
    window, provider, _ = host
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window.session_reset.click()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_case_sensitive_toggle_shortcut.isEnabled()
    assert provider.calls == 0


def test_m138_accepted_reset_restores_default_and_shortcut(host, monkeypatch) -> None:
    window, provider, memory = host
    personality = window._personality.snapshot()
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window.session_reset.click()
    assert not window.transcript_find_case_sensitive.isChecked()
    assert window.transcript_find_case_sensitive_toggle_shortcut.isEnabled()
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window.transcript_find_case_sensitive.isChecked()
    assert window._memory is memory
    assert window._personality.snapshot() == personality
    assert provider.calls == 0


def test_m138_no_provider_context_memory_or_task_side_effect(host) -> None:
    window, provider, memory = host
    before = window._context.provider_snapshot()
    personality = window._personality.snapshot()
    perception = window._perception
    transcript = window.chat.toPlainText()
    window.transcript_find_case_sensitive_toggle_shortcut.activated.emit()
    assert window._context.provider_snapshot() == before
    assert window._personality.snapshot() == personality
    assert window._perception is perception
    assert window._memory is memory
    assert window.chat.toPlainText() == transcript
    assert provider.calls == 0
